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

from dpc.dynamics import deriv
from dpc.model import NumericModel
from dpc.params import Params

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
