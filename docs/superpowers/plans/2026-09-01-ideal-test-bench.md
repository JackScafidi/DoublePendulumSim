# Ideal Test Bench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **EXCEPTION — Tasks 2 and 3 are collaborative.** The project owner is deriving the
> equations of motion themselves, with Claude writing the SymPy. Do not dispatch
> those tasks to a subagent and do not run ahead. Present each symbolic stage,
> show its output, and wait for the owner to confirm the physics before continuing.

**Goal:** A double-pendulum-on-a-cart simulator whose correctness is demonstrated by test, not assumed.

**Architecture:** A single frozen parameter object (real-world nominals times dimensionless correction factors) feeds a programmatic SymPy derivation that emits the manipulator-form equations. Those are lambdified into numeric functions, integrated with fixed-step RK4, and verified by four independent physics tests.

**Tech Stack:** Python 3.11+, SymPy (derivation), NumPy (numerics), matplotlib (plots), pytest (tests).

**Spec:** `docs/superpowers/specs/2026-09-01-ideal-test-bench-design.md`

## Global Constraints

- No physical numeric value may appear outside `dpc/params.py`. Every function takes a parameter argument.
- Coordinates: `x` positive right along the rail; `theta_1`, `theta_2` measured from straight **up**, positive counter-clockwise, both **absolute** from world vertical.
- State ordering is fixed: `s = [x, theta_1, theta_2, xdot, theta_1dot, theta_2dot]`. Positions first, then velocities.
- Generalised coordinate ordering is fixed: `q = [x, theta_1, theta_2]`.
- `m_rotor` is an *equivalent* mass (`J / r^2`), not a weighable one. It appears in kinetic energy only. It must **never** appear in the potential energy or in a normal-force term.
- `M`, `C*qdot`, `G` and the friction vector stay separately accessible; they are never fused into one expression.
- Integration is fixed-step RK4 only. No adaptive or symplectic integrator.
- Only the `drive="rigid"` branch is implemented. `drive="compliant"` raises `NotImplementedError`.
- Control-path arithmetic is written for later transcription to C: fixed-size arrays, explicit indexing, no Python-specific constructs.
- Effective parameter ordering is fixed and shared between `params.py` and `model.py`:
  `("m_cart", "m_rotor", "m1", "m2", "l1", "l2", "lc1", "lc2", "I1", "I2", "g", "b_cart", "b1", "b2", "c_cart", "c1", "c2", "eps_fric", "phi")`

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies, pytest configuration |
| `dpc/__init__.py` | Package marker |
| `dpc/params.py` | Nominals, corrections, friction, effective-value assembly |
| `dpc/model.py` | `ModelConfig`, symbolic derivation, lambdified numeric functions, disk cache |
| `dpc/simulate.py` | Fixed-step RK4 and the trajectory container |
| `dpc/linearize.py` | Finite-difference linearisation about an operating point |
| `dpc/viz.py` | Time-series plots |
| `tests/test_params.py` | Parameter assembly |
| `tests/test_kinematics.py` | Centre-of-mass positions and velocities |
| `tests/test_dynamics.py` | Mass matrix, gravity vector, friction vector |
| `tests/test_numeric.py` | Lambdified evaluation, accelerations, energy |
| `tests/test_integrator.py` | RK4 convergence order |
| `tests/test_energy.py` | Conservation under zero friction |
| `tests/test_degenerate.py` | Reduction to known simpler systems |
| `tests/test_linearize.py` | Small-angle agreement |

`dpc/linearize.py` is a deliberate addition to the four modules named in the spec. Linearisation is a self-contained concern with its own test, and folding it into `model.py` would make that file carry two unrelated responsibilities.

---

### Task 1: Project scaffolding and parameters

**Files:**
- Create: `pyproject.toml`, `dpc/__init__.py`, `dpc/params.py`
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `EFFECTIVE_NAMES: tuple[str, ...]`, `Nominal`, `Corrections`, `Friction`, `Params`, `Params.effective() -> dict[str, float]`, `Params.vector() -> tuple[float, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_params.py
import math
import pytest
from dpc.params import EFFECTIVE_NAMES, Corrections, Nominal, Params


def test_defaults_apply_unit_corrections():
    p = Params()
    eff = p.effective()
    assert eff["m1"] == pytest.approx(0.075)
    assert eff["I2"] == pytest.approx(1.5e-4)
    assert eff["g"] == pytest.approx(9.81)


def test_correction_scales_only_its_own_parameter():
    p = Params(corr=Corrections(k_m1=2.0))
    eff = p.effective()
    assert eff["m1"] == pytest.approx(0.150)
    assert eff["m2"] == pytest.approx(0.045)


def test_lengths_and_gravity_have_no_correction():
    assert not hasattr(Corrections(), "k_l1")
    assert not hasattr(Corrections(), "k_g")


def test_friction_is_zero_in_the_ideal_preset():
    eff = Params().effective()
    for name in ("b_cart", "b1", "b2", "c_cart", "c1", "c2", "phi"):
        assert eff[name] == 0.0


def test_vector_matches_the_canonical_ordering():
    p = Params()
    eff = p.effective()
    assert p.vector() == tuple(eff[name] for name in EFFECTIVE_NAMES)
    assert len(EFFECTIVE_NAMES) == 19


def test_params_are_frozen():
    p = Params()
    with pytest.raises(Exception):
        p.phi = 0.5


def test_nominals_are_physically_plausible():
    n = Nominal()
    assert 0 < n.lc1 <= n.l1
    assert 0 < n.lc2 <= n.l2
    assert n.I1 > 0 and n.I2 > 0
    assert math.isclose(n.g, 9.81)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_params.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc'`

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "dpc"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["numpy>=1.26", "sympy>=1.12", "matplotlib>=3.8"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.packages.find]
include = ["dpc*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Write `dpc/params.py`**

```python
"""Every physical constant in the project. Nothing numeric lives outside this file.

Each uncertain quantity is a real-world *nominal* multiplied by a dimensionless
*correction factor* that starts at 1.0. Nominals are owned by the engineer and
come from CAD, datasheets or a scale. Corrections are owned by the parameter
fitter and are what it is allowed to move.
"""

from dataclasses import dataclass, field

# Canonical ordering. Shared with model.py so lambdified functions can take a
# plain tuple. Do not reorder.
EFFECTIVE_NAMES: tuple[str, ...] = (
    "m_cart", "m_rotor", "m1", "m2",
    "l1", "l2", "lc1", "lc2",
    "I1", "I2", "g",
    "b_cart", "b1", "b2",
    "c_cart", "c1", "c2",
    "eps_fric", "phi",
)


@dataclass(frozen=True)
class Nominal:
    """Best real-world estimates, in SI units."""

    m_cart: float = 0.30   # kg, carriage + bracket + belt clamp. Real, weighable mass.
    m_rotor: float = 1.33  # kg, EQUIVALENT mass J/r^2 of the motor rotor seen through
                           # a 20T GT2 pulley. NOT the rotor's weighable mass (~0.28 kg).
                           # It has inertia but no weight: it must never appear in the
                           # potential energy or in a normal-force term.
    m1: float = 0.075      # kg, link 1 rod plus the elbow encoder body
    m2: float = 0.045      # kg, link 2 rod
    l1: float = 0.20       # m, measured with calipers -- no correction factor
    l2: float = 0.20       # m, measured with calipers -- no correction factor
    lc1: float = 0.12      # m, COM of link 1 from the cart joint (biased outward
                           # by the elbow encoder)
    lc2: float = 0.10      # m, COM of link 2 from the elbow
    I1: float = 3.0e-4     # kg m^2, about link 1's own COM
    I2: float = 1.5e-4     # kg m^2, about link 2's own COM
    g: float = 9.81        # m/s^2, known -- no correction factor


@dataclass(frozen=True)
class Corrections:
    """Dimensionless multipliers the fitter is allowed to move. All start at 1.0.

    Lengths and gravity are absent on purpose. Lengths are measurable to a
    fraction of a percent, and a free length would let the fitter trade length
    against mass to explain the same data. A correction on gravity would absorb
    scale errors from everywhere else and make the rest of the fit meaningless.
    """

    k_m_cart: float = 1.0
    k_m_rotor: float = 1.0
    k_m1: float = 1.0
    k_m2: float = 1.0
    k_lc1: float = 1.0
    k_lc2: float = 1.0
    k_I1: float = 1.0
    k_I2: float = 1.0


@dataclass(frozen=True)
class Friction:
    """Fitted as absolute values, not multipliers: their nominal is zero, and
    zero times any correction stays zero."""

    b_cart: float = 0.0    # N s/m, viscous along the rail
    b1: float = 0.0        # N m s, viscous at the cart joint
    b2: float = 0.0        # N m s, viscous at the elbow
    c_cart: float = 0.0    # N, Coulomb along the rail
    c1: float = 0.0        # N m, Coulomb at the cart joint
    c2: float = 0.0        # N m, Coulomb at the elbow
    eps_fric: float = 1e-3 # smoothing width; Coulomb uses tanh(v/eps) so the
                           # model stays differentiable for linearisation and
                           # gradient-based fitting


@dataclass(frozen=True)
class Params:
    nominal: Nominal = field(default_factory=Nominal)
    corr: Corrections = field(default_factory=Corrections)
    fric: Friction = field(default_factory=Friction)
    phi: float = 0.0       # rad, rail tilt from horizontal

    def effective(self) -> dict[str, float]:
        """Nominal times correction, plus the directly-fitted quantities."""
        n, c, f = self.nominal, self.corr, self.fric
        return {
            "m_cart": n.m_cart * c.k_m_cart,
            "m_rotor": n.m_rotor * c.k_m_rotor,
            "m1": n.m1 * c.k_m1,
            "m2": n.m2 * c.k_m2,
            "l1": n.l1,
            "l2": n.l2,
            "lc1": n.lc1 * c.k_lc1,
            "lc2": n.lc2 * c.k_lc2,
            "I1": n.I1 * c.k_I1,
            "I2": n.I2 * c.k_I2,
            "g": n.g,
            "b_cart": f.b_cart,
            "b1": f.b1,
            "b2": f.b2,
            "c_cart": f.c_cart,
            "c1": f.c1,
            "c2": f.c2,
            "eps_fric": f.eps_fric,
            "phi": self.phi,
        }

    def vector(self) -> tuple[float, ...]:
        """Effective values in EFFECTIVE_NAMES order, for lambdified functions."""
        eff = self.effective()
        return tuple(eff[name] for name in EFFECTIVE_NAMES)
```

- [ ] **Step 5: Create `dpc/__init__.py`**

```python
"""Double pendulum on a cart: simulation and control."""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pip install -e ".[dev]"` then `pytest tests/test_params.py -v`
Expected: 7 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml dpc/ tests/test_params.py
git commit -m "feat: parameter model with nominal times correction structure"
```

---

### Task 2: Symbolic kinematics — COLLABORATIVE

**Do not execute this task autonomously.** Present each stage below, show the
resulting expression, and wait for the owner to confirm it before proceeding.

**Files:**
- Create: `dpc/model.py` (kinematics section only)
- Test: `tests/test_kinematics.py`

**Interfaces:**
- Consumes: `EFFECTIVE_NAMES` from `dpc.params`.
- Produces: `ModelConfig`, and inside `model.py` the module-level symbols `t`, `q`, `qd`, `qdd`, `PARAM_SYMS`, plus `_kinematics(cfg) -> dict` returning keys `p_cart`, `p_c1`, `p_elbow`, `p_c2`, `v_cart`, `v_c1`, `v_c2`.

- [ ] **Step 1: Write the failing test**

Geometry facts this pins down, all checkable by hand:
with the rail level and both links upright, the elbow sits at height `l1` and
link 2's COM at `l1 + lc2`; laying link 1 flat to the right puts the elbow at
`x + l1` horizontally.

```python
# tests/test_kinematics.py
import sympy as sp
from dpc.model import ModelConfig, _kinematics, q


def _at(expr, x=0.0, th1=0.0, th2=0.0, l1=0.20, l2=0.20, lc1=0.12, lc2=0.10, phi=0.0):
    import dpc.model as m
    subs = {q[0]: x, q[1]: th1, q[2]: th2,
            m.S["l1"]: l1, m.S["l2"]: l2, m.S["lc1"]: lc1,
            m.S["lc2"]: lc2, m.S["phi"]: phi}
    return sp.Matrix(expr).subs(subs).evalf()


def test_upright_puts_elbow_directly_above_the_cart():
    k = _kinematics(ModelConfig())
    p = _at(k["p_elbow"], x=0.3, th1=0.0, th2=0.0)
    assert float(p[0]) == 0.3
    assert float(p[1]) == 0.20


def test_upright_stacks_link2_com_above_the_elbow():
    k = _kinematics(ModelConfig())
    p = _at(k["p_c2"], th1=0.0, th2=0.0)
    assert float(p[1]) == 0.30          # l1 + lc2


def test_link1_laid_flat_extends_horizontally():
    k = _kinematics(ModelConfig())
    p = _at(k["p_elbow"], x=0.0, th1=sp.pi / 2)
    assert abs(float(p[0]) - 0.20) < 1e-12
    assert abs(float(p[1])) < 1e-12


def test_hanging_link1_com_is_below_the_cart():
    k = _kinematics(ModelConfig())
    p = _at(k["p_c1"], th1=sp.pi)
    assert abs(float(p[1]) + 0.12) < 1e-12


def test_rail_tilt_raises_the_cart_as_it_advances():
    k = _kinematics(ModelConfig())
    p = _at(k["p_cart"], x=1.0, phi=sp.pi / 6)
    assert abs(float(p[1]) - 0.5) < 1e-12


def test_link2_angle_is_absolute_not_relative():
    """theta_2 = 0 means link 2 is vertical regardless of theta_1."""
    k = _kinematics(ModelConfig())
    a = _at(k["p_c2"], th1=0.0, th2=0.0)
    b = _at(k["p_c2"], th1=sp.pi / 2, th2=0.0)
    assert abs(float(a[1]) - float(b[1]) - 0.20) < 1e-12  # elbow dropped by l1


def test_velocities_are_time_derivatives_of_positions():
    k = _kinematics(ModelConfig())
    import dpc.model as m
    for pos, vel in (("p_cart", "v_cart"), ("p_c1", "v_c1"), ("p_c2", "v_c2")):
        expected = sp.Matrix(k[pos]).diff(m.t)
        assert sp.simplify(sp.Matrix(k[vel]) - expected) == sp.zeros(2, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_kinematics.py -v`
Expected: FAIL with `ImportError: cannot import name 'ModelConfig' from 'dpc.model'`

- [ ] **Step 3: Write the kinematics section of `dpc/model.py`**

Present this to the owner stage by stage before writing it: first the symbols
and the config, then the cart position on a tilted rail, then each COM, then the
velocities.

```python
"""Programmatic derivation of the equations of motion.

The model is described by a ModelConfig; derive() assembles the Lagrangian from
that description. Re-deriving after a model change is a function call, so the
equations never need re-deriving by hand.
"""

from dataclasses import dataclass
from typing import Literal

import sympy as sp

from dpc.params import EFFECTIVE_NAMES


@dataclass(frozen=True)
class ModelConfig:
    drive: Literal["rigid", "compliant"] = "rigid"
    friction: Literal["viscous", "viscous+coulomb"] = "viscous+coulomb"
    rail_tilt: bool = True


t = sp.Symbol("t", real=True)

# Generalised coordinates as functions of time, so sp.diff(expr, t) is exact.
x = sp.Function("x")(t)
th1 = sp.Function("theta1")(t)
th2 = sp.Function("theta2")(t)
q = (x, th1, th2)
qd = tuple(sp.diff(c, t) for c in q)
qdd = tuple(sp.diff(c, t, 2) for c in q)

# One symbol per effective parameter, in the canonical order.
S: dict[str, sp.Symbol] = {
    name: sp.Symbol(name, real=True, positive=name in {"m_cart", "m_rotor", "m1",
                                                       "m2", "l1", "l2", "g",
                                                       "eps_fric"})
    for name in EFFECTIVE_NAMES
}
PARAM_SYMS: tuple[sp.Symbol, ...] = tuple(S[name] for name in EFFECTIVE_NAMES)


def _kinematics(cfg: ModelConfig) -> dict:
    """Positions and velocities of every mass, in world coordinates.

    Angles are absolute from world vertical with zero pointing up, so a link at
    angle th has its far end offset by (l*sin(th), l*cos(th)). The rail may be
    tilted by phi, so the cart advances along (cos(phi), sin(phi)).
    """
    phi = S["phi"] if cfg.rail_tilt else sp.Integer(0)

    rail = sp.Matrix([sp.cos(phi), sp.sin(phi)])
    p_cart = x * rail

    d1 = sp.Matrix([sp.sin(th1), sp.cos(th1)])   # unit vector along link 1
    d2 = sp.Matrix([sp.sin(th2), sp.cos(th2)])   # unit vector along link 2

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_kinematics.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add dpc/model.py tests/test_kinematics.py
git commit -m "feat: symbolic kinematics for the cart and both links"
```

---

### Task 3: Lagrangian and equations of motion — COLLABORATIVE

**Do not execute this task autonomously.** Same rule as Task 2: present the
kinetic energy, the potential energy, the friction forces and the Euler-Lagrange
result in turn, and wait for confirmation at each stage.

**Files:**
- Modify: `dpc/model.py` (append)
- Test: `tests/test_dynamics.py`

**Interfaces:**
- Consumes: `_kinematics`, `S`, `q`, `qd`, `qdd`, `PARAM_SYMS`.
- Produces: `Model` dataclass with symbolic fields `M_sym` (3x3), `Cqd_sym` (3x1), `G_sym` (3x1), `Ffric_sym` (3x1), `T_sym`, `V_sym`, `B_sym` (3x1); and `derive(cfg) -> Model`.

Three physics points to state explicitly while deriving, because each is a
place a plausible-looking mistake hides:

1. `m_rotor` enters the kinetic energy and **nothing else**. It has inertia but
   no weight, so it is absent from `V`.
2. With absolute angles, elbow friction acts on the **relative** rate
   `th2dot - th1dot`, and by Newton's third law it appears with opposite signs
   in rows 2 and 3.
3. `M` is the Hessian of `T` with respect to `qdot`; the Coriolis and
   centrifugal terms are whatever is left of the Euler-Lagrange kinetic part
   after `M*qddot` is removed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dynamics.py
import sympy as sp
from dpc.model import ModelConfig, S, derive


def test_mass_matrix_is_symmetric():
    m = derive(ModelConfig())
    assert sp.simplify(m.M_sym - m.M_sym.T) == sp.zeros(3, 3)


def test_cart_inertia_includes_the_rotor():
    """M[0,0] is the total translating inertia, and is angle-independent:
    every mass shares the cart's horizontal velocity."""
    m = derive(ModelConfig())
    got = sp.simplify(m.M_sym[0, 0])
    want = S["m_cart"] + S["m_rotor"] + S["m1"] + S["m2"]
    assert sp.simplify(got - want) == 0


def test_rotor_has_no_weight():
    """m_rotor is an equivalent mass, so it must not appear in gravity."""
    m = derive(ModelConfig())
    assert S["m_rotor"] not in m.V_sym.free_symbols
    assert S["m_rotor"] not in m.G_sym.free_symbols


def test_gravity_vanishes_for_the_cart_on_a_level_rail():
    m = derive(ModelConfig())
    assert sp.simplify(m.G_sym[0].subs(S["phi"], 0)) == 0


def test_gravity_on_a_tilted_rail_uses_real_mass_only():
    """Advancing by x raises the cart by x*sin(phi), so the downhill term
    carries sin(phi) -- and m_rotor is absent because it has no weight."""
    m = derive(ModelConfig())
    got = sp.simplify(m.G_sym[0])
    want = (S["m_cart"] + S["m1"] + S["m2"]) * S["g"] * sp.sin(S["phi"])
    assert sp.simplify(got - want) == 0


def test_upright_is_an_equilibrium():
    """At zero angles on a level rail, the angular gravity terms vanish."""
    m = derive(ModelConfig())
    from dpc.model import th1, th2
    sub = {th1: 0, th2: 0, S["phi"]: 0}
    assert sp.simplify(m.G_sym[1].subs(sub)) == 0
    assert sp.simplify(m.G_sym[2].subs(sub)) == 0


def test_hanging_gravity_torque_has_restoring_sign():
    """Hanging is theta = pi. Displaced to just under pi, gravity must drive
    theta back up toward pi.

    G sits on the left-hand side of M*qddot + ... + G = B*u, so the induced
    acceleration is -M^-1 G. Driving theta upward therefore requires G[1] < 0.
    """
    m = derive(ModelConfig())
    from dpc.model import th1, th2
    sub = {th1: sp.pi - sp.Rational(1, 10), th2: sp.pi - sp.Rational(1, 10),
           S["phi"]: 0, S["m1"]: 1, S["m2"]: 1, S["lc1"]: 1, S["lc2"]: 1,
           S["l1"]: 1, S["g"]: 1}
    assert float(m.G_sym[1].subs(sub).evalf()) < 0


def test_elbow_friction_is_equal_and_opposite():
    m = derive(ModelConfig())
    pair = sp.simplify(m.Ffric_sym[1] + m.Ffric_sym[2])
    assert S["b2"] not in pair.free_symbols
    assert S["c2"] not in pair.free_symbols


def test_friction_vanishes_when_all_coefficients_are_zero():
    m = derive(ModelConfig())
    zero = {S[k]: 0 for k in ("b_cart", "b1", "b2", "c_cart", "c1", "c2")}
    assert sp.simplify(m.Ffric_sym.subs(zero)) == sp.zeros(3, 1)


def test_input_matrix_drives_the_cart_only():
    m = derive(ModelConfig())
    assert list(m.B_sym) == [1, 0, 0]


def test_compliant_drive_is_not_implemented():
    import pytest
    with pytest.raises(NotImplementedError):
        derive(ModelConfig(drive="compliant"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dynamics.py -v`
Expected: FAIL with `ImportError: cannot import name 'derive' from 'dpc.model'`

- [ ] **Step 3: Append the dynamics section to `dpc/model.py`**

```python
@dataclass(frozen=True)
class Model:
    cfg: ModelConfig
    T_sym: sp.Expr
    V_sym: sp.Expr
    M_sym: sp.Matrix
    Cqd_sym: sp.Matrix
    G_sym: sp.Matrix
    Ffric_sym: sp.Matrix
    B_sym: sp.Matrix


def _kinetic_energy(k: dict) -> sp.Expr:
    """Translational energy of every mass plus rotational energy of both links.

    m_rotor appears here and nowhere else: the belt ties rotor angle to cart
    position by x = r*theta_m, so (1/2) J theta_m_dot^2 becomes
    (1/2) (J/r^2) xdot^2, which is indistinguishable from translating mass.
    """
    v_cart, v_c1, v_c2 = k["v_cart"], k["v_c1"], k["v_c2"]
    w1, w2 = sp.diff(th1, t), sp.diff(th2, t)
    return sp.Rational(1, 2) * (
        (S["m_cart"] + S["m_rotor"]) * v_cart.dot(v_cart)
        + S["m1"] * v_c1.dot(v_c1) + S["I1"] * w1 ** 2
        + S["m2"] * v_c2.dot(v_c2) + S["I2"] * w2 ** 2
    )


def _potential_energy(k: dict) -> sp.Expr:
    """Gravity acting on real mass only. m_rotor is deliberately absent."""
    return S["g"] * (
        S["m_cart"] * k["p_cart"][1]
        + S["m1"] * k["p_c1"][1]
        + S["m2"] * k["p_c2"][1]
    )


def _friction(cfg: ModelConfig) -> sp.Matrix:
    """Generalised friction forces, written as they appear on the LHS.

    The elbow resists the RELATIVE rate th2dot - th1dot, because theta_2 is
    measured from vertical rather than from link 1. The reaction appears with
    the opposite sign on link 1.
    """
    xd, w1, w2 = qd
    rel = w2 - w1
    eps = S["eps_fric"]

    def coulomb(c, v):
        if cfg.friction == "viscous":
            return sp.Integer(0)
        return c * sp.tanh(v / eps)   # smooth, so linearisation still works

    f_cart = S["b_cart"] * xd + coulomb(S["c_cart"], xd)
    f_1 = S["b1"] * w1 + coulomb(S["c1"], w1)
    f_2 = S["b2"] * rel + coulomb(S["c2"], rel)

    return sp.Matrix([f_cart, f_1 - f_2, f_2])


def derive(cfg: ModelConfig = ModelConfig()) -> Model:
    """Assemble the Lagrangian from cfg and produce the manipulator form

        M(q) qddot + C(q, qdot) qdot + G(q) + Ffric(qdot) = B u
    """
    if cfg.drive != "rigid":
        raise NotImplementedError(
            f"drive={cfg.drive!r} is a planned seam, not an implementation"
        )

    k = _kinematics(cfg)
    T = _kinetic_energy(k)
    V = _potential_energy(k)

    # M is the Hessian of T with respect to the generalised velocities.
    M = sp.Matrix(3, 3, lambda i, j: sp.simplify(sp.diff(T, qd[i], qd[j])))

    # Euler-Lagrange on the kinetic part alone, minus M*qddot, leaves exactly
    # the Coriolis and centrifugal terms.
    euler_T = sp.Matrix([sp.diff(sp.diff(T, qd[i]), t) - sp.diff(T, q[i])
                         for i in range(3)])
    Cqd = sp.simplify(euler_T - M * sp.Matrix(qdd))

    G = sp.Matrix([sp.simplify(sp.diff(V, q[i])) for i in range(3)])

    return Model(
        cfg=cfg, T_sym=T, V_sym=V, M_sym=M, Cqd_sym=Cqd, G_sym=G,
        Ffric_sym=_friction(cfg), B_sym=sp.Matrix([1, 0, 0]),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dynamics.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add dpc/model.py tests/test_dynamics.py
git commit -m "feat: Lagrangian derivation of the equations of motion"
```

---

### Task 4: Numeric layer with disk cache

**Files:**
- Modify: `dpc/model.py` (append)
- Test: `tests/test_numeric.py`

**Interfaces:**
- Consumes: `Model`, `derive`, `PARAM_SYMS`.
- Produces: `NumericModel` with methods `M(q, p)`, `Cqd(q, qd, p)`, `G(q, p)`, `Ffric(qd, p)`, `accel(s, F, p) -> np.ndarray(3)`, `deriv(s, F, p) -> np.ndarray(6)`, `energy(s, p) -> float`; and `build(cfg, use_cache=True) -> NumericModel`. All take `p: Params`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_numeric.py
import numpy as np
import pytest
from dpc.model import ModelConfig, build
from dpc.params import Params

M = build(ModelConfig())
P = Params()


def test_mass_matrix_is_symmetric_positive_definite():
    A = M.M(np.array([0.1, 0.3, -0.2]), P)
    assert np.allclose(A, A.T)
    assert np.all(np.linalg.eigvals(A) > 0)


def test_at_rest_upright_no_force_the_system_barely_moves():
    s = np.zeros(6)
    assert np.allclose(M.accel(s, 0.0, P), 0.0, atol=1e-12)


def test_a_push_accelerates_the_cart_forward():
    s = np.zeros(6)
    assert M.accel(s, 1.0, P)[0] > 0


def test_hanging_at_rest_is_an_equilibrium():
    s = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    assert np.allclose(M.accel(s, 0.0, P), 0.0, atol=1e-9)


def test_upright_is_unstable_and_hanging_is_stable():
    """Same sign of displacement, opposite response.

    Upright is theta = 0: nudged to +0.05 the links tip further positive.
    Hanging is theta = pi: nudged to pi + 0.05 they swing back down toward pi,
    which is the negative direction.
    """
    up = np.array([0.0, 0.05, 0.05, 0.0, 0.0, 0.0])
    down = np.array([0.0, np.pi + 0.05, np.pi + 0.05, 0.0, 0.0, 0.0])
    assert M.accel(up, 0.0, P)[1] > 0     # tips further over
    assert M.accel(down, 0.0, P)[1] < 0   # swings back


def test_deriv_stacks_velocity_then_acceleration():
    s = np.array([0.0, 0.2, -0.1, 1.5, 0.3, -0.4])
    d = M.deriv(s, 0.0, P)
    assert np.allclose(d[:3], s[3:])
    assert np.allclose(d[3:], M.accel(s, 0.0, P))


def test_energy_is_higher_upright_than_hanging():
    up = np.zeros(6)
    down = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    assert M.energy(up, P) > M.energy(down, P)


def test_energy_grows_with_speed():
    slow = np.array([0.0, 0.0, 0.0, 0.1, 0.0, 0.0])
    fast = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    assert M.energy(fast, P) > M.energy(slow, P)


def test_cache_reuse_gives_identical_numbers():
    again = build(ModelConfig())
    s = np.array([0.1, 0.4, -0.3, 0.2, 0.1, -0.5])
    assert np.allclose(again.accel(s, 0.7, P), M.accel(s, 0.7, P))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_numeric.py -v`
Expected: FAIL with `ImportError: cannot import name 'build' from 'dpc.model'`

- [ ] **Step 3: Append the numeric layer to `dpc/model.py`**

The symbolic derivation is the slow part, so the cache stores the SymPy
matrices, keyed by the config and a hash of this source file. Lambdifying the
cached expressions is fast.

```python
import hashlib
import pickle
from pathlib import Path

import numpy as np

from dpc.params import Params

_CACHE_DIR = Path(__file__).parent / ".derivation_cache"


def _cache_key(cfg: ModelConfig) -> str:
    src = Path(__file__).read_bytes()
    stamp = f"{cfg.drive}|{cfg.friction}|{cfg.rail_tilt}".encode()
    return hashlib.sha256(src + stamp).hexdigest()[:16]


def _derive_cached(cfg: ModelConfig) -> Model:
    path = _CACHE_DIR / f"{_cache_key(cfg)}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    model = derive(cfg)
    _CACHE_DIR.mkdir(exist_ok=True)
    path.write_bytes(pickle.dumps(model))
    return model


class NumericModel:
    """Fast numeric evaluation of a derived Model.

    Kept deliberately plain -- fixed-size arrays, explicit indexing, no Python
    cleverness -- because this is the layer that gets transcribed to C.
    """

    def __init__(self, model: Model):
        self.model = model
        # Functions-of-time must become plain symbols before lambdify.
        plain_q = sp.symbols("q0 q1 q2", real=True)
        plain_qd = sp.symbols("v0 v1 v2", real=True)
        sub = dict(zip(q, plain_q)) | dict(zip(qd, plain_qd))
        args_q = (plain_q, PARAM_SYMS)
        args_all = (plain_q, plain_qd, PARAM_SYMS)

        def L(expr, args):
            return sp.lambdify(args, sp.Matrix(expr).subs(sub), "numpy")

        self._M = L(model.M_sym, args_q)
        self._Cqd = L(model.Cqd_sym, args_all)
        self._G = L(model.G_sym, args_q)
        self._Ffric = L(model.Ffric_sym, (plain_qd, PARAM_SYMS))
        self._E = sp.lambdify(args_all,
                              (model.T_sym + model.V_sym).subs(sub), "numpy")

    def M(self, qv, p: Params) -> np.ndarray:
        return np.asarray(self._M(tuple(qv), p.vector()), dtype=float)

    def Cqd(self, qv, qdv, p: Params) -> np.ndarray:
        return np.asarray(self._Cqd(tuple(qv), tuple(qdv), p.vector()),
                          dtype=float).reshape(3)

    def G(self, qv, p: Params) -> np.ndarray:
        return np.asarray(self._G(tuple(qv), p.vector()), dtype=float).reshape(3)

    def Ffric(self, qdv, p: Params) -> np.ndarray:
        return np.asarray(self._Ffric(tuple(qdv), p.vector()),
                          dtype=float).reshape(3)

    def accel(self, s, F: float, p: Params) -> np.ndarray:
        qv, qdv = s[0:3], s[3:6]
        rhs = np.array([F, 0.0, 0.0])
        rhs = rhs - self.Cqd(qv, qdv, p) - self.G(qv, p) - self.Ffric(qdv, p)
        return np.linalg.solve(self.M(qv, p), rhs)

    def deriv(self, s, F: float, p: Params) -> np.ndarray:
        out = np.empty(6)
        out[0:3] = s[3:6]
        out[3:6] = self.accel(s, F, p)
        return out

    def energy(self, s, p: Params) -> float:
        return float(self._E(tuple(s[0:3]), tuple(s[3:6]), p.vector()))


def build(cfg: ModelConfig = ModelConfig(), use_cache: bool = True) -> NumericModel:
    return NumericModel(_derive_cached(cfg) if use_cache else derive(cfg))
```

- [ ] **Step 4: Ignore the cache directory**

Append to `.gitignore`:

```
# Cached symbolic derivation
dpc/.derivation_cache/
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_numeric.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add dpc/model.py tests/test_numeric.py .gitignore
git commit -m "feat: lambdified numeric layer with cached derivation"
```

---

### Task 5: Fixed-step RK4 and convergence

**Files:**
- Create: `dpc/simulate.py`
- Test: `tests/test_integrator.py`

**Interfaces:**
- Consumes: `NumericModel.deriv`, `Params`.
- Produces: `Trajectory` (fields `t`, `s`, `F`), `rk4_step(model, s, F, dt, p) -> np.ndarray(6)`, `simulate(model, s0, force, t_end, dt, p) -> Trajectory`. `force` is `Callable[[float, np.ndarray], float]` taking `(time, state)`.

- [ ] **Step 1: Write the failing test**

Richardson extrapolation is what replaces a second integrator: halving `dt`
should cut RK4's error by about 16, so the measured order should be near 4.

```python
# tests/test_integrator.py
import numpy as np
from dpc.model import ModelConfig, build
from dpc.params import Params
from dpc.simulate import simulate

M = build(ModelConfig())
P = Params()
S0 = np.array([0.0, 2.5, 2.7, 0.0, 0.0, 0.0])


def _final(dt):
    return simulate(M, S0, lambda t, s: 0.0, t_end=1.0, dt=dt, p=P).s[-1]


def test_trajectory_shapes_line_up():
    tr = simulate(M, S0, lambda t, s: 0.0, t_end=1.0, dt=1e-3, p=P)
    assert tr.s.shape == (tr.t.size, 6)
    assert tr.F.shape == (tr.t.size,)
    assert np.allclose(tr.s[0], S0)


def test_initial_state_is_not_mutated():
    before = S0.copy()
    simulate(M, S0, lambda t, s: 0.0, t_end=0.1, dt=1e-3, p=P)
    assert np.array_equal(S0, before)


def test_force_callback_receives_time_and_state():
    seen = []
    simulate(M, S0, lambda t, s: seen.append((t, s.copy())) or 0.0,
             t_end=0.01, dt=1e-3, p=P)
    assert seen[0][0] == 0.0
    assert len(seen[0][1]) == 6


def test_rk4_converges_at_fourth_order():
    coarse, mid, fine = _final(4e-3), _final(2e-3), _final(1e-3)
    e_coarse = np.linalg.norm(coarse - fine)
    e_mid = np.linalg.norm(mid - fine)
    order = np.log2(e_coarse / e_mid)
    assert 3.5 < order < 4.5, f"observed order {order}"


def test_zero_force_from_rest_upright_stays_put():
    tr = simulate(M, np.zeros(6), lambda t, s: 0.0, t_end=2.0, dt=1e-3, p=P)
    assert np.allclose(tr.s[-1], 0.0, atol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.simulate'`

- [ ] **Step 3: Write `dpc/simulate.py`**

```python
"""Fixed-step RK4 integration.

Fixed step on purpose: it is what a real controller does, and what the STM32
will do. An adaptive integrator would take steps the target cannot take, hiding
a discrepancy that would only surface on hardware.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

from dpc.model import NumericModel
from dpc.params import Params

ForceFn = Callable[[float, np.ndarray], float]


@dataclass(frozen=True)
class Trajectory:
    t: np.ndarray   # (n,)
    s: np.ndarray   # (n, 6)
    F: np.ndarray   # (n,) force applied over each step


def rk4_step(model: NumericModel, s: np.ndarray, F: float, dt: float,
             p: Params) -> np.ndarray:
    """One classical RK4 step at constant force, as a zero-order hold."""
    k1 = model.deriv(s, F, p)
    k2 = model.deriv(s + 0.5 * dt * k1, F, p)
    k3 = model.deriv(s + 0.5 * dt * k2, F, p)
    k4 = model.deriv(s + dt * k3, F, p)
    return s + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def simulate(model: NumericModel, s0: np.ndarray, force: ForceFn,
             t_end: float, dt: float, p: Params) -> Trajectory:
    """Integrate from s0 to t_end. Force is held constant across each step,
    matching a controller running at 1/dt."""
    n = int(round(t_end / dt))
    t = np.linspace(0.0, n * dt, n + 1)
    s = np.empty((n + 1, 6))
    F = np.empty(n + 1)
    s[0] = np.asarray(s0, dtype=float)

    for i in range(n):
        F[i] = force(t[i], s[i])
        s[i + 1] = rk4_step(model, s[i], F[i], dt, p)
    F[n] = force(t[n], s[n])

    return Trajectory(t=t, s=s, F=F)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_integrator.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add dpc/simulate.py tests/test_integrator.py
git commit -m "feat: fixed-step RK4 integrator"
```

---

### Task 6: Energy conservation and degenerate cases

**Files:**
- Test: `tests/test_energy.py`, `tests/test_degenerate.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5. Produces no new source.

These two tests are the substance of the milestone. Energy conservation says
*something* is wrong; the degenerate cases say *which term*.

- [ ] **Step 1: Write the energy test**

```python
# tests/test_energy.py
import numpy as np
import pytest
from dpc.model import ModelConfig, build
from dpc.params import Friction, Params
from dpc.simulate import simulate

M = build(ModelConfig())
IDEAL = Params()                     # all friction already zero
DAMPED = Params(fric=Friction(b1=0.02, b2=0.02, b_cart=0.5))


def _energy_series(p, s0, dt=5e-4, t_end=6.0):
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=t_end, dt=dt, p=p)
    return np.array([M.energy(s, p) for s in tr.s])


@pytest.mark.parametrize("s0", [
    np.array([0.0, 3.0, 3.1, 0.0, 0.0, 0.0]),      # near hanging
    np.array([0.0, 0.4, -0.6, 0.0, 0.0, 0.0]),     # released near upright
    np.array([0.1, 1.2, -2.0, 0.5, 1.0, -1.5]),    # violent, chaotic
])
def test_energy_is_conserved_without_friction_or_force(s0):
    e = _energy_series(IDEAL, s0)
    drift = abs(e - e[0]).max() / max(abs(e[0]), 1e-12)
    assert drift < 1e-6, f"relative energy drift {drift:.2e}"


def test_energy_drift_shrinks_with_a_smaller_step():
    s0 = np.array([0.1, 1.2, -2.0, 0.5, 1.0, -1.5])
    coarse = _energy_series(IDEAL, s0, dt=2e-3, t_end=3.0)
    fine = _energy_series(IDEAL, s0, dt=1e-3, t_end=3.0)
    d_coarse = abs(coarse - coarse[0]).max()
    d_fine = abs(fine - fine[0]).max()
    assert d_fine < d_coarse


def test_friction_removes_energy_monotonically():
    s0 = np.array([0.0, 2.0, 2.2, 0.0, 0.0, 0.0])
    e = _energy_series(DAMPED, s0, dt=1e-3, t_end=4.0)
    assert e[-1] < e[0]
    assert np.all(np.diff(e) < 1e-9)


def test_tilted_rail_still_conserves_energy():
    p = Params(phi=0.05)
    e = _energy_series(p, np.array([0.0, 2.0, 2.2, 0.0, 0.0, 0.0]), t_end=3.0)
    drift = abs(e - e[0]).max() / abs(e[0])
    assert drift < 1e-6
```

- [ ] **Step 2: Write the degenerate-case test**

```python
# tests/test_degenerate.py
import numpy as np
from dpc.model import ModelConfig, build
from dpc.params import Corrections, Params
from dpc.simulate import simulate

M = build(ModelConfig())


def _fixed_pivot_double_pendulum_reference(s0, p, t_end, dt):
    """Independent RK4 of a double pendulum with an immovable pivot.

    Written from the textbook equations rather than reusing dpc.model, so it is
    a genuine cross-check rather than a restatement.
    """
    e = p.effective()
    m1, m2 = e["m1"], e["m2"]
    l1, lc1, lc2 = e["l1"], e["lc1"], e["lc2"]
    I1, I2, g = e["I1"], e["I2"], e["g"]

    a = I1 + m1 * lc1 ** 2 + m2 * l1 ** 2
    b = m2 * l1 * lc2
    c = I2 + m2 * lc2 ** 2

    def deriv(y):
        # Euler-Lagrange for the fixed-pivot pair, angles measured from up.
        #   row 1:  a*a1dd + b*cos(D)*a2dd + b*sin(D)*w2^2 = +(m1 lc1 + m2 l1) g sin(th1)
        #   row 2:  c*a2dd + b*cos(D)*a1dd - b*sin(D)*w1^2 = + m2 lc2 g sin(th2)
        # with D = th1 - th2. Written below using d = th2 - th1, so sin flips sign.
        th1, th2, w1, w2 = y
        d = th2 - th1
        Mm = np.array([[a, b * np.cos(d)], [b * np.cos(d), c]])
        rhs = np.array([
            b * np.sin(d) * w2 ** 2 + (m1 * lc1 + m2 * l1) * g * np.sin(th1),
            -b * np.sin(d) * w1 ** 2 + m2 * lc2 * g * np.sin(th2),
        ])
        acc = np.linalg.solve(Mm, rhs)
        return np.array([w1, w2, acc[0], acc[1]])

    y = np.array([s0[1], s0[2], s0[4], s0[5]])
    for _ in range(int(round(t_end / dt))):
        k1 = deriv(y)
        k2 = deriv(y + 0.5 * dt * k1)
        k3 = deriv(y + 0.5 * dt * k2)
        k4 = deriv(y + dt * k3)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return y


def test_a_heavy_cart_reproduces_a_fixed_pivot_double_pendulum():
    """k_m_cart = 1e4 makes the pivot effectively immovable while keeping the
    mass matrix well conditioned. Pushing to 1e7 would make M span 17 orders of
    magnitude and destroy the solve, so the tolerance is set to match 1e4."""
    p = Params(corr=Corrections(k_m_cart=1e4))
    s0 = np.array([0.0, 2.6, 2.9, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=2.0, dt=2e-4, p=p)
    ref = _fixed_pivot_double_pendulum_reference(s0, p, 2.0, 2e-4)
    assert abs(tr.s[-1][1] - ref[0]) < 1e-3
    assert abs(tr.s[-1][2] - ref[1]) < 1e-3


def test_cart_recoils_opposite_to_a_falling_pendulum():
    """Nothing pushes the system horizontally, so the momentum conjugate to x
    is conserved: the cart must move opposite to the falling links."""
    s0 = np.array([0.0, 0.2, 0.2, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=0.3, dt=1e-4, p=Params())
    assert tr.s[-1][0] < 0        # links fall to +x, so the cart goes to -x


def test_momentum_conjugate_to_x_is_conserved_on_a_level_rail():
    """On a level rail the potential energy does not depend on x, so by
    Noether's theorem dL/dxdot is exactly conserved. m_rotor belongs in this
    sum: the belt constraint makes rotor spin part of the x momentum."""
    p = Params()
    e = p.effective()
    s0 = np.array([0.0, 0.5, -0.3, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=1.0, dt=2e-4, p=p)

    def px(s):
        x, th1, th2, xd, w1, w2 = s
        v_cart = xd
        v_c1 = xd + e["lc1"] * np.cos(th1) * w1
        v_c2 = xd + e["l1"] * np.cos(th1) * w1 + e["lc2"] * np.cos(th2) * w2
        return ((e["m_cart"] + e["m_rotor"]) * v_cart
                + e["m1"] * v_c1 + e["m2"] * v_c2)

    assert abs(px(tr.s[-1]) - px(tr.s[0])) < 1e-8
```

- [ ] **Step 3: Run both suites**

Run: `pytest tests/test_energy.py tests/test_degenerate.py -v`
Expected: all pass. If energy drifts, suspect the derivation before the
integrator — check the momentum test, which localises the error to the mass
matrix.

- [ ] **Step 4: Commit**

```bash
git add tests/test_energy.py tests/test_degenerate.py
git commit -m "test: energy conservation and reduction to known systems"
```

---

### Task 7: Linearisation about an operating point

**Files:**
- Create: `dpc/linearize.py`
- Test: `tests/test_linearize.py`

**Interfaces:**
- Consumes: `NumericModel.deriv`, `Params`.
- Produces: `linearize(model, s0, F0, p, eps=1e-6) -> tuple[np.ndarray, np.ndarray]` returning `A` (6x6) and `B` (6x1).

Central differences rather than symbolic Jacobians: it is a dozen lines,
immune to algebra mistakes, and it is what the eventual C code would do.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_linearize.py
import numpy as np
from dpc.linearize import linearize
from dpc.model import ModelConfig, build
from dpc.params import Params
from dpc.simulate import simulate

M = build(ModelConfig())
P = Params()
UP = np.zeros(6)


def test_shapes_and_kinematic_block():
    A, B = linearize(M, UP, 0.0, P)
    assert A.shape == (6, 6) and B.shape == (6, 1)
    assert np.allclose(A[0:3, 0:3], 0.0, atol=1e-6)
    assert np.allclose(A[0:3, 3:6], np.eye(3), atol=1e-6)
    assert np.allclose(B[0:3, 0], 0.0, atol=1e-6)


def test_upright_equilibrium_has_a_right_half_plane_pole():
    A, _ = linearize(M, UP, 0.0, P)
    assert np.max(np.real(np.linalg.eigvals(A))) > 0.1


def test_hanging_equilibrium_is_marginally_stable():
    down = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    A, _ = linearize(M, down, 0.0, P)
    assert np.max(np.real(np.linalg.eigvals(A))) < 1e-6


def test_the_cart_is_the_only_directly_driven_state():
    _, B = linearize(M, UP, 0.0, P)
    assert abs(B[3, 0]) > 1e-3


def test_hanging_mode_frequencies_match_the_analytic_values():
    """With the pivot effectively fixed, the two swing frequencies about
    hanging solve det(K - w^2 M2) = 0 for the fixed-pivot pair, where

        M2 = [[a, b], [b, c]]                a = I1 + m1 lc1^2 + m2 l1^2
        K  = diag(g(m1 lc1 + m2 l1), g m2 lc2)   b = m2 l1 lc2
                                                 c = I2 + m2 lc2^2

    computed here by hand rather than taken from the model.
    """
    from dpc.params import Corrections

    p = Params(corr=Corrections(k_m_cart=1e4))
    e = p.effective()
    a = e["I1"] + e["m1"] * e["lc1"] ** 2 + e["m2"] * e["l1"] ** 2
    b = e["m2"] * e["l1"] * e["lc2"]
    c = e["I2"] + e["m2"] * e["lc2"] ** 2
    M2 = np.array([[a, b], [b, c]])
    K = np.diag([e["g"] * (e["m1"] * e["lc1"] + e["m2"] * e["l1"]),
                 e["g"] * e["m2"] * e["lc2"]])
    want = np.sort(np.sqrt(np.linalg.eigvals(np.linalg.solve(M2, K)).real))

    down = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    A, _ = linearize(M, down, 0.0, p)
    ev = np.linalg.eigvals(A)
    got = np.sort(np.abs(np.imag(ev[np.abs(np.imag(ev)) > 1e-6])))[::2]

    assert np.allclose(got, want, rtol=2e-3), f"got {got}, want {want}"


def test_small_angle_response_tracks_the_nonlinear_model():
    A, B = linearize(M, UP, 0.0, P)
    s0 = np.array([0.0, 1e-4, -1e-4, 0.0, 0.0, 0.0])
    dt, n = 1e-4, 2000

    lin = s0.copy()
    for _ in range(n):
        k1 = A @ lin
        k2 = A @ (lin + 0.5 * dt * k1)
        k3 = A @ (lin + 0.5 * dt * k2)
        k4 = A @ (lin + dt * k3)
        lin = lin + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

    tr = simulate(M, s0, lambda t, s: 0.0, t_end=n * dt, dt=dt, p=P)
    rel = np.linalg.norm(tr.s[-1] - lin) / np.linalg.norm(lin)
    assert rel < 1e-3, f"relative divergence {rel:.2e}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_linearize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.linearize'`

- [ ] **Step 3: Write `dpc/linearize.py`**

```python
"""Linearisation of the plant about an operating point.

Central finite differences rather than symbolic Jacobians: short, immune to
algebra slips, and identical to what the embedded C would compute.
"""

import numpy as np

from dpc.model import NumericModel
from dpc.params import Params


def linearize(model: NumericModel, s0: np.ndarray, F0: float, p: Params,
              eps: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    """Return (A, B) for sdot ~= A @ (s - s0) + B @ (F - F0) near (s0, F0)."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linearize.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add dpc/linearize.py tests/test_linearize.py
git commit -m "feat: finite-difference linearisation"
```

---

### Task 8: Plots

**Files:**
- Create: `dpc/viz.py`
- Test: `tests/test_viz.py`

**Interfaces:**
- Consumes: `Trajectory`, `NumericModel`, `Params`.
- Produces: `plot_trajectory(tr, model, p, title=None) -> matplotlib.figure.Figure`.

No animation in this milestone.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viz.py
import matplotlib
matplotlib.use("Agg")

import numpy as np
from dpc.model import ModelConfig, build
from dpc.params import Params
from dpc.simulate import simulate
from dpc.viz import plot_trajectory

M = build(ModelConfig())
P = Params()


def test_plot_returns_a_four_panel_figure():
    tr = simulate(M, np.array([0.0, 2.5, 2.7, 0.0, 0.0, 0.0]),
                  lambda t, s: 0.0, t_end=1.0, dt=1e-3, p=P)
    fig = plot_trajectory(tr, M, P, title="free swing")
    assert len(fig.axes) == 4
    assert fig.axes[0].get_title() == "free swing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_viz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.viz'`

- [ ] **Step 3: Write `dpc/viz.py`**

```python
"""Time-series plots. Animation is deliberately out of scope for milestone 1."""

import matplotlib.pyplot as plt
import numpy as np

from dpc.model import NumericModel
from dpc.params import Params
from dpc.simulate import Trajectory


def plot_trajectory(tr: Trajectory, model: NumericModel, p: Params,
                    title: str | None = None):
    """Angles, cart position, applied force, and total energy."""
    fig, ax = plt.subplots(4, 1, figsize=(9, 10), sharex=True)

    ax[0].plot(tr.t, np.degrees(tr.s[:, 1]), label=r"$\theta_1$")
    ax[0].plot(tr.t, np.degrees(tr.s[:, 2]), label=r"$\theta_2$")
    ax[0].set_ylabel("angle [deg]")
    ax[0].legend()
    ax[0].axhline(0.0, lw=0.5, color="k")
    if title:
        ax[0].set_title(title)

    ax[1].plot(tr.t, tr.s[:, 0])
    ax[1].set_ylabel("cart x [m]")

    ax[2].plot(tr.t, tr.F)
    ax[2].set_ylabel("force [N]")

    energy = np.array([model.energy(s, p) for s in tr.s])
    ax[3].plot(tr.t, energy - energy[0])
    ax[3].set_ylabel("energy drift [J]")
    ax[3].set_xlabel("time [s]")

    fig.tight_layout()
    return fig
```

- [ ] **Step 4: Run the whole suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add dpc/viz.py tests/test_viz.py
git commit -m "feat: trajectory plots"
```

---

## Milestone complete when

- `pytest` is green.
- Energy drift over a six-second chaotic swing is below `1e-6` relative.
- Measured RK4 convergence order is between 3.5 and 4.5.
- A heavy cart reproduces an independently coded fixed-pivot double pendulum to `1e-3`.
- Hanging-mode frequencies match the hand-computed analytic values to `0.2%`.
- Small-angle response tracks the linearised model to better than `0.1%`.
