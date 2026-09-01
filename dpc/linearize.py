"""Linearisation of the plant about an operating point.

Central finite differences rather than symbolic Jacobians: it is a dozen lines,
immune to algebra slips, and identical to what the embedded C would compute if
it ever needed to relinearise on the fly.
"""

import numpy as np

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
        A[:, j] = (model.deriv(s0 + step, F0, p)
                   - model.deriv(s0 - step, F0, p)) / (2.0 * eps)

    B = ((model.deriv(s0, F0 + eps, p)
          - model.deriv(s0, F0 - eps, p)) / (2.0 * eps)).reshape(6, 1)

    return A, B
