"""A PID on link 1, which is the shortest law that can chase a fall.

Measures the cart joint against upright and accelerates the cart *toward* the
lean, which is the sign that recovers an inverted pendulum rather than the one
that damps a hanging one. Rates come from RateEstimator, because the hardware
measures none.

It cannot balance the double pendulum and is not meant to: four gains act on
two of six states, and upright has more than one unstable mode. It exists as
the baseline the cascade and any later full-state law are measured against,
and as the shortest path that puts a real control law through the whole chain.
"""

import math

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register
from dpc.estimate import RateEstimator
from dpc.params import Params
from dpc.sensors import Measurement

TH1_TARGET = 0.0


@register("PID Controller")
class PIDController:

    PARAMS = (
        ParamSpec("kp", "proportional", "m/s²/rad",     50.0,  0.0, 200.0, step=1.0),
        ParamSpec("ki", "integral",     "m/s²/(rad·s)",  0.001, 0.0, 100.0, step=0.5),
        ParamSpec("kd", "derivative",   "m/s²/(rad/s)",  3.5,   0.0,  20.0, step=0.1),
        ParamSpec("kt", "anti-windup",  "1/s",           10.0,  0.0, 100.0, step=1.0),
    )

    __slots__ = ("p", "kp", "ki", "kd", "kt", "est", "i_term")

    p: Params

    def __init__(self, kp: float, ki: float, kd: float, kt: float) -> None:
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.kt = kt
        self.est = RateEstimator()
        self.i_term = 0.0
        """m/s^2. The I term's own contribution, not the raw error integral --
        kt's tracking correction is in output units, so holding the state in
        those units keeps ki out of a denominator."""

    def reset(self, p: Params) -> None:
        self.p = p
        self.est.tau = p.ctrl.tau_rate
        self.est.reset()
        self.i_term = 0.0

    def update(self, m: Measurement) -> ControlOutput:
        w1, w2 = self.est.update(m.th1, m.th2, m.dt)

        e1 = math.remainder(TH1_TARGET - m.th1, math.tau)

        a = -self.kp * e1 - self.i_term + self.kd * w1

        a_max = self.p.drive.a_max
        a_sat = max(-a_max, min(a, a_max))

        # Integrate the error and bleed off whatever the clamp refused.
        # (a - a_sat) is zero unless saturated, so one expression is both the
        # integration and the anti-windup, with no branch.
        self.i_term += (self.ki * e1 + self.kt * (a - a_sat)) * m.dt

        return ControlOutput(a_cmd=a_sat, mode="pid",
                             info={"e1": e1, "w1": w1, "w2": w2,
                                   "i": self.i_term, "x": m.x_count})
