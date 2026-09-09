"""What is done with the equations of motion, as distinct from what they are.

`model.py` produces the terms -- M, C*qdot, G, friction. This file decides what
to solve for. That split matters here because there are two drive modes, and
they differ only in which rows are treated as known.

Written plainly -- fixed-size arrays, explicit indexing, one linear solve per
call -- because the required-force path is transcribed to C++ next milestone.
"""

import numpy as np

from dpc.model import NumericModel
from dpc.params import Params


def _terms(model: NumericModel, s: np.ndarray, p: Params):
    """M and the collected right-hand-side terms h = C*qdot + G + Ffric.

    Fusing C, G and friction into one vector is safe here because nothing
    downstream needs them apart; they remain separately accessible on the model
    itself for anything that does.
    """
    qv, vv = s[0:3], s[3:6]
    M = model.M(qv, p)
    h = model.Cqd(qv, vv, p) + model.G(qv, p) + model.Ffric(vv, p)
    return M, h


# --------------------------------------------------------------------------
# Force-driven: the ideal plant. What a force actuator would give you.
# --------------------------------------------------------------------------

def accel(model: NumericModel, s: np.ndarray, F: float, p: Params) -> np.ndarray:
    """Solve M qddot = B F - C qdot - G - Ffric for all three accelerations."""
    M, h = _terms(model, s, p)
    rhs = np.array([F, 0.0, 0.0]) - h
    return np.linalg.solve(M, rhs)


def deriv(model: NumericModel, s: np.ndarray, F: float, p: Params) -> np.ndarray:
    """State derivative, in the fixed ordering: velocities then accelerations."""
    out = np.empty(6)
    out[0:3] = s[3:6]
    out[3:6] = accel(model, s, F, p)
    return out


# --------------------------------------------------------------------------
# Acceleration-driven: the stepper plant. Cart acceleration is prescribed.
# --------------------------------------------------------------------------

def link_accel(model: NumericModel, s: np.ndarray, a_cart: float,
               p: Params) -> np.ndarray:
    """Rows 2-3 of the manipulator equation, solved for the link accelerations
    with the cart acceleration taken as given:

        Mll qddot_l = -( Ml0 xddot + Cl + Gl + fl )

    Note what is absent from the right-hand side: m_cart, m_rotor, b_cart and
    c_cart appear only in row 1, so none of them reach this result. That is the
    reason for commanding acceleration rather than force -- the parameters that
    are hardest to measure stop mattering to the part of the plant the
    controller has to model.
    """
    M, h = _terms(model, s, p)
    rhs = -(M[1:3, 0] * a_cart + h[1:3])
    return np.linalg.solve(M[1:3, 1:3], rhs)


def required_force(model: NumericModel, s: np.ndarray, a_cart: float,
                   qdd_l: np.ndarray, p: Params) -> float:
    """Row 1, read backwards: the cart force the motor must supply to produce
    `a_cart` while the links accelerate at `qdd_l`.

        F = M00 xddot + M0l qddot_l + C0 + G0 + f0

    Never an input on this hardware -- a step/dir stepper has no force
    command -- but it is the diagnostic that step-loss detection needs.
    """
    M, h = _terms(model, s, p)
    return float(M[0, 0] * a_cart + M[0, 1:3] @ qdd_l + h[0])


def motor_torque(F: float, p: Params) -> float:
    """Belt force converted to motor shaft torque."""
    return F * p.drive.r_pulley


def deriv_accel(model: NumericModel, s: np.ndarray, a_cart: float,
                p: Params) -> np.ndarray:
    """State derivative with the cart acceleration prescribed.

    Same six states as the force-driven path, so the same integrator runs both.
    """
    out = np.empty(6)
    out[0:3] = s[3:6]
    out[3] = a_cart
    out[4:6] = link_accel(model, s, a_cart, p)
    return out
