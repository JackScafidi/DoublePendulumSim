"""Full-state feedback: one gain per state, one dot product, no loops.

Where the PID and the cascade each regulate one angle and hope the rest
follows, this weighs all six states at once -- cart position and velocity,
both link angles, both link rates -- which is what it takes to hold an
inverted double pendulum. It is the first law here that balances 'nudged'
rather than merely surviving it.

The gains are constants, computed offline by dpc.lqr_design and pasted in.
Nothing here solves anything: the MCU gets six multiplies and an add.

Two of the six states are not measured. The link rates come from
RateEstimator, and the cart velocity from a complementary filter -- dead
reckoning on the commanded acceleration, corrected slowly toward the
differenced step count. The prediction is optimistic, since the motor's jerk
limiter and lag mean it never delivers exactly what was asked, and correcting
that drift is what tau_v buys. Both signals are weaker than the three the
hardware actually measures, and K applies real gain to them.

Valid near upright only. Linearised there, and far from it -- hanging, folded,
flat -- it does not recover.
"""

import math

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register
from dpc.estimate import RateEstimator
from dpc.params import Params
from dpc.sensors import Measurement


@register("LQR Controller")
class LQRController:

    PARAMS = (
        ParamSpec("k_x",   "cart position",       "1/s²",           0.6196,  -50.0,  50.0, step=0.1),
        ParamSpec("k_th1", "link 1 angle",        "m/s²/rad",    -104.6876, -500.0, 500.0, step=1.0),
        ParamSpec("k_th2", "link 2 angle",        "m/s²/rad",     111.8694, -500.0, 500.0, step=1.0),
        ParamSpec("k_dx",  "cart velocity",       "1/s",            1.5906,  -50.0,  50.0, step=0.1),
        ParamSpec("k_w1",  "link 1 rate",         "m/s²/(rad/s)",  -3.6197,  -50.0,  50.0, step=0.1),
        ParamSpec("k_w2",  "link 2 rate",         "m/s²/(rad/s)",   9.8304,  -50.0,  50.0, step=0.1),
        ParamSpec("tau_v", "cart velocity blend", "s",              0.10,     0.0,   2.0, step=0.01),
    )

    __slots__ = ("p", "k_x", "k_th1", "k_th2", "k_dx", "k_w1", "k_w2",
                 "tau_v", "est", "xd", "x_prev", "primed", "a_prev")

    p: Params

    def __init__(self, k_x: float, k_th1: float, k_th2: float, k_dx: float,
                 k_w1: float, k_w2: float, tau_v: float) -> None:
        self.k_x = k_x
        self.k_th1 = k_th1
        self.k_th2 = k_th2
        self.k_dx = k_dx
        self.k_w1 = k_w1
        self.k_w2 = k_w2
        self.tau_v = tau_v
        self.est = RateEstimator()
        self.xd = 0.0
        """m/s. Complementary-filter estimate of the cart velocity."""
        self.x_prev = 0.0
        self.primed = False
        self.a_prev = 0.0
        """m/s^2. Last command, clamped. The acceleration that acted over the
        interval the predict step integrates across -- the raw command would
        dead-reckon an acceleration the motor never delivered."""

    def reset(self, p: Params) -> None:
        self.p = p
        self.est.tau = p.ctrl.tau_rate
        self.est.reset()
        self.xd = 0.0
        self.x_prev = 0.0
        self.primed = False
        self.a_prev = 0.0

    def update(self, m: Measurement) -> ControlOutput:
        w1, w2 = self.est.update(m.th1, m.th2, m.dt)

        # Cart velocity: dead-reckon the command forward, then correct toward
        # the differenced step count. The first tick only seeds the difference.
        xd_meas = 0.0
        if not self.primed:
            self.x_prev = m.x_count
            self.primed = True
        else:
            self.xd += self.a_prev * m.dt
            xd_meas = (m.x_count - self.x_prev) / m.dt
            self.x_prev = m.x_count
            alpha = 1.0 - math.exp(-m.dt / self.tau_v) if self.tau_v > 0.0 else 1.0
            self.xd += alpha * (xd_meas - self.xd)

        # u = -K s, about the zero state: upright, centred, at rest. Every sign
        # that matters is inside K, which came out of the Riccati solve.
        th1 = math.remainder(m.th1, math.tau)
        th2 = math.remainder(m.th2, math.tau)

        a = -(self.k_x * m.x_count
              + self.k_th1 * th1
              + self.k_th2 * th2
              + self.k_dx * self.xd
              + self.k_w1 * w1
              + self.k_w2 * w2)

        a_max = self.p.drive.a_max
        a_sat = max(-a_max, min(a, a_max))
        self.a_prev = a_sat

        return ControlOutput(a_cmd=a_sat, mode="lqr",
                             info={"th1": th1, "th2": th2, "w1": w1, "w2": w2,
                                   "xd": self.xd, "xd_meas": xd_meas,
                                   "x": m.x_count})
