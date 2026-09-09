import numpy as np
import pytest

from dpc.scenarios import SCENARIOS, by_key


def test_every_scenario_is_a_full_state_and_a_positive_duration():
    assert len(SCENARIOS) >= 4
    for sc in SCENARIOS:
        assert sc.s0.shape == (6,)
        assert sc.t_end > 0.0
        assert sc.note


def test_keys_are_unique():
    keys = [sc.key for sc in SCENARIOS]
    assert len(keys) == len(set(keys))


def test_lookup_by_key():
    assert by_key("hanging").label == "Hanging at rest"
    with pytest.raises(KeyError):
        by_key("nope")


def test_hanging_is_the_stable_equilibrium():
    sc = by_key("hanging")
    assert sc.s0[1] == pytest.approx(np.pi)
    assert sc.s0[2] == pytest.approx(np.pi)
    assert np.allclose(sc.s0[3:], 0.0)


def test_upright_is_the_unstable_equilibrium():
    assert np.allclose(by_key("upright").s0[1:3], 0.0)


def test_scenarios_are_frozen():
    with pytest.raises(Exception):
        SCENARIOS[0].t_end = 1.0
