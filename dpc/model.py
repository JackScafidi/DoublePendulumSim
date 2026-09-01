"""Programmatic derivation of the equations of motion.

The model is described by a ModelConfig, and derive() assembles the Lagrangian
from that description. Because SymPy performs the algebra, re-deriving after a
model change costs a function call rather than an evening, so the equations
never need re-deriving by hand.
"""

from dataclasses import dataclass
from typing import Literal

import sympy as sp

from dpc.params import EFFECTIVE_NAMES


@dataclass(frozen=True)
class ModelConfig:
    """Which physical effects the derivation should include.

    `drive="compliant"` is a named seam for the belt-spring model that hardware
    will eventually need. It adds states rather than terms, so it cannot be
    reached by setting a parameter to zero, and it is not implemented yet.
    """

    drive: Literal["rigid", "compliant"] = "rigid"
    friction: Literal["viscous", "viscous+coulomb"] = "viscous+coulomb"
    rail_tilt: bool = True


t = sp.Symbol("t", real=True)

# Generalised coordinates as explicit functions of time, so sp.diff(expr, t)
# produces exact time derivatives rather than zero.
x = sp.Function("x")(t)
th1 = sp.Function("theta1")(t)
th2 = sp.Function("theta2")(t)

q = (x, th1, th2)
qd = tuple(sp.diff(c, t) for c in q)
qdd = tuple(sp.diff(c, t, 2) for c in q)

_POSITIVE = {"m_cart", "m_rotor", "m1", "m2", "l1", "l2", "g", "eps_fric"}

# One symbol per effective parameter, in the canonical order from params.py.
S: dict[str, sp.Symbol] = {
    name: sp.Symbol(name, real=True, positive=name in _POSITIVE)
    for name in EFFECTIVE_NAMES
}
PARAM_SYMS: tuple[sp.Symbol, ...] = tuple(S[name] for name in EFFECTIVE_NAMES)


def _direction(theta: sp.Expr) -> sp.Matrix:
    """Unit vector along a link held at angle `theta`.

    Angles are measured from straight up, positive tipping the link toward +x:

        theta = 0     -> ( 0,  1)   upright
        theta = pi/2  -> ( 1,  0)   laid flat toward +x
        theta = pi    -> ( 0, -1)   hanging

    This is clockwise-positive on standard axes. It is chosen so that the cart
    force and the angular error share a sign: a pendulum falling toward +theta
    is corrected by driving the cart toward +x.
    """
    return sp.Matrix([sp.sin(theta), sp.cos(theta)])


def _kinematics(cfg: ModelConfig) -> dict:
    """World positions and velocities of every mass.

    Link 2's orientation uses theta_2 directly rather than theta_1 + theta_2:
    the angles are absolute, so only link 2's *attachment point* depends on
    link 1.
    """
    phi = S["phi"] if cfg.rail_tilt else sp.Integer(0)

    rail = sp.Matrix([sp.cos(phi), sp.sin(phi)])
    p_cart = x * rail

    d1 = _direction(th1)
    d2 = _direction(th2)

    p_c1 = p_cart + S["lc1"] * d1
    p_elbow = p_cart + S["l1"] * d1
    p_c2 = p_elbow + S["lc2"] * d2

    return {
        "p_cart": p_cart,
        "p_c1": p_c1,
        "p_elbow": p_elbow,
        "p_c2": p_c2,
        "v_cart": sp.diff(p_cart, t),
        "v_c1": sp.diff(p_c1, t),
        "v_c2": sp.diff(p_c2, t),
    }
