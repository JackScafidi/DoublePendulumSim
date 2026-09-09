"""The two control strips: what to run, and how to watch it.

Both are pure widgets -- they emit what the user did and hold no simulation
state. The window owns the clock.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from dpc.controllers.registry import Entry
from dpc.scenarios import SCENARIOS
from dpc.ui import theme as T
from dpc.ui.widgets import NeumorphicButton, NeumorphicSlider

SCRUB_STEPS = 1000
"""Slider resolution. Time is a float; the slider is an integer, so the scrub
position is a fraction of the scenario rather than a tick index."""


class SelectorPanel(QWidget):
    """Controller, scenario, Run."""

    run_pressed = Signal()
    controller_changed = Signal()

    def __init__(self, entries: tuple[Entry, ...], parent=None):
        super().__init__(parent)
        self._entries = entries

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(T.PAD_PANEL)

        title = QLabel("Double pendulum on a cart")
        title.setStyleSheet(
            f"font-size: {T.SIZE_TITLE}px; font-weight: 600; color: {T.TEXT};")
        h.addWidget(title)
        h.addStretch(1)

        self.controller = QComboBox()
        for e in entries:
            self.controller.addItem(e.label, e.key)
        # A controller that failed to import is listed but cannot be chosen --
        # visible, so a typo is diagnosable, and inert, so it cannot be run.
        for i, e in enumerate(entries):
            if e.error:
                self.controller.model().item(i).setEnabled(False)
        self.controller.currentIndexChanged.connect(self.controller_changed)

        self.scenario = QComboBox()
        for sc in SCENARIOS:
            self.scenario.addItem(sc.label, sc.key)

        # The one primary fill in the view: a coloured mass that extrudes from
        # the surface and carries its own inner shade.
        self.run = NeumorphicButton("Run", filled=True, offset=5)
        self.run.clicked.connect(self.run_pressed)

        for label, widget in (("Controller", self.controller),
                              ("Scenario", self.scenario)):
            lab = QLabel(label.upper())
            lab.setObjectName("sectionTitle")
            h.addWidget(lab)
            h.addWidget(widget)
        h.addWidget(self.run)

    @property
    def controller_count(self) -> int:
        return self.controller.count()

    @property
    def scenario_count(self) -> int:
        return self.scenario.count()

    @property
    def controller_entry(self) -> Entry:
        key = self.controller.currentData()
        return next(e for e in self._entries if e.key == key)

    @property
    def scenario_key(self) -> str:
        return self.scenario.currentData()


class TransportPanel(QWidget):
    """Play, scrub, speed, and an honest status line."""

    play_toggled = Signal(bool)
    scrubbed = Signal(float)
    speed_changed = Signal(float)

    SPEEDS = (0.25, 1.0, 2.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t_end = 1.0
        self._suppress = False

        h = QHBoxLayout(self)
        h.setContentsMargins(T.PAD_PANEL, 6, T.PAD_PANEL, 6)
        h.setSpacing(T.GAP_PANEL)

        self.play = NeumorphicButton("❚❚", offset=4, padding=(10, 6))
        self.play.setCheckable(True)
        self.play.setChecked(True)
        self.play.toggled.connect(self._on_play)
        h.addWidget(self.play)

        self.slider = NeumorphicSlider()
        self.slider.setRange(0, SCRUB_STEPS)
        self.slider.valueChanged.connect(self._on_scrub)
        h.addWidget(self.slider, 1)

        self.clock = QLabel("0.000")
        self.clock.setObjectName("value")
        self.total = QLabel("/ 0.000 s")
        self.total.setObjectName("unit")
        h.addWidget(self.clock)
        h.addWidget(self.total)

        self._speed_buttons = []
        for s in self.SPEEDS:
            b = NeumorphicButton(f"{s:g}×", offset=4, padding=(9, 5))
            b.setCheckable(True)
            b.setChecked(s == 1.0)
            b.clicked.connect(lambda _, v=s: self._on_speed(v))
            self._speed_buttons.append((s, b))
            h.addWidget(b)

        self.status = QLabel("")
        self.status.setObjectName("status")
        h.addWidget(self.status)

    def _on_play(self, on: bool) -> None:
        self.play.setText("❚❚" if on else "▶")
        self.play_toggled.emit(on)

    def _on_speed(self, value: float) -> None:
        for s, b in self._speed_buttons:
            b.setChecked(s == value)
        self.speed_changed.emit(value)

    def _on_scrub(self, v: int) -> None:
        if not self._suppress:
            self.scrubbed.emit(v / SCRUB_STEPS * self._t_end)

    def set_range(self, t_end: float) -> None:
        self._t_end = max(t_end, 1e-9)
        self.total.setText(f"/ {t_end:.3f} s")

    def set_cursor(self, t: float) -> None:
        """Moved by the clock, so the emitted-signal path is suppressed --
        otherwise every frame would look like a user scrub."""
        self.clock.setText(f"{t:.3f}")
        self._suppress = True
        self.slider.setValue(int(round(t / self._t_end * SCRUB_STEPS)))
        self._suppress = False

    def set_status(self, text: str) -> None:
        self.status.setText(text)
