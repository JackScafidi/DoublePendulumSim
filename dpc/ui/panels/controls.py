"""The two control strips: what to run, and how to watch it.

Both are pure widgets -- they emit what the user did and hold no simulation
state. The window owns the clock, and now draws it too: the run time belongs
beside the thing it is timing, in the Mechanism card header, rather than as two
more labels in a transport row that was already carrying four.

What is left here is one accent mass. Run is the primary fill in the view, so
play is a raised icon button with the interactive border, the scrub groove is
thin and part-strength, and the three speeds are one segmented control rather
than three separately extruded pills.
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from dpc.controllers.registry import Entry
from dpc.scenarios import SCENARIOS
from dpc.ui import theme as T
from dpc.ui.widgets import (FlatCombo, IconButton, NeumorphicButton,
                            NeumorphicSlider, SegmentedControl, StatusPill)

SCRUB_STEPS = 1000
"""Slider resolution. Time is a float; the slider is an integer, so the scrub
position is a fraction of the scenario rather than a tick index."""

BEHIND = "falling behind"
DONE = "done"
FAILED = "controller failed to load"
STATUSES = (BEHIND, DONE, FAILED)
"""Every status the pill can ever carry, so it can size itself to the widest
of them once and hold that width for the life of the window. BEHIND is the one
worth a colour -- it is what the whole pull-model run design exists to report,
so it is the one that gets the amber."""


class SelectorPanel(QWidget):
    """Controller, scenario, Run."""

    run_pressed = Signal()
    controller_changed = Signal()

    def __init__(self, entries: tuple[Entry, ...], parent=None):
        super().__init__(parent)
        self._entries = entries

        h = QHBoxLayout(self)
        # The same inset a card gives its contents. This strip sits outside a
        # card but directly above one, and an eye lines up a left edge before
        # it reads anything: at zero margin the window title started about
        # 22 px left of the MECHANISM label beneath it.
        h.setContentsMargins(T.CARD_INSET, 0, T.CARD_INSET, 0)
        h.setSpacing(T.PAD_PANEL)

        title = QLabel("Double pendulum on a cart")
        title.setStyleSheet(
            f"font-size: {T.SIZE_TITLE}px; font-weight: 600; color: {T.TEXT};")
        h.addWidget(title)
        h.addStretch(1)

        self.controller = FlatCombo()
        for e in entries:
            self.controller.addItem(e.label, e.key)
        # A controller that failed to import is listed but cannot be chosen --
        # visible, so a typo is diagnosable, and inert, so it cannot be run.
        model = self.controller.model()
        if isinstance(model, QStandardItemModel):
            for i, e in enumerate(entries):
                if e.error:
                    model.item(i).setEnabled(False)
        self.controller.currentIndexChanged.connect(self.controller_changed)

        self.scenario = FlatCombo()
        for sc in SCENARIOS:
            self.scenario.addItem(sc.label, sc.key)

        # The one primary fill in the view: a coloured mass that extrudes from
        # the surface and carries its own inner shade.
        self.run = NeumorphicButton("Run", filled=True,
                                    offset=T.SHADOW_PRIMARY)
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
    """Play, scrub, speed, and an honest status."""

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

        self.play = IconButton("pause", offset=T.SHADOW_CTRL)
        self.play.setCheckable(True)
        self.play.setChecked(True)
        self.play.toggled.connect(self._on_play)
        h.addWidget(self.play)

        self.slider = NeumorphicSlider()
        self.slider.setRange(0, SCRUB_STEPS)
        self.slider.valueChanged.connect(self._on_scrub)
        h.addWidget(self.slider, 1)

        # Fixed width, always in the layout. The slider is the only thing in
        # this row that stretches, so anything beside it that changes width
        # changes the length of the scrub groove -- and a groove that shortens
        # by 172 px the moment a run falls behind jumps the thumb by that much
        # mid-drag. Same rule as the play button's fixed square.
        self.status = StatusPill(STATUSES)
        h.addWidget(self.status)
        h.addSpacing(T.PAD_PANEL)

        self.speeds = SegmentedControl(tuple(f"{s:g}×" for s in self.SPEEDS),
                                       active=self.SPEEDS.index(1.0))
        self.speeds.selected.connect(
            lambda i: self.speed_changed.emit(self.SPEEDS[i]))
        h.addWidget(self.speeds)

    def _on_play(self, on: bool) -> None:
        self.play.glyph = "pause" if on else "play"
        self.play.update()
        self.play_toggled.emit(on)

    def _on_scrub(self, v: int) -> None:
        if not self._suppress:
            self.scrubbed.emit(v / SCRUB_STEPS * self._t_end)

    def set_range(self, t_end: float) -> None:
        self._t_end = max(t_end, 1e-9)

    def set_cursor(self, t: float) -> None:
        """Moved by the clock, so the emitted-signal path is suppressed --
        otherwise every frame would look like a user scrub."""
        self._suppress = True
        self.slider.setValue(int(round(t / self._t_end * SCRUB_STEPS)))
        self._suppress = False

    def set_status(self, text: str) -> None:
        self.status.set_status(text, alert=text == BEHIND)
