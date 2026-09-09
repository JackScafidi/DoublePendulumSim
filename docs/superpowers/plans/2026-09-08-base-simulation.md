# Base Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop — a controller that sees only real hardware signals, a motor model that applies real hardware limits, and an acceleration-driven plant.

**Architecture:** The plant becomes acceleration-driven by partitioning the manipulator equation the existing derivation already produces: rows 2-3 solve for link accelerations given cart acceleration, row 1 reads backwards for the force the motor had to supply. A new `dynamics.py` owns both drive paths; `motor.py`, `sensors.py`, `estimate.py` and `control.py` form the control chain above it.

**Tech Stack:** Python 3.11+, NumPy, SymPy (unchanged), matplotlib, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-base-simulation-design.md`

## Global Constraints

- No physical numeric value may appear outside `dpc/params.py`.
- State ordering is fixed: `s = [x, theta1, theta2, xdot, w1, w2]`. Generalised coordinates `q = [x, theta1, theta2]`.
- Angles are absolute from vertical, positive toward `+x`.
- `m_rotor` is an equivalent mass `J/r^2`. Kinetic energy only — never potential energy, never a normal-force term.
- `M`, `Cqd`, `G` and the friction vector stay separately accessible; never fused.
- Fixed-step RK4 only.
- Only `drive="rigid"` is implemented.
- Control-path code (`estimate.py`, `control.py`, `motor.py`) uses fixed-size arrays, explicit indexing, and no Python-specific constructs — it is transcribed to C++ next milestone.
- `ControlOutput.info` is strictly diagnostic. The loop never reads it back.
- Effective parameter ordering in `EFFECTIVE_NAMES` is fixed and unchanged. Drive and control parameters are **not** added to it — they do not appear in the equations of motion.
- Commits carry no co-author trailer.

---

## Deviations from the spec

Three refinements found while planning. Each is a deliberate change, recorded here so the spec and the code can be reconciled afterward.

1. **`MotorState` gains `v_count` and is frozen.** The velocity ceiling must clamp against the step generator's *own* rate, not the true cart velocity — the generator has no access to truth, and using `s[3]` would reintroduce exactly the clairvoyance the `Measurement` boundary exists to prevent. Frozen matches the rest of the codebase; `step()` returns a new state.

2. **Quantisation moves from the motor to the sensor read.** `MotorState.x_count` stays continuous; the integer step count is `round(x_count / step_res)`, and `sensors.measure()` reports `steps * step_res`. This is what the hardware literally does — firmware reads an integer counter — it cannot drift, and it avoids a state field that would only ever hold a rounded copy of another one. The spec's ordering of quantisation before lag becomes moot as a result.

3. **`params.py` gains a `Control` block** holding `ts`, `substeps` and `tau_rate`. The spec named these as `run()` defaults, but the no-numerics-outside-params constraint applies to them too.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `dpc/params.py` | all constants; adds `Drive` and `Control` blocks | modify |
| `dpc/dynamics.py` | both drive paths, block partition, required force, motor torque | create |
| `dpc/motor.py` | acceleration command -> hardware limits -> delivered acceleration | create |
| `dpc/sensors.py` | `Measurement`, and truth + motor state -> measurement | create |
| `dpc/estimate.py` | `RateEstimator` | create |
| `dpc/control.py` | `ControlOutput`, `Controller`, `ZeroController`, `ConstantController` | create |
| `dpc/simulate.py` | generalised `rk4_step`, unchanged `simulate()`, new `run()` and `Run` | modify |
| `dpc/model.py` | derivation and term evaluation only; loses `accel`/`deriv` | modify |
| `dpc/linearize.py` | call-site update | modify |
| `dpc/viz.py` | adds `plot_run` | modify |
| `tests/test_dynamics.py` | adds partition tests | modify |
| `tests/test_numeric.py` | call-site update | modify |
| `tests/test_integrator.py` | call-site update | modify |
| `tests/test_motor.py` | motor stages | create |
| `tests/test_sensors.py` | measurement boundary | create |
| `tests/test_estimate.py` | rate estimator | create |
| `tests/test_control.py` | controller contract | create |
| `tests/test_run.py` | end to end, cross-path agreement | create |

---

### Task 1: Drive and control parameters

**Files:**
- Modify: `dpc/params.py`
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Drive` with fields `r_pulley, steps_per_rev, microsteps, tau_hold, tau_derate, a_max, v_max, jerk_max, tau_lag, slip_enable` and properties `step_res -> float`, `tau_budget -> float`, `F_max -> float`; `Control` with `ts, substeps, tau_rate`; `Params.drive: Drive` and `Params.ctrl: Control`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_params.py`:

```python
import math

from dpc.params import Control, Drive


def test_drive_defaults():
    d = Drive()
    assert d.r_pulley == pytest.approx(6.4e-3)
    assert d.steps_per_rev == 200
    assert d.microsteps == 16
    assert d.slip_enable is False


def test_step_resolution_is_belt_travel_per_microstep():
    d = Drive()
    expected = 2.0 * math.pi * d.r_pulley / (d.steps_per_rev * d.microsteps)
    assert d.step_res == pytest.approx(expected)
    assert d.step_res == pytest.approx(12.566e-6, rel=1e-3)


def test_torque_budget_is_holding_torque_derated():
    d = Drive()
    assert d.tau_budget == pytest.approx(d.tau_hold * d.tau_derate)
    assert d.F_max == pytest.approx(d.tau_budget / d.r_pulley)


def test_control_defaults():
    c = Control()
    assert c.ts == pytest.approx(1e-3)
    assert c.substeps == 10


def test_params_carry_drive_and_control():
    p = Params()
    assert p.drive.a_max > 0
    assert p.ctrl.substeps >= 1


def test_drive_and_control_are_not_in_the_effective_vector():
    p = Params()
    assert len(p.vector()) == len(EFFECTIVE_NAMES) == 19
    assert "r_pulley" not in EFFECTIVE_NAMES
    assert "ts" not in EFFECTIVE_NAMES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_params.py -q`
Expected: FAIL with `ImportError: cannot import name 'Control' from 'dpc.params'`

- [ ] **Step 3: Write minimal implementation**

Add `import math` at the top of `dpc/params.py`, then insert these two dataclasses before `class Params`:

```python
@dataclass(frozen=True)
class Drive:
    """The stepper drive train. Provisional until the hardware is finalised.

    None of these appear in the equations of motion, so they are deliberately
    absent from EFFECTIVE_NAMES: they shape the command the motor accepts, not
    the physics of the plant.
    """

    r_pulley: float = 6.4e-3
    """m. 20T GT2 pitch radius. The same r that makes m_rotor = J/r^2."""

    steps_per_rev: int = 200
    """NEMA-17 at 1.8 degrees per full step."""

    microsteps: int = 16
    """TMC2209 microstepping divisor."""

    tau_hold: float = 0.40
    """N m. Holding torque of a typical 42x40 mm NEMA-17."""

    tau_derate: float = 0.5
    """Dimensionless. Available torque falls off with step rate; this is the
    fraction of holding torque treated as usable."""

    a_max: float = 10.0
    """m/s^2. Acceleration ceiling set by torque through the pulley."""

    v_max: float = 0.5
    """m/s. Step rate beyond this is unsustainable."""

    jerk_max: float = 200.0
    """m/s^3. How fast the step generator can ramp its own rate."""

    tau_lag: float = 3e-3
    """s. First-order stand-in for the step generator's finite bandwidth."""

    slip_enable: bool = False
    """Step loss is implemented but off by default. It is the only mechanism
    that makes the step-counted position differ from the truth, so enabling it
    is a deliberate question, not a default."""

    @property
    def step_res(self) -> float:
        """m of belt travel per microstep."""
        return 2.0 * math.pi * self.r_pulley / (self.steps_per_rev * self.microsteps)

    @property
    def tau_budget(self) -> float:
        """N m the motor can actually be relied on to deliver."""
        return self.tau_hold * self.tau_derate

    @property
    def F_max(self) -> float:
        """N at the belt corresponding to the torque budget."""
        return self.tau_budget / self.r_pulley


@dataclass(frozen=True)
class Control:
    """Loop timing. Not physical, but numeric, so it lives here like everything
    else numeric."""

    ts: float = 1e-3
    """s. Control period. One measurement, one command, one motor update."""

    substeps: int = 10
    """Plant integration steps per control tick. Exists only so integration
    error stays well below the effects under study."""

    tau_rate: float = 5e-3
    """s. Low-pass time constant on differenced angular rates."""
```

Then add two fields to `Params`, after `fric`:

```python
    drive: Drive = field(default_factory=Drive)
    ctrl: Control = field(default_factory=Control)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_params.py -q`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add dpc/params.py tests/test_params.py
git commit -m "feat: drive and control parameter blocks"
```

---

### Task 2: `dynamics.py` — force calculations and the block partition

**Files:**
- Create: `dpc/dynamics.py`
- Modify: `dpc/model.py` (remove `accel`, `deriv`), `dpc/simulate.py`, `dpc/linearize.py`, `tests/test_numeric.py`
- Test: `tests/test_dynamics.py`

**Interfaces:**
- Consumes: `NumericModel.M/Cqd/G/Ffric` from Task 0 (existing), `Params.drive.r_pulley` from Task 1.
- Produces:
  - `accel(model, s, F, p) -> np.ndarray` shape (3,)
  - `deriv(model, s, F, p) -> np.ndarray` shape (6,)
  - `link_accel(model, s, a_cart, p) -> np.ndarray` shape (2,)
  - `required_force(model, s, a_cart, qdd_l, p) -> float`
  - `motor_torque(F, p) -> float`
  - `deriv_accel(model, s, a_cart, p) -> np.ndarray` shape (6,)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dynamics.py`:

```python
import numpy as np
import pytest

from dpc.dynamics import (accel, deriv_accel, link_accel, motor_torque,
                          required_force)
from dpc.params import Friction, Nominal, Params

STATES = [
    np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    np.array([0.1, 0.3, -0.2, 0.4, -0.5, 0.6]),
    np.array([-0.2, 2.9, 3.1, -0.3, 0.7, -0.8]),
]

ROUGH = Params(fric=Friction(b_cart=0.4, b1=0.01, b2=0.008,
                             c_cart=0.5, c1=0.02, c2=0.015))


@pytest.mark.parametrize("s", STATES)
@pytest.mark.parametrize("F", [0.0, 1.5, -3.0])
@pytest.mark.parametrize("p", [Params(), ROUGH])
def test_partition_round_trips(model, s, F, p):
    """Solving forwards then backwards must return the same numbers.

    This is the whole partition under test at once: if any block index or sign
    is wrong, the recovered force will not match the force we started from.
    """
    qdd = accel(model, s, F, p)

    qdd_l = link_accel(model, s, qdd[0], p)
    assert qdd_l == pytest.approx(qdd[1:], abs=1e-9)

    assert required_force(model, s, qdd[0], qdd_l, p) == pytest.approx(F, abs=1e-9)


@pytest.mark.parametrize("s", STATES)
def test_link_accel_ignores_the_rail(model, s):
    """m_cart, m_rotor and rail friction live in row 1 alone.

    This is the architectural claim of the whole milestone, asserted rather
    than argued: the parameters the controller cannot measure well do not
    reach the part of the plant the controller has to know.
    """
    base = ROUGH
    perturbed = Params(
        nominal=Nominal(m_cart=base.nominal.m_cart * 3.0,
                        m_rotor=base.nominal.m_rotor * 0.5),
        fric=Friction(b_cart=9.9, b1=base.fric.b1, b2=base.fric.b2,
                      c_cart=7.7, c1=base.fric.c1, c2=base.fric.c2),
    )

    a_cart = 2.0
    assert link_accel(model, s, a_cart, base) == pytest.approx(
        link_accel(model, s, a_cart, perturbed), abs=1e-12)


def test_required_force_does_depend_on_the_rail(model):
    """The mirror of the test above: those parameters must still matter to the
    motor, or they would be unobservable everywhere and could not be fitted."""
    s = STATES[1]
    light = ROUGH
    heavy = Params(nominal=Nominal(m_cart=ROUGH.nominal.m_cart * 3.0),
                   fric=ROUGH.fric)

    a_cart = 2.0
    f_light = required_force(model, s, a_cart, link_accel(model, s, a_cart, light), light)
    f_heavy = required_force(model, s, a_cart, link_accel(model, s, a_cart, heavy), heavy)
    assert abs(f_heavy) > abs(f_light)


def test_motor_torque_is_force_times_pulley_radius():
    p = Params()
    assert motor_torque(10.0, p) == pytest.approx(10.0 * p.drive.r_pulley)


@pytest.mark.parametrize("s", STATES)
def test_deriv_accel_places_the_command_in_the_cart_slot(model, s):
    a_cart = -1.25
    d = deriv_accel(model, s, a_cart, Params())
    assert d[0:3] == pytest.approx(s[3:6])
    assert d[3] == pytest.approx(a_cart)
    assert d[4:6] == pytest.approx(link_accel(model, s, a_cart, Params()))
```

`tests/test_dynamics.py` already defines a `model` fixture. If it does not, add:

```python
@pytest.fixture(scope="module")
def model():
    from dpc.model import build
    return build()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dynamics.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.dynamics'`

- [ ] **Step 3: Create `dpc/dynamics.py`**

```python
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
    """State derivative: velocities, then accelerations."""
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
```

- [ ] **Step 4: Remove `accel` and `deriv` from `dpc/model.py`**

Delete the `accel` and `deriv` methods from `NumericModel` (they sit between `Ffric` and `energy`). Leave `M`, `Cqd`, `G`, `Ffric` and `energy` untouched. Update the class docstring's final sentence to read:

```python
    """Fast numeric evaluation of a derived Model.

    Term evaluation only. What is solved for -- and in which direction -- lives
    in dynamics.py, because there is more than one answer once the drive is a
    stepper.

    Deliberately plain -- fixed-size arrays, explicit indexing -- because this
    is the layer that gets transcribed to C++ for the STM32.
    """
```

- [ ] **Step 5: Update the three call sites**

In `dpc/linearize.py`, add `from dpc.dynamics import deriv` and replace the four `model.deriv(...)` calls with `deriv(model, ...)`:

```python
        A[:, j] = (deriv(model, s0 + step, F0, p)
                   - deriv(model, s0 - step, F0, p)) / (2.0 * eps)

    B = ((deriv(model, s0, F0 + eps, p)
          - deriv(model, s0, F0 - eps, p)) / (2.0 * eps)).reshape(6, 1)
```

In `dpc/simulate.py`, add `from dpc.dynamics import deriv` and replace the four `model.deriv(...)` calls inside `rk4_step` with `deriv(model, ...)`. (Task 3 rewrites this function; this keeps the tree green in between.)

In `tests/test_numeric.py`, add `from dpc.dynamics import accel, deriv` and rewrite every `M.accel(...)` as `accel(M, ...)` and every `M.deriv(...)` as `deriv(M, ...)`. No assertion values change.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, all tests including the six existing physics files

- [ ] **Step 7: Commit**

```bash
git add dpc/dynamics.py dpc/model.py dpc/simulate.py dpc/linearize.py tests/test_dynamics.py tests/test_numeric.py
git commit -m "feat: dynamics layer with acceleration-driven block partition"
```

---

### Task 3: Generalise the integrator

**Files:**
- Modify: `dpc/simulate.py`, `tests/test_integrator.py`

**Interfaces:**
- Consumes: `dynamics.deriv`.
- Produces: `rk4_step(f, s, u, dt) -> np.ndarray` where `f(s, u) -> np.ndarray` shape (6,). `simulate()` keeps its existing signature and behaviour.

- [ ] **Step 1: Write the failing test**

Replace the two `rk4_step` call sites in `tests/test_integrator.py` and add one new test:

```python
from dpc.dynamics import deriv


def _f(model, p):
    """Bind a model and parameter set into the derivative signature rk4_step
    wants. Built once, outside any loop."""
    def g(s, u):
        return deriv(model, s, u, p)
    return g


def test_rk4_step_takes_a_derivative_callable():
    one = rk4_step(_f(M, P), S0, 0.5, 1e-3)
    tr = simulate(M, S0, lambda t, s: 0.5, t_end=1e-3, dt=1e-3, p=P)
    assert np.allclose(one, tr.s[-1])


def test_rk4_step_is_exact_for_a_constant_derivative():
    """Four stages, one weighted sum: with a state-independent derivative RK4
    must reduce to plain Euler exactly."""
    s = np.zeros(6)
    out = rk4_step(lambda ss, uu: np.full(6, uu), s, 2.0, 0.1)
    assert out == pytest.approx(np.full(6, 0.2))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_integrator.py -q`
Expected: FAIL — `rk4_step()` still takes `(model, s, F, dt, p)`

- [ ] **Step 3: Rewrite `rk4_step` and `simulate`**

In `dpc/simulate.py`, replace `rk4_step` with:

```python
DerivFn = Callable[[np.ndarray, float], np.ndarray]
"""State derivative: takes (state, scalar input), returns the 6-vector.

Taking a callable rather than a model is what lets one integrator serve both
drive modes -- force-driven passes the force, stepper mode passes the delivered
acceleration -- without the integrator knowing which it is.
"""


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
```

and rewrite the body of `simulate` to build the closure once:

```python
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
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/simulate.py tests/test_integrator.py
git commit -m "refactor: rk4_step takes a derivative callable"
```

---

### Task 4: `motor.py`

**Files:**
- Create: `dpc/motor.py`
- Test: `tests/test_motor.py`

**Interfaces:**
- Consumes: `dynamics.link_accel`, `dynamics.required_force`, `dynamics.motor_torque`, `Params.drive`.
- Produces: `MotorState(a_lag, v_count, x_count, n_slip, slip_accum)` (frozen, all defaults 0); `MotorOut(a_del, F_req, tau, slipped, state)`; `step_count(st, p) -> int`; `step(model, a_cmd, s, st, dt, p) -> MotorOut`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_motor.py`:

```python
"""Each stage of the motor model gets its own test, and each test neutralises
the other stages so a failure names one mechanism."""

import numpy as np
import pytest

from dpc.model import build
from dpc.motor import MotorState, step, step_count
from dpc.params import Control, Drive, Params

TS = 1e-3
REST = np.zeros(6)


@pytest.fixture(scope="module")
def model():
    return build()


def _p(**drive):
    """A parameter set with every limit relaxed except the ones named."""
    base = dict(a_max=1e6, v_max=1e6, jerk_max=1e12, tau_lag=0.0,
                slip_enable=False)
    base.update(drive)
    return Params(drive=Drive(**base), ctrl=Control(ts=TS))


def test_zero_command_from_rest_changes_nothing(model):
    p = _p()
    out = step(model, 0.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(0.0)
    assert out.state.v_count == pytest.approx(0.0)
    assert out.state.x_count == pytest.approx(0.0)
    assert out.slipped is False


def test_jerk_limits_the_change_in_acceleration(model):
    p = _p(jerk_max=100.0)
    out = step(model, 50.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(100.0 * TS)


def test_jerk_limit_is_symmetric(model):
    p = _p(jerk_max=100.0)
    out = step(model, -50.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(-100.0 * TS)


def test_acceleration_saturates(model):
    p = _p(a_max=3.0)
    assert step(model, 99.0, REST, MotorState(), TS, p).a_del == pytest.approx(3.0)
    assert step(model, -99.0, REST, MotorState(), TS, p).a_del == pytest.approx(-3.0)


def test_velocity_ceiling_blocks_speeding_up(model):
    p = _p(v_max=0.5)
    st = MotorState(v_count=0.5)
    assert step(model, 5.0, REST, st, TS, p).a_del == pytest.approx(0.0)


def test_velocity_ceiling_still_allows_braking(model):
    """One-sided on purpose. A two-sided clamp builds a cart that cannot stop."""
    p = _p(v_max=0.5)
    st = MotorState(v_count=0.5)
    assert step(model, -5.0, REST, st, TS, p).a_del == pytest.approx(-5.0)

    st_rev = MotorState(v_count=-0.5)
    assert step(model, -5.0, REST, st_rev, TS, p).a_del == pytest.approx(0.0)
    assert step(model, 5.0, REST, st_rev, TS, p).a_del == pytest.approx(5.0)


def test_lag_reaches_63_percent_at_one_time_constant(model):
    tau = 10e-3
    p = _p(tau_lag=tau)
    st = MotorState()
    n = int(round(tau / TS))
    for _ in range(n):
        st = step(model, 1.0, REST, st, TS, p).state
    assert st.a_lag == pytest.approx(1.0 - np.exp(-1.0), rel=1e-9)


def test_lag_is_the_exact_zoh_response_not_backward_euler(model):
    """Backward Euler would give dt/(tau+dt) after one step. The gap is a few
    percent, and an unstable plant amplifies it until the model and the target
    visibly disagree."""
    tau = 10e-3
    p = _p(tau_lag=tau)
    out = step(model, 1.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(1.0 - np.exp(-TS / tau))
    assert out.a_del != pytest.approx(TS / (tau + TS), rel=1e-3)


def test_step_count_is_an_integer_number_of_microsteps(model):
    p = _p()
    res = p.drive.step_res
    st = MotorState(x_count=10.4 * res)
    assert step_count(st, p) == 10
    assert step_count(MotorState(x_count=-10.6 * res), p) == -11


def test_counter_advances_with_the_commanded_velocity(model):
    p = _p()
    st = MotorState()
    for _ in range(100):
        st = step(model, 1.0, REST, st, TS, p).state
    assert st.v_count == pytest.approx(0.1)
    assert st.x_count > 0.0


def test_required_force_is_reported_even_with_slip_disabled(model):
    p = _p()
    out = step(model, 2.0, REST, MotorState(), TS, p)
    assert out.tau == pytest.approx(out.F_req * p.drive.r_pulley)
    assert out.F_req != 0.0


def test_no_slip_when_disabled_even_under_impossible_demand(model):
    p = _p(a_max=1e6, slip_enable=False, tau_hold=1e-6)
    out = step(model, 5000.0, REST, MotorState(), TS, p)
    assert out.slipped is False
    assert out.a_del == pytest.approx(5000.0)


def test_slip_scales_delivery_and_banks_the_difference(model):
    p = _p(slip_enable=True, tau_hold=1e-4, tau_derate=1.0)
    out = step(model, 5000.0, REST, MotorState(), TS, p)
    assert out.slipped is True
    assert abs(out.a_del) < 5000.0
    assert out.state.n_slip == 1
    assert out.state.slip_accum != 0.0


def test_slip_makes_the_counter_diverge_from_the_truth(model):
    """The counter keeps counting the steps that were commanded, so the
    step-counted position drifts away from where the cart really is -- with no
    residual anywhere to reveal it."""
    p = _p(slip_enable=True, tau_hold=1e-4, tau_derate=1.0)
    st = MotorState()
    for _ in range(50):
        st = step(model, 5000.0, REST, st, TS, p).state
    commanded = st.v_count
    delivered = commanded - st.slip_accum
    assert abs(commanded - delivered) > 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_motor.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.motor'`

- [ ] **Step 3: Create `dpc/motor.py`**

```python
"""The step generator: a controller's acceleration command in, the cart's
actual acceleration out.

A step/dir stepper has no torque input. What leaves the MCU is a direction
level and a step frequency, reloaded once per control tick, so what the
controller really writes is a bounded change in step rate -- an acceleration.
Everything here is the gap between the acceleration asked for and the one the
hardware can produce.

Stages are applied in the order the hardware applies them. This file, minus the
slip check, is transcribed to C++ next milestone: fixed-size arithmetic,
explicit branches, no allocation.
"""

import math
from dataclasses import dataclass, replace

import numpy as np

from dpc.dynamics import link_accel, motor_torque, required_force
from dpc.model import NumericModel
from dpc.params import Params


@dataclass(frozen=True)
class MotorState:
    """Everything the step generator knows about itself.

    Note what is not here: the true cart velocity. The generator has no
    position or velocity sensor, so the velocity ceiling clamps against
    v_count -- its own commanded rate -- and never against the truth.
    """

    a_lag: float = 0.0
    """m/s^2. State of the bandwidth lag; the acceleration actually in effect."""

    v_count: float = 0.0
    """m/s. Cart velocity implied by the step rate being generated."""

    x_count: float = 0.0
    """m. Cart position implied by the steps commanded so far.

    NOT a measurement. When the motor slips, the steps are still counted and
    this keeps advancing, so it drifts away from the true position with nothing
    anywhere to contradict it."""

    n_slip: int = 0
    """Control ticks on which torque demand exceeded the budget."""

    slip_accum: float = 0.0
    """m/s. Velocity error banked by slip: the difference between what was
    counted and what was delivered."""


@dataclass(frozen=True)
class MotorOut:
    """One tick's result. F_req and tau are computed whether or not slip is
    enabled, because they are the diagnostics worth logging either way."""

    a_del: float
    """m/s^2 actually delivered to the cart."""

    F_req: float
    """N the plant required to produce it."""

    tau: float
    """N m at the motor shaft."""

    slipped: bool
    state: MotorState


def step_count(st: MotorState, p: Params) -> int:
    """The integer the firmware would read out of its step counter.

    Quantisation lives here rather than in the state because that is where it
    lives in hardware: the generator accumulates a rate, and what can be read
    back is a whole number of microsteps. Rounding a running total cannot
    drift, whereas accumulating rounded increments would.
    """
    return int(round(st.x_count / p.drive.step_res))


def step(model: NumericModel, a_cmd: float, s: np.ndarray, st: MotorState,
         dt: float, p: Params) -> MotorOut:
    """Apply one control tick's worth of hardware reality to a command."""
    d = p.drive

    # 1. Jerk limit. The generator ramps its own rate; it cannot step-change
    #    acceleration.
    da = d.jerk_max * dt
    a = min(max(a_cmd, st.a_lag - da), st.a_lag + da)

    # 2. Acceleration saturation, set by torque through the pulley.
    a = min(max(a, -d.a_max), d.a_max)

    # 3. Velocity ceiling, one-sided. Past v_max the step rate is
    #    unsustainable, so speeding up further is refused -- but braking is
    #    always allowed. A two-sided clamp here yields a cart that cannot stop.
    if st.v_count >= d.v_max and a > 0.0:
        a = 0.0
    if st.v_count <= -d.v_max and a < 0.0:
        a = 0.0

    # 4. First-order lag for the generator's finite bandwidth, discretised
    #    exactly. Backward Euler's dt/(tau+dt) is a few percent adrift, and an
    #    unstable plant amplifies that until the model and the target disagree.
    if d.tau_lag > 0.0:
        alpha = 1.0 - math.exp(-dt / d.tau_lag)
        a_del = st.a_lag + alpha * (a - st.a_lag)
    else:
        a_del = a

    # The counter advances with what was COMMANDED, before any slip is applied.
    # That is precisely what makes it diverge.
    v_count = st.v_count + a_del * dt
    x_count = st.x_count + st.v_count * dt + 0.5 * a_del * dt * dt

    # Diagnostics, always computed: the torque this delivery demands.
    qdd_l = link_accel(model, s, a_del, p)
    F_req = required_force(model, s, a_del, qdd_l, p)
    tau = motor_torque(F_req, p)

    # 5. Slip. Beyond the torque budget the rotor turns less than it was told
    #    to. The cart falls short AND the counter keeps counting -- an actuator
    #    fault that presents as a sensor fault, which on a cart with no
    #    independent position reference is the failure worth designing against.
    slipped = False
    n_slip, slip_accum = st.n_slip, st.slip_accum
    if d.slip_enable and abs(tau) > d.tau_budget:
        excess = (abs(tau) - d.tau_budget) / d.tau_budget
        scale = 1.0 / (1.0 + excess)
        a_lost = a_del * (1.0 - scale)
        a_del = a_del * scale
        slip_accum = slip_accum + a_lost * dt
        n_slip = n_slip + 1
        slipped = True

    return MotorOut(
        a_del=a_del,
        F_req=F_req,
        tau=tau,
        slipped=slipped,
        state=replace(st, a_lag=a_del, v_count=v_count, x_count=x_count,
                      n_slip=n_slip, slip_accum=slip_accum),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_motor.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/motor.py tests/test_motor.py
git commit -m "feat: stepper motor model with jerk, saturation, ceiling, lag and slip"
```

---

### Task 5: `sensors.py` — the wire boundary

**Files:**
- Create: `dpc/sensors.py`
- Test: `tests/test_sensors.py`

**Interfaces:**
- Consumes: `motor.MotorState`, `motor.step_count`.
- Produces: `Measurement(t, th1, th2, x_count, dt)` (frozen); `measure(t, s, st, dt, p) -> Measurement`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sensors.py`:

```python
import dataclasses

import numpy as np
import pytest

from dpc.motor import MotorState
from dpc.params import Params
from dpc.sensors import Measurement, measure

P = Params()
S = np.array([0.11, 0.22, 0.33, 0.44, 0.55, 0.66])


def test_measurement_carries_no_rates():
    """The structural guard. Hardware measures neither cart velocity nor either
    angular rate, so no controller may be handed one."""
    names = {f.name for f in dataclasses.fields(Measurement)}
    assert names == {"t", "th1", "th2", "x_count", "dt"}
    for forbidden in ("xdot", "w1", "w2", "s", "state"):
        assert forbidden not in names


def test_angles_come_from_truth_today():
    m = measure(0.5, S, MotorState(), 1e-3, P)
    assert m.th1 == pytest.approx(S[1])
    assert m.th2 == pytest.approx(S[2])
    assert m.t == pytest.approx(0.5)
    assert m.dt == pytest.approx(1e-3)


def test_position_comes_from_the_step_counter_not_the_truth():
    """The cart has no position sensor. What the controller sees is the total
    of the steps it commanded."""
    st = MotorState(x_count=0.02)
    m = measure(0.0, S, st, 1e-3, P)
    assert m.x_count != pytest.approx(S[0])
    assert m.x_count == pytest.approx(0.02, abs=P.drive.step_res)


def test_reported_position_is_quantised_to_whole_microsteps():
    res = P.drive.step_res
    st = MotorState(x_count=100.4 * res)
    m = measure(0.0, S, st, 1e-3, P)
    assert m.x_count == pytest.approx(100 * res)


def test_measurement_is_frozen():
    m = measure(0.0, S, MotorState(), 1e-3, P)
    with pytest.raises(Exception):
        m.th1 = 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sensors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.sensors'`

- [ ] **Step 3: Create `dpc/sensors.py`**

```python
"""The boundary between hardware and software, made explicit.

Everything above this line is truth the simulator happens to know. Everything
below it is what firmware actually has at the top of a control tick. The
Measurement struct is the whole of that second list -- if a quantity is not in
it, no controller may use it.
"""

from dataclasses import dataclass

import numpy as np

from dpc.motor import MotorState, step_count
from dpc.params import Params


@dataclass(frozen=True)
class Measurement:
    """Three signals and the timing they belong to. Nothing else exists.

    There are no rates here, because the hardware measures none: a controller
    that needs theta1dot must difference the angles itself, exactly as it will
    on the bench.
    """

    t: float
    """s since start."""

    th1: float
    """rad. Encoder at the cart joint. Quantised on hardware."""

    th2: float
    """rad. Encoder at the elbow. Quantised on hardware."""

    x_count: float
    """m. Position implied by the total of the steps commanded.

    Not a sensor reading. On an open-loop stepper the cart has no position
    reference at all, so this is the controller's own history played back to
    it, and it drifts silently from the truth whenever the motor slips."""

    dt: float
    """s. The control period this reading belongs to. Passed in rather than
    read from a clock so the same controller runs at any rate, in simulation
    or on the target."""


def measure(t: float, s: np.ndarray, st: MotorState, dt: float,
            p: Params) -> Measurement:
    """Build a measurement from the true state and the motor's own counter.

    Today the angles are copied from truth exactly: no quantisation, no noise.
    Those belong here, in this one function, and adding them will degrade every
    controller's inputs at once without any controller changing.
    """
    return Measurement(
        t=t,
        th1=float(s[1]),
        th2=float(s[2]),
        x_count=step_count(st, p) * p.drive.step_res,
        dt=dt,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sensors.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/sensors.py tests/test_sensors.py
git commit -m "feat: measurement boundary"
```

---

### Task 6: `estimate.py`

**Files:**
- Create: `dpc/estimate.py`
- Test: `tests/test_estimate.py`

**Interfaces:**
- Consumes: `Params.ctrl.tau_rate`.
- Produces: `RateEstimator(tau)` with `reset() -> None` and `update(th1, th2, dt) -> tuple[float, float]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_estimate.py`:

```python
import numpy as np
import pytest

from dpc.estimate import RateEstimator

DT = 1e-3


def test_first_call_reports_zero_rates():
    """One sample cannot imply a rate. Reporting a huge one from the initial
    zero would kick any controller on its first tick."""
    e = RateEstimator(tau=0.0)
    assert e.update(1.0, 2.0, DT) == (0.0, 0.0)


def test_unfiltered_estimator_is_an_exact_backward_difference():
    e = RateEstimator(tau=0.0)
    e.update(0.0, 0.0, DT)
    w1, w2 = e.update(0.003, -0.005, DT)
    assert w1 == pytest.approx(3.0)
    assert w2 == pytest.approx(-5.0)


def test_it_converges_to_the_true_rate_of_a_ramp():
    e = RateEstimator(tau=5e-3)
    th = 0.0
    for _ in range(200):
        th += 2.0 * DT
        w1, _ = e.update(th, 0.0, DT)
    assert w1 == pytest.approx(2.0, rel=1e-3)


def test_filter_lags_by_its_time_constant():
    """A first-order filter reaches 63.2% of a step in one tau. This is the
    price of differencing a noisy signal, and it is characterised rather than
    hidden."""
    tau = 10e-3
    e = RateEstimator(tau=tau)
    e.update(0.0, 0.0, DT)
    th = 0.0
    for _ in range(int(round(tau / DT))):
        th += 1.0 * DT
        w1, _ = e.update(th, 0.0, DT)
    assert w1 == pytest.approx(1.0 - np.exp(-1.0), rel=1e-6)


def test_reset_restores_the_unprimed_state():
    e = RateEstimator(tau=0.0)
    e.update(0.0, 0.0, DT)
    e.update(0.01, 0.01, DT)
    e.reset()
    assert e.update(5.0, 5.0, DT) == (0.0, 0.0)


def test_the_two_channels_are_independent():
    e = RateEstimator(tau=0.0)
    e.update(0.0, 0.0, DT)
    w1, w2 = e.update(0.001, 0.0, DT)
    assert w1 == pytest.approx(1.0)
    assert w2 == pytest.approx(0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_estimate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.estimate'`

- [ ] **Step 3: Create `dpc/estimate.py`**

```python
"""Reconstructing what the hardware does not measure.

The encoders give angles; a controller needs angular rates. Differencing is the
crudest way to get them and it amplifies quantisation noise, so the difference
is low-passed. This is deliberately the simplest thing that works -- it is the
seat an observer takes later, once there is a plant worth observing.

Lives on the controller's side of the wire, because on the target it runs on
the MCU alongside the control law.
"""

import math


class RateEstimator:
    """Backward difference of each angle with a first-order low-pass.

    The two channels are independent; nothing here couples them, and nothing
    here knows about the plant. Fixed-size scalar state, no allocation, for
    transcription to C++.
    """

    __slots__ = ("tau", "_th1", "_th2", "_w1", "_w2", "_primed")

    def __init__(self, tau: float = 0.0):
        self.tau = tau
        """s. Filter time constant. Zero gives a raw difference."""
        self.reset()

    def reset(self) -> None:
        """Forget everything. The next update primes the difference and reports
        zero rates rather than inventing one from a single sample."""
        self._th1 = 0.0
        self._th2 = 0.0
        self._w1 = 0.0
        self._w2 = 0.0
        self._primed = False

    def update(self, th1: float, th2: float, dt: float) -> tuple[float, float]:
        """One tick. Returns (w1, w2) in rad/s."""
        if not self._primed:
            self._th1 = th1
            self._th2 = th2
            self._primed = True
            return 0.0, 0.0

        raw1 = (th1 - self._th1) / dt
        raw2 = (th2 - self._th2) / dt
        self._th1 = th1
        self._th2 = th2

        if self.tau > 0.0:
            # Exact zero-order-hold response, matching motor.py's lag so the
            # two filters in the loop are discretised the same way.
            alpha = 1.0 - math.exp(-dt / self.tau)
            self._w1 = self._w1 + alpha * (raw1 - self._w1)
            self._w2 = self._w2 + alpha * (raw2 - self._w2)
        else:
            self._w1 = raw1
            self._w2 = raw2

        return self._w1, self._w2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_estimate.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/estimate.py tests/test_estimate.py
git commit -m "feat: rate estimator"
```

---

### Task 7: `control.py` — the controls system

**Files:**
- Create: `dpc/control.py`
- Test: `tests/test_control.py`

**Interfaces:**
- Consumes: `sensors.Measurement`, `estimate.RateEstimator`, `Params`.
- Produces: `ControlOutput(a_cmd, mode, info)`; `Controller` protocol with `reset(p)` and `update(m) -> ControlOutput`; `ZeroController()`; `ConstantController(a)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_control.py`:

```python
import numpy as np
import pytest

from dpc.control import ConstantController, ControlOutput, ZeroController
from dpc.params import Params
from dpc.sensors import Measurement

P = Params()


def _m(t=0.0, th1=0.0, th2=0.0, x=0.0, dt=1e-3):
    return Measurement(t=t, th1=th1, th2=th2, x_count=x, dt=dt)


def test_zero_controller_commands_zero_whatever_it_sees():
    c = ZeroController()
    c.reset(P)
    rng = np.random.default_rng(0)
    for _ in range(50):
        m = _m(th1=rng.normal(), th2=rng.normal(), x=rng.normal())
        assert c.update(m).a_cmd == 0.0


def test_constant_controller_commands_its_constant():
    c = ConstantController(2.5)
    c.reset(P)
    assert c.update(_m()).a_cmd == pytest.approx(2.5)
    assert c.update(_m(t=1.0, th1=3.0)).a_cmd == pytest.approx(2.5)


def test_output_carries_a_mode():
    assert ZeroController().update(_m()).mode == "idle"
    assert ConstantController(1.0).update(_m()).mode == "constant"


def test_output_is_frozen():
    out = ControlOutput(a_cmd=1.0)
    with pytest.raises(Exception):
        out.a_cmd = 2.0


def test_reset_takes_no_state():
    """The controller is never handed truth, not even at reset. It learns where
    the system is from its first measurement, exactly as it will on power-up."""
    import inspect
    sig = inspect.signature(ZeroController().reset)
    assert list(sig.parameters) == ["p"]


def test_reset_reproduces_an_identical_command_sequence():
    c = ConstantController(1.0)
    c.reset(P)
    first = [c.update(_m(t=i * 1e-3)).a_cmd for i in range(20)]
    c.reset(P)
    second = [c.update(_m(t=i * 1e-3)).a_cmd for i in range(20)]
    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_control.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.control'`

- [ ] **Step 3: Create `dpc/control.py`**

```python
"""The controls system: measurements in, a motor command out.

The signature is the whole point of this file. A controller receives a
Measurement -- three signals, no rates, a cart position that is really a step
count -- and returns an acceleration setpoint, because an acceleration setpoint
is what a step/dir stepper can actually be told. Nothing else crosses either
boundary.

Estimation lives on this side of the wire, in the controller itself, because
that is where it runs on the MCU.

The two controllers here exist to prove the loop closes. Real control laws --
balance, swing-up, the mode logic between them -- are the next piece of work.
"""

from dataclasses import dataclass, field
from typing import Protocol

from dpc.params import Params
from dpc.sensors import Measurement


@dataclass(frozen=True)
class ControlOutput:
    """What gets written to the motor, plus whatever is worth logging."""

    a_cmd: float
    """m/s^2. Acceleration setpoint for the step generator."""

    mode: str = "idle"
    """Which law produced this. Recorded so a trace can be read after the fact."""

    info: dict = field(default_factory=dict)
    """Diagnostics only. The loop never reads this back, and nothing downstream
    may depend on it -- it does not survive transcription to C++."""


class Controller(Protocol):
    """Stateful on purpose: a real controller carries an estimator, integral
    terms, mode hysteresis and its own previous command. A plain function would
    force all of that into closures or globals."""

    def reset(self, p: Params) -> None:
        """Return to a blank internal state.

        Deliberately does not receive the initial state. The controller is
        never handed truth -- it learns where the system is from its first
        update, exactly as it does on power-up.
        """
        ...

    def update(self, m: Measurement) -> ControlOutput:
        """One control tick."""
        ...


class ZeroController:
    """Commands nothing, ever.

    Lets the whole chain -- measurement, controller, motor, plant -- run without
    perturbing the physics, which is how the plumbing gets tested separately
    from any control law.
    """

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        return ControlOutput(a_cmd=0.0, mode="idle")


class ConstantController:
    """Commands a fixed acceleration.

    Held long enough this walks the motor model through its jerk limit, then
    its acceleration saturation, then its velocity ceiling, in that order --
    which exercises every stage of the actuator without needing a control law.
    """

    __slots__ = ("a",)

    def __init__(self, a: float):
        self.a = a

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        return ControlOutput(a_cmd=self.a, mode="constant")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_control.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/control.py tests/test_control.py
git commit -m "feat: controller interface with zero and constant laws"
```

---

### Task 8: The closed loop

**Files:**
- Modify: `dpc/simulate.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `Run` (frozen, fields `t, s, meas, a_cmd, a_del, F_req, tau, x_count, mode, slipped`); `run(model, s0, controller, p, t_end, ts=None, substeps=None) -> Run`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run.py`:

```python
import numpy as np
import pytest

from dpc.control import ConstantController, ZeroController
from dpc.dynamics import accel, deriv, deriv_accel
from dpc.model import build
from dpc.params import Control, Drive, Friction, Params
from dpc.simulate import rk4_step, run, simulate

TS = 1e-3
HANGING = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])


@pytest.fixture(scope="module")
def model():
    return build()


def test_every_channel_has_one_sample_per_tick(model):
    r = run(model, HANGING, ZeroController(), Params(), t_end=0.05, ts=TS)
    n = len(r.t)
    assert n == 51
    for arr in (r.s, r.meas, r.a_cmd, r.a_del, r.F_req, r.tau, r.x_count,
                r.slipped):
        assert len(arr) == n
    assert len(r.mode) == n
    assert r.s.shape == (n, 6)
    assert r.meas.shape == (n, 3)


def test_hanging_at_rest_under_zero_command_stays_there(model):
    r = run(model, HANGING, ZeroController(), Params(), t_end=1.0, ts=TS)
    assert r.s[-1] == pytest.approx(HANGING, abs=1e-9)
    assert np.allclose(r.a_del, 0.0)
    assert not r.slipped.any()


def test_the_counter_tracks_the_truth_while_slip_is_off(model):
    p = Params(drive=Drive(slip_enable=False))
    r = run(model, HANGING, ConstantController(1.0), p, t_end=0.5, ts=TS)
    assert r.x_count[-1] == pytest.approx(r.s[-1, 0], abs=2 * p.drive.step_res)


def test_a_constant_command_walks_the_motor_through_its_limits(model):
    """Jerk first, then saturation, then the velocity ceiling."""
    p = Params(drive=Drive(a_max=2.0, v_max=0.2, jerk_max=50.0, tau_lag=0.0))
    r = run(model, HANGING, ConstantController(99.0), p, t_end=1.0, ts=TS)

    assert np.max(np.abs(np.diff(r.a_del))) <= 50.0 * TS + 1e-9
    assert np.max(r.a_del) == pytest.approx(2.0, rel=1e-6)
    assert r.a_del[-1] == pytest.approx(0.0, abs=1e-9)
    assert r.s[-1, 3] == pytest.approx(0.2, rel=0.05)


def test_torque_is_reported_against_the_budget(model):
    p = Params()
    r = run(model, HANGING, ConstantController(1.0), p, t_end=0.2, ts=TS)
    assert np.all(np.isfinite(r.tau))
    assert r.tau == pytest.approx(r.F_req * p.drive.r_pulley)


def test_the_two_drive_paths_agree_on_the_state_derivative(model):
    """The decisive cross-check, stated exactly.

    Solve the full system for a force, take the cart acceleration it produced,
    and prescribe that same acceleration instead: every state derivative must
    come back identical. If the block partition disagrees with the full solve
    anywhere, this catches it to machine precision -- the analogue of the
    energy test for the derivation.
    """
    p = Params(fric=Friction(b_cart=0.3, b1=0.01, b2=0.008,
                             c_cart=0.4, c1=0.02, c2=0.01))
    states = [
        np.zeros(6),
        np.array([0.1, 0.3, -0.2, 0.4, -0.5, 0.6]),
        np.array([-0.2, 2.9, 3.1, -0.3, 0.7, -0.8]),
    ]
    for s in states:
        for F in (0.0, 1.5, -3.0):
            full = deriv(model, s, F, p)
            prescribed = deriv_accel(model, s, full[3], p)
            assert prescribed == pytest.approx(full, abs=1e-9)


def test_replaying_the_cart_acceleration_reproduces_the_trajectory(model):
    """The same claim at trajectory level, which is necessarily looser.

    The reference lets cart acceleration vary continuously within an RK4 step;
    the replay holds one value across it. That zero-order hold is a genuine
    O(dt) difference between the two integrations, so the tolerance here is set
    by the hold, not by the physics -- the exactness lives in the derivative
    test above.
    """
    p = Params(fric=Friction(b_cart=0.3, b1=0.01, b2=0.008))
    dt = 1e-4
    s0 = np.array([0.0, 2.9, 3.2, 0.0, 0.0, 0.0])

    ref = simulate(model, s0, lambda t, s: 0.8, t_end=0.2, dt=dt, p=p)

    def f(state, u):
        return deriv_accel(model, state, u, p)

    s = s0.copy()
    for i in range(len(ref.t) - 1):
        a_cart = accel(model, ref.s[i], ref.F[i], p)[0]
        s = rk4_step(f, s, a_cart, dt)

    assert s == pytest.approx(ref.s[-1], abs=1e-4)


def test_control_rate_is_independent_of_plant_accuracy(model):
    """Halving the plant step must not move the answer; the controller ran at
    the same rate in both."""
    p = Params()
    coarse = run(model, HANGING, ConstantController(0.5), p,
                 t_end=0.3, ts=TS, substeps=5)
    fine = run(model, HANGING, ConstantController(0.5), p,
               t_end=0.3, ts=TS, substeps=40)
    assert coarse.s[-1] == pytest.approx(fine.s[-1], abs=1e-6)


def test_defaults_come_from_params(model):
    p = Params(ctrl=Control(ts=2e-3, substeps=4))
    r = run(model, HANGING, ZeroController(), p, t_end=0.02)
    assert len(r.t) == 11
    assert r.t[1] == pytest.approx(2e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py -q`
Expected: FAIL with `ImportError: cannot import name 'run' from 'dpc.simulate'`

- [ ] **Step 3: Add `Run` and `run` to `dpc/simulate.py`**

Add the imports:

```python
from dpc.control import Controller
from dpc.dynamics import deriv, deriv_accel
from dpc.motor import MotorState, step as motor_step
from dpc.sensors import measure
```

and append:

```python
@dataclass(frozen=True)
class Run:
    """A closed-loop trace, sampled once per control tick.

    Control ticks rather than plant substeps: it is what firmware could log
    over a serial link, nothing in the chain changes between ticks, and the
    arrays stay small enough to keep.

    x_count minus s[:, 0] is the step-counting error, which is the signal that
    reveals slip -- and the one the real hardware has no way to compute.
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

        if i == n:
            break

        st = mo.state
        s[i + 1] = s[i]
        for _ in range(substeps):
            s[i + 1] = rk4_step(f, s[i + 1], mo.a_del, dt)

    return Run(t=t, s=s, meas=meas, a_cmd=a_cmd, a_del=a_del, F_req=F_req,
               tau=tau, x_count=x_count, mode=mode, slipped=slipped)
```

Note the final tick computes a measurement and a command but does not advance the plant, matching how `simulate()` already handles `F[n]`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, every test in every file

- [ ] **Step 5: Commit**

```bash
git add dpc/simulate.py tests/test_run.py
git commit -m "feat: closed-loop run with controller, motor and plant"
```

---

### Task 9: Plot a run

**Files:**
- Modify: `dpc/viz.py`
- Test: `tests/test_viz.py`

**Interfaces:**
- Consumes: `simulate.Run`.
- Produces: `plot_run(r: Run, p: Params, title: str | None = None)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_viz.py`:

```python
def test_plot_run_builds_four_panels(model):
    import matplotlib
    matplotlib.use("Agg")
    from dpc.control import ConstantController
    from dpc.params import Params
    from dpc.simulate import run
    from dpc.viz import plot_run

    p = Params()
    r = run(model, np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0]),
            ConstantController(1.0), p, t_end=0.05)
    fig = plot_run(r, p)
    assert len(fig.axes) == 4
```

If `tests/test_viz.py` has no `model` fixture, reuse whatever it already builds.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_viz.py -q`
Expected: FAIL with `ImportError: cannot import name 'plot_run'`

- [ ] **Step 3: Add `plot_run` to `dpc/viz.py`**

```python
def plot_run(r, p, title: str | None = None):
    """The four panels a closed-loop trace is read from.

    Commanded against delivered acceleration gets its own panel because the gap
    between them is the whole actuator model: where they separate tells you
    which limit is binding. Torque is drawn against the budget rather than
    alone, since the number only means anything relative to what the motor has.
    """
    fig, ax = plt.subplots(4, 1, figsize=(9, 10), sharex=True)

    ax[0].plot(r.t, np.degrees(r.s[:, 1]), label=r"$\theta_1$")
    ax[0].plot(r.t, np.degrees(r.s[:, 2]), label=r"$\theta_2$")
    ax[0].axhline(0.0, lw=0.5, color="k")
    ax[0].set_ylabel("angle [deg]")
    ax[0].legend(loc="upper right")
    if title:
        ax[0].set_title(title)

    ax[1].plot(r.t, r.s[:, 0], label="true")
    ax[1].plot(r.t, r.x_count, ls="--", label="step count")
    ax[1].set_ylabel("cart $x$ [m]")
    ax[1].legend(loc="upper right")

    ax[2].plot(r.t, r.a_cmd, label="commanded")
    ax[2].plot(r.t, r.a_del, label="delivered")
    ax[2].axhline(p.drive.a_max, lw=0.5, ls=":", color="k")
    ax[2].axhline(-p.drive.a_max, lw=0.5, ls=":", color="k")
    ax[2].set_ylabel(r"$\ddot{x}$ [m/s$^2$]")
    ax[2].legend(loc="upper right")

    ax[3].plot(r.t, r.tau)
    ax[3].axhline(p.drive.tau_budget, lw=0.5, ls=":", color="k")
    ax[3].axhline(-p.drive.tau_budget, lw=0.5, ls=":", color="k")
    ax[3].set_ylabel(r"$\tau_{motor}$ [N m]")
    ax[3].set_xlabel("time [s]")

    fig.tight_layout()
    return fig
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/viz.py tests/test_viz.py
git commit -m "feat: closed-loop trace plots"
```

---

## Done when

- `python -m pytest -q` is green, including the six pre-existing physics files with no tolerance changes.
- A control law can be added to `dpc/control.py` and evaluated through `run()` with no other file touched.
- `Measurement` still contains no rate, and no module outside `params.py` holds a numeric constant.
