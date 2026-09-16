"""Controls that extrude, and press in when you press them.

Two things the stylesheet cannot do. A coloured fill needs an inner shade of its
own hue to read as a solid mass rather than a flat pill, and pressing a control
should move it from raised to inset -- which is the half of this design language
that makes it feel physical instead of decorative.

Both are painted here, over the same machinery the panels use: one light source
at the top left, blur twice the offset, and a fill that is the same colour as
the surface unless it is deliberately a coloured mass.

The flat half of the file is the other side of the same rule. Extrusion is for
the hero controls; a thirty-row parameter table nests raised chips inside an
already-raised card until nothing is foreground. So the constants column's
fields are flat -- sunken fill, interactive border, no shadow margin -- and the
chevrons and glyphs Qt refuses to draw for them are painted here too.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import (QEasingCurve, QEvent, QPointF, QRectF, QSize, Qt,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDoubleSpinBox,
                               QLabel, QSizePolicy, QSlider, QWidget)

from dpc.ui import theme as T
from dpc.ui.neumorphic import (inner_shade_pixmap, inset_pixmap, raised_pixmap,
                               shadow_pad)

if TYPE_CHECKING:      # pragma: no cover
    _HostBase = QWidget
else:
    _HostBase = object
"""_Extruded calls width(), height() and update(), so it only makes sense mixed
into a QWidget. Declaring that for the type checker without putting QWidget in
the runtime MRO keeps the mixin out of PySide's multiple-inheritance rules."""

PRESS_MS = 170
"""Inside the 150-200 ms the design language asks for. Long enough to read as
movement, short enough not to lag the click."""

CHIP_SHADE_OFFSET = 2
"""The active speed chip's inner shade. Shallower than any other shade on the
page, because the chip is the smallest coloured mass on it -- at 3 the gathered
band reaches the middle of a 19 px pill and reads as a gradient."""

CHEVRON_W = 7.0
CHEVRON_H = 3.2
"""The drop/step indicator. Painted rather than set as an image, because a Qt
stylesheet can only put a glyph in a subcontrol from a file on disk, and a
dashboard that needs an icon cache on disk to look finished is worse than one
that draws seven pixels itself."""


def chevron(q: QPainter, cx: float, cy: float, colour: str,
            up: bool = False, width: float = CHEVRON_W,
            height: float = CHEVRON_H) -> None:
    """A two-segment chevron centred on (cx, cy), pointing down unless `up`."""
    dy = -height if up else height
    q.setPen(QPen(QColor(colour), 1.4, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    q.setBrush(Qt.BrushStyle.NoBrush)
    q.drawPolyline([QPointF(cx - width / 2.0, cy - dy / 2.0),
                    QPointF(cx, cy + dy / 2.0),
                    QPointF(cx + width / 2.0, cy - dy / 2.0)])


class _Extruded(_HostBase):
    """Shared painting for a control that extrudes and can be pushed in.

    `depth` runs 0 (fully raised) to 1 (fully inset); the two shadows are
    cross-faded across it rather than swapped, so the press reads as travel.
    """

    def _init_extrusion(self, offset: int, radius: float) -> None:
        self.offset = offset
        self.light_a = 1.0
        self.radius = radius
        self.pad = shadow_pad(offset)
        self.shade_offset = max(2, offset - 1)
        """The inner shade is gathered one step shallower than the outer
        shadow, so it stays inside the fill rather than ringing it. It is a
        DIFFERENT offset, so it carries a different transparent border and is
        drawn at its own inset -- see _paint_body."""
        self._depth = 0.0
        self._cache: dict = {}
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(PRESS_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_depth)

    def _set_depth(self, v) -> None:
        self._depth = float(v)
        self.update()

    def _to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._depth)
        self._anim.setEndValue(target)
        self._anim.start()

    def _pm(self, kind: str, w: int, h: int, shade: QColor | None = None):
        key = (kind, w, h)
        if key not in self._cache:
            if kind == "raised":
                # A control is small enough that a full-strength light halo
                # reads as an outline rather than a highlight.
                pm = raised_pixmap(w, h, self.offset, self.radius,
                                   light=self.light_a, dark=0.85)
            elif kind == "inset":
                pm = inset_pixmap(w, h, self.offset, self.radius)
            else:
                assert shade is not None, "the shade kind needs a colour"
                pm = inner_shade_pixmap(w, h, self.shade_offset,
                                        self.radius, shade)
            self._cache[key] = pm
        return self._cache[key]

    def _paint_body(self, q: QPainter, fill: QColor,
                    shade: QColor | None) -> QRectF:
        """Outer shadow, then the fill, then the inner shade if it is coloured."""
        w = max(self.width() - 2 * self.pad, 1)
        h = max(self.height() - 2 * self.pad, 1)
        body = QRectF(self.pad, self.pad, w, h)
        path = QPainterPath()
        path.addRoundedRect(body, self.radius, self.radius)

        d = self._depth
        if d < 1.0:
            q.setOpacity(1.0 - d)
            q.drawPixmap(0, 0, self._pm("raised", w, h))
        q.setOpacity(1.0)
        q.fillPath(path, fill)

        # Each pixmap carries shadow_pad(its own offset) of transparent border
        # with its shape at that inset, so it is drawn that far before the body
        # in both directions. The raised and inset halves are built at
        # self.offset, so their border is exactly self.pad and they land at the
        # widget origin; the shade is built shallower and lands inside it.
        if shade is not None:
            at = self.pad - shadow_pad(self.shade_offset)
            q.drawPixmap(at, at, self._pm("shade", w, h, shade))
        if d > 0.0:
            q.setOpacity(d)
            q.drawPixmap(0, 0, self._pm("inset", w, h))
            q.setOpacity(1.0)
        return body


class NeumorphicButton(QAbstractButton, _Extruded):
    """A button that extrudes from the surface and presses into it.

    Filled buttons carry the accent and its inner shade; the rest carry the
    interactive border, because a shadow near 1.2:1 cannot tell anyone a thing
    is clickable and colour has to do that job.
    """

    def __init__(self, text: str = "", filled: bool = False,
                 offset: int = T.SHADOW_CTRL, radius: float | None = None,
                 padding: tuple[int, int] = (16, 7), parent=None):
        super().__init__(parent)
        self._init_extrusion(offset, T.RADIUS_CTRL if radius is None else radius)
        self.setText(text)
        self.filled = filled
        # Dialled back on coloured masses only -- see raised_pixmap.
        self.light_a = 0.5 if filled else 1.0
        self._pad_x, self._pad_y = padding
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        m = self.fontMetrics().size(0, self.text())
        return m.grownBy(self.contentsMargins()).__class__(
            m.width() + 2 * (self._pad_x + self.pad),
            m.height() + 2 * (self._pad_y + self.pad))

    minimumSizeHint = sizeHint

    def _colours(self) -> tuple[QColor, QColor | None, QColor]:
        on = self.filled or (self.isCheckable() and self.isChecked())
        self.light_a = 0.5 if on else 1.0
        if on:
            shade = QColor(T.ACCENT_SHADE)
            shade.setAlphaF(0.5)
            return QColor(T.ACCENT), shade, QColor("#ffffff")
        return QColor(T.SURFACE), None, QColor(T.TEXT_2)

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill, shade, ink = self._colours()
        body = self._paint_body(q, fill, shade)

        if shade is None:
            q.setPen(QPen(QColor(T.BORDER_INTERACTIVE), 1))
            q.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5),
                              self.radius, self.radius)

        q.setPen(ink)
        # The label travels with the surface it sits on.
        q.translate(self._depth * 1.0, self._depth * 1.0)
        q.drawText(body, Qt.AlignmentFlag.AlignCenter, self.text())

    def mousePressEvent(self, e) -> None:
        super().mousePressEvent(e)
        self._to(1.0)

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        self._to(0.0)


class NeumorphicCheck(NeumorphicButton):
    """A square toggle. Checked is a filled mass with its inner shade and a
    white glyph -- the glyph is required, so the state is never colour alone."""

    def __init__(self, parent=None):
        super().__init__("", offset=T.SHADOW_CTRL, radius=T.RADIUS_CHECK,
                         padding=(0, 0), parent=parent)
        self.setCheckable(True)
        self.setFixedSize(17 + 2 * self.pad, 17 + 2 * self.pad)

    def sizeHint(self):
        return self.size()

    minimumSizeHint = sizeHint

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        fill = QColor(T.ACCENT) if on else QColor(T.SURFACE_SUNKEN)
        shade = None
        if on:
            shade = QColor(T.ACCENT_SHADE)
            shade.setAlphaF(0.5)
        body = self._paint_body(q, fill, shade)

        if not on:
            q.setPen(QPen(QColor(T.BORDER_INTERACTIVE), 1))
            q.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5),
                              self.radius, self.radius)
            return

        q.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        c = body.center()
        q.drawPolyline([QPointF(c.x() - 4.2, c.y() + 0.2),
                        QPointF(c.x() - 1.2, c.y() + 3.4),
                        QPointF(c.x() + 4.4, c.y() - 3.6)])


class NeumorphicSlider(QSlider):
    """An inset groove with a filled thumb.

    The track is a well pressed into the surface; the thumb is a coloured mass
    extruded from it with the same inner shade every other fill carries.

    The groove is deliberately thin and part-strength. At full accent and 8 px
    it ends a run as a ~1500 px bar -- the largest coloured area on the page,
    carrying the least information on it -- against the design's own rule of one
    primary fill per view. The thumb keeps the full accent, because the thumb is
    the part you aim at.
    """

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMinimumHeight(26)
        self._grooves: dict[tuple[int, int], QPixmap] = {}
        self._thumbs: dict[tuple[str, int], QPixmap] = {}
        """Two caches, because the two shapes have different lifetimes. The
        thumb is THUMB_D across whatever the window does, so its pixmaps are
        built once and kept. The groove is as wide as the window, so dragging
        an edge from 1000 to 1920 px would mint ~900 full-width pixmaps at
        ~158 KB each and hold every one of them for the window's lifetime."""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grooves.clear()

    def _groove(self, w: int, h: int):
        key = (w, h)
        if key not in self._grooves:
            self._grooves[key] = inset_pixmap(w, h, T.SHADOW_WELL, h / 2.0)
        return self._grooves[key]

    def _thumb_raised(self, d: int):
        """Cached like the shade beneath it. This is a rounded-rect render,
        two rolls, two tints and a composite -- and the slider repaints every
        frame of a run, because the clock moves the cursor by setValue."""
        key = ("raised", d)
        if key not in self._thumbs:
            self._thumbs[key] = raised_pixmap(d, d, T.SHADOW_WELL, d / 2.0)
        return self._thumbs[key]

    def _thumb_shade(self, d: int):
        key = ("shade", d)
        if key not in self._thumbs:
            shade = QColor(T.ACCENT_SHADE)
            shade.setAlphaF(0.55)
            self._thumbs[key] = inner_shade_pixmap(d, d, T.SHADOW_WELL,
                                                   d / 2.0, shade)
        return self._thumbs[key]

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)

        gh = T.GROOVE_H
        pad = T.SCRUB_PAD
        # The shadow's own border, which is NOT the groove inset -- they are
        # equal at this offset by arithmetic, not by intent.
        sp = shadow_pad(T.SHADOW_WELL)
        gw = max(self.width() - 2 * pad, 1)
        top = (self.height() - gh) / 2.0

        groove = QRectF(pad, top, gw, gh)
        path = QPainterPath()
        path.addRoundedRect(groove, gh / 2.0, gh / 2.0)
        q.fillPath(path, QColor(T.SURFACE_SUNKEN))
        q.drawPixmap(int(pad - sp), int(top - sp), self._groove(gw, gh))

        span = self.maximum() - self.minimum()
        frac = 0.0 if span <= 0 else (self.value() - self.minimum()) / span

        fill = QColor(T.ACCENT)
        fill.setAlphaF(T.GROOVE_FILL_A)
        q.save()
        q.setClipPath(path)
        q.fillRect(QRectF(pad, top, gw * frac, gh), fill)
        q.restore()

        d = T.THUMB_D
        cx = pad + gw * frac
        cy = self.height() / 2.0
        rect = QRectF(cx - d / 2.0, cy - d / 2.0, d, d)
        tx, ty = int(cx - d / 2.0 - sp), int(cy - d / 2.0 - sp)
        q.drawPixmap(tx, ty, self._thumb_raised(d))
        q.setBrush(QColor(T.ACCENT))
        q.setPen(Qt.PenStyle.NoPen)
        q.drawEllipse(rect)
        q.drawPixmap(tx, ty, self._thumb_shade(d))

    def mousePressEvent(self, e) -> None:
        """Jump to where the click landed -- a scrub bar you have to drag from
        the thumb is a scrub bar nobody uses."""
        pad = T.SCRUB_PAD
        gw = max(self.width() - 2 * pad, 1)
        frac = min(1.0, max(0.0, (e.position().x() - pad) / gw))
        self.setValue(round(self.minimum() + frac * (self.maximum() - self.minimum())))
        e.accept()

    mouseMoveEvent = mousePressEvent


class IconButton(NeumorphicButton):
    """A fixed square button whose label is drawn, not typed.

    `NeumorphicButton.sizeHint` measures its own text, so a play/pause toggle
    built from glyphs changes width every time it is pressed and shoves the
    whole transport row sideways. A drawn glyph in a fixed square cannot, and
    it renders the same whether or not IBM Plex is installed -- text glyphs are
    the first thing to break on a font fallback.

    It stays unfilled on purpose. The glyph already says which state it is in,
    so a fill here would be a second accent mass competing with Run.
    """

    def __init__(self, glyph: str, size: int = 22,
                 offset: int = T.SHADOW_CTRL, parent=None):
        super().__init__("", offset=offset, parent=parent)
        self.glyph = glyph
        self.setFixedSize(size + 2 * self.pad, size + 2 * self.pad)

    def sizeHint(self):
        return self.size()

    minimumSizeHint = sizeHint

    def _colours(self) -> tuple[QColor, QColor | None, QColor]:
        self.light_a = 1.0
        return QColor(T.SURFACE), None, QColor(T.TEXT)

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill, _, ink = self._colours()
        body = self._paint_body(q, fill, None)

        q.setPen(QPen(QColor(T.BORDER_INTERACTIVE), 1))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5),
                          self.radius, self.radius)

        q.translate(self._depth * 1.0, self._depth * 1.0)
        c = body.center()
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(ink)
        if self.glyph == "pause":
            for dx in (-4.0, 1.0):
                q.drawRoundedRect(QRectF(c.x() + dx, c.y() - 6.0, 3.0, 12.0),
                                  1.0, 1.0)
        else:
            path = QPainterPath()
            path.moveTo(c.x() - 4.0, c.y() - 6.5)
            path.lineTo(c.x() + 6.0, c.y())
            path.lineTo(c.x() - 4.0, c.y() + 6.5)
            path.closeSubpath()
            q.drawPath(path)
        q.setBrush(Qt.BrushStyle.NoBrush)


class FlatSpinBox(QDoubleSpinBox):
    """An editable value that is a field, not an object.

    Everything but the chevrons comes from the stylesheet: sunken fill, the
    interactive border, and a right gutter of T.ARROW_W. The gutter exists
    because the native up/down block is sized to nothing -- left alone, Windows
    draws its own framed arrows on top of whatever the field already shows.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(T.FIELD_W)
        self.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() - 5.0 - T.ARROW_W / 2.0
        cy = self.height() / 2.0
        chevron(q, cx, cy - 4.0, T.TEXT_3, up=True)
        chevron(q, cx, cy + 4.0, T.TEXT_3)
        q.end()


class FlatCombo(QComboBox):
    """A picker that says it opens.

    The stylesheet removes the native frame around the drop-down and nothing
    replaces the arrow, so the selectors read as read-only text fields. The
    border carries affordance; this carries the fact that a list is behind it.
    """

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        chevron(q, self.width() - 1.0 - (T.ARROW_W + 6) / 2.0,
                self.height() / 2.0, T.TEXT_3)
        q.end()


class FlatCheck(QAbstractButton):
    """The constants column's toggle: the same box as the fields around it.

    `NeumorphicCheck` reserves 3 * offset + 2 px of shadow margin a side, which
    makes its row twice the height of every read-only row beside it. The state
    is still colour plus a glyph, never colour alone -- only the extrusion is
    gone.
    """

    def __init__(self, side: int = 17, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.side = side
        self.setFixedSize(side, side)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return self.size()

    minimumSizeHint = sizeHint

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        body = QRectF(0.5, 0.5, self.side - 1.0, self.side - 1.0)

        path = QPainterPath()
        path.addRoundedRect(body, T.RADIUS_CHECK, T.RADIUS_CHECK)
        q.fillPath(path, QColor(T.ACCENT if on else T.SURFACE_SUNKEN))

        if not on:
            q.setPen(QPen(QColor(T.BORDER_INTERACTIVE), 1))
            q.setBrush(Qt.BrushStyle.NoBrush)
            q.drawRoundedRect(body, T.RADIUS_CHECK, T.RADIUS_CHECK)
            q.end()
            return

        q.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        c = body.center()
        q.drawPolyline([QPointF(c.x() - 4.2, c.y() + 0.2),
                        QPointF(c.x() - 1.2, c.y() + 3.4),
                        QPointF(c.x() + 4.4, c.y() - 3.6)])
        q.end()


class SegmentedControl(QWidget):
    """One inset track, N equal chips, the active one filled.

    Three separately extruded pills of unequal width are three objects that
    happen to sit near each other: the gap between two chips is each chip's own
    shadow margin rather than the spacing to its neighbour, and 0.25x is nearly
    three times the width of 1x. The style guide maps this pattern directly --
    tab bar to inset track, active tab to filled -- and a segmented control also
    says that the three of them are one choice.
    """

    selected = Signal(int)

    def __init__(self, labels: tuple[str, ...], active: int = 0, parent=None):
        super().__init__(parent)
        self.labels = labels
        self._active = active
        self._cache: dict = {}
        self.pad = T.SHADOW_WELL
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Fixed in both directions, so the layout takes sizeHint verbatim and
        # the control behaves exactly as the setFixedSize it replaces -- but
        # sizeHint is re-read afterwards, and setFixedSize was not.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _chip(self) -> tuple[int, int]:
        """One chip, measured from the widest label.

        Measured HERE rather than in __init__. A widget is not polished at
        construction, so its fontMetrics are the platform default rather than
        the 11 px the stylesheet resolves to -- which errs 5 px wide on this
        box and would clip the widest label on any platform whose default is
        smaller. A size computed once and frozen never finds out.
        """
        fm = self.fontMetrics()
        return (max(fm.horizontalAdvance(t) for t in self.labels)
                + 2 * T.PAD_PANEL, fm.height() + 2 * T.PAD_ICON)

    def sizeHint(self) -> QSize:
        chip_w, chip_h = self._chip()
        return QSize(len(self.labels) * chip_w + 2 * self.pad,
                     chip_h + 2 * self.pad)

    minimumSizeHint = sizeHint

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.updateGeometry()

    @property
    def active(self) -> int:
        return self._active

    def set_active(self, index: int) -> None:
        self._active = index
        self.update()

    def _pm(self, kind: str, w: int, h: int, radius: float):
        key = (kind, w, h)
        if key not in self._cache:
            if kind == "track":
                self._cache[key] = inset_pixmap(w, h, self.pad, radius)
            else:
                shade = QColor(T.ACCENT_SHADE)
                shade.setAlphaF(0.5)
                self._cache[key] = inner_shade_pixmap(
                    w, h, CHIP_SHADE_OFFSET, radius, shade)
        return self._cache[key]

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = max(self.width() - 2 * self.pad, 1)
        h = max(self.height() - 2 * self.pad, 1)
        r = h / 2.0
        track = QRectF(self.pad, self.pad, w, h)
        path = QPainterPath()
        path.addRoundedRect(track, r, r)
        q.fillPath(path, QColor(T.SURFACE_SUNKEN))
        # Every shadow pixmap carries 3 * offset + 2 px of transparent border
        # with its shape at that offset, so it is drawn that far before the
        # shape it belongs to, in both directions.
        at = self.pad - (self.pad * 3 + 2)
        q.drawPixmap(at, at, self._pm("track", w, h, r))

        chip_w = w / len(self.labels)
        for i, text in enumerate(self.labels):
            chip = QRectF(self.pad + i * chip_w, self.pad, chip_w, h)
            if i == self._active:
                inner = chip.adjusted(1.0, 1.0, -1.0, -1.0)
                cr = inner.height() / 2.0
                cp = QPainterPath()
                cp.addRoundedRect(inner, cr, cr)
                q.fillPath(cp, QColor(T.ACCENT))
                at = shadow_pad(CHIP_SHADE_OFFSET)
                q.drawPixmap(int(inner.x()) - at, int(inner.y()) - at,
                             self._pm("shade", int(inner.width()),
                                      int(inner.height()), cr))
                q.setPen(QColor("#ffffff"))
            else:
                q.setPen(QColor(T.TEXT_2))
            q.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
        q.end()

    def mousePressEvent(self, e) -> None:
        chip_w = max(self.width() - 2 * self.pad, 1) / len(self.labels)
        i = int((e.position().x() - self.pad) // chip_w)
        i = min(len(self.labels) - 1, max(0, i))
        if i != self._active:
            self.set_active(i)
            self.selected.emit(i)
        e.accept()


class StatusPill(QLabel):
    """The transport's status, as a mark rather than a caption.

    "falling behind" is the one thing the whole pull-model run design exists to
    report, and as muted text at the far end of an otherwise empty row it is
    the quietest element on the page. Amber is this project's existing mark for
    "not the default state"; it marks a condition and never data, which is why
    it may be the same amber the modified bullet uses.

    Its width is measured ONCE, from the longest status it can ever carry, and
    never moves again -- empty included, where it paints nothing but still
    holds the space. This is the same rule the play button follows, for the
    same reason: the slider is the only thing in the transport row that
    stretches, so every pixel a neighbour gains or loses comes out of the scrub
    groove. A status arriving mid-run would otherwise shorten the groove by its
    own width and jump the thumb by that much under the user's finger.
    """

    def __init__(self, statuses: tuple[str, ...] = (), parent=None):
        super().__init__("", parent)
        self.alert = False
        self.statuses = statuses
        self.setContentsMargins(T.PAD_PILL_X, T.PAD_PILL_Y,
                                T.PAD_PILL_X, T.PAD_PILL_Y)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Preferred)

    def sizeHint(self) -> QSize:
        """The widest status it can carry, not the one it is carrying. Measured
        here rather than in __init__ so that the font being measured is the one
        the stylesheet resolved, not the platform default."""
        fm = self.fontMetrics()
        widest = max((fm.horizontalAdvance(t) for t in self.statuses),
                     default=0)
        m = self.contentsMargins()
        return QSize(widest + m.left() + m.right(),
                     fm.height() + m.top() + m.bottom())

    minimumSizeHint = sizeHint

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.updateGeometry()

    def set_status(self, text: str, alert: bool = False) -> None:
        """Called every frame while a status persists, so it is guarded: an
        unconditional update() here repaints the transport bar fifty times a
        second to draw the same word again."""
        if text == self.text() and alert == self.alert:
            return
        self.alert = alert
        self.setText(text)
        self.update()

    def paintEvent(self, event) -> None:
        # No status: hold the space, paint nothing. setVisible(False) would
        # take the width back out of the row -- see the class docstring.
        if not self.text():
            return
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)

        # The WIDGET is as wide as the longest status; the MARK is as wide as
        # the status it is carrying, centred in that slot. Reserving the space
        # is what keeps the groove still; painting a 131 px capsule around the
        # word "done" would make the reservation the loudest thing in the row.
        m = self.contentsMargins()
        w = min(float(self.width()),
                self.fontMetrics().horizontalAdvance(self.text())
                + m.left() + m.right())
        body = QRectF((self.width() - w) / 2.0 + 0.5, 0.5,
                      w - 1.0, self.height() - 1.0)
        r = body.height() / 2.0
        path = QPainterPath()
        path.addRoundedRect(body, r, r)
        q.fillPath(path, QColor(T.MODIFIED if self.alert
                                else T.SURFACE_SUNKEN))
        if not self.alert:
            q.setPen(QPen(QColor(T.BORDER), 1))
            q.setBrush(Qt.BrushStyle.NoBrush)
            q.drawRoundedRect(body, r, r)
        q.setPen(QColor("#ffffff") if self.alert else QColor(T.TEXT_2))
        q.drawText(body, Qt.AlignmentFlag.AlignCenter, self.text())
        q.end()
