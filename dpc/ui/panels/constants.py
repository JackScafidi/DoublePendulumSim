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
"""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QDoubleSpinBox, QFrame,
                               QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from dpc.controllers.registry import Entry
from dpc.params import Params
from dpc.scenarios import Scenario
from dpc.ui import theme as T
from dpc.ui.widgets import NeumorphicButton, NeumorphicCheck

DRIVE_FIELDS = (
    ("a_max", "a_max", "m/s²", 0.1, 100.0, 0.5),
    ("v_max", "v_max", "m/s", 0.01, 10.0, 0.05),
    ("jerk_max", "jerk_max", "m/s³", 1.0, 100000.0, 25.0),
    ("tau_lag", "τ lag", "s", 0.0, 0.1, 0.001),
)
"""name, label, unit, lo, hi, step. The editable half of the drive block."""

NOTE_WIDTH = T.CONSTANTS_WIDTH - 24
"""Wrapping width for the explanatory notes."""

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
        0, 0, NOTE_WIDTH, 10000, Qt.TextWordWrap, text)
    lab.setMinimumHeight(rect.height() + 4)
    return lab


def _value(text: str, unit: str = "") -> QWidget:
    """A read-only value plus its unit. The QLabel holding the number is exposed
    as `.value_label` so a caller updating every frame can setText on it instead
    of rebuilding the widget."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    v = QLabel(text)
    v.setObjectName("value")
    h.addWidget(v)
    if unit:
        u = QLabel(unit)
        u.setObjectName("unit")
        h.addWidget(u)
    w.value_label = v
    return w


class Row(QWidget):
    """One constant: marker, name, baseline, control.

    The marker and the inline baseline are what keep a long list legible once
    you have been tuning a while -- without them you cannot tell an edited value
    from a default, or remember what the default was.
    """

    def __init__(self, label: str, control: QWidget,
                 baseline: float | None = None, fmt: str = "{:g}"):
        super().__init__()
        self.baseline = baseline
        self.fmt = fmt
        self.modified = False
        self.current = baseline

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

        self.set_modified(False)

    def set_modified(self, on: bool) -> None:
        self.modified = on
        self.mark.setStyleSheet(
            f"color: {T.MODIFIED if on else 'transparent'};"
            f" font-size: {T.SIZE_TICK}px;")
        if on and self.baseline is not None:
            self.base.setText(f"({self.fmt.format(self.baseline)})")
        else:
            self.base.setText("")

    def check(self, value: float) -> None:
        if self.baseline is not None:
            self.set_modified(abs(value - self.baseline) > 1e-12)


class ConstantsPanel(QScrollArea):
    changed = Signal(str, float)
    """Dotted name and new value: "controller.a", "drive.a_max". Emitted so the
    window can forward it into a Command without translating anything."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFixedWidth(T.CONSTANTS_WIDTH)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._body = QWidget()
        self._v = QVBoxLayout(self._body)
        self._v.setContentsMargins(2, 0, 8, 2)
        self._v.setSpacing(T.GAP_SECTION)
        self.setWidget(self._body)

        self._rows: dict[str, Row] = {}
        self._only_modified = False

        self._header()
        self._controller_box = self._section("Controller")
        self._scenario_box = self._section("Scenario")
        self._drive_box = self._section("Drive")
        self._plant_box = self._section("Plant")
        self._live_box = self._section("Live")
        self._v.addStretch(1)

        self._live_labels: dict[str, QLabel] = {}
        self._live_keys: list[str] = []

    # -- header -----------------------------------------------------------

    def _header(self) -> None:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 2, 0, 0)
        h.setSpacing(4)

        self.filter_btn = NeumorphicButton("modified", offset=3, padding=(7, 4))
        self.filter_btn.setCheckable(True)
        self.filter_btn.setToolTip("Show only values changed from their default")
        self.filter_btn.toggled.connect(self._set_filter)

        self.copy_btn = NeumorphicButton("copy", offset=3, padding=(7, 4))
        self.copy_btn.setToolTip(
            "Copy the modified values as Python, to paste into params.py")
        self.copy_btn.clicked.connect(self.copy_modified)

        self.reset_btn = NeumorphicButton("reset", offset=3, padding=(7, 4))
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

    def _section(self, title: str) -> QVBoxLayout:
        head = QLabel(title.upper())
        head.setObjectName("sectionTitle")
        self._v.addWidget(head)
        box = QVBoxLayout()
        box.setSpacing(1)
        self._v.addLayout(box)
        return box

    def _clear(self, box: QVBoxLayout, prefix: str | None = None) -> None:
        while box.count():
            item = box.takeAt(0)
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

    def _spin(self, name: str, lo, hi, step, value, unit) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(3 if step < 0.1 else 2)
        s.setValue(value)
        s.setSuffix(f" {unit}" if unit else "")
        s.setFixedWidth(118)
        s.setAlignment(Qt.AlignRight)
        s.valueChanged.connect(lambda v, n=name: self._edited(n, float(v)))
        return s

    def _edited(self, name: str, value: float) -> None:
        row = self._rows.get(name)
        if row is not None:
            row.current = value
            row.check(value)
            self._apply_filter()
        self.changed.emit(name, value)

    def _add(self, box: QVBoxLayout, name: str, label: str, control: QWidget,
             baseline: float, current: float, fmt: str = "{:g}") -> None:
        row = Row(label, control, baseline=baseline, fmt=fmt)
        row.current = current
        row.check(current)
        self._rows[name] = row
        box.addWidget(row)

    # -- content ----------------------------------------------------------

    def set_controller(self, entry: Entry, values: dict[str, float]) -> None:
        """Build the controller's widgets from what it declares about itself."""
        self._clear(self._controller_box, "controller.")
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
            spin = self._spin(name, spec.lo, spec.hi, spec.step, value,
                              spec.unit)
            self._add(self._controller_box, name, spec.label, spin,
                      spec.default, value)
        self._apply_filter()

    def set_scenario(self, sc: Scenario) -> None:
        self._clear(self._scenario_box)
        rows = (
            ("θ₁", f"{math.degrees(sc.s0[1]):.2f}", "deg"),
            ("θ₂", f"{math.degrees(sc.s0[2]):.2f}", "deg"),
            ("x", f"{sc.s0[0]:.3f}", "m"),
            ("duration", f"{sc.t_end:.2f}", "s"),
        )
        for label, val, unit in rows:
            self._scenario_box.addWidget(Row(label, _value(val, unit)))
        self._scenario_box.addWidget(_note(sc.note))

    def set_params(self, p: Params, substeps: int) -> None:
        base = Params().drive
        self._clear(self._drive_box, "drive.")
        d = p.drive
        for field, label, unit, lo, hi, step in DRIVE_FIELDS:
            name = f"drive.{field}"
            value = getattr(d, field)
            spin = self._spin(name, lo, hi, step, value, unit)
            self._add(self._drive_box, name, label, spin,
                      getattr(base, field), value)

        slip = NeumorphicCheck()
        slip.setChecked(d.slip_enable)
        slip.toggled.connect(
            lambda v: self._edited("drive.slip_enable", float(bool(v))))
        self._add(self._drive_box, "drive.slip_enable", "slip", slip,
                  float(base.slip_enable), float(d.slip_enable), "{:.0f}")

        for label, val, unit in (
            ("τ budget", f"{d.tau_budget * 1e3:.1f}", "mN·m"),
            ("step res", f"{d.step_res * 1e6:.2f}", "µm"),
            ("ts", f"{p.ctrl.ts * 1e3:.2f}", "ms"),
            ("substeps", str(substeps), ""),
        ):
            self._drive_box.addWidget(Row(label, _value(val, unit)))

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
        )
        for label, val, unit in plant:
            self._plant_box.addWidget(Row(label, _value(val, unit)))
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
                widget = _value(val, unit)
                self._live_labels[label] = widget.value_label
                self._live_box.addWidget(Row(label, widget))
            self._live_keys = keys
            return
        for label, val, _ in rows:
            self._live_labels[label].setText(val)
