import sympy as sp

import dpc.model as m
from dpc.model import ModelConfig, _kinematics, q


def _at(expr, x=0.0, th1=0.0, th2=0.0, l1=0.20, l2=0.20, lc1=0.12, lc2=0.10,
        phi=0.0):
    subs = {q[0]: x, q[1]: th1, q[2]: th2,
            m.S["l1"]: l1, m.S["l2"]: l2, m.S["lc1"]: lc1,
            m.S["lc2"]: lc2, m.S["phi"]: phi}
    return sp.Matrix(expr).subs(subs).evalf()


def test_upright_puts_elbow_directly_above_the_cart():
    k = _kinematics(ModelConfig())
    p = _at(k["p_elbow"], x=0.3, th1=0.0, th2=0.0)
    assert abs(float(p[0]) - 0.3) < 1e-12
    assert abs(float(p[1]) - 0.20) < 1e-12


def test_upright_stacks_link2_com_above_the_elbow():
    k = _kinematics(ModelConfig())
    p = _at(k["p_c2"], th1=0.0, th2=0.0)
    assert abs(float(p[1]) - 0.30) < 1e-12          # l1 + lc2


def test_positive_theta_tips_the_link_toward_plus_x():
    k = _kinematics(ModelConfig())
    p = _at(k["p_elbow"], x=0.0, th1=sp.pi / 2)
    assert abs(float(p[0]) - 0.20) < 1e-12
    assert abs(float(p[1])) < 1e-12


def test_hanging_link1_com_is_below_the_cart():
    k = _kinematics(ModelConfig())
    p = _at(k["p_c1"], th1=sp.pi)
    assert abs(float(p[1]) + 0.12) < 1e-12


def test_rail_tilt_raises_the_cart_as_it_advances():
    k = _kinematics(ModelConfig())
    p = _at(k["p_cart"], x=1.0, phi=sp.pi / 6)
    assert abs(float(p[1]) - 0.5) < 1e-12


def test_link2_angle_is_absolute_not_relative():
    """theta_2 = 0 means link 2 is vertical no matter what theta_1 is, so
    swinging link 1 down to horizontal drops link 2's COM by exactly l1."""
    k = _kinematics(ModelConfig())
    a = _at(k["p_c2"], th1=0.0, th2=0.0)
    b = _at(k["p_c2"], th1=sp.pi / 2, th2=0.0)
    assert abs(float(a[1]) - float(b[1]) - 0.20) < 1e-12


def test_rail_tilt_can_be_switched_off():
    k = _kinematics(ModelConfig(rail_tilt=False))
    assert m.S["phi"] not in sp.Matrix(k["p_cart"]).free_symbols


def test_velocities_are_time_derivatives_of_positions():
    k = _kinematics(ModelConfig())
    for pos, vel in (("p_cart", "v_cart"), ("p_c1", "v_c1"), ("p_c2", "v_c2")):
        expected = sp.Matrix(k[pos]).diff(m.t)
        assert sp.simplify(sp.Matrix(k[vel]) - expected) == sp.zeros(2, 1)
