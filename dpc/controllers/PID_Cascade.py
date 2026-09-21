"""Two nested PIDs: link 2 asks link 1 to lean, link 1 asks the cart to move.

The outer loop regulates the elbow and emits a lean angle for link 1 rather
than an acceleration, so the inner loop's setpoint moves instead of sitting at
upright. Both loops chase the fall for the same reason -- recovering a link
means driving its pivot the way the link is already going, and link 2's pivot
is the top of link 1.

The usual cascade assumption does not hold. Link 2 falls at 8.58 rad/s against
link 1's 8.00, so the outer loop's plant is the faster of the two and there is
no timescale separation to lean on. That shows up as a narrow band of usable
outer gain: kp2 = 1.0 takes survival on 'nudged' from 0.80 s to 1.53 s against
a single loop swept just as hard, and kp2 = 2.0 gives all of it back.

Defaults come from a survival sweep on 'nudged', not from pole placement. That
sweep's own spread is 10-20% on a plant whose tail is chaotic, so they are the
best point found rather than a tuned optimum. The lean clamp is inert at these
gains -- the outer loop never asks for more than about 14 degrees before the
links are lost -- and is kept for a law with more authority.
"""

import math

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register
from dpc.estimate import RateEstimator
from dpc.params import Params
from dpc.sensors import Measurement

TH2_TARGET = 0.0


@register("Cascaded PID")
class CascadeController:

    PARAMS = (
        ParamSpec("kp2",  "outer proportional", "rad/rad",     1.0,  0.0,  20.0, step=0.1),
        ParamSpec("ki2",  "outer integral",     "rad/(rad·s)", 0.0,  0.0,  20.0, step=0.1),
        ParamSpec("kd2",  "outer derivative",   "s",           0.1,  0.0,   5.0, step=0.01),
        ParamSpec("lean", "max lean",           "rad",         0.2,  0.0,   1.0, step=0.01),
        ParamSpec("kp",   "proportional",       "m/s²/rad",   70.0, 10.0, 200.0, step=1.0),
        ParamSpec("ki",   "integral",           "m/s²/(rad·s)", 0.0, 0.0, 100.0, step=0.5),
        ParamSpec("kd",   "derivative",         "m/s²/(rad/s)", 5.0, 0.0,  50.0, step=0.1),
        ParamSpec("kt",   "anti-windup",        "1/s",         10.0, 0.0, 100.0, step=1.0),
    )

    __slots__ = ("p", "kp", "ki", "kd", "kt", "kp2", "ki2", "kd2", "lean",
                 "est", "i_term", "i2_term")

    p: Params

    def __init__(self, kp2: float, ki2: float, kd2: float, lean: float,
                 kp: float, ki: float, kd: float, kt: float) -> None:
        self.kp2 = kp2
        self.ki2 = ki2
        self.kd2 = kd2
        self.lean = lean
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.kt = kt
        self.est = RateEstimator()
        self.i_term = 0.0
        self.i2_term = 0.0

    def reset(self, p: Params) -> None:
        self.p = p
        self.est.tau = p.ctrl.tau_rate
        self.est.reset()
        self.i_term = 0.0
        self.i2_term = 0.0

    def update(self, m: Measurement) -> ControlOutput:
        w1, w2 = self.est.update(m.th1, m.th2, m.dt)

        # Outer: link 2's error asks link 1 to lean, clamped to a lean the
        # inner loop can actually deliver.
        e2 = math.remainder(TH2_TARGET - m.th2, math.tau)
        th1_target = -self.kp2 * e2 - self.i2_term + self.kd2 * w2
        th1_sat = max(-self.lean, min(th1_target, self.lean))
        self.i2_term += (self.ki2 * e2 + self.kt * (th1_target - th1_sat)) * m.dt

        # Inner: unchanged, except the setpoint now moves.
        e1 = math.remainder(th1_sat - m.th1, math.tau)
        a = -self.kp * e1 - self.i_term + self.kd * w1
        a_max = self.p.drive.a_max
        a_sat = max(-a_max, min(a, a_max))
        self.i_term += (self.ki * e1 + self.kt * (a - a_sat)) * m.dt

        return ControlOutput(a_cmd=a_sat, mode="cascade",
                             info={"e1": e1, "e2": e2, "w1": w1, "w2": w2,
                                   "th1_target": th1_sat, "i": self.i_term,
                                   "i2": self.i2_term, "x": m.x_count})
