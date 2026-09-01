"""Reduction to systems whose behaviour is known independently.

Unlike energy conservation, these localise a fault to a specific term, because
each one exercises a different part of the equations against an answer derived
somewhere other than dpc.model.
"""

import numpy as np

from dpc.model import ModelConfig, build
from dpc.params import Corrections, Params
from dpc.simulate import simulate

M = build(ModelConfig())


def _fixed_pivot_double_pendulum_reference(s0, p, t_end, dt):
    """Independent RK4 of a double pendulum on an immovable pivot.

    Written from a hand derivation rather than by reusing dpc.model, so this is
    a genuine cross-check rather than a restatement of the same code. With
    angles measured from up and D = th1 - th2:

        a*th1dd + b*cos(D)*th2dd + b*sin(D)*w2^2 = +(m1 lc1 + m2 l1) g sin(th1)
        c*th2dd + b*cos(D)*th1dd - b*sin(D)*w1^2 = + m2 lc2 g sin(th2)

        a = I1 + m1 lc1^2 + m2 l1^2      b = m2 l1 lc2      c = I2 + m2 lc2^2

    Below it is written with d = th2 - th1, so each sin flips sign.
    """
    e = p.effective()
    m1, m2 = e["m1"], e["m2"]
    l1, lc1, lc2 = e["l1"], e["lc1"], e["lc2"]
    I1, I2, g = e["I1"], e["I2"], e["g"]

    a = I1 + m1 * lc1 ** 2 + m2 * l1 ** 2
    b = m2 * l1 * lc2
    c = I2 + m2 * lc2 ** 2

    def deriv(y):
        th1, th2, w1, w2 = y
        d = th2 - th1
        Mm = np.array([[a, b * np.cos(d)], [b * np.cos(d), c]])
        rhs = np.array([
            b * np.sin(d) * w2 ** 2 + (m1 * lc1 + m2 * l1) * g * np.sin(th1),
            -b * np.sin(d) * w1 ** 2 + m2 * lc2 * g * np.sin(th2),
        ])
        acc = np.linalg.solve(Mm, rhs)
        return np.array([w1, w2, acc[0], acc[1]])

    y = np.array([s0[1], s0[2], s0[4], s0[5]])
    for _ in range(int(round(t_end / dt))):
        k1 = deriv(y)
        k2 = deriv(y + 0.5 * dt * k1)
        k3 = deriv(y + 0.5 * dt * k2)
        k4 = deriv(y + dt * k3)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return y


def test_a_heavy_cart_reproduces_a_fixed_pivot_double_pendulum():
    """k_m_cart = 1e4 makes the pivot effectively immovable while keeping the
    mass matrix well conditioned. Pushing to 1e7 would make M span seventeen
    orders of magnitude and the linear solve would return noise.
    """
    p = Params(corr=Corrections(k_m_cart=1e4))
    s0 = np.array([0.0, 2.6, 2.9, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=2.0, dt=2e-4, p=p)
    ref = _fixed_pivot_double_pendulum_reference(s0, p, 2.0, 2e-4)
    assert abs(tr.s[-1][1] - ref[0]) < 1e-3
    assert abs(tr.s[-1][2] - ref[1]) < 1e-3


def test_cart_recoils_opposite_to_a_falling_pendulum():
    """Nothing pushes the system along the rail, so the cart must move opposite
    to the falling links."""
    s0 = np.array([0.0, 0.2, 0.2, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=0.3, dt=1e-4, p=Params())
    assert tr.s[-1][0] < 0


def test_momentum_conjugate_to_x_is_conserved_on_a_level_rail():
    """On a level rail the potential energy does not depend on x, so by
    Noether's theorem dL/dxdot is exactly conserved.

    m_rotor belongs in this sum even though it has no weight: the belt
    constraint makes rotor spin part of the momentum conjugate to x.
    """
    p = Params()
    e = p.effective()
    s0 = np.array([0.0, 0.5, -0.3, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=1.0, dt=2e-4, p=p)

    def px(s):
        _, th1, th2, xd, w1, w2 = s
        v_c1 = xd + e["lc1"] * np.cos(th1) * w1
        v_c2 = (xd + e["l1"] * np.cos(th1) * w1
                + e["lc2"] * np.cos(th2) * w2)
        return ((e["m_cart"] + e["m_rotor"]) * xd
                + e["m1"] * v_c1 + e["m2"] * v_c2)

    assert abs(px(tr.s[-1]) - px(tr.s[0])) < 1e-8


def test_a_rotor_only_cart_still_conserves_momentum():
    """Doubling m_rotor changes the momentum budget but must not break its
    conservation -- a check that the rotor is coupled through the constraint
    rather than bolted on."""
    p = Params(corr=Corrections(k_m_rotor=2.0))
    e = p.effective()
    s0 = np.array([0.0, 0.5, -0.3, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=1.0, dt=2e-4, p=p)

    def px(s):
        _, th1, th2, xd, w1, w2 = s
        v_c1 = xd + e["lc1"] * np.cos(th1) * w1
        v_c2 = (xd + e["l1"] * np.cos(th1) * w1
                + e["lc2"] * np.cos(th2) * w2)
        return ((e["m_cart"] + e["m_rotor"]) * xd
                + e["m1"] * v_c1 + e["m2"] * v_c2)

    assert abs(px(tr.s[-1]) - px(tr.s[0])) < 1e-8
