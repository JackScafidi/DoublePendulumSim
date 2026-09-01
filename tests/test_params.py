import math

import pytest

from dpc.params import EFFECTIVE_NAMES, Corrections, Nominal, Params


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
