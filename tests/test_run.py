import numpy as np
import pytest

from dpc.controllers.constant import ConstantController
from dpc.controllers.zero import ZeroController
from dpc.dynamics import accel, deriv, deriv_accel
from dpc.model import ModelConfig, build
from dpc.params import Control, Drive, Friction, Params
from dpc.simulate import rk4_step, run, simulate

M = build(ModelConfig())
TS = 1e-3
HANGING = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])


def test_every_channel_has_one_sample_per_tick():
    r = run(M, HANGING, ZeroController(), Params(), t_end=0.05, ts=TS)
    n = len(r.t)
    assert n == 51
    for arr in (r.s, r.meas, r.a_cmd, r.a_del, r.F_req, r.tau, r.x_count,
                r.slipped):
        assert len(arr) == n
    assert len(r.mode) == n
    assert r.s.shape == (n, 6)
    assert r.meas.shape == (n, 3)


def test_hanging_at_rest_under_zero_command_stays_there():
    r = run(M, HANGING, ZeroController(), Params(), t_end=1.0, ts=TS)
    assert r.s[-1] == pytest.approx(HANGING, abs=1e-9)
    assert np.allclose(r.a_del, 0.0)
    assert not r.slipped.any()


def test_the_counter_tracks_the_truth_while_slip_is_off():
    p = Params(drive=Drive(slip_enable=False))
    r = run(M, HANGING, ConstantController(1.0), p, t_end=0.5, ts=TS)
    assert r.x_count[-1] == pytest.approx(r.s[-1, 0], abs=2 * p.drive.step_res)


def test_a_constant_command_walks_the_motor_through_its_limits():
    """Jerk first, then saturation, then the velocity ceiling, in that order."""
    p = Params(drive=Drive(a_max=2.0, v_max=0.2, jerk_max=50.0, tau_lag=0.0))
    r = run(M, HANGING, ConstantController(99.0), p, t_end=1.0, ts=TS)

    # Ramping up: every tick's change is bounded by the jerk limit.
    at_sat = int(np.argmax(r.a_del >= 2.0 - 1e-12))
    assert at_sat > 1
    assert np.max(np.abs(np.diff(r.a_del[:at_sat + 1]))) <= 50.0 * TS + 1e-9

    # Then saturation holds it at a_max, and finally the ceiling zeroes it.
    assert np.max(r.a_del) == pytest.approx(2.0, rel=1e-6)
    assert r.a_del[-1] == pytest.approx(0.0, abs=1e-9)
    assert r.s[-1, 3] == pytest.approx(0.2, rel=0.05)


def test_the_velocity_ceiling_bypasses_the_jerk_limit():
    """Deliberate: the ceiling is a protective clamp, not a planned ramp.

    A generator that eased off in advance of v_max would need lookahead it does
    not have, so acceleration is cut to zero the moment the rate becomes
    unsustainable. Ramping the rate UP is jerk-limited; refusing to ramp it up
    any further is free.
    """
    p = Params(drive=Drive(a_max=2.0, v_max=0.2, jerk_max=50.0, tau_lag=0.0))
    r = run(M, HANGING, ConstantController(99.0), p, t_end=1.0, ts=TS)

    drops = np.diff(r.a_del)
    assert np.min(drops) == pytest.approx(-2.0, rel=1e-6)
    assert np.max(drops) <= 50.0 * TS + 1e-9


def test_torque_is_reported_against_the_budget():
    p = Params()
    r = run(M, HANGING, ConstantController(1.0), p, t_end=0.2, ts=TS)
    assert np.all(np.isfinite(r.tau))
    assert r.tau == pytest.approx(r.F_req * p.drive.r_pulley)


def test_the_two_drive_paths_agree_on_the_state_derivative():
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
            full = deriv(M, s, F, p)
            prescribed = deriv_accel(M, s, full[3], p)
            assert prescribed == pytest.approx(full, abs=1e-9)


def test_replaying_the_cart_acceleration_reproduces_the_trajectory():
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

    ref = simulate(M, s0, lambda t, s: 0.8, t_end=0.2, dt=dt, p=p)

    def f(state, u):
        return deriv_accel(M, state, u, p)

    s = s0.copy()
    for i in range(len(ref.t) - 1):
        a_cart = accel(M, ref.s[i], ref.F[i], p)[0]
        s = rk4_step(f, s, a_cart, dt)

    assert s == pytest.approx(ref.s[-1], abs=1e-4)


def test_control_rate_is_independent_of_plant_accuracy():
    """Halving the plant step must not move the answer; the controller ran at
    the same rate in both."""
    p = Params()
    coarse = run(M, HANGING, ConstantController(0.5), p,
                 t_end=0.3, ts=TS, substeps=5)
    fine = run(M, HANGING, ConstantController(0.5), p,
               t_end=0.3, ts=TS, substeps=40)
    assert coarse.s[-1] == pytest.approx(fine.s[-1], abs=1e-6)


def test_defaults_come_from_params():
    p = Params(ctrl=Control(ts=2e-3, substeps=4))
    r = run(M, HANGING, ZeroController(), p, t_end=0.02)
    assert len(r.t) == 11
    assert r.t[1] == pytest.approx(2e-3)


def test_slip_drives_the_counter_away_from_the_truth():
    """With slip enabled and the torque budget starved, the cart falls short of
    every command while the counter records all of them. The gap is invisible
    to the controller: nothing it can measure disagrees."""
    p = Params(drive=Drive(a_max=50.0, jerk_max=1e6, tau_lag=0.0,
                           tau_hold=1e-3, tau_derate=1.0, slip_enable=True))
    r = run(M, HANGING, ConstantController(40.0), p, t_end=0.2, ts=TS)

    assert r.slipped.any()
    assert abs(r.x_count[-1] - r.s[-1, 0]) > 1e-3
