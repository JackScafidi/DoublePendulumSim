"""The end stops.

The rail is finite, and reaching the end of it is a fully inelastic collision
with something rigid. These tests fix where the wall is, that nothing ever
crosses it, and that the impulse arrives through the mass matrix rather than by
zeroing one number.
"""

from dataclasses import replace

import numpy as np
import pytest

from dpc.controllers.constant import ConstantController
from dpc.controllers.zero import ZeroController
from dpc.dynamics import deriv_accel
from dpc.model import ModelConfig, build
from dpc.motor import MotorState, step
from dpc.params import EFFECTIVE_NAMES, Control, Drive, Params
from dpc.rail import impact, side
from dpc.scenarios import by_key
from dpc.simulate import rk4_step, run
from dpc.ui.source import SimSource

M = build(ModelConfig())
P = Params()
TS = 1e-3
HANGING = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])


# --------------------------------------------------------------------------
# Where the wall is.
# --------------------------------------------------------------------------

def test_the_rail_is_half_a_metre_of_travel():
    p = Params()
    assert p.nominal.rail_len == pytest.approx(0.50)
    assert p.x_lim == pytest.approx(0.25)


def test_the_rail_is_not_a_term_in_the_equations_of_motion():
    """It constrains the state; it does not appear in M, C, G or friction, so
    it must never reach the lambdified parameter vector."""
    p = Params()
    assert "rail_len" not in EFFECTIVE_NAMES
    assert "rail_len" not in p.effective()
    assert len(p.vector()) == len(EFFECTIVE_NAMES) == 19


def test_side_names_the_stop_the_cart_is_against():
    p = Params()
    assert side(0.0, p) == 0
    assert side(0.2, p) == 0
    assert side(-0.2, p) == 0
    assert side(p.x_lim, p) == 1
    assert side(p.x_lim + 0.01, p) == 1
    assert side(-p.x_lim, p) == -1
    assert side(-p.x_lim - 0.01, p) == -1


# --------------------------------------------------------------------------
# The impact itself.
# --------------------------------------------------------------------------

def test_the_cart_ends_the_impact_at_exactly_zero_velocity():
    p = Params()
    s = np.array([p.x_lim + 0.001, 2.0, 2.4, 0.8, 1.5, -1.2])
    out = impact(M, s, p)
    assert out[0] == p.x_lim
    assert out[3] == 0.0


def test_the_links_are_kicked_through_the_mass_matrix():
    """Zeroing xdot on its own would leave the links untouched, which is not
    what a rigid stop does: the impulse couples into both joints."""
    p = Params()
    s = np.array([p.x_lim, 2.0, 2.4, 0.8, 1.5, -1.2])
    out = impact(M, s, p)
    assert not np.allclose(out[4:6], s[4:6])


def test_the_impact_cannot_create_energy():
    p = Params()
    for s in (np.array([p.x_lim, 2.0, 2.4, 0.8, 1.5, -1.2]),
              np.array([-p.x_lim, 0.3, -0.5, -0.6, -0.9, 0.4])):
        out = impact(M, s, p)
        assert M.energy(out, p) <= M.energy(s, p) + 1e-12


def test_an_impact_at_rest_changes_nothing():
    """Sitting against the stop with no closing speed is not a collision."""
    p = Params()
    s = np.array([p.x_lim, np.pi, np.pi, 0.0, 0.0, 0.0])
    assert np.array_equal(impact(M, s, p), s)


def test_impact_away_from_a_stop_leaves_the_state_alone():
    """The cart is clamped with min/max rather than placed at side()*x_lim,
    which would teleport a cart in the middle of the rail to the origin."""
    p = Params()
    s = np.array([0.1, 2.0, 2.4, 0.8, 1.5, -1.2])
    assert np.array_equal(impact(M, s, p), s)


def test_the_stop_pushes_and_never_pulls():
    """The constraint is unilateral. A cart already heading back down the rail
    is leaving the stop, and taking its velocity would be the wall holding on
    to it. The guard lives in impact() rather than at the call sites, so no
    call site can forget it."""
    p = Params()
    s = np.array([p.x_lim + 1e-9, 2.0, 2.4, -0.7, 1.5, -1.2])
    out = impact(M, s, p)
    assert out[0] == p.x_lim
    assert np.array_equal(out[3:6], s[3:6])


# --------------------------------------------------------------------------
# The closed loop: the cart never leaves the rail.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("a", [2.0, -2.0])
def test_a_constant_push_parks_the_cart_on_the_stop(a):
    """Drive hard enough for long enough and the cart arrives at the stop,
    stops dead, and stays there for the rest of the run."""
    p = Params()
    r = run(M, HANGING, ConstantController(a), p, t_end=1.0, ts=TS,
            substeps=2)
    x, xdot = r.s[:, 0], r.s[:, 3]

    assert np.max(np.abs(x)) == pytest.approx(p.x_lim, abs=1e-12)
    assert x[-1] == pytest.approx(np.sign(a) * p.x_lim, abs=1e-12)

    first = int(np.argmax(np.abs(x) >= p.x_lim - 1e-12))
    assert first > 0
    assert x[first:] == pytest.approx(np.sign(a) * p.x_lim, abs=1e-12)
    assert xdot[first:] == pytest.approx(0.0, abs=1e-12)


def test_the_run_records_the_ticks_spent_against_a_stop():
    r = run(M, HANGING, ConstantController(2.0), P, t_end=1.0, ts=TS,
            substeps=2)
    assert r.pinned.shape == r.slipped.shape
    assert r.pinned.dtype == bool
    assert not r.pinned[0]
    assert r.pinned.any()


# --------------------------------------------------------------------------
# The step generator's own copy of the wall.
# --------------------------------------------------------------------------

def _p_motor(**drive) -> Params:
    """Limits wound out of the way: this is about the stop, nothing else.

    A test reinstates only the limit it needs to see."""
    relaxed = Drive(a_max=1e6, v_max=1e6, jerk_max=1e12, tau_lag=0.0)
    return Params(drive=replace(relaxed, **drive), ctrl=Control(ts=TS))


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_the_counter_stops_at_the_end_stop(sign):
    p = _p_motor()
    st = MotorState(x_count=sign * (p.x_lim - 1e-4), v_count=sign * 0.5)
    out = step(M, 0.0, HANGING, st, TS, p)

    assert out.pinned is True
    assert out.state.x_count == sign * p.x_lim
    assert out.state.v_count == 0.0
    assert out.state.a_lag == 0.0
    assert out.state.n_pin == 1
    assert out.a_del == 0.0


def test_the_counter_is_free_away_from_the_stops():
    p = _p_motor()
    out = step(M, 1.0, HANGING, MotorState(), TS, p)
    assert out.pinned is False
    assert out.state.n_pin == 0
    assert out.state.v_count != 0.0


def test_pinned_ticks_accumulate():
    p = _p_motor()
    st = MotorState(x_count=p.x_lim - 1e-4, v_count=0.5)
    for expected in (1, 2, 3):
        out = step(M, 2.0, HANGING, st, TS, p)
        assert out.pinned is True
        assert out.state.n_pin == expected
        assert out.state.x_count == p.x_lim
        st = out.state


def test_the_generator_delivers_nothing_into_a_wall():
    """Pinned, the firmware is clamping its own motion at the stop, so nothing
    at all leaves the step generator. A residual acceleration here would be
    integrated by the plant and kick the links on every substep."""
    r = run(M, HANGING, ConstantController(2.0), P, t_end=1.0, ts=TS,
            substeps=2)
    assert r.pinned.any()
    assert np.all(r.a_del[r.pinned] == 0.0)
    assert np.all(np.isfinite(r.tau[r.pinned]))


def test_a_command_away_from_the_stop_releases_the_counter():
    """Pinning is not a latch. The first tick pulling away starts from rest and
    lands strictly inside the rail, so the counter frees itself and the rate
    ramps up under the jerk limit exactly as it would from any other start."""
    p = _p_motor(jerk_max=100.0)
    st = MotorState(x_count=p.x_lim - 1e-4, v_count=0.5)
    held = step(M, 2.0, HANGING, st, TS, p)
    assert held.pinned is True

    out = step(M, -2.0, HANGING, held.state, TS, p)
    assert out.pinned is False
    assert out.state.x_count < p.x_lim
    assert abs(out.a_del) <= p.drive.jerk_max * TS
    assert out.a_del == pytest.approx(-p.drive.jerk_max * TS)


def test_the_links_see_a_fixed_pivot_while_the_counter_is_pinned():
    """The generator delivers nothing and the plant-side impact holds the true
    cart, so across a pinned stretch the links must evolve exactly as they
    would about a pivot nailed to the stop. The only impulse they ever feel is
    the one real contact."""
    r = run(M, HANGING, ConstantController(2.0), P, t_end=1.0, ts=TS,
            substeps=2)

    i1 = len(r.t) - 1
    i0 = i1 - 100
    assert r.pinned[i0:i1 + 1].all()

    def f(state: np.ndarray, u: float) -> np.ndarray:
        return deriv_accel(M, state, u, P)

    s = r.s[i0].copy()
    for _ in range(i1 - i0):
        for _ in range(2):
            s = rk4_step(f, s, 0.0, TS / 2.0)

    assert s == pytest.approx(r.s[i1], abs=1e-12)


# --------------------------------------------------------------------------
# The counter starts where the cart starts.
# --------------------------------------------------------------------------

OFFSET = np.array([0.1, np.pi, np.pi, 0.0, 0.0, 0.0])
"""Hanging, but a tenth of a metre off centre."""


def test_the_counter_starts_where_the_cart_starts():
    """The counter's wall and the plant's are the same wall only if the two
    agree about where the cart began. A counter that always started from zero
    would carry its own rail, offset from the real one by s0[0], and the run
    would open with a counting error it never earned.

    Half a microstep rather than zero because what the controller reads back is
    quantised on the way out, exactly as it is on hardware."""
    r = run(M, OFFSET, ZeroController(), P, t_end=0.01, ts=TS)
    assert abs(r.x_count[0] - 0.1) <= 0.5 * P.drive.step_res
    assert abs(r.x_count[0] - r.s[0, 0]) <= 0.5 * P.drive.step_res


def test_the_live_source_seeds_its_counter_too():
    src = SimSource(M, P, substeps=2)
    src.start(ZeroController(), replace(by_key("hanging"), s0=OFFSET))
    first = src.poll(TS)[0]
    assert abs(first.x_count - 0.1) <= 0.5 * P.drive.step_res


def test_the_live_source_sees_the_same_wall():
    """The dashboard integrates the plant itself rather than calling run(), so
    it applies the stops itself too. A cart that could leave the rail during
    playback but not in a batch run would be two different plants."""
    src = SimSource(M, P, substeps=2)
    src.start(ConstantController(2.0), by_key("hanging"))
    samples = src.poll(1.0)

    x = np.array([s.truth[0] for s in samples if s.truth is not None])
    assert np.max(np.abs(x)) == pytest.approx(P.x_lim, abs=1e-12)
    assert samples[-1].pinned
    assert src.n_pin > 0
