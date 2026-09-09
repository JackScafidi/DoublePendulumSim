"""The dashboard window.

Owns three things and delegates everything else: the sample buffer, the source,
and the playback clock. The panels render what they are handed; the source
produces samples; nothing but this file knows about both.

tick() is deliberately callable without the timer, so a test can drive the clock
itself instead of sleeping.
"""

import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QVBoxLayout, QWidget)

from dpc.controllers.registry import build, discover
from dpc.model import build as build_model
from dpc.params import Params
from dpc.scenarios import by_key
from dpc.ui import theme as T
from dpc.ui.panels.animation import AnimationPanel
from dpc.ui.panels.constants import ConstantsPanel
from dpc.ui.panels.controls import SelectorPanel, TransportPanel
from dpc.ui.panels.plots import PlotPanel
from dpc.ui.neumorphic import NeumorphicFrame
from dpc.ui.panels.card import card
from dpc.ui.sample import Command, SampleBuffer
from dpc.ui.source import SimSource

FRAME_MS = 20
"""Repaint interval. 50 Hz: past that the eye gains nothing and the solver
starts competing with the paint."""

WINDOW_S = 6.0
"""How much history the plots show. Longer than any shipped scenario, so a
whole run stays visible; on a long hardware session it becomes a moving window."""


class Dashboard(QMainWindow):
    def __init__(self, model=None, params: Params | None = None):
        super().__init__()
        self.setWindowTitle("Double pendulum on a cart")
        self.setStyleSheet(T.stylesheet())
        self.resize(1440, 900)

        self.entries = discover()
        self.params = params or Params()
        self.model = model if model is not None else build_model()
        self.source = SimSource(self.model, self.params)
        self.buffer = SampleBuffer()

        self.cursor = 0.0
        """s. What is being drawn -- equal to the buffer head when live, behind
        it when scrubbing back through history."""
        self.speed = 1.0
        self.playing = True
        self._t_wall = time.perf_counter()
        self._controller_values: dict[str, float] = {}

        self._build()
        self._on_controller_changed()
        self.constants.set_scenario(by_key(self.selectors.scenario_key))
        self.constants.set_params(self.params, self.source.substeps)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(FRAME_MS)

    # -- assembly ---------------------------------------------------------

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(T.PAD_WINDOW, T.PAD_WINDOW,
                                 T.PAD_WINDOW, T.PAD_WINDOW)
        outer.setSpacing(T.GAP_PANEL)

        left = QVBoxLayout()
        left.setSpacing(T.GAP_PANEL)

        self.selectors = SelectorPanel(self.entries)
        self.selectors.run_pressed.connect(self.run)
        self.selectors.controller_changed.connect(self._on_controller_changed)
        self.selectors.scenario.currentIndexChanged.connect(
            lambda: self.constants.set_scenario(by_key(self.selectors.scenario_key)))
        left.addWidget(self.selectors)

        self.animation = AnimationPanel()
        left.addWidget(card("Mechanism", self.animation), 5)

        self.transport = TransportPanel()
        self.transport.play_toggled.connect(self._on_play)
        self.transport.speed_changed.connect(self._on_speed)
        self.transport.scrubbed.connect(self._on_scrub)
        left.addWidget(card(None, self.transport, well=False))

        self.plots = PlotPanel()
        left.addWidget(self.plots, 6)

        outer.addLayout(left, 1)

        self.constants = ConstantsPanel()
        self.constants.changed.connect(self._on_constant_changed)
        outer.addWidget(card(None, self.constants, well=False))

        self.setCentralWidget(root)

    # -- wiring -----------------------------------------------------------

    def _on_controller_changed(self) -> None:
        entry = self.selectors.controller_entry
        self._controller_values = {p.name: p.default for p in entry.params}
        self.constants.set_controller(entry, self._controller_values)

    def _on_constant_changed(self, name: str, value: float) -> None:
        """Straight through to the source as a command -- the same path the
        hardware link will take, exercised on every edit."""
        if name.startswith("controller."):
            self._controller_values[name.split(".", 1)[1]] = value
        self.source.send(Command(kind="set_param", name=name, value=value))
        if name.startswith("drive."):
            self.params = self.source.params
            self.plots.set_limits(self.params)
            self.constants.set_params(self.params, self.source.substeps)

    def _on_play(self, on: bool) -> None:
        self.playing = on
        self._t_wall = time.perf_counter()

    def _on_speed(self, value: float) -> None:
        self.speed = value
        self._t_wall = time.perf_counter()

    def _on_scrub(self, t: float) -> None:
        """Scrubbing back reviews the buffer; the source is never asked for
        anything it has already produced."""
        self.cursor = t
        self._t_wall = time.perf_counter()
        self._render()

    # -- the loop ---------------------------------------------------------

    def run(self) -> None:
        entry = self.selectors.controller_entry
        if entry.error:
            self.transport.set_status("controller failed to load")
            return
        scenario = by_key(self.selectors.scenario_key)

        self.buffer.clear()
        self.animation.clear()
        self.plots.clear_traces()
        self.plots.set_limits(self.params)
        self.source.params = self.params
        self.source.start(build(entry, self._controller_values), scenario)

        self.cursor = 0.0
        self._t_wall = time.perf_counter()
        self.transport.set_range(scenario.t_end)
        self.transport.set_status("")
        self.playing = True
        self.transport.play.setChecked(True)

    def tick(self, dt: float | None = None) -> None:
        """One frame.

        `dt` is normally the wall-clock interval since the last frame. Passing
        it explicitly lets a test advance the clock deterministically instead of
        sleeping, which is the only reason this is a parameter.
        """
        now = time.perf_counter()
        if dt is None:
            dt = now - self._t_wall
        self._t_wall = now

        if self.playing and not self.source.done:
            self.cursor = min(self.cursor + dt * self.speed,
                              self.buffer.t_head + 1.0)
            got = self.source.poll(self.cursor)
            for s in got:
                self.buffer.append(s)
            if len(got) >= self.source.max_ticks_per_poll:
                self.transport.set_status("falling behind")
            elif self.source.done:
                self.transport.set_status("done")

        # Never draw ahead of what exists: the cursor may have run past the
        # head when the solver could not keep up.
        self.cursor = min(self.cursor, self.buffer.t_head)
        self._render()

    def _render(self) -> None:
        self.transport.set_cursor(self.cursor)
        self.animation.show_sample(self.buffer.at(self.cursor), self.params)
        self.plots.redraw(self.buffer.window(
            max(0.0, self.cursor - WINDOW_S), self.cursor))
        self._render_live()

    def _render_live(self) -> None:
        import math

        s = self.buffer.at(self.cursor)
        if s is None:
            self.constants.set_live([("—", "no run yet", "")])
            return
        x_true = float(s.truth[0]) if s.truth is not None else float("nan")
        err = (s.x_count - x_true) * 1e3
        self.constants.set_live([
            ("θ₁ / θ₂", f"{math.degrees(s.th1):.1f} / {math.degrees(s.th2):.1f}", "deg"),
            ("cart x", f"{x_true:.4f}", "m"),
            ("step count", f"{s.x_count:.4f}", "m"),
            ("counting error", f"{err:+.2f}", "mm"),
            ("a cmd / del", f"{s.a_cmd:.2f} / {s.a_del:.2f}", "m/s²"),
            ("τ motor", f"{s.tau * 1e3:.1f}", "mN·m"),
            ("mode", s.mode, ""),
            ("slipped", str(self.source.n_slip), "ticks"),
        ])


def main() -> int:
    app = QApplication(sys.argv)
    win = Dashboard()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
