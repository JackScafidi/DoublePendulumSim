"""The step generator: a controller's acceleration command in, the cart's
actual acceleration out.

A step/dir stepper has no torque input. What leaves the MCU is a direction
level and a step frequency, reloaded once per control tick, so what the
controller really writes is a bounded change in step rate -- an acceleration.
Everything here is the gap between the acceleration asked for and the one the
hardware can produce.

Stages are applied in the order the hardware applies them, ending with the end
stop: the rail is finite, and a generator that kept ramping its rate into a
wall would carry a counter that claims a position the rail does not have. The
plant enforces the same wall on the true state -- the two are separate because
the counter is a belief and the state is the truth, and slip is precisely the
case where they differ.

This file, minus the slip check, is transcribed to C++ next milestone:
fixed-size arithmetic, explicit branches, no allocation.
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

    n_pin: int = 0
    """Control ticks spent against an end stop."""

    slip_accum: float = 0.0
    """m/s. Velocity error banked by slip: the difference between what was
    counted and what was delivered."""


@dataclass(frozen=True)
class MotorOut:
    """One tick's result.

    F_req and tau are computed whether or not slip is enabled, because they are
    the diagnostics worth logging either way.
    """

    a_del: float
    """m/s^2 actually delivered to the cart."""

    F_req: float
    """N the plant required in order to produce it."""

    tau: float
    """N m at the motor shaft."""

    slipped: bool
    """Whether the torque budget was exceeded on this tick."""

    pinned: bool
    """Whether the counter was held against an end stop on this tick."""

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

    # 6. End stop. The firmware clamps its own motion at the stop, and a
    #    generator delivers nothing into a wall: the step rate goes to zero,
    #    so the delivered acceleration goes with it and the plant has nothing
    #    to integrate. The true cart is held by the plant-side impact instead,
    #    so the links see a fixed pivot, and the only impulse they ever feel is
    #    the one real contact -- not a fresh kick on every tick spent parked.
    #
    #    Zeroing the lag state too means a command pulling AWAY lands strictly
    #    inside the rail on the same tick -- v_count is zero and 0.5 a dt^2 is
    #    inward -- so the counter releases and ramps from rest. Pinning is a
    #    condition, not a latch.
    #
    #    What is NOT modelled is stall torque: tau below still comes from the
    #    free plant, so driving into a stop never registers as slip. That is a
    #    decision deferred rather than an oversight -- the holding torque of a
    #    stalled rotor is a curve nobody here has measured.
    #
    #    Last, after slip, so the counter is clamped whatever else happened to
    #    it this tick.
    a_lag = a_del
    pinned = False
    n_pin = st.n_pin

    # dpc.rail.side, written out: this file is on the MCU side of the wire and
    # does not get to depend on the plant.
    sgn = 0
    if x_count <= -p.x_lim:
        sgn = -1
    elif x_count >= p.x_lim:
        sgn = 1

    if sgn != 0:
        x_count = sgn * p.x_lim
        v_count = 0.0
        a_del = 0.0
        a_lag = 0.0
        n_pin = n_pin + 1
        pinned = True
        # One extra solve, on pinned ticks only, so the torque trace reads what
        # the motor is holding against a stationary pivot rather than a figure
        # for an acceleration that was never delivered.
        qdd_l = link_accel(model, s, a_del, p)
        F_req = required_force(model, s, a_del, qdd_l, p)
        tau = motor_torque(F_req, p)

    return MotorOut(
        a_del=a_del,
        F_req=F_req,
        tau=tau,
        slipped=slipped,
        pinned=pinned,
        state=replace(st, a_lag=a_lag, v_count=v_count, x_count=x_count,
                      n_slip=n_slip, slip_accum=slip_accum, n_pin=n_pin),
    )
