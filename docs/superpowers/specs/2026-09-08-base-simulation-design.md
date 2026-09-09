# Base Simulation Design

*2026-09-08*

## Goal

Complete the boilerplate base simulation: a closed loop running
controller -> motor -> plant, in which the controller receives only the signals
the real hardware will deliver and emits only the command the real hardware will
accept.

The milestone is finished when a control law can be dropped into `dpc/control.py`
and evaluated end to end without touching any other file.

Explicitly out of scope: any actual control law (LQR, MPC, swing-up), state
estimation beyond rate reconstruction, parameter fitting, and automatic tuning.

## Hardware premise

Open-loop stepper drive: NEMA-17 through a TMC2209 onto a 20T GT2 belt,
`r_pulley = 6.4 mm`. This is already implied by `params.py`, where `m_rotor` is
the equivalent mass `J / r^2` seen through that pulley.

The premise has one decisive consequence. **A step/dir stepper has no torque
input.** What leaves the MCU is a DIR level and STEP pulses at a frequency
reloaded once per control tick. A step rate is a velocity; a bounded change in
step rate is an acceleration. So the command the controller emits is an
**acceleration setpoint**, and everything else in this design follows from that.

## Architecture

The plant becomes **acceleration-driven** rather than force-driven. Cart
acceleration is a prescribed input; the equations are solved for the link
accelerations and read backwards for the force the motor had to supply.

This requires no new derivation. It is a block partition of the matrices
`model.py` already produces. With `q = [x | theta1 theta2]`:

```
[ M00  M0l ] [ xdd ]   [ C0 ]   [ G0 ]   [ f0 ]   [ F ]
[ Ml0  Mll ] [ qddl] + [ Cl ] + [ Gl ] + [ fl ] = [ 0 ]
```

Force-driven solves all three rows for `qdd`. Acceleration-driven takes `xdd` as
given, solves rows 2-3 (a 2x2 system) for `qddl`, then evaluates row 1 to obtain
the required force and hence `tau_motor = F * r_pulley`.

### Why acceleration-driven is the better control model

The badly-conditioned parameters live almost entirely in row 1. `m_cart`,
`m_rotor`, `b_cart` and `c_cart` appear in the required-force expression and
**nowhere in the link accelerations**. When the controller commands acceleration,
the step generator enforces it regardless of those quantities, so row 1 leaves
the control-relevant model entirely and the plant the controller must know
depends only on `m1, m2, lc1, lc2, I1, I2, l1, g` -- the parameters measurable
with calipers and a scale.

A force-driven model inverts this: hitting an intended acceleration would require
accurately fitting the worst-conditioned parameters in the set, to obtain
something the hardware supplies for free.

The apparent loss -- force is no longer a directly saturable input -- is not a
real loss, because the hardware has no force input either. In exchange
`tau_motor` becomes a computed diagnostic available every tick, which is what
step-loss detection needs.

## Module layout

Constants stay in one file; each layer above it is a strictly thinner
abstraction over the one below.

| File | Responsibility | Status |
|---|---|---|
| `dpc/params.py` | every physical constant, plus the new drive block | extend |
| `dpc/model.py` | symbolic derivation; evaluation of `M`, `Cqd`, `G`, `Ffric`, energy | narrow |
| `dpc/dynamics.py` | force calculations: both drive paths, required force, motor torque | new |
| `dpc/motor.py` | command -> hardware realities -> delivered acceleration; owns the step counter | new |
| `dpc/sensors.py` | true state + motor state -> `Measurement` | new |
| `dpc/estimate.py` | `RateEstimator`: angles -> angular rates | new |
| `dpc/control.py` | `Measurement` -> `ControlOutput`; the controls system | new |
| `dpc/simulate.py` | open-loop `simulate()`; new closed-loop `run()` | extend |
| `dpc/linearize.py` | finite-difference linearisation | call-site update |
| `dpc/viz.py` | plots | extend |

### `model.py` narrows

`NumericModel.accel` and `NumericModel.deriv` move to `dynamics.py` as free
functions taking the model as their first argument. `model.py` is then solely
concerned with what the terms *are*; `dynamics.py` with what is done with them.
This touches about a dozen call sites in `tests/test_numeric.py` plus `linearize.py` and
`simulate.py`. Every change is mechanical -- `M.accel(s, F, P)` becomes
`accel(M, s, F, P)` -- and no assertion value changes.

## Interfaces

### The wire boundary

The boundary between hardware and software is the physical wire, and the
`Measurement` struct is that boundary made explicit. It carries the three signals
firmware actually has and nothing else.

```python
@dataclass(frozen=True)
class Measurement:
    t: float          # s, tick timestamp
    th1: float        # rad, encoder 1 -- quantised on hardware
    th2: float        # rad, encoder 2 -- quantised on hardware
    x_count: float    # m, from the COMMANDED step total. Not a sensor.
    dt: float         # s, control period this reading belongs to
```

`xdot`, `theta1dot` and `theta2dot` are absent because the hardware does not
measure them. Any controller needing rates must reconstruct them from what it is
given, exactly as it will on the bench. `x_count` is not a sensor reading either:
it is a running total of commanded steps, and it diverges silently from the true
position when the motor slips.

Today `sensors.measure()` populates all three from truth, without noise,
quantisation or drift. Each of those is a later edit to that one function, and no
controller changes when they land.

### The controller

```python
@dataclass(frozen=True)
class ControlOutput:
    a_cmd: float                # m/s^2, acceleration setpoint for the step generator
    mode: str = "idle"          # "balance" | "swingup" | "idle"
    info: dict = field(default_factory=dict)   # diagnostics; never read back


class Controller(Protocol):
    def reset(self, p: Params) -> None: ...
    def update(self, m: Measurement) -> ControlOutput: ...
```

Three properties this fixes:

- **Stateful.** A real controller carries an estimator, integral terms, mode
  hysteresis and the previous command. A pure function forces those into closures
  or globals. `reset()` allows a clean re-run without reconstructing the object.
- **`dt` arrives with the measurement; the controller never reads a clock.** The
  same class therefore runs at any rate, in simulation or on the target, without
  edits, and a test can run it at two rates to check consistency.
- **Estimation lives inside the controller.** The only real boundary is the wire,
  and estimation is on the controller's side of it -- as it is on the MCU.
  `estimate.RateEstimator` is composed by controllers that need rates.

`reset()` deliberately does **not** receive the initial state: the controller
is never handed truth, only measurements. It resets to a blank internal state and
learns where the system is from its first `update()`.

Shipped implementations, sufficient to prove the loop closes and nothing more:

- `ZeroController` -- commands `0.0` always. Lets the full chain run without
  perturbing the physics.
- `ConstantController(a)` -- commands a fixed acceleration, driving the motor
  model into its jerk limit, its saturation and its velocity ceiling.

### The motor

`motor.py` applies hardware effects in the order the hardware applies them:

1. **Jerk limit.** The step generator ramps its rate; `|da| <= jerk_max * ts`.
2. **Acceleration saturation.** `|a| <= a_max`, set by torque through the pulley.
3. **Velocity ceiling, one-sided.** Beyond `v_max` the step rate is
   unsustainable, so acceleration is clamped only in the direction that would
   increase speed. Deceleration is always permitted.
4. **Step quantisation.** The velocity increment is realisable only in whole
   microsteps, which is what makes `x_count` genuinely discrete.
5. **First-order lag**, `tau_lag`, for the step generator's finite bandwidth.
   Discretised exactly as `alpha = 1 - exp(-dt/tau)`. Backward Euler is not
   acceptable here: the resulting few-percent error is amplified by the unstable
   plant and puts the model and the target visibly out of agreement.
6. **Slip.** The torque demanded by the acceleration surviving stages 1-5 is
   obtained from `dynamics.required_force`, which is why `motor.step()` takes the
   model and the true state. If it
   exceeds `tau_hold * tau_derate`, only the fraction the motor can back up is
   delivered and the remainder is banked as step-counter error.

```python
@dataclass
class MotorState:
    a_lag: float = 0.0        # m/s^2, lag filter state
    x_count: float = 0.0      # m, position implied by commanded steps
    steps: int = 0            # integer step total
    n_slip: int = 0           # ticks where torque demand exceeded budget
    slip_accum: float = 0.0   # m/s, velocity error banked by slip
```

`motor.py` owns the step counter, because the counter is a property of the step
generator. `sensors.measure()` reads `x_count` from the motor and the angles from
truth.

Slip is implemented now but gated behind `slip_enable: bool = False`. It is the
only mechanism that makes `x_count` differ from the truth, so without it that
field is decorative; defaulting it off keeps the base simulation clean until the
question is deliberately asked.

### Drive parameters

Added to `params.py`. Provisional, to be constrained as the hardware is finalised.

| Parameter | Value | Source |
|---|---|---|
| `r_pulley` | 6.4 mm | implied by `m_rotor = J / r^2` |
| `steps_per_rev` | 200 | NEMA-17, 1.8 deg |
| `microsteps` | 16 | TMC2209 |
| step resolution | 12.6 um | `2*pi*r / 3200`, derived not stored |
| `tau_hold` | 0.40 N m | typical 42x40 mm NEMA-17 |
| `tau_derate` | 0.5 | torque falls off with step rate |
| `a_max` | 10 m/s^2 | `tau/r` over the equivalent moving mass, derated |
| `v_max` | 0.5 m/s | 40 kHz microstep ceiling |
| `jerk_max` | 200 m/s^3 | provisional |
| `tau_lag` | 3 ms | inner-loop bandwidth stand-in |
| `slip_enable` | `False` | see above |

## The simulation loop

Two clocks. The plant integrates at `dt`; the controller runs at `ts`. The
separation is what allows the control rate to be varied without disturbing the
physics.

```python
for each control tick:                         # ts = 1 ms
    m       = sensors.measure(t, s_true, motor, ts, p)
    out     = controller.update(m)
    a_del, motor = motor.step(model, out.a_cmd, s_true, motor, ts, p)
    for k in range(substeps):                  # dt = ts / 10
        s_true = rk4_step(deriv_accel, s_true, a_del, dt, p)
```

**The motor updates once per control tick and `a_delivered` is held across the
substeps.** This is faithful, not simplified: the step-rate timer is reloaded once
per tick, so the jerk limiter, saturation, quantiser and lag are all genuinely
discrete at `ts`. Running them at the substep rate would make the simulation
disagree with the firmware. The substeps exist only so that plant integration
error stays well below the effects under study.

Defaults `ts = 1e-3`, `substeps = 10`, both settable.

`rk4_step` is generalised to `rk4_step(f, s, u, dt)`, taking a derivative
callable. Both drive modes then share one integrator: force-driven passes
`deriv` with `u = F`, stepper mode passes `deriv_accel` with `u = a_delivered`.
The four-evaluation structure measured by the convergence test is unchanged.

### Two entry points

`simulate(model, s0, force, t_end, dt, p) -> Trajectory` is **unchanged**:
open-loop, force-driven, no controller and no motor. The six physics tests
continue to use it, because energy conservation and RK4 convergence are
statements about the plant, and routing them through a controller would only
obscure what is being measured.

`run(model, s0, controller, p, ts, substeps, t_end) -> Run` is new, and is the
full chain.

A single unified loop with a mode flag was rejected: the two have different
inputs, different outputs and different reasons to exist, and fusing them makes
every physics test carry machinery it does not use.

```python
@dataclass(frozen=True)
class Run:
    t: np.ndarray          # (n,)   control tick times
    s: np.ndarray          # (n, 6) true state
    meas: np.ndarray       # (n, 3) [th1, th2, x_count] as the controller saw them
    a_cmd: np.ndarray      # (n,)   requested acceleration
    a_del: np.ndarray      # (n,)   delivered acceleration
    F_req: np.ndarray      # (n,)   force the plant required
    tau: np.ndarray        # (n,)   motor torque
    x_count: np.ndarray    # (n,)   step-counted position
    mode: list[str]        # (n,)   active law
    slipped: np.ndarray    # (n,)   bool
```

Logging happens at control ticks rather than substeps: it is what firmware could
log over a serial link, nothing in the chain changes between ticks, and
`x_count - s[:, 0]` is then directly the slip-drift signal.

## Testing

The existing six physics test files must keep passing with no change beyond the
mechanical rename. They are the primary safety net: any tolerance shift in
`test_energy`, `test_integrator` or `test_degenerate` means the refactor broke
the plant.

**`test_dynamics.py` additions.** Two tests carry the weight:

- *Round-trip.* For any state and force `F`, compute `qdd` force-driven, feed
  `qdd[0]` to `link_accel` and recover `qdd[1:]`, then feed both to
  `required_force` and recover `F`. Any sign or index error in the partition
  fails this at every state.
- *Rail invariance.* Perturbing `b_cart`, `c_cart`, `m_cart` or `m_rotor` leaves
  `link_accel` unchanged to machine precision while `required_force` moves. This
  promotes the central architectural claim from an argument to an assertion.

**`test_motor.py`.** One test per stage, each isolating its stage by neutralising
the others: jerk bound; saturation; the one-sidedness of the velocity ceiling
(its own test, because a two-sided clamp yields a cart that cannot brake); lag
reaching 63.2% at `t = tau_lag`; velocity increments as integer multiples of the
step resolution; slip off by default and `x_count` diverging with `n_slip`
incrementing when enabled; a zero command from rest leaving the state untouched.

**`test_control.py`.** `ZeroController` commands zero for any state.
`ConstantController` drives the motor into each limit in turn. `reset()`
reproduces an identical command sequence. One structural test asserts that
`Measurement` has no rate fields, which is what prevents a future controller from
quietly acquiring clairvoyance.

**`test_estimate.py`.** `RateEstimator` recovers the rate of an analytic signal
within its characterised lag.

**`test_sensors.py`.** `measure()` is currently the identity on angles, and takes
`x_count` from the motor rather than from truth.

**`test_run.py`.** End to end. `ZeroController` from hanging rest stays at rest.
Every `Run` array has length `n`. And the decisive one:

- *Cross-path agreement.* Run force-driven `simulate()`, extract `xdd(t)`, replay
  it through the acceleration-driven path, and require the trajectories to agree
  to integration tolerance. This is the sharpest check that both halves of
  `dynamics.py` describe the same physics -- the analogue of the
  energy-conservation test for the derivation.

No controller-performance tests: there is no control law yet to have performance.

## Constraints carried forward

- No physical numeric value appears outside `params.py`.
- State ordering `s = [x, th1, th2, xdot, w1, w2]`; generalised coordinates
  `q = [x, th1, th2]`. Angles absolute from vertical, positive toward `+x`.
- `m_rotor` is an equivalent mass. It appears in kinetic energy only, never in
  potential energy or a normal-force term.
- `M`, `Cqd`, `G` and the friction vector stay separately accessible.
- Fixed-step RK4 only.
- Only `drive="rigid"` is implemented.

## Forward compatibility

Everything between `Measurement` in and `a_cmd` out is code that will run on the
STM32: `estimate.py`, `control.py`, and the command-generation half of
`motor.py`. It is written to the existing C-transcription constraint -- fixed-size
arrays, explicit indexing, no Python-specific constructs, `info` dicts strictly
diagnostic and never read back by the loop.

The next milestone ports exactly that set to C++ (C++17, Eigen, nanobind), runs
the same source in simulation and on the target, and accepts it by
differential-testing the C++ controller against this Python reference over many
random states. Nothing in this milestone should make that port harder.
