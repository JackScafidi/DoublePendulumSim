"""The controls system: measurements in, a motor command out.

The signature is the whole point of this file. A controller receives a
Measurement -- three signals, no rates, a cart position that is really a step
count -- and returns an acceleration setpoint, because an acceleration setpoint
is what a step/dir stepper can actually be told. Nothing else crosses either
boundary.

Estimation lives on this side of the wire, inside the controller, because that
is where it runs on the MCU.

This module holds the contract only. The control laws themselves live in
dpc/controllers/, one per module, each declaring its own tunable parameters so
that adding one needs no changes anywhere else.
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
