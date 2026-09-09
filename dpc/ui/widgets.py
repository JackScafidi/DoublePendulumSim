"""Controls that extrude, and press in when you press them.

Two things the stylesheet cannot do. A coloured fill needs an inner shade of its
own hue to read as a solid mass rather than a flat pill, and pressing a control
should move it from raised to inset -- which is the half of this design language
that makes it feel physical instead of decorative.

Both are painted here, over the same machinery the panels use: one light source
at the top left, blur twice the offset, and a fill that is the same colour as
the surface unless it is deliberately a coloured mass.
"""

from PySide6.QtCore import (QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation,
                            Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QSlider, QStyle

from dpc.ui import theme as T
from dpc.ui.neumorphic import inner_shade_pixmap, inset_pixmap, raised_pixmap

PRESS_MS = 170
"""Inside the 150-200 ms the design language asks for. Long enough to read as
movement, short enough not to lag the click."""


class _Extruded:
    """Shared painting for a control that extrudes and can be pushed in.

    `depth` runs 0 (fully raised) to 1 (fully inset); the two shadows are
    cross-faded across it rather than swapped, so the press reads as travel.
    """

    def _init_extrusion(self, offset: int, radius: float) -> None:
        self.offset = offset
        self.radius = radius
        self.pad = offset * 3 + 2
        self._depth = 0.0
        self._cache: dict = {}
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(PRESS_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
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
                pm = raised_pixmap(w, h, self.offset, self.radius)
            elif kind == "inset":
                pm = inset_pixmap(w, h, self.offset, self.radius)
            else:
                pm = inner_shade_pixmap(w, h, max(2, self.offset - 1),
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

        # Each pixmap already carries `pad` of transparent border with its shape
        # at (pad, pad), so every one of them is drawn at the widget origin.
        if shade is not None:
            q.drawPixmap(0, 0, self._pm("shade", w, h, shade))
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
                 offset: int = 4, radius: float | None = None,
                 padding: tuple[int, int] = (16, 7), parent=None):
        super().__init__(parent)
        self._init_extrusion(offset, T.RADIUS_CTRL if radius is None else radius)
        self.setText(text)
        self.filled = filled
        self._pad_x, self._pad_y = padding
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        m = self.fontMetrics().size(0, self.text())
        return m.grownBy(self.contentsMargins()).__class__(
            m.width() + 2 * (self._pad_x + self.pad),
            m.height() + 2 * (self._pad_y + self.pad))

    minimumSizeHint = sizeHint

    def _colours(self) -> tuple[QColor, QColor | None, QColor]:
        on = self.filled or (self.isCheckable() and self.isChecked())
        if on:
            shade = QColor(T.ACCENT_SHADE)
            shade.setAlphaF(0.5)
            return QColor(T.ACCENT), shade, QColor("#ffffff")
        return QColor(T.SURFACE), None, QColor(T.TEXT_2)

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)
        fill, shade, ink = self._colours()
        body = self._paint_body(q, fill, shade)

        if shade is None:
            q.setPen(QPen(QColor(T.BORDER_INTERACTIVE), 1))
            q.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5),
                              self.radius, self.radius)

        q.setPen(ink)
        # The label travels with the surface it sits on.
        q.translate(self._depth * 1.0, self._depth * 1.0)
        q.drawText(body, Qt.AlignCenter, self.text())

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
        super().__init__("", offset=3, radius=6, padding=(0, 0), parent=parent)
        self.setCheckable(True)
        self.setFixedSize(17 + 2 * self.pad, 17 + 2 * self.pad)

    def sizeHint(self):
        return self.size()

    minimumSizeHint = sizeHint

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)
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

        q.setPen(QPen(QColor("#ffffff"), 2.0, Qt.SolidLine, Qt.RoundCap,
                      Qt.RoundJoin))
        c = body.center()
        q.drawPolyline([QPointF(c.x() - 4.2, c.y() + 0.2),
                        QPointF(c.x() - 1.2, c.y() + 3.4),
                        QPointF(c.x() + 4.4, c.y() - 3.6)])


class NeumorphicSlider(QSlider):
    """An inset groove with a filled thumb.

    The track is a well pressed into the surface; the thumb is a coloured mass
    extruded from it with the same inner shade every other fill carries.
    """

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setMinimumHeight(26)
        self._cache: dict = {}

    def _groove(self, w: int, h: int):
        key = (w, h)
        if key not in self._cache:
            self._cache[key] = inset_pixmap(w, h, 3, h / 2.0)
        return self._cache[key]

    def _thumb_shade(self, d: int):
        key = ("thumb", d)
        if key not in self._cache:
            shade = QColor(T.ACCENT_SHADE)
            shade.setAlphaF(0.55)
            self._cache[key] = inner_shade_pixmap(d, d, 3, d / 2.0, shade)
        return self._cache[key]

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)

        gh = 8
        pad = 11
        gw = max(self.width() - 2 * pad, 1)
        top = (self.height() - gh) / 2.0

        groove = QRectF(pad, top, gw, gh)
        path = QPainterPath()
        path.addRoundedRect(groove, gh / 2.0, gh / 2.0)
        q.fillPath(path, QColor(T.SURFACE_SUNKEN))
        q.drawPixmap(int(pad - 11), int(top - 11), self._groove(gw, gh))

        span = self.maximum() - self.minimum()
        frac = 0.0 if span <= 0 else (self.value() - self.minimum()) / span

        q.save()
        q.setClipPath(path)
        q.fillRect(QRectF(pad, top, gw * frac, gh), QColor(T.ACCENT))
        q.restore()

        d = 18
        cx = pad + gw * frac
        cy = self.height() / 2.0
        rect = QRectF(cx - d / 2.0, cy - d / 2.0, d, d)
        q.drawPixmap(int(cx - d / 2.0 - 11), int(cy - d / 2.0 - 11),
                     raised_pixmap(d, d, 3, d / 2.0))
        q.setBrush(QColor(T.ACCENT))
        q.setPen(Qt.NoPen)
        q.drawEllipse(rect)
        q.drawPixmap(int(cx - d / 2.0 - 11), int(cy - d / 2.0 - 11),
                     self._thumb_shade(d))

    def mousePressEvent(self, e) -> None:
        """Jump to where the click landed -- a scrub bar you have to drag from
        the thumb is a scrub bar nobody uses."""
        pad = 11
        gw = max(self.width() - 2 * pad, 1)
        frac = min(1.0, max(0.0, (e.position().x() - pad) / gw))
        self.setValue(round(self.minimum() + frac * (self.maximum() - self.minimum())))
        e.accept()

    mouseMoveEvent = mousePressEvent
