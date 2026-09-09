import numpy as np
import pytest

from dpc.ui.sample import Command, Sample, SampleBuffer


def _s(t, th1=0.0, a_del=0.0, truth=True):
    return Sample(t=t, th1=th1, th2=0.0, x_count=0.0, a_cmd=0.0, a_del=a_del,
                  F_req=0.0, tau=0.0, mode="idle", slipped=False,
                  truth=np.zeros(6) if truth else None)


def test_empty_buffer():
    b = SampleBuffer()
    assert len(b) == 0
    assert b.at(0.0) is None
    assert b.t_head == 0.0


def test_append_and_head():
    b = SampleBuffer()
    for i in range(5):
        b.append(_s(i * 0.1))
    assert len(b) == 5
    assert b.t_head == pytest.approx(0.4)


def test_it_grows_past_its_initial_capacity():
    """A live hardware session runs for as long as you leave it running."""
    b = SampleBuffer(capacity=4)
    for i in range(1000):
        b.append(_s(i * 1e-3, th1=float(i)))
    assert len(b) == 1000
    assert b.window(0.0, 1.0)["th1"][-1] == pytest.approx(999.0)


def test_window_slices_by_time():
    b = SampleBuffer()
    for i in range(100):
        b.append(_s(i * 0.01, th1=float(i)))
    w = b.window(0.20, 0.30)
    assert w["th1"][0] == pytest.approx(20.0)
    assert w["th1"][-1] == pytest.approx(30.0)


def test_window_returns_every_channel():
    b = SampleBuffer()
    b.append(_s(0.0))
    w = b.window(0.0, 1.0)
    for key in ("t", "th1", "th2", "x_count", "a_cmd", "a_del", "F_req",
                "tau", "slipped", "truth"):
        assert key in w
    assert w["truth"].shape == (1, 6)


def test_at_returns_the_sample_in_force():
    """The animation draws one sample: the most recent at or before the cursor,
    never an interpolation the simulator did not produce."""
    b = SampleBuffer()
    for i in range(10):
        b.append(_s(i * 0.1, th1=float(i)))
    assert b.at(0.55).th1 == pytest.approx(5.0)
    assert b.at(0.0).th1 == pytest.approx(0.0)
    assert b.at(99.0).th1 == pytest.approx(9.0)
    assert b.at(-1.0) is None


def test_absent_truth_survives_the_round_trip():
    """What hardware will deliver: measured signals, no true state."""
    b = SampleBuffer()
    b.append(_s(0.0, truth=False))
    assert b.at(0.0).truth is None


def test_clear_resets():
    b = SampleBuffer()
    for i in range(10):
        b.append(_s(i * 0.1))
    b.clear()
    assert len(b) == 0
    assert b.at(0.05) is None


def test_command_defaults():
    c = Command(kind="start")
    assert c.name == "" and c.value == 0.0
