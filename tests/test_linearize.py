import numpy as np

from dpc.linearize import linearize
from dpc.model import ModelConfig, build
from dpc.params import Corrections, Params
from dpc.simulate import simulate

M = build(ModelConfig())
P = Params()
UP = np.zeros(6)
DOWN = np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0])


def test_shapes_and_kinematic_block():
    """The top half of A is pure bookkeeping: d/dt of position is velocity."""
    A, B = linearize(M, UP, 0.0, P)
    assert A.shape == (6, 6) and B.shape == (6, 1)
    assert np.allclose(A[0:3, 0:3], 0.0, atol=1e-6)
    assert np.allclose(A[0:3, 3:6], np.eye(3), atol=1e-6)
    assert np.allclose(B[0:3, 0], 0.0, atol=1e-6)


def test_upright_equilibrium_has_a_right_half_plane_pole():
    A, _ = linearize(M, UP, 0.0, P)
    assert np.max(np.real(np.linalg.eigvals(A))) > 0.1


def test_hanging_equilibrium_is_marginally_stable():
    """Frictionless, so the hanging modes sit exactly on the imaginary axis."""
    A, _ = linearize(M, DOWN, 0.0, P)
    assert np.max(np.real(np.linalg.eigvals(A))) < 1e-6


def test_cart_position_is_a_free_integrator():
    """On a level rail the dynamics contain xdot but never x: sliding the whole
    apparatus along the rail changes nothing. So A has a structural pole at the
    origin that no amount of friction can move, and cart position can only ever
    be stabilised by feedback. This is why x must appear in the LQR state.
    """
    from dpc.params import Friction
    damped = Params(fric=Friction(b1=0.01, b2=0.01, b_cart=0.5))
    A, _ = linearize(M, DOWN, 0.0, damped)
    real = np.sort(np.real(np.linalg.eigvals(A)))
    assert abs(real[-1]) < 1e-9              # exactly one pole at the origin
    assert real[-2] < -1e-6                  # every other mode is damped


def test_friction_damps_every_mode_except_the_free_integrator():
    from dpc.params import Friction
    undamped = np.linalg.eigvals(linearize(M, DOWN, 0.0, Params())[0])
    damped = np.linalg.eigvals(
        linearize(M, DOWN, 0.0,
                  Params(fric=Friction(b1=0.01, b2=0.01, b_cart=0.5)))[0])

    # Without friction the swing modes sit on the imaginary axis.
    assert np.allclose(np.sort(np.real(undamped))[-2], 0.0, atol=1e-9)
    # With friction they move off it, leaving only the position pole behind.
    assert (np.sort(np.real(damped)) < -1e-6).sum() == 5


def test_the_cart_is_the_only_directly_driven_state():
    _, B = linearize(M, UP, 0.0, P)
    assert abs(B[3, 0]) > 1e-3


def test_hanging_mode_frequencies_match_the_analytic_values():
    """With the pivot effectively fixed, the two swing frequencies about
    hanging solve det(K - w^2 M2) = 0 for the fixed-pivot pair, where

        M2 = [[a, b], [b, c]]                    a = I1 + m1 lc1^2 + m2 l1^2
        K  = diag(g(m1 lc1 + m2 l1), g m2 lc2)   b = m2 l1 lc2
                                                 c = I2 + m2 lc2^2

    computed here by hand rather than taken from the model.
    """
    p = Params(corr=Corrections(k_m_cart=1e4))
    e = p.effective()
    a = e["I1"] + e["m1"] * e["lc1"] ** 2 + e["m2"] * e["l1"] ** 2
    b = e["m2"] * e["l1"] * e["lc2"]
    c = e["I2"] + e["m2"] * e["lc2"] ** 2
    M2 = np.array([[a, b], [b, c]])
    K = np.diag([e["g"] * (e["m1"] * e["lc1"] + e["m2"] * e["l1"]),
                 e["g"] * e["m2"] * e["lc2"]])
    want = np.sort(np.sqrt(np.linalg.eigvals(np.linalg.solve(M2, K)).real))

    A, _ = linearize(M, DOWN, 0.0, p)
    ev = np.linalg.eigvals(A)
    got = np.sort(np.abs(np.imag(ev[np.abs(np.imag(ev)) > 1e-6])))[::2]

    assert np.allclose(got, want, rtol=2e-3), f"got {got}, want {want}"


def test_small_angle_response_tracks_the_nonlinear_model():
    """Validates the linearisation the LQR will later be built on."""
    A, _ = linearize(M, UP, 0.0, P)
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


def test_large_angle_response_does_not_track_the_linear_model():
    """The converse check: if the linearisation matched at large angles too,
    something would be wrong with the nonlinear model."""
    A, _ = linearize(M, UP, 0.0, P)
    s0 = np.array([0.0, 0.8, -0.8, 0.0, 0.0, 0.0])
    dt, n = 1e-4, 2000

    lin = s0.copy()
    for _ in range(n):
        lin = lin + dt * (A @ lin)

    tr = simulate(M, s0, lambda t, s: 0.0, t_end=n * dt, dt=dt, p=P)
    rel = np.linalg.norm(tr.s[-1] - lin) / np.linalg.norm(lin)
    assert rel > 1e-2
