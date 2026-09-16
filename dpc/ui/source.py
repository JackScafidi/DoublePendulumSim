"""Where samples come from.

The dashboard consumes samples and never asks what produced them. Today that is
a solver; later it is a serial port carrying frames from the STM32. Same
protocol, same struct, so no plot and no panel changes when the hardware
arrives.

SimSource is a pull model: it computes exactly the ticks the playback clock has
reached and no more. Pausing therefore computes nothing, and a command sent
mid-run lands on the next tick -- which is the bidirectional path behaving in
simulation as it will on the bench.
"""

from dataclasses import replace
from typing import Protocol

import numpy as np

from dpc.dynamics import deriv_accel
from dpc.model import NumericModel
from dpc.motor import MotorState
from dpc.motor import step as motor_step
from dpc.params import Params
from dpc.rail import impact, side
from dpc.scenarios import Scenario
from dpc.sensors import measure
from dpc.simulate import rk4_step
from dpc.ui.sample import Command, Sample


class Source(Protocol):
    """Anything that can produce samples and accept commands."""

    def start(self, controller, scenario: Scenario) -> None: ...
    def poll(self, t_playback: float) -> list[Sample]: ...
    def send(self, cmd: Command) -> None: ...
    def stop(self) -> None: ...


class SimSource:
    """Runs the model on demand against a playback clock.

    substeps defaults to 2 rather than the library's 10. RK4 at dt = 1 ms is
    already converged for this plant -- dropping from 40 substeps to 1 moves the
    final state by 2.4e-9 -- while the cost is linear, so 10 substeps buys
    thirteen digits nobody reads and gives up real-time playback. At 2 the
    simulator runs at about twice real time, leaving headroom to fast-forward.
    """

    def __init__(self, model: NumericModel, params: Params, substeps: int = 2,
                 max_ticks_per_poll: int = 20000):
        self.model = model
        self.params = params
        self.substeps = substeps

        self.max_ticks_per_poll = max_ticks_per_poll
        """A large clock jump must not simulate minutes of plant inside one
        repaint. Hitting this cap means playback has fallen behind, which the UI
        reports rather than hides.

        Set well above a full scenario's tick count (5 s at 1 kHz is 5000) so
        that reaching the end of a run is detected by the scenario check rather
        than masked by this cap."""

        self._controller = None
        self._scenario: Scenario | None = None
        self._s = np.zeros(6)
        self._motor = MotorState()
        self._i = 0
        self.done = True

    @property
    def ts(self) -> float:
        return self.params.ctrl.ts

    @property
    def n_slip(self) -> int:
        """Control ticks lost to step slip so far in this run."""
        return self._motor.n_slip

    @property
    def n_pin(self) -> int:
        """Control ticks spent against an end stop so far in this run."""
        return self._motor.n_pin

    def start(self, controller, scenario: Scenario) -> None:
        self._controller = controller
        self._scenario = scenario
        self._restart()

    def _restart(self) -> None:
        assert self._scenario is not None and self._controller is not None
        self._s = np.array(self._scenario.s0, dtype=float)
        # Seeded from the scenario for the same reason run() seeds it: a
        # scenario that starts off centre must not open with a counting error.
        self._motor = MotorState(x_count=float(self._s[0]))
        self._i = 0
        self.done = False
        self._controller.reset(self.params)

    def stop(self) -> None:
        self.done = True

    def send(self, cmd: Command) -> None:
        """Applied to state now, so it takes effect on the next tick computed."""
        if cmd.kind == "reset":
            self._restart()
        elif cmd.kind == "stop":
            self.done = True
        elif cmd.kind == "set_param":
            target, _, field = cmd.name.partition(".")
            if target == "controller":
                setattr(self._controller, field, cmd.value)
            elif target == "drive":
                self.params = replace(
                    self.params,
                    drive=replace(self.params.drive, **{field: cmd.value}))
            else:
                raise ValueError(f"unknown command target {cmd.name!r}")

    def poll(self, t_playback: float) -> list[Sample]:
        """Every sample from the current head up to t_playback."""
        if self.done or self._controller is None or self._scenario is None:
            return []

        out: list[Sample] = []
        ts, sub = self.ts, self.substeps
        dt = ts / sub
        p = self.params

        def f(state: np.ndarray, u: float) -> np.ndarray:
            return deriv_accel(self.model, state, u, p)

        while len(out) < self.max_ticks_per_poll:
            t_next = (self._i + 1) * ts
            if t_next > t_playback + 1e-12:
                break
            if t_next > self._scenario.t_end + 1e-12:
                self.done = True
                break

            t_now = self._i * ts
            m = measure(t_now, self._s, self._motor, ts, p)
            cmd = self._controller.update(m)
            mo = motor_step(self.model, cmd.a_cmd, self._s, self._motor, ts, p)

            s_next = self._s
            for _ in range(sub):
                s_next = rk4_step(f, s_next, mo.a_del, dt)
                # The same wall simulate.run() enforces, applied at the same
                # place: after every substep, so the cart is never drawn or
                # logged anywhere the rail does not reach.
                if side(float(s_next[0]), p) != 0:
                    s_next = impact(self.model, s_next, p)

            self._s = s_next
            self._motor = mo.state
            self._i += 1

            out.append(Sample(
                t=t_next,
                th1=float(s_next[1]), th2=float(s_next[2]),
                x_count=m.x_count,
                a_cmd=cmd.a_cmd, a_del=mo.a_del,
                F_req=mo.F_req, tau=mo.tau,
                mode=cmd.mode, slipped=mo.slipped, pinned=mo.pinned,
                truth=s_next.copy(),
            ))

        return out
