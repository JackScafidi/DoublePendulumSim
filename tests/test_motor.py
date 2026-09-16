"""Each stage of the motor model gets its own test, and each test neutralises
the other stages, so a failure names one mechanism rather than the chain."""

from dataclasses import replace

import numpy as np
import pytest

from dpc.model import ModelConfig, build
from dpc.motor import MotorState, step, step_count
from dpc.params import Control, Drive, Params

M = build(ModelConfig())
TS = 1e-3
REST = np.zeros(6)


RELAXED = Drive(a_max=1e6, v_max=1e6, jerk_max=1e12, tau_lag=0.0,
                slip_enable=False)
"""Every limit wound out of the way. A test reinstates only the one it is
about, so a failure names one stage of the motor model."""


def _p(**drive) -> Params:
    """A parameter set with every limit relaxed except the ones named."""
    return Params(drive=replace(RELAXED, **drive), ctrl=Control(ts=TS))


def test_zero_command_from_rest_changes_nothing():
    p = _p()
    out = step(M, 0.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(0.0)
    assert out.state.v_count == pytest.approx(0.0)
    assert out.state.x_count == pytest.approx(0.0)
    assert out.slipped is False


def test_jerk_limits_the_change_in_acceleration():
    p = _p(jerk_max=100.0)
    out = step(M, 50.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(100.0 * TS)


def test_jerk_limit_is_symmetric():
    p = _p(jerk_max=100.0)
    out = step(M, -50.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(-100.0 * TS)


def test_acceleration_saturates():
    p = _p(a_max=3.0)
    assert step(M, 99.0, REST, MotorState(), TS, p).a_del == pytest.approx(3.0)
    assert step(M, -99.0, REST, MotorState(), TS, p).a_del == pytest.approx(-3.0)


def test_velocity_ceiling_blocks_speeding_up():
    p = _p(v_max=0.5)
    st = MotorState(v_count=0.5)
    assert step(M, 5.0, REST, st, TS, p).a_del == pytest.approx(0.0)


def test_velocity_ceiling_still_allows_braking():
    """One-sided on purpose. A two-sided clamp builds a cart that cannot stop."""
    p = _p(v_max=0.5)
    st = MotorState(v_count=0.5)
    assert step(M, -5.0, REST, st, TS, p).a_del == pytest.approx(-5.0)

    st_rev = MotorState(v_count=-0.5)
    assert step(M, -5.0, REST, st_rev, TS, p).a_del == pytest.approx(0.0)
    assert step(M, 5.0, REST, st_rev, TS, p).a_del == pytest.approx(5.0)


def test_the_ceiling_clamps_against_the_counter_not_the_truth():
    """The generator has no velocity sensor. It knows only the rate it is
    generating, so a cart that is really moving fast while the counter says
    otherwise gets no protection -- which is the honest behaviour."""
    p = _p(v_max=0.5)
    fast_truth = np.array([0.0, 0.0, 0.0, 99.0, 0.0, 0.0])
    assert step(M, 5.0, fast_truth, MotorState(), TS, p).a_del == pytest.approx(5.0)


def test_lag_reaches_63_percent_at_one_time_constant():
    tau = 10e-3
    p = _p(tau_lag=tau)
    st = MotorState()
    for _ in range(int(round(tau / TS))):
        st = step(M, 1.0, REST, st, TS, p).state
    assert st.a_lag == pytest.approx(1.0 - np.exp(-1.0), rel=1e-9)


def test_lag_is_the_exact_zoh_response_not_backward_euler():
    """Backward Euler would give dt/(tau+dt) after one step. The gap is a few
    percent, and an unstable plant amplifies it until the model and the target
    visibly disagree."""
    tau = 10e-3
    p = _p(tau_lag=tau)
    out = step(M, 1.0, REST, MotorState(), TS, p)
    assert out.a_del == pytest.approx(1.0 - np.exp(-TS / tau))
    assert out.a_del != pytest.approx(TS / (tau + TS), rel=1e-3)


def test_step_count_is_an_integer_number_of_microsteps():
    p = _p()
    res = p.drive.step_res
    assert step_count(MotorState(x_count=10.4 * res), p) == 10
    assert step_count(MotorState(x_count=-10.6 * res), p) == -11


def test_counter_advances_with_the_commanded_velocity():
    p = _p()
    st = MotorState()
    for _ in range(100):
        st = step(M, 1.0, REST, st, TS, p).state
    assert st.v_count == pytest.approx(0.1)
    assert st.x_count > 0.0


def test_required_force_is_reported_even_with_slip_disabled():
    p = _p()
    out = step(M, 2.0, REST, MotorState(), TS, p)
    assert out.tau == pytest.approx(out.F_req * p.drive.r_pulley)
    assert out.F_req != 0.0


def test_no_slip_when_disabled_even_under_impossible_demand():
    p = _p(slip_enable=False, tau_hold=1e-6)
    out = step(M, 5000.0, REST, MotorState(), TS, p)
    assert out.slipped is False
    assert out.a_del == pytest.approx(5000.0)


def test_slip_scales_delivery_and_banks_the_difference():
    p = _p(slip_enable=True, tau_hold=1e-4, tau_derate=1.0)
    out = step(M, 5000.0, REST, MotorState(), TS, p)
    assert out.slipped is True
    assert abs(out.a_del) < 5000.0
    assert out.state.n_slip == 1
    assert out.state.slip_accum != 0.0


def test_slip_makes_the_counter_diverge_from_what_was_delivered():
    """The counter keeps counting the steps that were commanded, so the
    step-counted position drifts away from where the cart really is -- with no
    residual anywhere to reveal it."""
    p = _p(slip_enable=True, tau_hold=1e-4, tau_derate=1.0)
    st = MotorState()
    # Bounded so that fifty ticks of counting stay inside the rail: the
    # divergence under test is slip, and a counter pinned against an end stop
    # would be a different mechanism answering the question.
    for _ in range(50):
        st = step(M, 100.0, REST, st, TS, p).state
    assert st.n_slip == 50
    assert abs(st.slip_accum) > 1e-6
    assert abs(st.v_count) > abs(st.v_count - st.slip_accum)
