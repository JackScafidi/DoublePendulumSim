"""Every constant the run is using, in one column.

Laid out after FTC Dashboard's configuration panel, because it solves the same
problem: a long list of live-editable values where the thing you most need to
see is which ones you have moved away from their defaults.

Three ideas come from it directly. A **modified marker** sits in its own leading
column -- an amber bullet when a value differs from the baseline, an invisible
placeholder otherwise, so nothing shifts sideways as values change. The
**baseline is shown inline**, dimmed and parenthesised, beside anything you have
edited, so you can always see what you moved it from. And a **filter** collapses
the panel to only the modified rows, which is how you check what you actually
changed after twenty minutes of tuning.

The fourth is adapted rather than copied. FTC's Save writes values back to the
robot; here `params.py` is the source of truth, so the equivalent is to hand you
a snippet to paste into it.

Controller knobs and drive limits are editable -- those are what gets tuned
while playing. Plant parameters and scenario initial conditions are read-only:
they are measured or declared facts, and a constants panel is the wrong place to
edit physics by accident.

The controller section is built from the controller's own PARAMS declaration.
Nothing here names a controller, which is what lets a new file in
dpc/controllers/ arrive with working widgets and no edit to this file.

Every row is one rhythm and one grid. An editable row built from extruded
controls is twice the height of a read-only one, because each raised control
reserves `3 * offset + 2` px of shadow margin a side -- so the column reads as
two lists spliced together, the value column jumps sideways between row types,
and the extra height is what pushes the set off the bottom of a 900 px window.
Extrusion is for the hero controls, not for a thirty-row parameter table; here
the fields are flat, the pitch is fixed, and the unit has a column of its own.
"""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QScrollArea, QVBoxLayout, QWidget)

from dpc.controllers.registry import Entry
from dpc.params import Params
from dpc.scenarios import Scenario
from dpc.ui import theme as T
from dpc.ui.widgets import FlatCheck, FlatSpinBox, NeumorphicButton

DRIVE_FIELDS = (
    ("a_max", "a_max", "m/s²", 0.1, 100.0, 0.5, 1.0, 2),
    ("v_max", "v_max", "m/s", 0.01, 10.0, 0.05, 1.0, 3),
    ("jerk_max", "jerk_max", "m/s³", 1.0, 100000.0, 25.0, 1.0, 0),
    ("tau_lag", "τ lag", "ms", 0.0, 100.0, 0.5, 1e3, 3),
)
"""name, label, unit, lo, hi, step, scale, decimals.

`scale` and the unit are what the field is DISPLAYED in; `lo`, `hi` and `step`
are in those display units too, and only the value crossing the panel boundary
is SI. A 3-decimal `0.003 s` is a field that reads as all zeros and whose single
step is a rounding decision -- `3.000 ms` is the number you would actually type.
"""

NOTE_WIDTH = T.CONSTANTS_WIDTH - T.SCROLLBAR_W - (2 + T.PAD_PANEL) - 6
"""Wrapping width for the explanatory notes. The arithmetic, once, in order:
the column is 300 wide; the scroll bar is laid out beside the viewport and
takes its 8 px out of it, leaving 292; the body's own margins take 2 and 8,
leaving a 282 px content box; and 6 px of slack keeps the longest note off the
edge. SCROLLBAR_W appears ONCE -- it used to be subtracted here and reserved
again as a right margin, which made the body 2 px wider than the viewport it
sits in and clipped the right edge of every row."""

MARK = "●"
"""The modified bullet. Drawn transparent when unmodified rather than omitted,
so the name column never shifts as values change."""


def _note(text: str) -> QLabel:
    """A wrapped explanatory line.

    Qt does not propagate a word-wrapped QLabel's height-for-width through a
    QScrollArea's layout, so the label reports a single line's height and the
    next widget is laid out on top of it. Measuring the wrapped text and
    setting that as a minimum is the fix.
    """
    lab = QLabel(text)
    lab.setObjectName("note")
    lab.setWordWrap(True)
    lab.setMinimumWidth(NOTE_WIDTH)
    rect = lab.fontMetrics().boundingRect(
        0, 0, NOTE_WIDTH, 10000, Qt.TextFlag.TextWordWrap, text)
    lab.setMinimumHeight(rect.height() + 4)
    return lab


def _value(text: str) -> QLabel:
    """A read-only value in the field column.

    Same padding as the editable field beside it, so both kinds of row put
    their last digit on one right edge. FIELD_W is a MINIMUM, not a fixed
    width: half the live block and three plant rows carry a composite
    "a / b" value that is wider than a single number, and a fixed field
    clipped those from the left -- "149.1 / 144.5" arrived as ". / 144.5",
    which is worse than an unaligned column because it is wrong. A wide value
    takes the space from the stretch in the middle of the row instead.
    """
    lab = QLabel(text)
    lab.setObjectName("value")
    lab.setMinimumWidth(T.FIELD_W)
    lab.setAlignment(Qt.AlignmentFlag.AlignRight
                     | Qt.AlignmentFlag.AlignVCenter)
    return lab


class SectionHead(QWidget):
    """A section title, with the space above it and the rule that starts it.

    A header equidistant from the block above and its own rows belongs to
    neither, which is what made five sections read as one run. The space above
    is roughly three times the space below, and a hairline marks where the
    previous section ended.
    """

    def __init__(self, title: str, first: bool = False, parent=None):
        super().__init__(parent)
        self.title = title
        self.detail = ""
        self.rule = not first
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0 if first else T.GAP_SECTION_BEFORE,
                             0, T.GAP_SECTION_AFTER)
        v.setSpacing(0)
        self.label = QLabel()
        self.label.setObjectName("sectionTitle")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.label)
        self._refresh()

    def set_detail(self, detail: str) -> None:
        """Whose numbers these are. The column never said, and the artboard's
        headers read "Controller -- constant acceleration" all along."""
        self.detail = detail
        self._refresh()

    def _refresh(self) -> None:
        text = f'<span style="color:{T.TEXT_2}">{self.title.upper()}</span>'
        if self.detail:
            text += f'<span style="color:{T.TEXT_3}"> — {self.detail}</span>'
        self.label.setText(text)

    def paintEvent(self, event) -> None:
        if not self.rule:
            return
        q = QPainter(self)
        q.setPen(QPen(QColor(T.INK_FAINT), 1))
        y = int(T.GAP_SECTION_BEFORE / 2)
        q.drawLine(0, y, self.width(), y)
        q.end()


class Row(QWidget):
    """One constant: marker, name, baseline, field, unit.

    The marker and the inline baseline are what keep a long list legible once
    you have been tuning a while -- without them you cannot tell an edited value
    from a default, or remember what the default was.
    """

    def __init__(self, label: str, control: QWidget, unit: str = "",
                 baseline: float | None = None, fmt: str = "{:g}",
                 scale: float = 1.0):
        super().__init__()
        self.baseline = baseline
        self.fmt = fmt
        self.scale = scale
        self.modified = False
        self.current = baseline
        self.setFixedHeight(T.ROW_PITCH)

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(5)

        self.mark = QLabel(MARK)
        self.mark.setFixedWidth(9)
        h.addWidget(self.mark)

        self.name = QLabel(label)
        self.name.setObjectName("label")
        h.addWidget(self.name)
        h.addStretch(1)

        self.base = QLabel("")
        self.base.setObjectName("baseline")
        h.addWidget(self.base)
        h.addWidget(control)

        self.unit = QLabel(unit)
        self.unit.setObjectName("unit")
        self.unit.setFixedWidth(T.UNIT_W)
        h.addWidget(self.unit)

        self.set_modified(False)

    def set_modified(self, on: bool) -> None:
        self.modified = on
        self.mark.setStyleSheet(
            f"color: {T.MODIFIED if on else 'transparent'};"
            f" font-size: {T.SIZE_TICK}px;")
        if on and self.baseline is not None:
            # Shown in the same unit the field is shown in: a baseline in SI
            # beside a field in ms is two numbers that look unrelated.
            shown = self.fmt.format(self.baseline * self.scale)
            self.base.setText(f"({shown})")
        else:
            self.base.setText("")

    def check(self, value: float) -> None:
        if self.baseline is not None:
            self.set_modified(abs(value - self.baseline) > 1e-12)


class ScrollFade(QWidget):
    """The fade at the foot of the scroll viewport.

    A row cut through the middle of its glyphs with nothing under it reads as
    broken. The same row under a fade reads as scrollable, which is what it is.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        clear = QColor(T.SURFACE)
        clear.setAlpha(0)
        grad = QLinearGradient(0.0, 0.0, 0.0, float(self.height()))
        grad.setColorAt(0.0, clear)
        grad.setColorAt(1.0, QColor(T.SURFACE))
        q.fillRect(self.rect(), grad)
        q.end()


class ConstantsPanel(QScrollArea):
    changed = Signal(str, float)
    """Dotted name and new value: "controller.a", "drive.a_max". Emitted so the
    window can forward it into a Command without translating anything."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFixedWidth(T.CONSTANTS_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._body = QWidget()
        self._v = QVBoxLayout(self._body)
        # PAD_PANEL only. The scroll bar is not an overlay -- the sheet
        # gives it a width and a background, not a position, so Qt lays it
        # out beside the viewport and the handle is never painted over the
        # unit column. Reserving SCROLLBAR_W here as well would be the width
        # taken twice, which is what pushed the body past the viewport.
        self._v.setContentsMargins(2, 0, T.PAD_PANEL, 2)
        self._v.setSpacing(0)
        self.setWidget(self._body)

        self._rows: dict[str, Row] = {}
        self._heads: list[SectionHead] = []
        self._only_modified = False

        self._header()
        # Hierarchy follows rate of change. LIVE is the only block that moves
        # every frame, and it was the first thing to go off the bottom of the
        # window while eight rows of PLANT that never change held the space
        # above it.
        self._controller_box, self._controller_head = (
            self._section("Controller"))
        self._scenario_box, self._scenario_head = self._section("Scenario")
        self._drive_box, _ = self._section("Drive")
        self._live_box, _ = self._section("Live")
        self._plant_box, _ = self._section("Plant")
        self._v.addStretch(1)

        self._live_labels: dict[str, QLabel] = {}
        self._live_keys: list[str] = []

        self._fade = ScrollFade(self.viewport())
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(lambda *_: self._place_fade())

    # -- viewport ---------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_fade()

    def _place_fade(self) -> None:
        vp = self.viewport()
        self._fade.setGeometry(0, vp.height() - T.FADE_H,
                               vp.width(), T.FADE_H)
        self._fade.setVisible(self.verticalScrollBar().maximum() > 0)
        self._fade.raise_()

    # -- header -----------------------------------------------------------

    def _header(self) -> None:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 2, 0, 0)
        h.setSpacing(4)

        self.filter_btn = NeumorphicButton("modified",
                                           offset=T.SHADOW_CTRL,
                                           padding=(7, 4))
        self.filter_btn.setCheckable(True)
        self.filter_btn.setToolTip("Show only values changed from their default")
        self.filter_btn.toggled.connect(self._set_filter)

        self.copy_btn = NeumorphicButton("copy", offset=T.SHADOW_CTRL,
                                         padding=(7, 4))
        self.copy_btn.setToolTip(
            "Copy the modified values as Python, to paste into params.py")
        self.copy_btn.clicked.connect(self.copy_modified)

        self.reset_btn = NeumorphicButton("reset", offset=T.SHADOW_CTRL,
                                          padding=(7, 4))
        self.reset_btn.setToolTip("Return every value to its default")
        self.reset_btn.clicked.connect(self.reset_modified)

        h.addStretch(1)
        for b in (self.filter_btn, self.copy_btn, self.reset_btn):
            h.addWidget(b)
        self._v.addWidget(bar)

    def _set_filter(self, on: bool) -> None:
        self._only_modified = on
        self._apply_filter()

    def _apply_filter(self) -> None:
        for row in self._rows.values():
            row.setVisible(row.modified or not self._only_modified)

    def reset_modified(self) -> None:
        """Emit each modified value back at its baseline. Reuses the ordinary
        edit path, so a reset reaches the source exactly as a keystroke does."""
        for name, row in list(self._rows.items()):
            if row.modified and row.baseline is not None:
                self.changed.emit(name, float(row.baseline))

    def modified_snippet(self) -> str:
        lines = [f"{n.split('.', 1)[1]}={self._rows[n].current:g},"
                 for n in sorted(self._rows) if self._rows[n].modified]
        return "\n".join(lines) if lines else "# nothing modified"

    def copy_modified(self) -> None:
        """FTC's Save writes to the robot. Here params.py is the source of
        truth, so the equivalent is a snippet to paste into it."""
        QApplication.clipboard().setText(self.modified_snippet())

    # -- scaffolding ------------------------------------------------------

    def _section(self, title: str) -> tuple[QVBoxLayout, SectionHead]:
        head = SectionHead(title, first=not self._heads)
        self._heads.append(head)
        self._v.addWidget(head)
        box = QVBoxLayout()
        box.setSpacing(0)
        self._v.addLayout(box)
        return box, head

    def _clear(self, box: QVBoxLayout, prefix: str | None = None) -> None:
        while box.count():
            item = box.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                # setParent(None) BEFORE deleteLater: deletion is deferred to
                # the event loop, and until it happens a widget removed from a
                # layout still paints at its last geometry -- which shows up as
                # a discarded row drawn on top of a live one.
                w.setParent(None)
                w.deleteLater()
        if prefix:
            for key in [k for k in self._rows if k.startswith(prefix)]:
                del self._rows[key]

    def _spin(self, name: str, lo: float, hi: float, step: float,
              value: float, decimals: int = 2,
              scale: float = 1.0) -> FlatSpinBox:
        """A flat field. The suffix lives in the row's unit column instead of
        inside the box, which is what stops `m/s³` losing its exponent and the
        stepper arrows landing on top of the glyph."""
        s = FlatSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        s.setValue(value * scale)
        s.valueChanged.connect(
            lambda v, n=name, k=scale: self._edited(n, float(v) / k))
        return s

    def _edited(self, name: str, value: float) -> None:
        row = self._rows.get(name)
        if row is not None:
            row.current = value
            row.check(value)
            self._apply_filter()
        self.changed.emit(name, value)

    def _add(self, box: QVBoxLayout, name: str, label: str, control: QWidget,
             baseline: float, current: float, unit: str = "",
             fmt: str = "{:g}", scale: float = 1.0) -> None:
        row = Row(label, control, unit=unit, baseline=baseline, fmt=fmt,
                  scale=scale)
        row.current = current
        row.check(current)
        self._rows[name] = row
        box.addWidget(row)

    # -- content ----------------------------------------------------------

    def set_controller(self, entry: Entry, values: dict[str, float]) -> None:
        """Build the controller's widgets from what it declares about itself."""
        self._clear(self._controller_box, "controller.")
        self._controller_head.set_detail(entry.label)
        if entry.error:
            self._controller_box.addWidget(_note(entry.error))
            return
        if not entry.params:
            lab = QLabel("No parameters.")
            lab.setObjectName("note")
            self._controller_box.addWidget(lab)
            return
        for spec in entry.params:
            name = f"controller.{spec.name}"
            value = values.get(spec.name, spec.default)
            decimals = 3 if spec.step < 0.1 else 2
            spin = self._spin(name, spec.lo, spec.hi, spec.step, value,
                              decimals)
            self._add(self._controller_box, name, spec.label, spin,
                      spec.default, value, spec.unit)
        self._apply_filter()

    def set_scenario(self, sc: Scenario) -> None:
        self._clear(self._scenario_box)
        self._scenario_head.set_detail(sc.label)
        rows = (
            ("θ₁", f"{math.degrees(sc.s0[1]):.2f}", "deg"),
            ("θ₂", f"{math.degrees(sc.s0[2]):.2f}", "deg"),
            ("x", f"{sc.s0[0]:.3f}", "m"),
            ("duration", f"{sc.t_end:.2f}", "s"),
        )
        for label, val, unit in rows:
            self._scenario_box.addWidget(Row(label, _value(val), unit))
        self._scenario_box.addWidget(_note(sc.note))

    def set_params(self, p: Params, substeps: int) -> None:
        base = Params().drive
        self._clear(self._drive_box, "drive.")
        d = p.drive
        for field, label, unit, lo, hi, step, scale, dec in DRIVE_FIELDS:
            name = f"drive.{field}"
            value = getattr(d, field)
            spin = self._spin(name, lo, hi, step, value, dec, scale)
            self._add(self._drive_box, name, label, spin,
                      getattr(base, field), value, unit, scale=scale)

        slip = FlatCheck()
        slip.setChecked(d.slip_enable)
        slip.toggled.connect(
            lambda v: self._edited("drive.slip_enable", float(bool(v))))
        self._add(self._drive_box, "drive.slip_enable", "slip", slip,
                  float(base.slip_enable), float(d.slip_enable), "",
                  "{:.0f}")

        for label, val, unit in (
            ("τ budget", f"{d.tau_budget * 1e3:.1f}", "mN·m"),
            ("step res", f"{d.step_res * 1e6:.2f}", "µm"),
            ("ts", f"{p.ctrl.ts * 1e3:.2f}", "ms"),
            ("substeps", str(substeps), ""),
        ):
            self._drive_box.addWidget(Row(label, _value(val), unit))

        self._clear(self._plant_box)
        e = p.effective()
        plant = (
            ("m_cart", f"{e['m_cart']:.3f}", "kg"),
            ("m_rotor", f"{e['m_rotor']:.3f}", "kg"),
            ("m₁ / m₂", f"{e['m1']:.3f} / {e['m2']:.3f}", "kg"),
            ("l₁ / l₂", f"{e['l1']:.3f} / {e['l2']:.3f}", "m"),
            ("lc₁ / lc₂", f"{e['lc1']:.3f} / {e['lc2']:.3f}", "m"),
            ("I₁", f"{e['I1']:.2e}", "kg·m²"),
            ("I₂", f"{e['I2']:.2e}", "kg·m²"),
            ("g", f"{e['g']:.3f}", "m/s²"),
            ("rail length", f"{p.nominal.rail_len * 1e3:.0f}", "mm"),
        )
        for label, val, unit in plant:
            self._plant_box.addWidget(Row(label, _value(val), unit))
        self._plant_box.addWidget(_note("Measured quantities. Edit in params.py."))
        self._apply_filter()

    def set_live(self, rows: list[tuple[str, str, str]]) -> None:
        """Called every frame, so the widgets are built once and only their text
        changes afterwards. Rebuilding them at 50 Hz churns deleteLater and
        drags the scroll position with it."""
        keys = [label for label, _, _ in rows]
        if keys != self._live_keys:
            self._clear(self._live_box)
            self._live_labels.clear()
            for label, val, unit in rows:
                widget = _value(val)
                self._live_labels[label] = widget
                self._live_box.addWidget(Row(label, widget, unit))
            self._live_keys = keys
            return
        for label, val, _ in rows:
            self._live_labels[label].setText(val)
