"""Offline design of the state-feedback gain the LQR controller carries.

Host-side on purpose. The controller in dpc/controllers holds six constants
and a dot product, which is all the MCU ever runs; everything expensive --
linearising, discretising, solving the Riccati equation -- happens here, once,
on a laptop. That split is also why this module may use whatever numerics it
likes while dpc/controllers may not.

No scipy: solve_discrete_are is a dozen lines of iteration when the problem is
this small, and iterating has the advantage that convergence is visible rather
than asserted. Nothing here runs in a control loop, so the cost is irrelevant.
"""

import numpy as np

from dpc.linearize import linearize_accel
from dpc.model import NumericModel
from dpc.params import Params

ANGLE_TOL = 0.1
"""rad. The largest link deflection the design is asked to tolerate. Not a
limit the controller enforces -- it is the denominator in Bryson's rule, so it
sets how expensive a tilt is relative to everything else."""

RATE_TOL = 2.0
"""rad/s. Same role for the link rates."""

CONTROL_PENALTY = 1000.0
"""Multiplier on R, found by sweep rather than derived.

Bryson's rule normalises the weights against each other; it does not promise
that the resulting law fits inside the actuator. Here it does not: at R =
1/a_max^2 the gains ask for 40 m/s^2 from a cart that can deliver 10, the
command is clamped 99% of the time, and the plant falls over faster than under
a PID. Penalising control a thousand times harder brings the peak demand
inside the limit, and 'nudged' balances indefinitely instead of surviving a
fifth of a second.

Sweeping it is not optional and the optimum is sharp: 100 still saturates 91%
of the time and loses the links in half a second, 10000 saturates 76% and
loses them at 1.1 s. It is the first thing to re-sweep if a_max, the plant, or
the tolerances change."""


def weights(p: Params, angle_tol: float = ANGLE_TOL,
            rate_tol: float = RATE_TOL,
            control_penalty: float = CONTROL_PENALTY
            ) -> tuple[np.ndarray, np.ndarray]:
    """Bryson's rule: weight each quantity by one over the square of the
    largest value worth tolerating.

    Three of the five tolerances are real limits rather than preferences --
    the rail half-length and the velocity ceiling come from Params, and the
    acceleration ceiling is what the motor can actually deliver. Only the
    angle and rate tolerances are chosen, which is what makes them the two
    knobs worth turning.
    """
    q = np.array([
        1.0 / p.x_lim ** 2,
        1.0 / angle_tol ** 2,
        1.0 / angle_tol ** 2,
        1.0 / p.drive.v_max ** 2,
        1.0 / rate_tol ** 2,
        1.0 / rate_tol ** 2,
    ])
    R = np.array([[control_penalty / p.drive.a_max ** 2]])
    return np.diag(q), R


def discretize(A: np.ndarray, B: np.ndarray,
               ts: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact zero-order-hold discretisation, by exponentiating the augmented
    block matrix

        [[A, B], [0, 0]] * ts   ->   [[Ad, Bd], [0, I]]

    Exact rather than Euler because the design should not depend on the
    control period being small: at ts = 1 ms Euler is within a percent or two,
    but the same number would be quietly wrong if the rate were ever dropped.

    The exponential is a scaled-and-squared Taylor series -- numpy has no
    expm, and for a 7x7 matrix this is shorter than the alternative.
    """
    n = A.shape[0]
    Maug = np.zeros((n + 1, n + 1))
    Maug[:n, :n] = A
    Maug[:n, n:] = B
    E = _expm(Maug * ts)
    return E[:n, :n], E[:n, n:]


def _expm(M: np.ndarray, terms: int = 18) -> np.ndarray:
    """Matrix exponential by scaling and squaring.

    Halve the argument until its norm is comfortably below one, sum the Taylor
    series there where it converges fast, then square back up.
    """
    norm = float(np.abs(M).sum(axis=1).max())
    k = max(0, int(np.ceil(np.log2(norm))) + 1) if norm > 0.5 else 0
    S = M / (2.0 ** k)

    E = np.eye(M.shape[0])
    term = np.eye(M.shape[0])
    for i in range(1, terms + 1):
        term = term @ S / i
        E = E + term

    for _ in range(k):
        E = E @ E
    return E


def dlqr(Ad: np.ndarray, Bd: np.ndarray, Q: np.ndarray, R: np.ndarray,
         tol: float = 1e-10, iters: int = 200000) -> np.ndarray:
    """Solve the discrete-time Riccati equation by iterating it to a fixed
    point, and return K for u = -K @ s.

    P starts at Q and is pushed through

        P <- Q + Ad' P Ad - Ad' P Bd (R + Bd' P Bd)^-1 Bd' P Ad

    until it stops moving. The iteration is the value function of a
    finite-horizon problem growing one step longer each pass, so convergence
    is the horizon ceasing to matter -- which is what an infinite-horizon gain
    means in the first place.

    The tolerance is relative. P's entries run to six figures on this plant,
    so an absolute threshold is a test that a well-conditioned problem can
    never pass, and the iteration fails by timing out rather than by being
    wrong.
    """
    P = Q.copy()
    for i in range(iters):
        S = R + Bd.T @ P @ Bd
        K = np.linalg.solve(S, Bd.T @ P @ Ad)
        P_next = Q + Ad.T @ P @ Ad - Ad.T @ P @ Bd @ K
        if np.abs(P_next - P).max() <= tol * max(1.0, float(np.abs(P_next).max())):
            P = P_next
            break
        P = P_next
    else:
        raise RuntimeError(f"Riccati iteration did not converge in {iters}")

    S = R + Bd.T @ P @ Bd
    return np.linalg.solve(S, Bd.T @ P @ Ad)


def design(model: NumericModel, p: Params, angle_tol: float = ANGLE_TOL,
           rate_tol: float = RATE_TOL,
           control_penalty: float = CONTROL_PENALTY) -> np.ndarray:
    """The whole path: linearise about upright, weight, discretise, solve.

    Returns K as a plain (6,) vector in the canonical state order
    [x, th1, th2, xdot, w1, w2], which is the order the controller's PARAMS
    and its dot product both use.
    """
    A, B = linearize_accel(model, np.zeros(6), 0.0, p)
    Q, R = weights(p, angle_tol, rate_tol, control_penalty)
    Ad, Bd = discretize(A, B, p.ctrl.ts)
    return dlqr(Ad, Bd, Q, R).reshape(6)
