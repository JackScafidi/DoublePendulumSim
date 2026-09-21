"""Linearisation of the plant about an operating point.

Central finite differences rather than symbolic Jacobians: it is a dozen lines,
immune to algebra slips, and identical to what the embedded C would compute if
it ever needed to relinearise on the fly.
"""

import numpy as np

from dpc.dynamics import deriv, deriv_accel
from dpc.model import NumericModel
from dpc.params import Params


def linearize(model: NumericModel, s0: np.ndarray, F0: float, p: Params,
              eps: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    """Return (A, B) such that, near the operating point,

        sdot ~= A @ (s - s0) + B @ (F - F0)

    A is 6x6 and B is 6x1. Central differences are used rather than forward
    ones because they are second-order accurate, which keeps the truncation
    error well below the rounding error at this step size.
    """
    s0 = np.asarray(s0, dtype=float)

    A = np.empty((6, 6))
    for j in range(6):
        step = np.zeros(6)
        step[j] = eps
        A[:, j] = (deriv(model, s0 + step, F0, p)
                   - deriv(model, s0 - step, F0, p)) / (2.0 * eps)

    B = ((deriv(model, s0, F0 + eps, p)
          - deriv(model, s0, F0 - eps, p)) / (2.0 * eps)).reshape(6, 1)

    return A, B


def linearize_accel(model: NumericModel, s0: np.ndarray, a0: float, p: Params,
                    eps: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    """Return (A, B) for the acceleration-driven plant, such that near the
    operating point

        sdot ~= A @ (s - s0) + B @ (a_cart - a0)

    The stepper takes an acceleration, not a force, so this is the pair a
    controller for this hardware must be designed against. Using the
    force-driven pair above and commanding the result would scale every gain by
    an effective mass, which is not a mistake any simulation makes loudly.

    Two rows are exact rather than approximated, because deriv_accel prescribes
    the cart acceleration instead of solving for it: row 3 of A is zero and
    B[3] is one. They are differenced anyway rather than written in, so that
    the finite differences stay the single source of the answer and those
    entries can be asserted as a check on the operating point.
    """
    s0 = np.asarray(s0, dtype=float)

    A = np.empty((6, 6))
    for j in range(6):
        step = np.zeros(6)
        step[j] = eps
        A[:, j] = (deriv_accel(model, s0 + step, a0, p)
                   - deriv_accel(model, s0 - step, a0, p)) / (2.0 * eps)

    B = ((deriv_accel(model, s0, a0 + eps, p)
          - deriv_accel(model, s0, a0 - eps, p)) / (2.0 * eps)).reshape(6, 1)

    return A, B
