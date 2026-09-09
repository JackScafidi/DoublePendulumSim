"""The controls system: measurements in, a motor command out.

The signature is the whole point of this file. A controller receives a
Measurement -- three signals, no rates, a cart position that is really a step
count -- and returns an acceleration setpoint, because an acceleration setpoint
is what a step/dir stepper can actually be told. Nothing else crosses either
boundary.

Estimation lives on this side of the wire, inside the controller, because that
is where it runs on the MCU.

The two controllers here exist to prove the loop closes. Real control laws --
balance, swing-up, and the mode logic between them -- are the next piece of
work, and they go in this file without anything else changing.
"""

from dataclasses import dataclass, field
from typing import Protocol

from dpc.params import Params
from dpc.sensors import Measurement


@dataclass(frozen=True)
class ControlOutput:
    """What gets written to the motor, plus whatever is worth logging."""

    a_cmd: float
    """m/s^2. Acceleration setpoint for the step generator."""

    mode: str = "idle"
    """Which law produced this, so a trace can be read after the fact."""

    info: dict = field(default_factory=dict)
    """Diagnostics only. The loop never reads this back and nothing downstream
    may depend on it -- it does not survive transcription to C++."""


class Controller(Protocol):
    """Stateful on purpose: a real controller carries an estimator, integral
    terms, mode hysteresis and its own previous command. A plain function would
    force all of that into closures or globals."""

    def reset(self, p: Params) -> None:
        """Return to a blank internal state.

        Deliberately does not receive the initial state. The controller is
        never handed truth -- it learns where the system is from its first
        update, exactly as it does on power-up.
        """
        ...

    def update(self, m: Measurement) -> ControlOutput:
        """One control tick."""
        ...


class ZeroController:
    """Commands nothing, ever.

    Lets the whole chain -- measurement, controller, motor, plant -- run without
    perturbing the physics, which is how the plumbing gets tested separately
    from any control law.
    """

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        return ControlOutput(a_cmd=0.0, mode="idle")


class ConstantController:
    """Commands a fixed acceleration.

    Held long enough this walks the motor model through its jerk limit, then
    its acceleration saturation, then its velocity ceiling, in that order --
    which exercises every stage of the actuator without needing a control law.
    """

    __slots__ = ("a",)

    def __init__(self, a: float):
        self.a = a

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        return ControlOutput(a_cmd=self.a, mode="constant")
