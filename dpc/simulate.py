"""Fixed-step RK4 integration.

Fixed step on purpose. It is what a real controller does and what the STM32
will do, so the simulator and the target stay on the same footing. An adaptive
integrator would take steps the target cannot take, hiding a class of
discrepancy that would only surface on hardware.

Accuracy is verified by step halving rather than by a second integrator:
running at dt and dt/2 and comparing gives both the observed convergence order
and an error estimate, with no extra dependency.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

from dpc.control import Controller
from dpc.dynamics import deriv, deriv_accel
from dpc.model import NumericModel
from dpc.motor import MotorState
from dpc.motor import step as motor_step
from dpc.params import Params
from dpc.sensors import measure

ForceFn = Callable[[float, np.ndarray], float]
"""Control law: takes (time, state), returns the cart force in newtons."""

DerivFn = Callable[[np.ndarray, float], np.ndarray]
"""State derivative: takes (state, scalar input), returns the 6-vector.

Taking a callable rather than a model is what lets one integrator serve both
drive modes -- force-driven passes the force, stepper mode passes the delivered
acceleration -- without the integrator ever knowing which it is.
"""


@dataclass(frozen=True)
class Trajectory:
    t: np.ndarray
    """(n,) sample times."""

    s: np.ndarray
    """(n, 6) states, ordered [x, th1, th2, xdot, w1, w2]."""

    F: np.ndarray
    """(n,) force held across the step that begins at the matching time."""


def rk4_step(f: DerivFn, s: np.ndarray, u: float, dt: float) -> np.ndarray:
    """One classical RK4 step with the input held constant across it.

    Written plainly for later transcription to C++: four evaluations, one
    weighted sum, no allocation beyond the stage vectors.
    """
    k1 = f(s, u)
    k2 = f(s + 0.5 * dt * k1, u)
    k3 = f(s + 0.5 * dt * k2, u)
    k4 = f(s + dt * k3, u)
    return s + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def simulate(model: NumericModel, s0: np.ndarray, force: ForceFn,
             t_end: float, dt: float, p: Params) -> Trajectory:
    """Integrate from s0 to t_end at fixed step dt.

    The force is sampled once per step and held, which is exactly what a
    controller running at 1/dt does. `s0` is copied, never modified.
    """
    n = int(round(t_end / dt))
    t = np.linspace(0.0, n * dt, n + 1)
    s = np.empty((n + 1, 6))
    F = np.empty(n + 1)
    s[0] = np.asarray(s0, dtype=float)

    def f(state: np.ndarray, u: float) -> np.ndarray:
        return deriv(model, state, u, p)

    for i in range(n):
        F[i] = force(t[i], s[i])
        s[i + 1] = rk4_step(f, s[i], F[i], dt)

    F[n] = force(t[n], s[n])
    return Trajectory(t=t, s=s, F=F)


# --------------------------------------------------------------------------
# Closed loop: measurement, controller, motor, plant.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Run:
    """A closed-loop trace, sampled once per control tick.

    Control ticks rather than plant substeps: it is what firmware could log
    over a serial link, nothing in the chain changes between ticks, and the
    arrays stay small enough to keep.

    x_count minus s[:, 0] is the step-counting error -- the signal that reveals
    slip, and the one the real hardware has no way to compute.
    """

    t: np.ndarray
    """(n,) tick times."""

    s: np.ndarray
    """(n, 6) true state."""

    meas: np.ndarray
    """(n, 3) [th1, th2, x_count] as the controller saw them."""

    a_cmd: np.ndarray
    """(n,) m/s^2 requested."""

    a_del: np.ndarray
    """(n,) m/s^2 delivered."""

    F_req: np.ndarray
    """(n,) N the plant required."""

    tau: np.ndarray
    """(n,) N m at the motor shaft."""

    x_count: np.ndarray
    """(n,) m implied by the step counter."""

    mode: list[str]
    """(n,) which law was active."""

    slipped: np.ndarray
    """(n,) bool."""


def run(model: NumericModel, s0: np.ndarray, controller: Controller,
        p: Params, t_end: float, ts: float | None = None,
        substeps: int | None = None) -> Run:
    """Integrate the full chain: measurement, controller, motor, plant.

    Two clocks. The controller runs at ts; the plant integrates at ts/substeps.
    Separating them is what allows the control rate to be varied without
    disturbing the physics, and it is what the hardware does -- one command per
    tick, held.

    The motor updates once per tick and its delivered acceleration is held
    across the substeps. That is faithful rather than simplified: the step-rate
    timer is reloaded once per control tick, so the jerk limiter, the
    saturation, the ceiling and the lag are all genuinely discrete at ts.
    """
    ts = p.ctrl.ts if ts is None else ts
    substeps = p.ctrl.substeps if substeps is None else substeps
    dt = ts / substeps

    n = int(round(t_end / ts))
    t = np.linspace(0.0, n * ts, n + 1)

    s = np.empty((n + 1, 6))
    meas = np.empty((n + 1, 3))
    a_cmd = np.empty(n + 1)
    a_del = np.empty(n + 1)
    F_req = np.empty(n + 1)
    tau = np.empty(n + 1)
    x_count = np.empty(n + 1)
    slipped = np.empty(n + 1, dtype=bool)
    mode: list[str] = []

    s[0] = np.asarray(s0, dtype=float)
    st = MotorState()
    controller.reset(p)

    def f(state: np.ndarray, u: float) -> np.ndarray:
        return deriv_accel(model, state, u, p)

    for i in range(n + 1):
        m = measure(t[i], s[i], st, ts, p)
        out = controller.update(m)
        mo = motor_step(model, out.a_cmd, s[i], st, ts, p)

        meas[i] = (m.th1, m.th2, m.x_count)
        a_cmd[i] = out.a_cmd
        a_del[i] = mo.a_del
        F_req[i] = mo.F_req
        tau[i] = mo.tau
        x_count[i] = m.x_count
        slipped[i] = mo.slipped
        mode.append(out.mode)

        # The final tick is measured and commanded but never applied, matching
        # how simulate() records a trailing force it does not integrate.
        if i == n:
            break

        st = mo.state
        s[i + 1] = s[i]
        for _ in range(substeps):
            s[i + 1] = rk4_step(f, s[i + 1], mo.a_del, dt)

    return Run(t=t, s=s, meas=meas, a_cmd=a_cmd, a_del=a_del, F_req=F_req,
               tau=tau, x_count=x_count, mode=mode, slipped=slipped)
