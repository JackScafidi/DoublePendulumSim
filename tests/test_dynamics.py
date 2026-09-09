import numpy as np
import pytest
import sympy as sp

from dpc.dynamics import (accel, deriv_accel, link_accel, motor_torque,
                          required_force)
from dpc.model import ModelConfig, S, build, derive, th1, th2
from dpc.params import Friction, Nominal, Params


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


# --------------------------------------------------------------------------
# The block partition: rows 2-3 solved forwards, row 1 read backwards.
# --------------------------------------------------------------------------

NM = build(ModelConfig())

STATES = [
    np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    np.array([0.1, 0.3, -0.2, 0.4, -0.5, 0.6]),
    np.array([-0.2, 2.9, 3.1, -0.3, 0.7, -0.8]),
]

ROUGH = Params(fric=Friction(b_cart=0.4, b1=0.01, b2=0.008,
                             c_cart=0.5, c1=0.02, c2=0.015))


@pytest.mark.parametrize("s", STATES)
@pytest.mark.parametrize("F", [0.0, 1.5, -3.0])
@pytest.mark.parametrize("p", [Params(), ROUGH])
def test_partition_round_trips(s, F, p):
    """Solving forwards then backwards must return the same numbers.

    This is the whole partition under test at once: if any block index or sign
    is wrong, the recovered force will not match the one we started from.
    """
    qdd = accel(NM, s, F, p)

    qdd_l = link_accel(NM, s, qdd[0], p)
    assert qdd_l == pytest.approx(qdd[1:], abs=1e-9)

    assert required_force(NM, s, qdd[0], qdd_l, p) == pytest.approx(F, abs=1e-9)


@pytest.mark.parametrize("s", STATES)
def test_link_accel_ignores_the_rail(s):
    """m_cart, m_rotor and rail friction live in row 1 alone.

    This is the architectural claim of the whole milestone, asserted rather
    than argued: the parameters the controller cannot measure well do not reach
    the part of the plant the controller has to know.
    """
    base = ROUGH
    perturbed = Params(
        nominal=Nominal(m_cart=base.nominal.m_cart * 3.0,
                        m_rotor=base.nominal.m_rotor * 0.5),
        fric=Friction(b_cart=9.9, b1=base.fric.b1, b2=base.fric.b2,
                      c_cart=7.7, c1=base.fric.c1, c2=base.fric.c2),
    )

    a_cart = 2.0
    assert link_accel(NM, s, a_cart, base) == pytest.approx(
        link_accel(NM, s, a_cart, perturbed), abs=1e-12)


def test_required_force_does_depend_on_the_rail():
    """The mirror of the test above: those parameters must still matter to the
    motor, or they would be unobservable everywhere and could never be fitted."""
    s = STATES[1]
    light = ROUGH
    heavy = Params(nominal=Nominal(m_cart=ROUGH.nominal.m_cart * 3.0),
                   fric=ROUGH.fric)

    a_cart = 2.0
    f_light = required_force(NM, s, a_cart, link_accel(NM, s, a_cart, light), light)
    f_heavy = required_force(NM, s, a_cart, link_accel(NM, s, a_cart, heavy), heavy)
    assert abs(f_heavy) > abs(f_light)


def test_motor_torque_is_force_times_pulley_radius():
    p = Params()
    assert motor_torque(10.0, p) == pytest.approx(10.0 * p.drive.r_pulley)


@pytest.mark.parametrize("s", STATES)
def test_deriv_accel_places_the_command_in_the_cart_slot(s):
    a_cart = -1.25
    p = Params()
    d = deriv_accel(NM, s, a_cart, p)
    assert d[0:3] == pytest.approx(s[3:6])
    assert d[3] == pytest.approx(a_cart)
    assert d[4:6] == pytest.approx(link_accel(NM, s, a_cart, p))
