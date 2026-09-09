import numpy as np
import pytest

from dpc.dynamics import deriv
from dpc.model import ModelConfig, build
from dpc.params import Params
from dpc.simulate import rk4_step, simulate

M = build(ModelConfig())
P = Params()
S0 = np.array([0.0, 2.5, 2.7, 0.0, 0.0, 0.0])


def _f(model, p):
    """Bind a model and parameter set into the derivative signature rk4_step
    wants. Built once, outside any loop."""
    def g(s, u):
        return deriv(model, s, u, p)
    return g


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

    def probe(t, s):
        seen.append((t, s.copy()))
        return 0.0

    simulate(M, S0, probe, t_end=0.01, dt=1e-3, p=P)
    assert seen[0][0] == 0.0
    assert len(seen[0][1]) == 6


def test_rk4_converges_at_fourth_order():
    """Richardson extrapolation stands in for a reference integrator: halving
    dt must cut RK4's error by about 16, so log2 of the error ratio is ~4."""
    coarse, mid, fine = _final(4e-3), _final(2e-3), _final(1e-3)
    e_coarse = np.linalg.norm(coarse - fine)
    e_mid = np.linalg.norm(mid - fine)
    order = np.log2(e_coarse / e_mid)
    assert 3.5 < order < 4.5, f"observed order {order}"


def test_zero_force_from_rest_upright_stays_put():
    tr = simulate(M, np.zeros(6), lambda t, s: 0.0, t_end=2.0, dt=1e-3, p=P)
    assert np.allclose(tr.s[-1], 0.0, atol=1e-9)


def test_a_single_step_matches_the_loop():
    one = rk4_step(_f(M, P), S0, 0.5, 1e-3)
    tr = simulate(M, S0, lambda t, s: 0.5, t_end=1e-3, dt=1e-3, p=P)
    assert np.allclose(tr.s[-1], one)


def test_force_is_held_constant_across_a_step():
    """Zero-order hold: the force recorded for step i is the one applied
    through it, matching a controller running at 1/dt."""
    tr = simulate(M, S0, lambda t, s: 1.0 if t < 5e-4 else 0.0,
                  t_end=2e-3, dt=1e-3, p=P)
    assert tr.F[0] == 1.0
    assert tr.F[1] == 0.0


def test_rk4_step_is_exact_for_a_constant_derivative():
    """Four stages, one weighted sum: with a state-independent derivative RK4
    must reduce to plain Euler exactly."""
    out = rk4_step(lambda ss, uu: np.full(6, uu), np.zeros(6), 2.0, 0.1)
    assert out == pytest.approx(np.full(6, 0.2))
