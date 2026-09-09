import dataclasses

import numpy as np
import pytest

from dpc.motor import MotorState
from dpc.params import Params
from dpc.sensors import Measurement, measure

P = Params()
S = np.array([0.11, 0.22, 0.33, 0.44, 0.55, 0.66])


def test_measurement_carries_no_rates():
    """The structural guard. Hardware measures neither cart velocity nor either
    angular rate, so no controller may be handed one."""
    names = {f.name for f in dataclasses.fields(Measurement)}
    assert names == {"t", "th1", "th2", "x_count", "dt"}
    for forbidden in ("xdot", "w1", "w2", "s", "state"):
        assert forbidden not in names


def test_angles_come_from_truth_today():
    m = measure(0.5, S, MotorState(), 1e-3, P)
    assert m.th1 == pytest.approx(S[1])
    assert m.th2 == pytest.approx(S[2])
    assert m.t == pytest.approx(0.5)
    assert m.dt == pytest.approx(1e-3)


def test_position_comes_from_the_step_counter_not_the_truth():
    """The cart has no position sensor. What the controller sees is the total
    of the steps it commanded."""
    st = MotorState(x_count=0.02)
    m = measure(0.0, S, st, 1e-3, P)
    assert m.x_count != pytest.approx(S[0])
    assert m.x_count == pytest.approx(0.02, abs=P.drive.step_res)


def test_reported_position_is_quantised_to_whole_microsteps():
    res = P.drive.step_res
    m = measure(0.0, S, MotorState(x_count=100.4 * res), 1e-3, P)
    assert m.x_count == pytest.approx(100 * res)


def test_measurement_is_frozen():
    m = measure(0.0, S, MotorState(), 1e-3, P)
    with pytest.raises(Exception):
        m.th1 = 0.0
