"""The end stops: a constraint on the state, not a term in the model.

The rail has a finite length, and the cart reaching the end of it is a fully
inelastic collision with something rigid. That is a jump in the velocities, not
a force in the equations of motion, so it is applied between integration steps
rather than added to the derivative.

The impulse acts on the cart coordinate alone -- the stop can only push along
the rail -- but it is applied THROUGH the mass matrix. Zeroing xdot on its own
would leave the links spinning about a pivot that changed velocity
instantaneously, which creates kinetic energy out of nothing at the joint and
does not match the hardware: a real cart hitting a real stop jolts both links.
Solving M w = B and choosing the impulse that lands the cart at exactly zero
gives every coordinate its share, and it can only remove energy.

Written plainly -- one solve, explicit indexing -- because it sits in the plant
beside the rest of the integration path.
"""

import numpy as np

from dpc.model import NumericModel
from dpc.params import Params

B = np.array([1.0, 0.0, 0.0])
"""The input direction: the stop acts on the cart coordinate only, the same
column the motor pushes through."""


def side(x: float, p: Params) -> int:
    """Which stop the cart is against: -1, 0 or +1."""
    if x <= -p.x_lim:
        return -1
    if x >= p.x_lim:
        return 1
    return 0


def impact(model: NumericModel, s: np.ndarray, p: Params) -> np.ndarray:
    """The state just after a fully inelastic hit against a rigid end stop.

    Safe to call on any state, which is the point: the conditions live here
    rather than in every caller, so no integration loop can forget one.

    The cart is brought onto the rail by clamping -- a no-op in the interior,
    exact at either stop -- rather than by placing it at side()*x_lim, which
    would teleport a cart in the middle of the rail to the origin.

    The constraint is unilateral: a stop pushes and never pulls. The impulse is
    applied only when the cart is moving INTO the stop it is against. A cart
    that is leaving keeps its velocity, and a cart parked with no closing speed
    passes through bit for bit, so repeated calls while it is held are
    idempotent.
    """
    out = np.empty(6)
    out[0:3] = s[0:3]
    out[0] = min(max(float(s[0]), -p.x_lim), p.x_lim)
    out[3:6] = s[3:6]

    sgn = side(float(s[0]), p)
    if sgn == 0 or float(s[3]) * sgn <= 0.0:
        return out

    M = model.M(s[0:3], p)
    w = np.linalg.solve(M, B)
    J = -s[3] / w[0]
    out[3:6] = s[3:6] + J * w
    out[3] = 0.0
    return out
