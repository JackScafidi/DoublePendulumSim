# Double pendulum on a cart — ideal test bench

Design for milestone 1 of a rebuilt simulation and control stack.

## Context

An earlier, complete version of this project exists in `_reference/` (MATLAB,
gitignored, local only). It is being rebuilt from scratch so the engineering is
derived rather than inherited.

The long arc is:

1. **Ideal controls problem** — frictionless and force-driven, but with
   realistic nominal parameter values and every correction factor at unity.
2. **Real physics** — an automatic tuner adjusts the correction factors until
   the model matches measured hardware data.
3. **Hardware** — hand-written C on an STM32 Nucleo-H743ZI2 driving a belted cart.

This document covers milestone 1 only, but every decision in it is made with
stages 2 and 3 in view.

## Goals

Produce a simulator that is *demonstrably* correct, not merely plausible. The
milestone is complete when the plant can be run from an arbitrary initial state
and four independent tests confirm the physics.

No controller is written in this milestone.

## The physical model

### System

A cart moving on a horizontal rail, carrying a two-link pendulum. Three degrees
of freedom, one actuator: underactuated.

Both links are modelled as **general rigid bodies** — each has mass, length, a
centre-of-mass offset, and its own rotational inertia. Point masses and uniform
rods are recovered as special cases by choosing parameter values. This
generality is not decoration: real pendulum arms carry an encoder body at one
end and a clamp at the other, so their true centre of mass is not at midspan
and their true inertia is not the textbook formula. Without these parameters,
stage 2 could not fit the model to hardware.

### Coordinates

- `x` — cart position, positive to the right.
- `theta_1`, `theta_2` — link angles measured from **straight up**, positive
  tipping the link toward `+x`, both **absolute** (measured from vertical, not
  from the preceding link). A link at angle `theta` points along
  `(sin(theta), cos(theta))`.
- Gravity acts in `-y`.

Positive-toward-`+x` is clockwise on standard axes, not counter-clockwise. It
is chosen deliberately: the cart force is positive toward `+x`, and correcting
a pendulum that has fallen toward `+theta` requires driving the cart toward
`+x`. Input and error therefore share a sign, which keeps the control gains
positive and the arithmetic aligned with intuition. It is also the convention
used throughout the cart-pole literature.

Upright is therefore the origin. This is chosen because the control target is
the inverted equilibrium: linearisation happens at zero, the LQR state is
naturally small near the goal, and no offset is carried through the controller.

Absolute angles make the equations symmetric in the two links and easier to
sanity-check. The cost is that the hardware disagrees — the elbow encoder reads
a *relative* angle, so the mapping `theta_2 = theta_1 + theta_elbow` will be
written as an explicit, tested sensor-model function rather than being applied
ad hoc.

### Input

Force `F` applied to the cart. Forward dynamics: force is specified, motion is
solved for.

This is the textbook underactuated formulation, chosen so results can be
compared against published work. It does not match the eventual hardware, where
a stepper prescribes cart *position* and the force is an output rather than an
input. That inverse direction is a rearrangement of the same equations and will
be added when needed; it is deliberately not built now.

When it is added, it earns its place twice over: under prescribed cart motion
the row-1 equation returns the force the motor must supply, which is the torque
budget. A stepper behaves kinematically only while it has torque margin; past
that it drops steps, and since cart position is inferred from step count, the
state estimate then fails silently.

### Equations

Standard manipulator form, with `q = [x, theta_1, theta_2]`:

    M(q) qddot + C(q, qdot) qdot + G(q) + F_fric(qdot) = B u,    B = [1, 0, 0]^T

`M`, `C`, `G` and the friction term stay **separately accessible** rather than
fused into a single expression. Energy-shaping swing-up needs `G` alone; the
linearisation is cleaner term by term; and the C transcription wants them
separate.

### State vector

    s = [x, theta_1, theta_2, xdot, theta_1dot, theta_2dot]

Positions first, then velocities, so the linearised `A` matrix comes out in the
standard block form expected by the LQR and Kalman filter.

## Parameters

Every physical constant lives in `params.py`. No numeric physical value appears
anywhere else in the codebase; every function takes a parameter object.

### Two layers: nominal times correction

Each uncertain quantity is expressed as a **nominal** — a best real-world
estimate in real units, from CAD, a datasheet, or a scale — multiplied by a
**dimensionless correction factor** that defaults to `1.0`:

    m1_effective = m1_nominal * k_m1

The engineer owns the nominals. The stage-2 auto-tuner owns the corrections and
never modifies a nominal. Simulation runs in real units from the start; the
ideal case is not non-dimensional.

This structure is chosen for four reasons:

- **Scaling.** Every unknown the optimiser sees is a dimensionless number near
  one, rather than a mass at `0.04` beside an inertia at `1.5e-4`. Gradient
  methods behave far better on that.
- **Priors.** "Trusted to ten percent" is `k` in `[0.9, 1.1]` for every
  parameter, independent of units.
- **Regularisation.** A penalty on `(k - 1)^2` makes the fitter prefer
  explanations close to measurement, straying only when the data insists.
  Without it, a fitter will happily return a four-kilogram pendulum arm that
  fits the noise beautifully.
- **Diagnosis.** A correction far from one is not a tuned parameter, it is a
  message: the CAD is wrong, or the model is missing a term.

### Which parameters get corrections

| Kind | Parameters | Form |
|---|---|---|
| Known nominal, uncertain scale | masses, COM offsets, inertias | `nominal * k`, `k` starts at `1.0` |
| No meaningful nominal | `b_*`, `c_*`, `phi` | fitted directly, starts at `0.0` |
| Measured directly | `l1`, `l2` | fixed, no correction |
| Known | `g` | fixed, no correction |

Friction and rail tilt cannot be multiplicative: their nominal is zero, and
`0 * k` is zero forever. They are fitted as absolute values.

Lengths are fixed because they are measurable with calipers to a fraction of a
percent. Leaving them free would let the fitter trade length against mass to
explain the same data, degrading conditioning for no gain in fidelity.

`g` is fixed deliberately. A correction factor on gravity would become a sponge
absorbing scale errors from everywhere else, rendering the remaining fit
meaningless.

### Nominal values

| Parameter | Nominal | Source | Correction |
|---|---|---|---|
| `m_cart` | 0.30 kg | carriage, bracket, belt clamp | yes |
| `m_rotor` | 1.33 kg | rotor inertia through the pulley | yes |
| `m1` | 0.075 kg | link 1 rod plus elbow encoder body | yes |
| `m2` | 0.045 kg | link 2 rod | yes |
| `l1`, `l2` | 0.20 m | measured | no |
| `lc1` | 0.12 m | biased outward by the elbow encoder | yes |
| `lc2` | 0.10 m | near midspan | yes |
| `I1` | 3.0e-4 kg m^2 | about link 1's own COM | yes |
| `I2` | 1.5e-4 kg m^2 | about link 2's own COM | yes |
| `g` | 9.81 m/s^2 | known | no |
| `b_cart`, `b1`, `b2` | 0.0 | viscous friction | fitted directly |
| `c_cart`, `c1`, `c2` | 0.0 | Coulomb friction | fitted directly |
| `eps_fric` | 1e-3 | Coulomb smoothing width | fixed |
| `phi` | 0.0 | rail tilt from horizontal | fitted directly |

### Why cart mass is split

`m_cart` is real mass. `m_rotor` is not mass at all: it is the motor
rotor's rotational inertia in disguise.

The belt ties rotor angle to cart position by `x = r * theta_m`, so rotor
kinetic energy becomes

    T_rotor = (1/2) J theta_m_dot^2 = (1/2) (J / r^2) xdot^2

which is exactly the kinetic energy of a mass `J / r^2` translating at `xdot`.
The Lagrangian cannot distinguish the two. With a 20T GT2 pulley the effective
radius is only 6.4 mm, so dividing by `r^2` multiplies rotor inertia by roughly
25,000 and yields about 1.33 kg — four times the cart's mechanical mass. The
cart is, dynamically, mostly motor.

The two are kept separate because they behave differently in three places:

1. **Gravity.** On a tilted rail the downhill force is
   `m_cart * g * sin(phi)`. Reflected inertia contributes nothing — a
   spinning rotor is not pulled downhill. Lumping the two would make the tilt
   term wrong by roughly a factor of five.
2. **Coulomb friction.** Normal force comes from real weight, so again only
   mechanical mass and the pendulum's weight participate.
3. **Uncertainty.** Mechanical mass is weighable to a percent. Reflected
   inertia derives from a datasheet figure that varies 2.5x across NEMA 17
   vendors. Separate corrections let the tuner fix the uncertain one without
   corrupting the known one.

`m_rotor` is also a design choice rather than a fact: a 40T pulley quarters
it, at the cost of halving force resolution per step. Worth revisiting once
cart agility is observed.

### Friction and drag

Friction is present as a knob but exactly zero in the ideal preset, so the
system is genuinely conservative and energy conservation becomes a hard test
rather than an approximate one.

Rail tilt is included despite looking pedantic: a rail half a degree off level
is a common and real system-identification finding, and without the parameter a
fitter will distort other values trying to explain the resulting bias.

Coulomb friction, when nonzero, is non-smooth and would break linearisation and
gradient-based tuning, so it is implemented as a smoothed approximation with a
width parameter.

Quadratic aerodynamic drag is deliberately **excluded** until measured data
demands it.

## Architecture

    dpc/
      params.py     every physical constant, one place
      model.py      config, symbolic derivation, numeric functions
      simulate.py   fixed-step RK4 and trajectory container
      viz.py        time-series plots
    tests/
      test_energy.py
      test_degenerate.py
      test_linearisation.py
      test_integrator.py
    docs/
    pyproject.toml

### Derivation is programmatic

The requirement is that the model never needs hand-re-deriving: all future
change should happen by configuration and parameter values.

A single maximal model covering every future effect is not achievable. Some
effects are genuinely parameterisable — Coulomb friction, drag, rail tilt, tip
payload, reflected rotor inertia — because they add *terms* to equations that
already exist, and vanish exactly at zero. Others are not: belt compliance and
actuator lag each add **states**, and their ideal limits (`k -> infinity`,
`tau -> 0`) are singular. They cannot be reached by setting a number, and
approaching them makes the system violently stiff.

The resolution is to make the derivation itself programmatic rather than to
make one enormous model. Because SymPy performs the algebra, re-deriving costs
a function call.

    @dataclass(frozen=True)
    class ModelConfig:
        drive:     "rigid" | "compliant"           = "rigid"
        friction:  "viscous" | "viscous+coulomb"   = "viscous+coulomb"
        rail_tilt: bool                            = True

`derive(config)` assembles the Lagrangian from this description and returns a
`Model` exposing the mass matrix, the forcing terms, and fast numeric functions
for acceleration, energy, and linearisation.

Only the `rigid` branch is implemented in this milestone. `compliant` exists as
a named, unimplemented seam so the shape is correct when hardware needs it.

This covers the class of effects that can currently be named. Something outside
it — flexible links, a bending rail — would still require new code. No
architecture prevents that, and the spec does not claim otherwise.

### Derivation and numeric code are one artifact

`model.py` owns the SymPy derivation and lambdifies it into numeric functions,
with a transparent on-disk cache keyed to the source so the cost is paid once.
There is no separately committed generated-code file, so the equations and the
executing code cannot drift apart.

The eventual C transcription is not blocked by this: SymPy emits C expressions
on demand, which is a better source than hand-copied Python.

### Written for later transcription

Control-path arithmetic is written in a C-translatable style — fixed-size
arrays, explicit loops, no Python-specific constructs — so that generating
embedded C later is transcription rather than a rewrite. Simulation, plotting,
and tuning code around it has no such constraint.

## Integration

Fixed-step RK4, and only that. It matches how a real controller runs: fixed
sample rate, fixed step. Keeping the simulator on the same footing as the
target avoids a class of discrepancy that would otherwise appear at the
hardware transition.

Accuracy is verified by **step halving**: running at `dt` and `dt/2` and
applying Richardson extrapolation yields both the observed convergence order
and an error estimate, with no second integrator and no additional dependency.

Adaptive and symplectic integrators were considered and rejected — adaptive
because variable steps correspond to nothing the embedded target can do, and
symplectic because its energy advantage largely disappears once friction and
control forces are present.

## Verification

Four tests, which are the substance of the milestone.

1. **Energy conservation.** All friction zero, no applied force. Total energy
   must stay flat within the integrator's error bound. Catches most derivation
   errors at once, though it does not localise them.
2. **Degenerate cases.** With `m2 = 0` and `I2 = 0` the system must reduce
   exactly to a single pendulum on a cart. With the cart held fixed it must
   reduce to a plain double pendulum. Both have known behaviour, and unlike the
   energy test these localise an error to a specific term.
3. **Small-angle agreement.** Near upright, with small displacements, the
   nonlinear model must track the linearised model. This validates the
   linearisation the LQR will later be built on.
4. **Integrator convergence order.** Halving the timestep must reduce error by
   the factor RK4 promises. Confirms the integrator independently of whether
   the physics is right.

## Out of scope for this milestone

- Any controller. LQR, energy-shaping swing-up, and MPC will be **hand-derived**
  in a later session and coded from that derivation.
- Animation. Time-series plots only for now.
- State estimation, sensor models, actuator models.
- The parameter auto-tuner.
- Belt compliance, C generation, hardware.
