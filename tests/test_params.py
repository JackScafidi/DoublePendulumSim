import math

import pytest

from dpc.params import (EFFECTIVE_NAMES, Control, Corrections, Drive,
                        Friction, Nominal, Params)


def test_defaults_apply_unit_corrections():
    p = Params()
    eff = p.effective()
    assert eff["m1"] == pytest.approx(0.075)
    assert eff["I2"] == pytest.approx(1.5e-4)
    assert eff["g"] == pytest.approx(9.81)


def test_correction_scales_only_its_own_parameter():
    p = Params(corr=Corrections(k_m1=2.0))
    eff = p.effective()
    assert eff["m1"] == pytest.approx(0.150)
    assert eff["m2"] == pytest.approx(0.045)


def test_lengths_and_gravity_have_no_correction():
    assert not hasattr(Corrections(), "k_l1")
    assert not hasattr(Corrections(), "k_g")


def test_friction_is_zero_in_the_ideal_preset():
    eff = Params().effective()
    for name in ("b_cart", "b1", "b2", "c_cart", "c1", "c2", "phi"):
        assert eff[name] == 0.0


def test_vector_matches_the_canonical_ordering():
    p = Params()
    eff = p.effective()
    assert p.vector() == tuple(eff[name] for name in EFFECTIVE_NAMES)
    assert len(EFFECTIVE_NAMES) == 19


def test_params_are_frozen():
    p = Params()
    with pytest.raises(Exception):
        p.phi = 0.5


def test_nominals_are_physically_plausible():
    n = Nominal()
    assert 0 < n.lc1 <= n.l1
    assert 0 < n.lc2 <= n.l2
    assert n.I1 > 0 and n.I2 > 0
    assert math.isclose(n.g, 9.81)


def test_drive_defaults():
    d = Drive()
    assert d.r_pulley == pytest.approx(6.4e-3)
    assert d.steps_per_rev == 200
    assert d.microsteps == 16
    assert d.slip_enable is False


def test_step_resolution_is_belt_travel_per_microstep():
    d = Drive()
    expected = 2.0 * math.pi * d.r_pulley / (d.steps_per_rev * d.microsteps)
    assert d.step_res == pytest.approx(expected)
    assert d.step_res == pytest.approx(12.566e-6, rel=1e-3)


def test_torque_budget_is_holding_torque_derated():
    d = Drive()
    assert d.tau_budget == pytest.approx(d.tau_hold * d.tau_derate)
    assert d.F_max == pytest.approx(d.tau_budget / d.r_pulley)


def test_control_defaults():
    c = Control()
    assert c.ts == pytest.approx(1e-3)
    assert c.substeps == 10


def test_params_carry_drive_and_control():
    p = Params()
    assert p.drive.a_max > 0
    assert p.ctrl.substeps >= 1


def test_drive_and_control_are_not_in_the_effective_vector():
    """The drive is not part of the physics, so it must not reach the
    lambdified functions."""
    p = Params()
    assert len(p.vector()) == len(EFFECTIVE_NAMES) == 19
    assert "r_pulley" not in EFFECTIVE_NAMES
    assert "ts" not in EFFECTIVE_NAMES


def test_vector_is_cached_on_the_instance():
    """Rebuilt on every lambdified call otherwise -- four times per solve, and
    a solve happens forty times per control tick."""
    p = Params()
    assert p.vector() is p.vector()


def test_cached_vector_still_matches_effective():
    for p in (Params(),
              Params(corr=Corrections(k_m1=2.0)),
              Params(fric=Friction(b_cart=0.4, c_cart=0.5))):
        eff = p.effective()
        assert p.vector() == tuple(eff[name] for name in EFFECTIVE_NAMES)


def test_caching_does_not_disturb_equality_or_hashing():
    a, b = Params(), Params()
    a.vector()
    assert a == b
    assert hash(a) == hash(b)
