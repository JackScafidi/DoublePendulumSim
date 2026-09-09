import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dpc.model import ModelConfig  # noqa: E402
from dpc.model import build as build_model  # noqa: E402
from dpc.ui.app import Dashboard  # noqa: E402

M = build_model(ModelConfig())


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dash(qapp):
    d = Dashboard(model=M)
    d._timer.stop()          # the tests drive the clock themselves
    yield d
    d.close()


def test_window_assembles_with_every_panel(dash):
    for name in ("selectors", "animation", "transport", "plots", "constants"):
        assert getattr(dash, name) is not None


def test_the_selectors_are_populated_from_discovery(dash):
    assert dash.selectors.controller_count >= 2
    assert dash.selectors.scenario_count >= 4


def test_running_then_ticking_produces_samples(dash):
    dash.run()
    for _ in range(20):
        dash.tick(dt=0.02)
    assert len(dash.buffer) > 0


def test_the_cursor_never_runs_past_the_head(dash):
    """The solver can fall behind the wall clock; drawing ahead of what exists
    would show a frozen frame while the clock kept counting."""
    dash.run()
    for _ in range(20):
        dash.tick(dt=0.02)
    assert dash.cursor <= dash.buffer.t_head + 1e-9


def test_editing_a_constant_reaches_the_source(dash):
    """The command path the hardware link will use, exercised on every edit."""
    dash.run()
    dash.constants.changed.emit("drive.a_max", 1.0)
    for _ in range(40):
        dash.tick(dt=0.02)
    w = dash.buffer.window(0.0, dash.buffer.t_head)
    assert len(w["a_del"]) > 0
    assert max(abs(w["a_del"])) <= 1.0 + 1e-6


def test_scrubbing_back_reviews_history_without_resimulating(dash):
    dash.run()
    for _ in range(30):
        dash.tick(dt=0.02)
    head = dash.buffer.t_head
    n = len(dash.buffer)
    dash._on_scrub(head / 2.0)
    assert dash.cursor == pytest.approx(head / 2.0)
    assert len(dash.buffer) == n


def test_a_paused_dashboard_computes_nothing(dash):
    dash.run()
    for _ in range(10):
        dash.tick(dt=0.02)
    n = len(dash.buffer)
    dash._on_play(False)
    for _ in range(30):
        dash.tick(dt=0.02)
    assert len(dash.buffer) == n


def test_the_run_ends_and_says_so(dash):
    dash.run()
    for _ in range(400):
        dash.tick(dt=0.05)
        if dash.source.done:
            break
    assert dash.source.done
    assert dash.transport.status.text() == "done"


def test_a_failed_controller_cannot_be_run(dash, monkeypatch):
    """Listed so a typo is diagnosable, inert so it cannot be started."""
    from dpc.controllers.registry import Entry
    monkeypatch.setattr(type(dash.selectors), "controller_entry",
                        property(lambda self: Entry(key="x", label="x",
                                                    error="boom")))
    dash.run()
    assert dash.transport.status.text() == "controller failed to load"
    assert len(dash.buffer) == 0
