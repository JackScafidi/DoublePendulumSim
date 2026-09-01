"""Programmatic derivation of the equations of motion.

The model is described by a ModelConfig, and derive() assembles the Lagrangian
from that description. Because SymPy performs the algebra, re-deriving after a
model change costs a function call rather than an evening, so the equations
never need re-deriving by hand.
"""

import hashlib
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import sympy as sp

from dpc.params import EFFECTIVE_NAMES, Params


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


@dataclass(frozen=True)
class Model:
    """The derived equations, in manipulator form

        M(q) qddot + C(q, qdot) qdot + G(q) + Ffric(qdot) = B u

    The pieces are kept separate rather than fused: energy-shaping swing-up
    needs G alone, the linearisation is cleaner term by term, and the eventual
    C transcription wants them apart.
    """

    cfg: ModelConfig
    T_sym: sp.Expr
    V_sym: sp.Expr
    M_sym: sp.Matrix
    Cqd_sym: sp.Matrix
    G_sym: sp.Matrix
    Ffric_sym: sp.Matrix
    B_sym: sp.Matrix


def _kinetic_energy(k: dict) -> sp.Expr:
    """Konig's theorem for each body: translation of the centre of mass plus
    rotation about it. There is no cross term precisely because I1 and I2 are
    defined about each link's own COM.

    m_rotor appears here and nowhere else. The belt ties rotor angle to cart
    position by x = r*theta_m, so (1/2) J theta_m_dot^2 becomes
    (1/2) (J/r^2) xdot^2, which is indistinguishable from translating mass.

    The angular rates are theta1dot and theta2dot rather than theta1dot and
    (theta2dot - theta1dot): the angles are absolute, so theta2dot is already
    link 2's true angular velocity in space.
    """
    v_cart, v_c1, v_c2 = k["v_cart"], k["v_c1"], k["v_c2"]
    w1, w2 = sp.diff(th1, t), sp.diff(th2, t)

    return sp.Rational(1, 2) * (
        (S["m_cart"] + S["m_rotor"]) * v_cart.dot(v_cart)
        + S["m1"] * v_c1.dot(v_c1) + S["I1"] * w1 ** 2
        + S["m2"] * v_c2.dot(v_c2) + S["I2"] * w2 ** 2
    )


def _potential_energy(k: dict) -> sp.Expr:
    """Gravity acting on real mass only.

    m_rotor is deliberately absent: it stores kinetic energy but has no weight.
    Including it here would put a phantom downhill force on a tilted rail.
    """
    return S["g"] * (
        S["m_cart"] * k["p_cart"][1]
        + S["m1"] * k["p_c1"][1]
        + S["m2"] * k["p_c2"][1]
    )


def _friction(cfg: ModelConfig) -> sp.Matrix:
    """Generalised friction forces, written as they appear on the left-hand side.

    Three sites, two independent rates. The rail resists xdot and the cart
    joint resists theta1dot, but the elbow resists the RELATIVE rate
    theta2dot - theta1dot, because theta_2 is measured from vertical rather
    than from link 1. Links rotating together do not bend the elbow, and that
    difference correctly gives zero.

    By Newton's third law the elbow torque on link 2 has an equal and opposite
    reaction on link 1, which is the -f2 in the middle row. Omitting it yields
    a machine that manufactures angular momentum from nothing.

    Coulomb friction uses tanh(v/eps) rather than sign(v) so the model stays
    differentiable, which both linearisation and gradient-based fitting need.
    """
    xd, w1, w2 = qd
    rel = w2 - w1

    def coulomb(c: sp.Symbol, v: sp.Expr) -> sp.Expr:
        if cfg.friction == "viscous":
            return sp.Integer(0)
        return c * sp.tanh(v / S["eps_fric"])

    f_rail = S["b_cart"] * xd + coulomb(S["c_cart"], xd)
    f_1 = S["b1"] * w1 + coulomb(S["c1"], w1)
    f_2 = S["b2"] * rel + coulomb(S["c2"], rel)

    return sp.Matrix([f_rail, f_1 - f_2, f_2])


def derive(cfg: ModelConfig = ModelConfig()) -> Model:
    """Assemble the Lagrangian from cfg and extract the manipulator form."""
    if cfg.drive != "rigid":
        raise NotImplementedError(
            f"drive={cfg.drive!r} is a planned seam, not an implementation. "
            "Belt compliance adds states rather than terms, so it cannot be "
            "reached by setting a parameter to zero."
        )

    k = _kinematics(cfg)
    T = _kinetic_energy(k)
    V = _potential_energy(k)

    # M is the Hessian of T with respect to the generalised velocities.
    M = sp.Matrix(3, 3, lambda i, j: sp.simplify(sp.diff(T, qd[i], qd[j])))

    # Euler-Lagrange applied to the kinetic part alone, minus M*qddot, leaves
    # exactly the Coriolis and centrifugal terms.
    euler_T = sp.Matrix([
        sp.diff(sp.diff(T, qd[i]), t) - sp.diff(T, q[i]) for i in range(3)
    ])
    Cqd = sp.simplify(euler_T - M * sp.Matrix(qdd))

    G = sp.Matrix([sp.simplify(sp.diff(V, q[i])) for i in range(3)])

    return Model(
        cfg=cfg,
        T_sym=T,
        V_sym=V,
        M_sym=M,
        Cqd_sym=Cqd,
        G_sym=G,
        Ffric_sym=_friction(cfg),
        B_sym=sp.Matrix([1, 0, 0]),
    )


# --------------------------------------------------------------------------
# Numeric layer
# --------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / ".derivation_cache"


def _cache_key(cfg: ModelConfig) -> str:
    """Keyed on this file's contents as well as the config, so editing the
    derivation invalidates the cache automatically."""
    src = Path(__file__).read_bytes()
    stamp = f"{cfg.drive}|{cfg.friction}|{cfg.rail_tilt}".encode()
    return hashlib.sha256(src + stamp).hexdigest()[:16]


def _derive_cached(cfg: ModelConfig) -> Model:
    """derive() takes the better part of a minute; lambdify does not. So the
    cache stores the SymPy result, not the compiled functions."""
    path = _CACHE_DIR / f"{_cache_key(cfg)}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())

    model = derive(cfg)
    _CACHE_DIR.mkdir(exist_ok=True)
    path.write_bytes(pickle.dumps(model))
    return model


class NumericModel:
    """Fast numeric evaluation of a derived Model.

    Deliberately plain -- fixed-size arrays, explicit indexing, one linear
    solve -- because this is the layer that gets transcribed to C for the
    STM32. Nothing here should depend on Python-specific behaviour.
    """

    __slots__ = ("model", "_M", "_Cqd", "_G", "_Ffric", "_E")

    def __init__(self, model: Model):
        self.model = model

        # lambdify needs plain symbols, not functions of time.
        pq = sp.symbols("q0 q1 q2", real=True)
        pv = sp.symbols("v0 v1 v2", real=True)
        sub = dict(zip(q, pq)) | dict(zip(qd, pv))

        def plain(expr):
            return sp.Matrix(expr).subs(sub)

        M_p, G_p = plain(model.M_sym), plain(model.G_sym)
        for name, mat in (("M", M_p), ("G", G_p)):
            leaked = set(pv) & mat.free_symbols
            if leaked:
                raise AssertionError(
                    f"{name} depends on velocity {sorted(map(str, leaked))}; "
                    "its lambdified signature takes position only"
                )

        self._M = sp.lambdify((pq, PARAM_SYMS), M_p, "numpy")
        self._G = sp.lambdify((pq, PARAM_SYMS), G_p, "numpy")
        self._Cqd = sp.lambdify((pq, pv, PARAM_SYMS), plain(model.Cqd_sym), "numpy")
        self._Ffric = sp.lambdify((pv, PARAM_SYMS), plain(model.Ffric_sym), "numpy")
        self._E = sp.lambdify((pq, pv, PARAM_SYMS),
                              (model.T_sym + model.V_sym).subs(sub), "numpy")

    def M(self, qv, p: Params) -> np.ndarray:
        return np.asarray(self._M(tuple(qv), p.vector()), dtype=float)

    def Cqd(self, qv, vv, p: Params) -> np.ndarray:
        return np.asarray(self._Cqd(tuple(qv), tuple(vv), p.vector()),
                          dtype=float).reshape(3)

    def G(self, qv, p: Params) -> np.ndarray:
        return np.asarray(self._G(tuple(qv), p.vector()), dtype=float).reshape(3)

    def Ffric(self, vv, p: Params) -> np.ndarray:
        return np.asarray(self._Ffric(tuple(vv), p.vector()),
                          dtype=float).reshape(3)

    def accel(self, s, F: float, p: Params) -> np.ndarray:
        """Solve M qddot = B F - C qdot - G - Ffric for the accelerations."""
        qv, vv = s[0:3], s[3:6]
        rhs = np.array([F, 0.0, 0.0])
        rhs = rhs - self.Cqd(qv, vv, p) - self.G(qv, p) - self.Ffric(vv, p)
        return np.linalg.solve(self.M(qv, p), rhs)

    def deriv(self, s, F: float, p: Params) -> np.ndarray:
        """State derivative, in the fixed ordering: velocities then accelerations."""
        out = np.empty(6)
        out[0:3] = s[3:6]
        out[3:6] = self.accel(s, F, p)
        return out

    def energy(self, s, p: Params) -> float:
        """Total mechanical energy T + V. Conserved exactly when friction is
        zero and no force is applied, which is the sharpest available test of
        the derivation."""
        return float(self._E(tuple(s[0:3]), tuple(s[3:6]), p.vector()))


def build(cfg: ModelConfig = ModelConfig(), use_cache: bool = True) -> NumericModel:
    """Derive (or load) the model and wrap it in fast numeric functions."""
    return NumericModel(_derive_cached(cfg) if use_cache else derive(cfg))
