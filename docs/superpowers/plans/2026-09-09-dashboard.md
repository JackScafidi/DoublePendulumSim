# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A desktop dashboard that runs any controller against any scenario and shows the mechanism, its constants, and its signals.

**Architecture:** A `Source` abstraction the dashboard consumes without knowing its origin, filling an appendable `SampleBuffer`. `SimSource` produces samples on demand against a playback clock, so pausing computes nothing and commands land mid-run. Controllers live in a discovered package and declare their own tunable parameters, so a new file appears in the selector with working widgets.

**Tech Stack:** Python 3.11+, NumPy, PySide6, pyqtgraph, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-dashboard-design.md`

## Global Constraints

- No physical numeric value outside `dpc/params.py`. Scenario initial conditions are configuration and live in `dpc/scenarios.py`.
- State ordering is fixed: `s = [x, theta1, theta2, xdot, w1, w2]`.
- `dpc/controllers/` keeps the C-transcription constraints: fixed-size arrays, explicit indexing, no Python-specific constructs, `info` dicts strictly diagnostic and never read back.
- `dpc/ui/` is host-only. Nothing outside `dpc/ui/` may import from it, and deleting it must leave the simulator working.
- The dashboard reads `Sample.truth` only for drawing, never for anything a controller does.
- Only `SimSource` is implemented. `SerialSource` is a named seam.
- PySide6 and pyqtgraph are an optional dependency group; the physics suite runs without them.
- The existing 152 tests keep passing, apart from import updates where controllers moved.
- Commits carry no co-author trailer.

---

## Deviations from the spec

Two, both to protect the "deleting `dpc/ui/` leaves the simulator working" constraint.

1. **`ParamSpec` and `@register` live in `dpc/controllers/registry.py`, not `dpc/ui/registry.py`.** Controllers declare their own parameters, so putting the declaration in the UI package would make `dpc/controllers/` — the code destined for the MCU — import from host-only UI code.

2. **Scenarios live in `dpc/scenarios.py`, not `dpc/ui/scenarios.py`.** An initial condition plus a duration is simulation configuration, useful headless and in tests. Nothing about it is UI.

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `dpc/params.py` | adds a cached effective-parameter vector | modify |
| `dpc/scenarios.py` | `Scenario`, the shipped set, lookup | create |
| `dpc/controllers/__init__.py` | package marker | create |
| `dpc/controllers/registry.py` | `ParamSpec`, `Entry`, `@register`, `discover`, `build` | create |
| `dpc/controllers/basic.py` | `ZeroController`, `ConstantController` | create |
| `dpc/control.py` | keeps the contract only; loses the implementations | modify |
| `dpc/ui/__init__.py` | empty — must not import Qt | create |
| `dpc/ui/sample.py` | `Sample`, `Command`, `SampleBuffer` | create |
| `dpc/ui/source.py` | `Source` protocol, `SimSource` | create |
| `dpc/ui/panels/` | animation, plots, constants, transport, selectors | create |
| `dpc/ui/app.py` | window assembly, `main()` | create |
| `pyproject.toml` | `ui` optional dependency group, `dpc-dash` script | modify |
| `tests/test_params.py` | vector caching | modify |
| `tests/test_control.py` | imports follow the move | modify |
| `tests/test_run.py`, `tests/test_viz.py` | imports follow the move | modify |
| `tests/test_scenarios.py` | shipped scenarios are sane and runnable | create |
| `tests/test_registry.py` | discovery, failure isolation, construction | create |
| `tests/test_sample.py` | buffer append, window, growth | create |
| `tests/test_source.py` | playback clock, completion, commands | create |
| `tests/test_app.py` | offscreen smoke test | create |

---

### Task 1: Cache the effective-parameter vector

**Files:**
- Modify: `dpc/params.py`
- Test: `tests/test_params.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Params.vector()` unchanged in signature, now memoised on the instance.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_params.py`:

```python
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
```

Add `Friction` to the import line at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_params.py -q`
Expected: FAIL on `test_vector_is_cached_on_the_instance` — each call builds a new tuple.

- [ ] **Step 3: Write the implementation**

Replace `Params.vector` in `dpc/params.py`:

```python
    def vector(self) -> tuple[float, ...]:
        """Effective values in EFFECTIVE_NAMES order, for lambdified functions.

        Memoised on the instance. Every lambdified call -- M, Cqd, G, Ffric --
        asks for this, so it is rebuilt four times per solve and forty times
        per control tick at substeps=10. Assembling the dict costs 1.7 us,
        which is about 29% of the time a solve takes.

        Params is frozen, so object.__setattr__ is the way in. The cache lives
        in __dict__ rather than in a field, which leaves the dataclass-generated
        __eq__ and __hash__ untouched -- both read the declared fields only.
        """
        cached = self.__dict__.get("_vector_cache")
        if cached is None:
            eff = self.effective()
            cached = tuple(eff[name] for name in EFFECTIVE_NAMES)
            object.__setattr__(self, "_vector_cache", cached)
        return cached
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, all 155 tests, and noticeably faster than the previous ~80 s.

- [ ] **Step 5: Commit**

```bash
git add dpc/params.py tests/test_params.py
git commit -m "perf: memoise the effective-parameter vector"
```

---

### Task 2: Scenarios

**Files:**
- Create: `dpc/scenarios.py`
- Test: `tests/test_scenarios.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Scenario(key, label, s0, t_end, note)` frozen dataclass; `SCENARIOS: tuple[Scenario, ...]`; `by_key(key) -> Scenario`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scenarios.py`:

```python
import numpy as np
import pytest

from dpc.scenarios import SCENARIOS, Scenario, by_key


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
    sc = by_key("upright")
    assert np.allclose(sc.s0[1:3], 0.0)


def test_scenarios_are_frozen():
    with pytest.raises(Exception):
        SCENARIOS[0].t_end = 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scenarios.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.scenarios'`

- [ ] **Step 3: Write the implementation**

Create `dpc/scenarios.py`:

```python
"""Starting conditions worth running from.

A scenario says where the mechanism begins and how long to watch. It says
nothing about how the mechanism is driven -- that is the controller's job. The
two are orthogonal on purpose: any controller runs from any scenario, and it is
the cross product that shows a control law's weaknesses.

Angles follow the project convention: measured from straight up, positive
toward +x. So pi is hanging and 0 is inverted.
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Scenario:
    key: str
    """Stable identifier, used in saved configurations."""

    label: str
    """What the selector shows."""

    s0: np.ndarray
    """(6,) initial state [x, th1, th2, xdot, w1, w2]."""

    t_end: float
    """s. How long to watch -- distinct from how long a controller pushes."""

    note: str
    """Why this case is interesting."""


def _state(x=0.0, th1=0.0, th2=0.0, xd=0.0, w1=0.0, w2=0.0) -> np.ndarray:
    return np.array([x, th1, th2, xd, w1, w2], dtype=float)


PI = math.pi

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "hanging", "Hanging at rest",
        _state(th1=PI, th2=PI), 5.0,
        "The stable equilibrium. Nothing happens unless the cart moves, so it "
        "is the cleanest way to see what a command alone does.",
    ),
    Scenario(
        "upright", "Balanced upright",
        _state(), 5.0,
        "The unstable equilibrium. Exactly balanced, so any controller that "
        "does nothing looks perfect -- which makes it a trap as well as a test.",
    ),
    Scenario(
        "nudged", "Upright, 5 degrees off",
        _state(th1=math.radians(5.0), th2=math.radians(5.0)), 5.0,
        "The real balancing problem. Small enough for a linear controller, "
        "large enough that doing nothing falls over.",
    ),
    Scenario(
        "folded", "Upright link 1, hanging link 2",
        _state(th2=PI), 5.0,
        "The links disagree. Exercises the elbow coupling that a single "
        "pendulum model would miss entirely.",
    ),
    Scenario(
        "flat", "Both links horizontal",
        _state(th1=PI / 2, th2=PI / 2), 5.0,
        "Maximum gravitational torque, far from any linearisation point. "
        "Where swing-up has to work and small-angle control cannot.",
    ),
)

_BY_KEY = {sc.key: sc for sc in SCENARIOS}


def by_key(key: str) -> Scenario:
    """Look a scenario up, raising KeyError if it is not one of ours."""
    return _BY_KEY[key]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scenarios.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/scenarios.py tests/test_scenarios.py
git commit -m "feat: scenario definitions"
```

---

### Task 3: Controller registry and the controllers package

**Files:**
- Create: `dpc/controllers/__init__.py`, `dpc/controllers/registry.py`, `dpc/controllers/basic.py`
- Modify: `dpc/control.py`, `tests/test_control.py`, `tests/test_run.py`, `tests/test_viz.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `dpc.control.Controller`, `ControlOutput`; `dpc.sensors.Measurement`.
- Produces: `ParamSpec(name, label, unit, default, lo, hi, step)`; `Entry(key, label, cls, params, error)`; `register(label)` decorator; `discover() -> tuple[Entry, ...]`; `build(entry, values: dict[str, float]) -> Controller`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:

```python
import pytest

from dpc.controllers.registry import Entry, ParamSpec, build, discover
from dpc.params import Params
from dpc.sensors import Measurement


def _entry(key):
    for e in discover():
        if e.key == key:
            return e
    raise AssertionError(f"{key} not discovered; got {[e.key for e in discover()]}")


def test_discovery_finds_the_shipped_controllers():
    keys = {e.key for e in discover()}
    assert {"zero", "constant"} <= keys


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
    broken = tmp_path / "broken_ctrl.py"
    broken.write_text("raise RuntimeError('half-written')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(pkg, "__path__", list(pkg.__path__) + [str(tmp_path)])

    entries = discover()
    bad = [e for e in entries if e.error]
    assert any("half-written" in e.error for e in bad)
    assert all(e.cls is None for e in bad)
    assert {"zero", "constant"} <= {e.key for e in entries}


def test_entries_come_back_sorted_by_label():
    labels = [e.label for e in discover()]
    assert labels == sorted(labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.controllers'`

- [ ] **Step 3: Create the registry**

Create `dpc/controllers/__init__.py`:

```python
"""Control laws.

One law per module. Each declares its tunable parameters and registers itself,
which is what lets the dashboard show it without any UI code knowing it exists.

This package is destined for the MCU, so it keeps the project's C-transcription
constraints: fixed-size arrays, explicit indexing, no Python-specific
constructs. It must never import from dpc.ui.
"""
```

Create `dpc/controllers/registry.py`:

```python
"""Self-declaration, so a new control law needs no UI changes.

A controller states what it is called and what knobs it has. The dashboard
reads that and builds the widgets. Without this the folder-drop promise would
be false: every new law would need dashboard code.
"""

import importlib
import pkgutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParamSpec:
    """One tunable number, described well enough to build a widget from."""

    name: str
    """Constructor keyword this value is passed as."""

    label: str
    """Human wording for the widget."""

    unit: str
    """Shown beside the value. Empty string for dimensionless."""

    default: float
    lo: float
    hi: float
    step: float = 0.1
    """Increment for one click of a spin box."""


@dataclass(frozen=True)
class Entry:
    """A discovered controller, or a module that failed to import."""

    key: str
    label: str
    cls: type | None = None
    params: tuple[ParamSpec, ...] = ()
    error: str | None = None
    """Import failure message. When set, cls is None and the entry is shown
    disabled rather than being silently dropped."""


_REGISTRY: dict[str, Entry] = {}


def register(label: str, key: str | None = None):
    """Class decorator. `key` defaults to the class name minus 'Controller',
    lowercased, so ConstantController becomes 'constant'."""
    def wrap(cls):
        k = key or cls.__name__.removesuffix("Controller").lower()
        _REGISTRY[k] = Entry(key=k, label=label, cls=cls,
                             params=tuple(getattr(cls, "PARAMS", ())))
        return cls
    return wrap


def discover() -> tuple[Entry, ...]:
    """Import every module in this package so the decorators fire.

    A module that raises on import becomes a disabled entry carrying its
    message. Losing one controller to a typo is acceptable; losing the whole
    dashboard is not.
    """
    import dpc.controllers as pkg

    failures: list[Entry] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name == "registry":
            continue
        try:
            importlib.import_module(f"{pkg.__name__}.{info.name}")
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            failures.append(Entry(key=info.name,
                                  label=f"{info.name} (failed to load)",
                                  error=f"{type(exc).__name__}: {exc}"))

    entries = list(_REGISTRY.values()) + failures
    return tuple(sorted(entries, key=lambda e: e.label))


def build(entry: Entry, values: dict[str, float]):
    """Construct a controller, filling in declared defaults for anything the
    caller did not supply."""
    if entry.cls is None:
        raise ValueError(f"{entry.key} failed to load: {entry.error}")
    kwargs = {p.name: values.get(p.name, p.default) for p in entry.params}
    return entry.cls(**kwargs)
```

Note the broken-module test injects an extra path onto `dpc.controllers.__path__`; `iter_modules` walks it, and the import failure is caught. That is the mechanism under test.

- [ ] **Step 4: Move the controllers**

Create `dpc/controllers/basic.py`:

```python
"""The two controllers that exist to prove the loop closes.

Neither is a control law. ZeroController lets the whole chain run without
perturbing the physics; ConstantController walks the motor model through its
jerk limit, its saturation and its velocity ceiling in that order.
"""

import math

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register
from dpc.params import Params
from dpc.sensors import Measurement


@register("Zero command")
class ZeroController:
    """Commands nothing, ever."""

    PARAMS: tuple[ParamSpec, ...] = ()

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        return ControlOutput(a_cmd=0.0, mode="idle")


@register("Constant acceleration")
class ConstantController:
    """Push at a fixed acceleration for a while, then stop pushing.

    `hold` is a controller parameter, not a scenario one: it is how long to
    push, whereas scenario duration is how long to watch. Pushing for one
    second and watching for five is the normal way to see what the mechanism
    does once you stop driving it.
    """

    PARAMS = (
        ParamSpec("a", "acceleration", "m/s^2", 2.0, -10.0, 10.0, step=0.1),
        ParamSpec("hold", "hold for", "s", 1.0, 0.0, 30.0, step=0.1),
    )

    __slots__ = ("a", "hold")

    def __init__(self, a: float, hold: float = math.inf):
        self.a = a
        self.hold = hold

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        if m.t >= self.hold:
            return ControlOutput(a_cmd=0.0, mode="coast")
        return ControlOutput(a_cmd=self.a, mode="constant")
```

The constructor default is `math.inf` while the declared default is 1.0. That is deliberate: existing tests construct `ConstantController(1.0)` and expect a command that never stops, whereas a dashboard user wants a finite push.

In `dpc/control.py`, delete the `ZeroController` and `ConstantController` classes and update the module docstring's closing paragraph to:

```python
"""...

This module holds the contract only. The control laws themselves live in
dpc/controllers/, one per module, each declaring its own tunable parameters.
"""
```

- [ ] **Step 5: Update the importers**

In `tests/test_control.py`, `tests/test_run.py` and `tests/test_viz.py`, change
`from dpc.control import ConstantController, ZeroController` to
`from dpc.controllers.basic import ConstantController, ZeroController`,
keeping `ControlOutput` imported from `dpc.control` where it is used.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add dpc/controllers tests/test_registry.py dpc/control.py tests/test_control.py tests/test_run.py tests/test_viz.py
git commit -m "feat: controller package with self-declaring parameters"
```

---

### Task 4: Sample, Command and the buffer

**Files:**
- Create: `dpc/ui/__init__.py`, `dpc/ui/sample.py`
- Test: `tests/test_sample.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Sample`, `Command`, `SampleBuffer` with `append(Sample)`, `__len__`, `t_head -> float`, `window(t0, t1) -> dict[str, np.ndarray]`, `at(t) -> Sample | None`, `clear()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sample.py`:

```python
import numpy as np
import pytest

from dpc.ui.sample import Command, Sample, SampleBuffer


def _s(t, th1=0.0, a_del=0.0):
    return Sample(t=t, th1=th1, th2=0.0, x_count=0.0, a_cmd=0.0, a_del=a_del,
                  F_req=0.0, tau=0.0, mode="idle", slipped=False,
                  truth=np.zeros(6))


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
    """The animation draws one sample: the most recent one at or before the
    cursor, never an interpolation the simulator did not produce."""
    b = SampleBuffer()
    for i in range(10):
        b.append(_s(i * 0.1, th1=float(i)))
    assert b.at(0.55).th1 == pytest.approx(5.0)
    assert b.at(0.0).th1 == pytest.approx(0.0)
    assert b.at(99.0).th1 == pytest.approx(9.0)
    assert b.at(-1.0) is None


def test_clear_resets_without_reallocating_the_world():
    b = SampleBuffer()
    for i in range(10):
        b.append(_s(i * 0.1))
    b.clear()
    assert len(b) == 0
    assert b.at(0.05) is None


def test_command_defaults():
    c = Command(kind="start")
    assert c.name == "" and c.value == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sample.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.ui'`

- [ ] **Step 3: Write the implementation**

Create `dpc/ui/__init__.py`:

```python
"""Host-only dashboard code.

Nothing outside this package may import from it, and deleting it must leave the
simulator working. This module deliberately imports nothing -- in particular no
Qt -- so that dpc.ui.sample can be used in headless tests.
"""
```

Create `dpc/ui/sample.py`:

```python
"""The vocabulary the dashboard speaks, whatever is producing the data.

Nothing here knows about Qt, and nothing here knows whether a solver or a
serial port produced the numbers. That is the point: the same struct, the same
buffer and the same plots serve simulation today and hardware later.
"""

from dataclasses import dataclass, field

import numpy as np

_CHANNELS = ("t", "th1", "th2", "x_count", "a_cmd", "a_del", "F_req", "tau")


@dataclass(frozen=True)
class Sample:
    """One control tick, from wherever."""

    t: float
    """s since the run started."""

    th1: float
    th2: float
    """rad. What the encoders reported."""

    x_count: float
    """m. Position implied by the step counter -- not a measurement."""

    a_cmd: float
    """m/s^2 the controller asked for."""

    a_del: float
    """m/s^2 the motor delivered."""

    F_req: float
    """N the plant required."""

    tau: float
    """N m at the motor shaft."""

    mode: str
    """Which law was active."""

    slipped: bool
    """Whether the torque budget was exceeded on this tick."""

    truth: np.ndarray | None = None
    """(6,) true state, or None.

    On hardware this does not exist -- there is no sensor for it. Keeping it
    explicitly None rather than absent means the traces that use it simply stop
    drawing when the real cart is connected, with no branching anywhere."""


@dataclass(frozen=True)
class Command:
    """The upward path: what the dashboard sends to whatever is producing data.

    SimSource applies these to the next tick. A SerialSource would frame them
    up the wire. Building the path now costs nothing and cannot be retrofitted
    without rewriting the source layer.
    """

    kind: str
    """"start" | "stop" | "reset" | "set_param"."""

    name: str = ""
    """Dotted target for set_param: "drive.a_max" or "controller.a"."""

    value: float = 0.0


class SampleBuffer:
    """Append-and-window storage for a run.

    Growable rather than fixed, because a hardware session has no known length.
    Simulation is then the special case that fills it quickly, and the same
    scrub bar works over both.
    """

    __slots__ = ("_n", "_cap", "_cols", "_truth", "_mode", "_slipped")

    def __init__(self, capacity: int = 4096):
        self._n = 0
        self._cap = max(1, capacity)
        self._cols = {name: np.empty(self._cap) for name in _CHANNELS}
        self._truth = np.full((self._cap, 6), np.nan)
        self._slipped = np.zeros(self._cap, dtype=bool)
        self._mode: list[str] = []

    def __len__(self) -> int:
        return self._n

    @property
    def t_head(self) -> float:
        """Time of the most recent sample; 0.0 when empty."""
        return float(self._cols["t"][self._n - 1]) if self._n else 0.0

    def _grow(self) -> None:
        self._cap *= 2
        for name, arr in self._cols.items():
            self._cols[name] = np.resize(arr, self._cap)
        truth = np.full((self._cap, 6), np.nan)
        truth[:self._n] = self._truth[:self._n]
        self._truth = truth
        self._slipped = np.resize(self._slipped, self._cap)

    def append(self, s: Sample) -> None:
        if self._n == self._cap:
            self._grow()
        i = self._n
        for name in _CHANNELS:
            self._cols[name][i] = getattr(s, name)
        self._slipped[i] = s.slipped
        if s.truth is not None:
            self._truth[i] = s.truth
        self._mode.append(s.mode)
        self._n = i + 1

    def clear(self) -> None:
        self._n = 0
        self._mode.clear()
        self._truth[:] = np.nan

    def window(self, t0: float, t1: float) -> dict[str, np.ndarray]:
        """Every channel over [t0, t1], as views a plot can draw directly."""
        t = self._cols["t"][:self._n]
        lo = int(np.searchsorted(t, t0, side="left"))
        hi = int(np.searchsorted(t, t1, side="right"))
        out = {name: self._cols[name][lo:hi] for name in _CHANNELS}
        out["slipped"] = self._slipped[lo:hi]
        out["truth"] = self._truth[lo:hi]
        return out

    def at(self, t: float) -> Sample | None:
        """The sample in force at time t -- the most recent one at or before it.

        Deliberately not interpolated: the animation should show states the
        simulator actually produced.
        """
        if self._n == 0:
            return None
        i = int(np.searchsorted(self._cols["t"][:self._n], t, side="right")) - 1
        if i < 0:
            return None
        truth = self._truth[i]
        return Sample(
            **{name: float(self._cols[name][i]) for name in _CHANNELS},
            mode=self._mode[i],
            slipped=bool(self._slipped[i]),
            truth=None if np.isnan(truth[0]) else truth.copy(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sample.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/ui tests/test_sample.py
git commit -m "feat: sample vocabulary and append-and-window buffer"
```

---

### Task 5: SimSource

**Files:**
- Create: `dpc/ui/source.py`
- Test: `tests/test_source.py`

**Interfaces:**
- Consumes: `dpc.model.NumericModel`, `dpc.motor`, `dpc.sensors.measure`, `dpc.dynamics.deriv_accel`, `dpc.simulate.rk4_step`, `dpc.ui.sample.Sample/Command`, `dpc.scenarios.Scenario`.
- Produces: `Source` protocol; `SimSource(model, params, substeps=2)` with `start(controller, scenario)`, `poll(t_playback) -> list[Sample]`, `send(Command)`, `stop()`, `done -> bool`, `params -> Params`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_source.py`:

```python
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
    assert all(s.a_cmd == pytest.approx(3.0) for s in after)


def test_drive_parameters_can_be_commanded():
    src = _src()
    src.start(_constant(a=99.0), by_key("hanging"))
    src.send(Command(kind="set_param", name="drive.a_max", value=1.0))
    out = src.poll(0.5)
    assert max(abs(s.a_del) for s in out) == pytest.approx(1.0, rel=1e-6)


def test_reset_returns_to_the_scenario_start():
    src = _src()
    src.start(_constant(), by_key("nudged"))
    src.poll(0.2)
    src.send(Command(kind="reset"))
    out = src.poll(0.001)
    assert out[0].t == pytest.approx(0.001)
    assert not src.done


def test_a_poll_is_bounded_so_the_ui_cannot_freeze():
    """A huge clock jump must return promptly rather than simulating minutes
    of plant inside one repaint."""
    src = _src(max_ticks_per_poll=50)
    src.start(_constant(), by_key("hanging"))
    assert len(src.poll(4.0)) == 50


def test_substeps_default_is_the_dashboard_value_not_the_library_one():
    assert _src().substeps == 2
    assert Params().ctrl.substeps == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_source.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dpc.ui.source'`

- [ ] **Step 3: Write the implementation**

Create `dpc/ui/source.py`:

```python
"""Where samples come from.

The dashboard consumes samples and never asks what produced them. Today that is
a solver; later it is a serial port carrying frames from the STM32. Same
protocol, same struct, so no plot and no panel changes when the hardware
arrives.

SimSource is a pull model: it computes exactly the ticks the playback clock has
reached and no more. Pausing therefore computes nothing, and a command sent
mid-run lands on the next tick -- which is the bidirectional path behaving in
simulation as it will on the bench.
"""

from dataclasses import replace
from typing import Protocol

import numpy as np

from dpc.dynamics import deriv_accel
from dpc.model import NumericModel
from dpc.motor import MotorState
from dpc.motor import step as motor_step
from dpc.params import Params
from dpc.scenarios import Scenario
from dpc.sensors import measure
from dpc.simulate import rk4_step
from dpc.ui.sample import Command, Sample


class Source(Protocol):
    """Anything that can produce samples and accept commands."""

    def start(self, controller, scenario: Scenario) -> None: ...
    def poll(self, t_playback: float) -> list[Sample]: ...
    def send(self, cmd: Command) -> None: ...
    def stop(self) -> None: ...


class SimSource:
    """Runs the model on demand against a playback clock.

    substeps defaults to 2 rather than the library's 10. RK4 at dt = 1 ms is
    already converged for this plant -- dropping from 40 substeps to 1 moves the
    final state by 2.4e-9 -- while the cost is linear, so 10 substeps buys
    thirteen digits nobody reads and gives up real-time playback. At 2 the
    simulator runs at about twice real time, leaving headroom to fast-forward.
    """

    def __init__(self, model: NumericModel, params: Params, substeps: int = 2,
                 max_ticks_per_poll: int = 20000):
        self.model = model
        self.params = params
        self.substeps = substeps
        self.max_ticks_per_poll = max_ticks_per_poll
        """A large clock jump must not simulate minutes of plant inside one
        repaint. Hitting this cap means playback falls behind, which the UI
        reports rather than hides.

        Set well above a full scenario's tick count (5 s at 1 kHz is 5000) so
        that reaching the end of a run is detected by the scenario check rather
        than masked by this cap."""

        self._controller = None
        self._scenario: Scenario | None = None
        self._s = np.zeros(6)
        self._motor = MotorState()
        self._i = 0
        self.done = True

    @property
    def ts(self) -> float:
        return self.params.ctrl.ts

    def start(self, controller, scenario: Scenario) -> None:
        self._controller = controller
        self._scenario = scenario
        self._restart()

    def _restart(self) -> None:
        self._s = np.array(self._scenario.s0, dtype=float)
        self._motor = MotorState()
        self._i = 0
        self.done = False
        self._controller.reset(self.params)

    def stop(self) -> None:
        self.done = True

    def send(self, cmd: Command) -> None:
        """Applied to state now, so it takes effect on the next tick computed."""
        if cmd.kind == "reset":
            self._restart()
        elif cmd.kind == "stop":
            self.done = True
        elif cmd.kind == "set_param":
            target, _, field = cmd.name.partition(".")
            if target == "controller":
                setattr(self._controller, field, cmd.value)
            elif target == "drive":
                self.params = replace(
                    self.params,
                    drive=replace(self.params.drive, **{field: cmd.value}))
            else:
                raise ValueError(f"unknown command target {cmd.name!r}")

    def poll(self, t_playback: float) -> list[Sample]:
        """Every sample from the current head up to t_playback."""
        if self.done or self._controller is None:
            return []

        out: list[Sample] = []
        ts, sub = self.ts, self.substeps
        dt = ts / sub
        p = self.params

        def f(state: np.ndarray, u: float) -> np.ndarray:
            return deriv_accel(self.model, state, u, p)

        while len(out) < self.max_ticks_per_poll:
            t_next = (self._i + 1) * ts
            if t_next > t_playback + 1e-12:
                break
            if t_next > self._scenario.t_end + 1e-12:
                self.done = True
                break

            t_now = self._i * ts
            m = measure(t_now, self._s, self._motor, ts, p)
            cmd = self._controller.update(m)
            mo = motor_step(self.model, cmd.a_cmd, self._s, self._motor, ts, p)

            s_next = self._s
            for _ in range(sub):
                s_next = rk4_step(f, s_next, mo.a_del, dt)

            self._s = s_next
            self._motor = mo.state
            self._i += 1

            out.append(Sample(
                t=t_next,
                th1=float(s_next[1]), th2=float(s_next[2]),
                x_count=m.x_count,
                a_cmd=cmd.a_cmd, a_del=mo.a_del,
                F_req=mo.F_req, tau=mo.tau,
                mode=cmd.mode, slipped=mo.slipped,
                truth=s_next.copy(),
            ))

        return out
```

Note `p` is bound once at the top of `poll`, so a `set_param` arriving between polls takes effect on the next poll rather than mid-loop — which is what "next tick" means.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_source.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dpc/ui/source.py tests/test_source.py
git commit -m "feat: pull-model simulation source"
```

---

### Task 6: Visual design pass

**Files:**
- Create: a design artifact and `docs/dashboard-visual-design.md` recording the decisions

**Interfaces:**
- Consumes: the layout agreed in the spec.
- Produces: a colour palette, type scale, spacing scale, pendulum rendering treatment and plot styling, recorded concretely enough for Task 7 to translate into Qt stylesheets and pyqtgraph theming.

This task is interactive and must not be skipped: the project owner asked
explicitly that the real visuals be designed deliberately rather than emerge
from widget code.

- [ ] **Step 1: Invoke the design skill** with the layout from the spec — constants column full height right, animation top-left, transport bar beneath it, 2x2 plot grid below, selectors above the animation.

- [ ] **Step 2: Present the result and get the look approved.**

- [ ] **Step 3: Record the decisions** in `docs/dashboard-visual-design.md` as concrete values: hex colours for background, panel, grid, text, and one colour per signal (theta1, theta2, true position, step count, commanded, delivered, torque, budget line); font family and sizes for panel titles, labels and numeric readouts; spacing unit; pendulum link widths and joint radii.

- [ ] **Step 4: Commit**

```bash
git add docs/dashboard-visual-design.md
git commit -m "docs: dashboard visual design"
```

---

### Task 7: Panels

**Files:**
- Create: `dpc/ui/panels/__init__.py`, `animation.py`, `plots.py`, `constants.py`, `transport.py`, `selectors.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `SampleBuffer`, `Sample`, `Scenario`, `Entry`, `ParamSpec`, `Params`, and the palette from Task 6.
- Produces: `AnimationPanel(QWidget)` with `show_sample(Sample | None, Params)`; `PlotPanel(QWidget)` with `redraw(window: dict, Params)`; `ConstantsPanel(QWidget)` with `set_controller(Entry)`, `set_scenario(Scenario)`, `set_params(Params)`, `set_live(dict)`, signal `changed(str, float)`; `TransportPanel(QWidget)` with signals `play_pressed()`, `pause_pressed()`, `scrubbed(float)`, `speed_changed(float)` and `set_range(float)`, `set_cursor(float)`, `set_status(str)`; `SelectorPanel(QWidget)` with signals `run_pressed()` and properties `controller_entry`, `scenario`.

- [ ] **Step 1: Add the optional dependency group**

In `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
ui = ["PySide6>=6.6", "pyqtgraph>=0.13"]

[project.scripts]
dpc-dash = "dpc.ui.app:main"
```

Install with `.venv/Scripts/python.exe -m pip install -e ".[ui,dev]"`.

- [ ] **Step 2: Write the panels**

The panel *bodies* are written against the palette Task 6 produces, so their
code is not reproduced here -- it would be invented colour values that the
design pass then contradicts. The **Interfaces** block above is the binding
part: those signatures and signals are what Task 8 wires together, and they do
not change whatever the design pass decides.

Each panel is a `QWidget` that owns its layout and exposes the interface above.
Rules that apply to all of them, and that the smoke test in Task 8 depends on:

- No panel computes anything. They render what they are handed. Every
  calculation belongs in `source.py` or `sample.py`, which is what keeps the
  logic testable without Qt.
- No panel holds a reference to the source or the buffer. `app.py` pushes data
  in.
- `ConstantsPanel` builds its controller widgets from `Entry.params` — one
  labelled `QDoubleSpinBox` per `ParamSpec`, range from `lo`/`hi`, increment
  from `step`, suffix from `unit`. It must never name a controller explicitly.
- `ConstantsPanel` emits `changed(name, value)` with dotted names
  (`"controller.a"`, `"drive.a_max"`) so `app.py` can forward them straight into
  a `Command` without translation.
- Plant parameters and scenario values render as read-only labels.
- `AnimationPanel` draws from `Sample.truth` when present and from the measured
  angles plus `x_count` when it is `None`, so the same panel works on hardware.
  Cart position, link 1 from the cart at `th1`, link 2 from the elbow at `th2`,
  with `l1`/`l2` read from `Params` — never hardcoded.
- `PlotPanel` holds four `pyqtgraph.PlotWidget`s in a 2x2 grid: angles in
  degrees; cart position with true and step-counted traces; commanded against
  delivered acceleration with `+/-a_max` lines; torque with `+/-tau_budget`
  lines. Curves are created once and updated with `setData`, never recreated,
  or the redraw allocates on every frame.

- [ ] **Step 3: Verify the panels import and construct**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "from PySide6.QtWidgets import QApplication; from dpc.ui.panels.animation import AnimationPanel; app=QApplication([]); AnimationPanel(); print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add dpc/ui/panels pyproject.toml
git commit -m "feat: dashboard panels"
```

---

### Task 8: The window and the entry point

**Files:**
- Create: `dpc/ui/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: every panel, `SimSource`, `SampleBuffer`, `discover()`, `SCENARIOS`.
- Produces: `Dashboard(QMainWindow)` with `tick()`, `run()`, `set_speed(float)`; `main() -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dpc.ui.app import Dashboard  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dash(qapp):
    return Dashboard()


def test_window_assembles_with_every_panel(dash):
    for name in ("selectors", "animation", "transport", "plots", "constants"):
        assert getattr(dash, name) is not None


def test_the_selectors_are_populated_from_discovery(dash):
    assert dash.selectors.controller_count >= 2
    assert dash.selectors.scenario_count >= 4


def test_running_then_ticking_produces_samples(dash):
    dash.run()
    for _ in range(20):
        dash.tick()
    assert len(dash.buffer) > 0


def test_the_cursor_never_runs_past_the_head(dash):
    dash.run()
    for _ in range(20):
        dash.tick()
    assert dash.cursor <= dash.buffer.t_head + 1e-9


def test_editing_a_constant_reaches_the_source(dash):
    dash.run()
    dash.constants.changed.emit("drive.a_max", 1.0)
    for _ in range(40):
        dash.tick()
    w = dash.buffer.window(0.0, dash.buffer.t_head)
    assert max(abs(w["a_del"])) <= 1.0 + 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -q`
Expected: FAIL with `ImportError: cannot import name 'Dashboard'`

- [ ] **Step 3: Write `dpc/ui/app.py`**

`Dashboard` assembles the layout, owns the `SampleBuffer`, the `SimSource` and
the playback clock, and wires the panels together:

- A `QTimer` at 20 ms calls `tick()`. `tick()` advances the cursor by
  `elapsed * speed`, calls `source.poll(cursor)`, appends what comes back, then
  pushes `buffer.at(cursor)` to the animation and `buffer.window(...)` to the
  plots.
- `tick()` must be callable without the timer, which is what makes the test
  above deterministic — it drives the clock itself rather than sleeping.
- Scrubbing sets the cursor backwards; the source is not asked for anything it
  has already produced, so history replays from the buffer.
- When `poll` returns `max_ticks_per_poll` samples the status line reads
  "falling behind", rather than the UI pretending it is at the requested speed.
- `constants.changed` is connected straight to
  `source.send(Command(kind="set_param", name=..., value=...))`.
- `main()` creates the `QApplication`, builds the model once (about 0.6 s from
  cache), shows the window, and returns `app.exec()`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS

- [ ] **Step 5: Launch it**

Run: `.venv/Scripts/python.exe -m dpc.ui.app`
Expected: the window opens, a run plays, plots update, scrubbing works.

- [ ] **Step 6: Commit**

```bash
git add dpc/ui/app.py tests/test_app.py
git commit -m "feat: dashboard window and entry point"
```

---

## Done when

- `.venv/Scripts/python.exe -m pytest -q` is green, including the pre-existing physics tests.
- `dpc-dash` opens a window, runs any controller against any scenario, and plays back with a working scrub bar.
- Dropping a new controller module into `dpc/controllers/` makes it appear in the selector with working widgets and no UI code changed.
- Deleting `dpc/ui/` leaves the simulator and its test suite working.
