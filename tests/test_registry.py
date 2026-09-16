import pytest

from dpc.controllers.registry import build, discover
from dpc.params import Params
from dpc.sensors import Measurement


def _entry(key):
    for e in discover():
        if e.key == key:
            return e
    raise AssertionError(f"{key} not discovered; got {[e.key for e in discover()]}")


def test_discovery_finds_the_shipped_controllers():
    assert {"zero", "constant"} <= {e.key for e in discover()}


def test_entries_carry_a_label_and_their_parameters():
    e = _entry("constant")
    assert e.label == "Constant acceleration"
    assert [p.name for p in e.params] == ["a", "hold"]
    assert e.error is None


def test_param_specs_are_usable_as_widget_definitions():
    """Everything a spin box needs, or the dashboard has to special-case."""
    for p in _entry("constant").params:
        assert p.label and p.unit is not None
        assert p.lo <= p.default <= p.hi
        assert p.step > 0.0


def test_build_passes_values_as_keyword_arguments():
    c = build(_entry("constant"), {"a": 3.0, "hold": 0.5})
    c.reset(Params())
    assert c.update(Measurement(0.0, 0.0, 0.0, 0.0, 1e-3)).a_cmd == pytest.approx(3.0)
    assert c.update(Measurement(0.9, 0.0, 0.0, 0.0, 1e-3)).a_cmd == pytest.approx(0.0)


def test_build_falls_back_to_declared_defaults():
    c = build(_entry("constant"), {})
    c.reset(Params())
    assert c.update(Measurement(0.0, 0.0, 0.0, 0.0, 1e-3)).a_cmd == pytest.approx(2.0)


def test_a_broken_module_is_listed_disabled_rather_than_raising(tmp_path, monkeypatch):
    """A half-written MPC must not stop the window opening."""
    import dpc.controllers as pkg

    (tmp_path / "broken_ctrl.py").write_text(
        "raise RuntimeError('half-written')\n", encoding="utf-8")
    monkeypatch.setattr(pkg, "__path__", list(pkg.__path__) + [str(tmp_path)])

    entries = discover()
    messages = [e.error for e in entries if e.error is not None]
    assert any("half-written" in msg for msg in messages)
    assert all(e.cls is None for e in entries if e.error is not None)
    assert {"zero", "constant"} <= {e.key for e in entries}


def test_building_a_failed_entry_refuses_rather_than_crashing_obscurely():
    from dpc.controllers.registry import Entry
    with pytest.raises(ValueError, match="failed to load"):
        build(Entry(key="x", label="x", error="boom"), {})


def test_entries_come_back_sorted_by_label():
    labels = [e.label for e in discover()]
    assert labels == sorted(labels)
