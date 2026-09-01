import pytest
import sympy as sp

from dpc.model import ModelConfig, S, derive, th1, th2


def test_mass_matrix_is_symmetric():
    m = derive(ModelConfig())
    assert sp.simplify(m.M_sym - m.M_sym.T) == sp.zeros(3, 3)


def test_cart_inertia_includes_the_rotor():
    """M[0,0] is the total translating inertia, and is angle-independent:
    every mass shares the cart's velocity along the rail."""
    m = derive(ModelConfig())
    want = S["m_cart"] + S["m_rotor"] + S["m1"] + S["m2"]
    assert sp.simplify(m.M_sym[0, 0] - want) == 0


def test_rotor_has_no_weight():
    """m_rotor is an equivalent mass, so it must not appear in gravity."""
    m = derive(ModelConfig())
    assert S["m_rotor"] not in m.V_sym.free_symbols
    assert S["m_rotor"] not in m.G_sym.free_symbols


def test_gravity_vanishes_for_the_cart_on_a_level_rail():
    m = derive(ModelConfig())
    assert sp.simplify(m.G_sym[0].subs(S["phi"], 0)) == 0


def test_gravity_on_a_tilted_rail_uses_real_mass_only():
    """Advancing by x raises the cart by x*sin(phi), so the downhill term
    carries sin(phi) -- and m_rotor is absent because it has no weight."""
    m = derive(ModelConfig())
    want = (S["m_cart"] + S["m1"] + S["m2"]) * S["g"] * sp.sin(S["phi"])
    assert sp.simplify(m.G_sym[0] - want) == 0


def test_upright_is_an_equilibrium():
    m = derive(ModelConfig())
    sub = {th1: 0, th2: 0, S["phi"]: 0}
    assert sp.simplify(m.G_sym[1].subs(sub)) == 0
    assert sp.simplify(m.G_sym[2].subs(sub)) == 0


def test_hanging_gravity_torque_has_restoring_sign():
    """Hanging is theta = pi. Displaced to just under pi, gravity must drive
    theta back up toward pi.

    G sits on the left-hand side of M*qddot + ... + G = B*u, so the induced
    acceleration is -M^-1 G. Driving theta upward therefore needs G[1] < 0.
    """
    m = derive(ModelConfig())
    sub = {th1: sp.pi - sp.Rational(1, 10), th2: sp.pi - sp.Rational(1, 10),
           S["phi"]: 0, S["m1"]: 1, S["m2"]: 1, S["lc1"]: 1, S["lc2"]: 1,
           S["l1"]: 1, S["g"]: 1}
    assert float(m.G_sym[1].subs(sub).evalf()) < 0


def test_elbow_friction_is_equal_and_opposite():
    """Rows 1 and 2 must cancel the elbow term exactly: the torque on link 2
    has an equal and opposite reaction on link 1."""
    m = derive(ModelConfig())
    pair = sp.simplify(m.Ffric_sym[1] + m.Ffric_sym[2])
    assert S["b2"] not in pair.free_symbols
    assert S["c2"] not in pair.free_symbols


def test_elbow_friction_vanishes_when_the_links_move_together():
    """theta2dot == theta1dot means the elbow is not bending, so no friction."""
    m = derive(ModelConfig())
    from dpc.model import qd
    same = {qd[2]: qd[1]}
    assert S["b2"] not in sp.simplify(m.Ffric_sym[2].subs(same)).free_symbols


def test_friction_vanishes_when_all_coefficients_are_zero():
    m = derive(ModelConfig())
    zero = {S[k]: 0 for k in ("b_cart", "b1", "b2", "c_cart", "c1", "c2")}
    assert sp.simplify(m.Ffric_sym.subs(zero)) == sp.zeros(3, 1)


def test_viscous_only_config_drops_the_coulomb_terms():
    m = derive(ModelConfig(friction="viscous"))
    syms = m.Ffric_sym.free_symbols
    for name in ("c_cart", "c1", "c2"):
        assert S[name] not in syms


def test_input_matrix_drives_the_cart_only():
    m = derive(ModelConfig())
    assert list(m.B_sym) == [1, 0, 0]


def test_coriolis_terms_are_quadratic_in_velocity():
    """C*qdot must vanish at rest -- it carries no position-only terms."""
    m = derive(ModelConfig())
    from dpc.model import qd
    at_rest = {v: 0 for v in qd}
    assert sp.simplify(m.Cqd_sym.subs(at_rest)) == sp.zeros(3, 1)


def test_compliant_drive_is_not_implemented():
    with pytest.raises(NotImplementedError):
        derive(ModelConfig(drive="compliant"))
