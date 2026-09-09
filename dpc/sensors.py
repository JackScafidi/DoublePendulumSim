"""The boundary between hardware and software, made explicit.

Everything above this line is truth the simulator happens to know. Everything
below it is what firmware actually has at the top of a control tick. The
Measurement struct is the whole of that second list -- if a quantity is not in
it, no controller may use it.
"""

from dataclasses import dataclass

import numpy as np

from dpc.motor import MotorState, step_count
from dpc.params import Params


@dataclass(frozen=True)
class Measurement:
    """Three signals and the timing they belong to. Nothing else exists.

    There are no rates here, because the hardware measures none: a controller
    that needs theta1dot must difference the angles itself, exactly as it will
    on the bench.
    """

    t: float
    """s since start."""

    th1: float
    """rad. Encoder at the cart joint. Quantised on hardware."""

    th2: float
    """rad. Encoder at the elbow. Quantised on hardware."""

    x_count: float
    """m. Position implied by the total of the steps commanded.

    Not a sensor reading. On an open-loop stepper the cart has no position
    reference at all, so this is the controller's own history played back to
    it, and it drifts silently from the truth whenever the motor slips."""

    dt: float
    """s. The control period this reading belongs to. Passed in rather than
    read from a clock, so the same controller runs at any rate, in simulation
    or on the target, without edits."""


def measure(t: float, s: np.ndarray, st: MotorState, dt: float,
            p: Params) -> Measurement:
    """Build a measurement from the true state and the motor's own counter.

    Today the angles are copied from truth exactly: no quantisation, no noise.
    Those belong here, in this one function, and adding them will degrade every
    controller's inputs at once without any controller changing.
    """
    return Measurement(
        t=t,
        th1=float(s[1]),
        th2=float(s[2]),
        x_count=step_count(st, p) * p.drive.step_res,
        dt=dt,
    )
