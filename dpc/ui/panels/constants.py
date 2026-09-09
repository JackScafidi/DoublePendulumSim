"""Every constant the run is using, in one column.

Controller knobs and drive limits are editable -- those are what gets tuned
while playing. Plant parameters and scenario initial conditions are read-only:
they are measured or declared facts, and a constants panel is the wrong place to
edit physics by accident.

The controller section is built from the controller's own PARAMS declaration.
Nothing here names a controller, which is what lets a new file in
dpc/controllers/ arrive with working widgets and no edit to this file.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
                               QScrollArea, QVBoxLayout, QWidget)

from dpc.controllers.registry import Entry
from dpc.params import Params
from dpc.scenarios import Scenario
from dpc.ui import theme as T
from dpc.ui.widgets import NeumorphicCheck

DRIVE_FIELDS = (
    ("a_max", "a_max", "m/s²", 0.1, 100.0, 0.5),
    ("v_max", "v_max", "m/s", 0.01, 10.0, 0.05),
    ("jerk_max", "jerk_max", "m/s³", 1.0, 100000.0, 25.0),
    ("tau_lag", "τ lag", "s", 0.0, 0.1, 0.001),
)
"""name, label, unit, lo, hi, step. The editable half of the drive block."""


def _row(label: str, widget: QWidget) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lab = QLabel(label)
    lab.setObjectName("label")
    h.addWidget(lab)
    h.addStretch(1)
    h.addWidget(widget)
    return w


def _value(text: str, unit: str = "") -> QWidget:
    """A value plus its unit. The QLabel holding the number is exposed as
    `.value_label` so a caller that updates every frame can setText on it
    instead of rebuilding the widget."""
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

        self._controller_box = self._section("Controller")
        self._scenario_box = self._section("Scenario")
        self._drive_box = self._section("Drive")
        self._plant_box = self._section("Plant")
        self._live_box = self._section("Live")
        self._v.addStretch(1)

        self._drive_spins: dict[str, QDoubleSpinBox] = {}
        self._live_labels: dict[str, QLabel] = {}
        self._live_keys: list[str] = []

    # -- scaffolding ------------------------------------------------------

    def _section(self, title: str) -> QVBoxLayout:
        head = QLabel(title.upper())
        head.setObjectName("sectionTitle")
        self._v.addWidget(head)
        box = QVBoxLayout()
        box.setSpacing(1)
        self._v.addLayout(box)
        return box

    @staticmethod
    def _clear(box: QVBoxLayout) -> None:
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _spin(self, name: str, lo, hi, step, value, unit) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(3 if step < 0.1 else 2)
        s.setValue(value)
        s.setSuffix(f" {unit}" if unit else "")
        s.setFixedWidth(124)
        s.setAlignment(Qt.AlignRight)
        s.valueChanged.connect(lambda v, n=name: self.changed.emit(n, float(v)))
        return s

    # -- content ----------------------------------------------------------

    def set_controller(self, entry: Entry, values: dict[str, float]) -> None:
        """Build the controller's widgets from what it declares about itself."""
        self._clear(self._controller_box)
        if entry.error:
            lab = QLabel(entry.error)
            lab.setObjectName("note")
            lab.setWordWrap(True)
            self._controller_box.addWidget(lab)
            return
        if not entry.params:
            lab = QLabel("No parameters.")
            lab.setObjectName("note")
            self._controller_box.addWidget(lab)
            return
        for spec in entry.params:
            spin = self._spin(f"controller.{spec.name}", spec.lo, spec.hi,
                              spec.step, values.get(spec.name, spec.default),
                              spec.unit)
            self._controller_box.addWidget(_row(spec.label, spin))

    def set_scenario(self, sc: Scenario) -> None:
        import math
        self._clear(self._scenario_box)
        rows = (
            ("θ₁", f"{math.degrees(sc.s0[1]):.2f}", "deg"),
            ("θ₂", f"{math.degrees(sc.s0[2]):.2f}", "deg"),
            ("x", f"{sc.s0[0]:.3f}", "m"),
            ("duration", f"{sc.t_end:.2f}", "s"),
        )
        for label, val, unit in rows:
            self._scenario_box.addWidget(_row(label, _value(val, unit)))
        note = QLabel(sc.note)
        note.setObjectName("note")
        note.setWordWrap(True)
        self._scenario_box.addWidget(note)

    def set_params(self, p: Params, substeps: int) -> None:
        self._clear(self._drive_box)
        self._drive_spins.clear()
        d = p.drive
        for name, label, unit, lo, hi, step in DRIVE_FIELDS:
            spin = self._spin(f"drive.{name}", lo, hi, step,
                              getattr(d, name), unit)
            self._drive_spins[name] = spin
            self._drive_box.addWidget(_row(label, spin))

        slip = NeumorphicCheck()
        slip.setChecked(d.slip_enable)
        slip.toggled.connect(
            lambda v: self.changed.emit("drive.slip_enable", float(bool(v))))
        self._drive_box.addWidget(_row("slip", slip))
        self._drive_box.addWidget(
            _row("τ budget", _value(f"{d.tau_budget * 1e3:.1f}", "mN·m")))
        self._drive_box.addWidget(
            _row("step res", _value(f"{d.step_res * 1e6:.2f}", "µm")))
        self._drive_box.addWidget(_row("ts", _value(f"{p.ctrl.ts * 1e3:.2f}", "ms")))
        self._drive_box.addWidget(_row("substeps", _value(str(substeps))))

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
            self._plant_box.addWidget(_row(label, _value(val, unit)))
        note = QLabel("Measured quantities. Edit in params.py.")
        note.setObjectName("note")
        note.setWordWrap(True)
        self._plant_box.addWidget(note)

    def set_live(self, rows: list[tuple[str, str, str]]) -> None:
        """Called every frame, so the widgets are built once and only their
        text changes afterwards. Rebuilding them at 50 Hz churns deleteLater
        and drags the scroll position with it."""
        keys = [label for label, _, _ in rows]
        if keys != self._live_keys:
            self._clear(self._live_box)
            self._live_labels.clear()
            for label, val, unit in rows:
                widget = _value(val, unit)
                self._live_labels[label] = widget.value_label
                self._live_box.addWidget(_row(label, widget))
            self._live_keys = keys
            return
        for label, val, _ in rows:
            self._live_labels[label].setText(val)
