import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dpc.controllers.registry import discover  # noqa: E402
from dpc.params import Params  # noqa: E402
from dpc.scenarios import by_key  # noqa: E402
from dpc.ui.panels.constants import ConstantsPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    p = ConstantsPanel()
    entry = next(e for e in discover() if e.key == "constant")
    p.set_controller(entry, {s.name: s.default for s in entry.params})
    p.set_scenario(by_key("hanging"))
    p.set_params(Params(), 2)
    return p


def test_nothing_is_marked_at_the_defaults(panel):
    assert not any(r.modified for r in panel._rows.values())


def test_editing_marks_the_row_and_shows_what_it_moved_from(panel):
    """The two things that keep a long list legible: which values you moved,
    and what they were before."""
    row = panel._rows["drive.a_max"]
    baseline = row.baseline

    panel._edited("drive.a_max", baseline + 3.0)
    assert row.modified
    assert row.base.text() == f"({baseline:g})"

    panel._edited("drive.a_max", baseline)
    assert not row.modified
    assert row.base.text() == ""


def test_the_marker_keeps_its_column_when_unmodified(panel):
    """Transparent, not hidden -- otherwise every name shifts sideways the
    moment a value changes."""
    row = panel._rows["drive.v_max"]
    assert row.mark.text()
    assert "transparent" in row.mark.styleSheet()
    panel._edited("drive.v_max", row.baseline + 0.2)
    assert "transparent" not in row.mark.styleSheet()


def test_the_filter_collapses_to_only_what_changed(panel):
    panel._edited("drive.a_max", 4.0)
    panel.filter_btn.setChecked(True)
    assert panel._rows["drive.a_max"].isVisibleTo(panel)
    assert not panel._rows["drive.v_max"].isVisibleTo(panel)

    panel.filter_btn.setChecked(False)
    assert panel._rows["drive.v_max"].isVisibleTo(panel)


def test_reset_emits_every_modified_value_back_at_its_baseline(panel):
    seen = []
    panel.changed.connect(lambda n, v: seen.append((n, v)))

    panel._edited("drive.a_max", 4.0)
    panel._edited("controller.a", 7.0)
    seen.clear()

    panel.reset_modified()
    assert dict(seen) == {
        "drive.a_max": panel._rows["drive.a_max"].baseline,
        "controller.a": panel._rows["controller.a"].baseline,
    }


def test_the_snippet_carries_only_what_changed(panel):
    assert panel.modified_snippet() == "# nothing modified"
    panel._edited("drive.a_max", 4.0)
    panel._edited("controller.a", 5.5)
    assert panel.modified_snippet() == "a=5.5,\na_max=4,"


def test_read_only_rows_are_never_marked(panel):
    """Plant values and scenario initial conditions have no baseline to differ
    from -- they are facts, not settings."""
    assert "plant.m_cart" not in panel._rows
    assert all(r.baseline is not None for r in panel._rows.values())
