import numpy as np
import pytest

from dpc.controllers.registry import build, discover
from dpc.model import ModelConfig
from dpc.model import build as build_model
from dpc.params import Params
from dpc.scenarios import by_key
from dpc.ui.sample import Command
from dpc.ui.source import SimSource

M = build_model(ModelConfig())


def _entry(key):
    return next(e for e in discover() if e.key == key)


def _src(**kw):
    return SimSource(M, Params(), **kw)


def _constant(a=2.0, hold=99.0):
    return build(_entry("constant"), {"a": a, "hold": hold})


def test_poll_produces_only_what_the_clock_asks_for():
    """Nothing is computed ahead of the playback cursor, so pausing genuinely
    pauses instead of racing to the end of the scenario."""
    src = _src()
    src.start(_constant(), by_key("hanging"))
    first = src.poll(0.010)
    assert len(first) == 10
    assert first[-1].t == pytest.approx(0.010)
    assert src.poll(0.010) == []


def test_samples_are_contiguous_across_polls():
    src = _src()
    src.start(_constant(), by_key("hanging"))
    got = src.poll(0.005) + src.poll(0.012)
    times = [s.t for s in got]
    assert times == pytest.approx(list(np.arange(1, len(times) + 1) * 1e-3))


def test_truth_is_populated_in_simulation():
    src = _src()
    src.start(_constant(), by_key("nudged"))
    s = src.poll(0.002)[0]
    assert s.truth is not None and s.truth.shape == (6,)


def test_it_stops_at_the_end_of_the_scenario():
    src = _src()
    sc = by_key("hanging")
    src.start(_constant(), sc)
    src.poll(sc.t_end + 5.0)
    assert src.done
    assert src.poll(sc.t_end + 10.0) == []


def test_hanging_at_rest_under_zero_command_does_not_move():
    src = _src()
    src.start(build(_entry("zero"), {}), by_key("hanging"))
    out = src.poll(0.05)
    assert out[-1].truth == pytest.approx(by_key("hanging").s0, abs=1e-9)


def test_a_command_takes_effect_on_the_following_tick_and_not_before():
    """Bidirectional path, exercised in simulation exactly as hardware will."""
    src = _src()
    src.start(_constant(a=0.0), by_key("hanging"))
    before = src.poll(0.005)
    assert all(s.a_cmd == pytest.approx(0.0) for s in before)

    src.send(Command(kind="set_param", name="controller.a", value=3.0))
    after = src.poll(0.010)
    assert after
    assert all(s.a_cmd == pytest.approx(3.0) for s in after)


def test_drive_parameters_can_be_commanded():
    src = _src()
    src.start(_constant(a=99.0), by_key("hanging"))
    src.send(Command(kind="set_param", name="drive.a_max", value=1.0))
    out = src.poll(0.5)
    assert max(abs(s.a_del) for s in out) == pytest.approx(1.0, rel=1e-6)


def test_an_unknown_command_target_is_refused_rather_than_ignored():
    src = _src()
    src.start(_constant(), by_key("hanging"))
    with pytest.raises(ValueError, match="unknown command target"):
        src.send(Command(kind="set_param", name="plant.m1", value=1.0))


def test_reset_returns_to_the_scenario_start():
    src = _src()
    src.start(_constant(), by_key("nudged"))
    src.poll(0.2)
    src.send(Command(kind="reset"))
    out = src.poll(0.001)
    assert out[0].t == pytest.approx(0.001)
    assert not src.done


def test_a_poll_is_bounded_so_the_ui_cannot_freeze():
    """A huge clock jump must return promptly rather than simulating minutes of
    plant inside one repaint."""
    src = _src(max_ticks_per_poll=50)
    src.start(_constant(), by_key("hanging"))
    assert len(src.poll(4.0)) == 50


def test_substeps_default_is_the_dashboard_value_not_the_library_one():
    assert _src().substeps == 2
    assert Params().ctrl.substeps == 10
