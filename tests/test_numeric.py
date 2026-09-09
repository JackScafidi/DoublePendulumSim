import numpy as np

from dpc.dynamics import accel, deriv
from dpc.model import ModelConfig, build
from dpc.params import Corrections, Params

M = build(ModelConfig())
P = Params()


def test_mass_matrix_is_symmetric_positive_definite():
    A = M.M(np.array([0.1, 0.3, -0.2]), P)
    assert np.allclose(A, A.T)
    assert np.all(np.linalg.eigvals(A) > 0)


def test_at_rest_upright_with_no_force_nothing_moves():
    assert np.allclose(accel(M, np.zeros(6), 0.0, P), 0.0, atol=1e-12)


def test_a_push_accelerates_the_cart_forward():
    assert accel(M, np.zeros(6), 1.0, P)[0] > 0


def test_hanging_at_rest_is_an_equilibrium():
    s = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    assert np.allclose(accel(M, s, 0.0, P), 0.0, atol=1e-9)


def test_upright_is_unstable_and_hanging_is_stable():
    """Same sign of displacement, opposite response.

    Upright is theta = 0: nudged to +0.05 the links tip further positive.
    Hanging is theta = pi: nudged to pi + 0.05 they swing back toward pi,
    which is the negative direction.
    """
    up = np.array([0.0, 0.05, 0.05, 0.0, 0.0, 0.0])
    down = np.array([0.0, np.pi + 0.05, np.pi + 0.05, 0.0, 0.0, 0.0])
    assert accel(M, up, 0.0, P)[1] > 0
    assert accel(M, down, 0.0, P)[1] < 0


def test_deriv_stacks_velocity_then_acceleration():
    s = np.array([0.0, 0.2, -0.1, 1.5, 0.3, -0.4])
    d = deriv(M, s, 0.0, P)
    assert np.allclose(d[:3], s[3:])
    assert np.allclose(d[3:], accel(M, s, 0.0, P))


def test_energy_is_higher_upright_than_hanging():
    up = np.zeros(6)
    down = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    assert M.energy(up, P) > M.energy(down, P)


def test_energy_grows_with_speed():
    slow = np.array([0.0, 0.0, 0.0, 0.1, 0.0, 0.0])
    fast = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    assert M.energy(fast, P) > M.energy(slow, P)


def test_rotor_adds_inertia_but_no_weight():
    """Doubling m_rotor must make the cart harder to push while leaving the
    potential energy -- and so the hanging/upright energy gap -- untouched."""
    heavy = Params(corr=Corrections(k_m_rotor=2.0))
    s = np.zeros(6)
    assert abs(accel(M, s, 1.0, heavy)[0]) < abs(accel(M, s, 1.0, P)[0])

    down = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])
    gap_ref = M.energy(s, P) - M.energy(down, P)
    gap_heavy = M.energy(s, heavy) - M.energy(down, heavy)
    assert abs(gap_heavy - gap_ref) < 1e-12


def test_a_tilted_rail_pulls_the_cart_downhill():
    tilted = Params(phi=0.26)          # about 15 degrees
    assert accel(M, np.zeros(6), 0.0, tilted)[0] < 0


def test_viscous_friction_opposes_cart_motion():
    from dpc.params import Friction
    damped = Params(fric=Friction(b_cart=5.0))
    moving = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    assert accel(M, moving, 0.0, damped)[0] < 0


def test_cache_reuse_gives_identical_numbers():
    again = build(ModelConfig())
    s = np.array([0.1, 0.4, -0.3, 0.2, 0.1, -0.5])
    assert np.allclose(accel(again, s, 0.7, P), accel(M, s, 0.7, P))
