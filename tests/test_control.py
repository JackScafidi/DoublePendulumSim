import inspect

import numpy as np
import pytest

from dpc.control import ConstantController, ControlOutput, ZeroController
from dpc.params import Params
from dpc.sensors import Measurement

P = Params()


def _m(t=0.0, th1=0.0, th2=0.0, x=0.0, dt=1e-3):
    return Measurement(t=t, th1=th1, th2=th2, x_count=x, dt=dt)


def test_zero_controller_commands_zero_whatever_it_sees():
    c = ZeroController()
    c.reset(P)
    rng = np.random.default_rng(0)
    for _ in range(50):
        m = _m(th1=rng.normal(), th2=rng.normal(), x=rng.normal())
        assert c.update(m).a_cmd == 0.0


def test_constant_controller_commands_its_constant():
    c = ConstantController(2.5)
    c.reset(P)
    assert c.update(_m()).a_cmd == pytest.approx(2.5)
    assert c.update(_m(t=1.0, th1=3.0)).a_cmd == pytest.approx(2.5)


def test_output_carries_a_mode():
    assert ZeroController().update(_m()).mode == "idle"
    assert ConstantController(1.0).update(_m()).mode == "constant"


def test_output_is_frozen():
    out = ControlOutput(a_cmd=1.0)
    with pytest.raises(Exception):
        out.a_cmd = 2.0


def test_reset_takes_no_state():
    """The controller is never handed truth, not even at reset. It learns where
    the system is from its first measurement, exactly as it will on power-up."""
    for ctor in (ZeroController(), ConstantController(1.0)):
        assert list(inspect.signature(ctor.reset).parameters) == ["p"]


def test_update_takes_only_a_measurement():
    """Nothing else may reach a controller -- not the model, not the parameters,
    and above all not the state."""
    for ctor in (ZeroController(), ConstantController(1.0)):
        assert list(inspect.signature(ctor.update).parameters) == ["m"]


def test_reset_reproduces_an_identical_command_sequence():
    c = ConstantController(1.0)
    c.reset(P)
    first = [c.update(_m(t=i * 1e-3)).a_cmd for i in range(20)]
    c.reset(P)
    second = [c.update(_m(t=i * 1e-3)).a_cmd for i in range(20)]
    assert first == second
