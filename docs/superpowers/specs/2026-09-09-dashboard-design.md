# Dashboard Design

*2026-09-09*

## Goal

A desktop dashboard that runs a controller against a scenario and shows what
happened: an animation of the mechanism, the full constant set, and plots of the
signals that matter.

The milestone is finished when a controller can be selected, configured, run
against any scenario, and watched -- and when dropping a new controller file
into `dpc/controllers/` makes it appear in the selector with working widgets and
no UI code changed.

Explicitly out of scope: the control laws themselves (PID, LQR, MPC, swing-up),
the serial link to hardware, and parameter fitting.

## The end goal shapes the design

The dashboard is eventually a hardware monitor and console, not only a
simulation viewer. It must display live values from the real mechanism and send
commands back to it. That is not built here, but it decides three things now.

**A source abstraction.** The dashboard never knows where its data came from. It
consumes `Sample` records from a `Source`. `SimSource` produces them by running
the model; a later `SerialSource` will produce them by parsing frames off USB.
Same struct, same plots, same animation.

**A command path in both directions.** `Source.send(cmd)` exists from the first
day. `SimSource` applies commands to the next tick; `SerialSource` will frame
them up the wire. Designing this in costs nothing now and is a rewrite of the
source layer if deferred.

**An appendable buffer, not a fixed array.** Live hardware delivers samples one
at a time, indefinitely. So the data model is an append-and-window buffer, and
simulation is the special case that fills it quickly. One code path serves both,
and the scrub bar works in either.

Only `SimSource` is implemented. `SerialSource` is a named seam, in the manner
of `drive="compliant"` in `model.py`.

## Data vocabulary

```python
@dataclass(frozen=True)
class Sample:
    """One control tick, from wherever."""
    t: float
    th1: float; th2: float; x_count: float      # the wire signals
    a_cmd: float; a_del: float                  # command and delivery
    F_req: float; tau: float                    # diagnostics
    mode: str; slipped: bool
    truth: np.ndarray | None = None             # (6,) -- None on hardware
```

`truth` carries the `Measurement` discipline into the UI. In simulation the true
state is known and worth drawing; on hardware it does not exist. Making it
explicitly `None` rather than absent means plots that use it simply stop drawing
a line when the real cart is connected -- no branching, no separate mode.

```python
@dataclass(frozen=True)
class Command:
    kind: str      # "start" | "stop" | "reset" | "set_param"
    name: str = ""
    value: float = 0.0


class Source(Protocol):
    def start(self, controller, scenario) -> None: ...
    def poll(self, t_playback: float) -> list[Sample]: ...
    def send(self, cmd: Command) -> None: ...
    def stop(self) -> None: ...
```

`SampleBuffer` holds columns as growable NumPy arrays and exposes slices by time
window. Plots read slices; the animation reads one sample.

## The run model

Measured on this machine: one control tick costs about 2 ms at the library
default of `substeps=10`, which is 0.5x real time. The substeps are the reason,
and they are buying accuracy that is not needed.

| substeps | speed | final-state error vs substeps=40 |
|---|---|---|
| 40 | 0.13x | -- |
| 10 (library default) | 0.51x | 2.2e-13 |
| 4 | 1.20x | 9.3e-12 |
| 2 | 2.00x | 1.5e-10 |
| 1 | 3.14x | 2.4e-9 |

RK4 at `dt = 1 ms` is already converged for this plant. The dashboard therefore
runs at `substeps=2` -- 2x real time, leaving headroom for fast-forward -- while
`Control.substeps` stays at 10 as the library default, because the physics tests
should remain conservative. The value in force is shown in the constants column,
so what is being watched is never ambiguous.

**One optimisation is taken here.** `Params.vector()` is rebuilt from scratch
inside every lambdified call, so `M`, `Cqd`, `G` and `Ffric` each pay 1.7 us of
dict assembly -- 6.8 us of the 23.8 us that `_terms` costs. `Params` is a frozen
dataclass and hashable, so the vector is cached, removing about 29% of every
solve with no behavioural change. The existing suite plus one equality test
guard it.

**The loop is a pull model with no threads.** A `QTimer` at 50 Hz advances a
playback clock and asks the source for every sample up to it; `SimSource`
simulates those ticks on demand and appends them. Pausing computes nothing.
Commands land mid-run, which is the bidirectional path working in simulation
exactly as it will on hardware. Speed is a multiplier on the playback clock;
past the solver's ceiling the UI reports that it is falling behind rather than
silently lying about the rate. The eventual `SerialSource` needs no thread
either, since Qt's `readyRead` is event-driven.

**Two clocks: a live head and a view cursor.** The head is how far the source has
produced; the cursor is what is drawn. Equal means watching live. Scrub back and
history is replayed from the buffer without re-simulating. This is how a
telemetry viewer behaves, and it is what hardware will require.

## Controllers and scenarios

These are orthogonal. A run is the cross product: any controller against any
scenario.

**The interface stays in `control.py`; the implementations move to
`dpc/controllers/`.** `Controller`, `ControlOutput` and `Measurement` are the
contract and belong with the contract. `ZeroController` and `ConstantController`
move into the folder alongside the future PID and LQR, so there is exactly one
place a control law ever lives.

**Each controller declares its own knobs.** This is what makes dropping in a file
work:

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str; label: str; unit: str
    default: float; lo: float; hi: float


@register("Constant acceleration")
class ConstantController:
    PARAMS = (
        ParamSpec("a",    "acceleration", "m/s^2",  2.0, -10.0, 10.0),
        ParamSpec("hold", "hold for",     "s",      1.0,   0.0, 30.0),
    )
```

The dashboard reads `PARAMS`, builds one labelled spin box per entry, and passes
the values as keyword arguments. A new controller appears fully configured with
no UI edits. Without this declaration every new controller would need dashboard
code and the folder-drop promise would be false.

`hold` is a controller parameter, not a scenario one: it is how long to push
before commanding zero, whereas scenario duration is how long to watch. Pushing
for 1 s and watching for 5 s is a normal thing to want. Together they are the
near-term "put in an acceleration and a time".

**Scenarios are initial conditions**, declared the same way:

```python
@dataclass(frozen=True)
class Scenario:
    key: str; label: str
    s0: np.ndarray     # (6,)
    t_end: float
    note: str          # why this case is interesting
```

Shipped: hanging at rest, balanced upright, upright nudged 5 degrees, link 2
hanging from an upright link 1, and both links horizontal.

**Discovery walks the package** with `pkgutil`, importing each module so the
decorators fire. A controller module that raises on import is listed as a
disabled entry carrying its error message rather than taking the dashboard down;
a half-written MPC must not stop the window opening.

## Layout

Constants column runs the full window height on the right, so the whole
parameter set is visible at once. The left column holds, top to bottom:
controller and scenario selectors with a Run button, the animation, a transport
bar (play/pause, scrub, speed), and a 2x2 grid of plots.

```
+-------------------------------------------+----------------+
| Controller v   Scenario v   [Run]         |  Controller    |
+-------------------------------------------+  Scenario      |
|                                           |  Drive         |
|              animation                    |  Plant         |
|                                           |  Live readout  |
+-------------------------------------------+                |
| > ----------o--------  1.84 s   1x        |                |
+---------------------+---------------------+                |
| angles              | cart x              |                |
+---------------------+---------------------+                |
| accel cmd / delivered | torque vs budget  |                |
+---------------------+---------------------+----------------+
```

Plots: angles in degrees; cart position with true and step-counted traces
overlaid; commanded against delivered acceleration with the `a_max` lines drawn;
motor torque against the budget lines. Each is the pairing that makes the number
mean something -- torque alone says nothing without the budget beside it, and the
gap between commanded and delivered acceleration is the whole actuator model.

**Editable:** controller `PARAMS` and the drive block (`a_max`, `v_max`,
`jerk_max`, `tau_lag`, `slip_enable`). Those are what gets tuned while playing.
**Read-only:** plant parameters and scenario initial conditions, which are
measured or declared facts and are changed in source. This is easy to loosen
later; starting loose would make the constants column a place where physics gets
edited by accident.

**Visual design is a separate pass.** The layout above is structure. Colour,
typography, spacing, the pendulum rendering and plot styling are designed
deliberately before being translated into Qt stylesheets and pyqtgraph theming.

## Module layout

```
dpc/ui/
    sample.py      Sample, Command, SampleBuffer
    source.py      Source protocol, SimSource
    scenarios.py   Scenario, the registry, the shipped scenarios
    registry.py    ParamSpec, @register, discovery
    panels/        animation, constants, plots, transport, selectors
    app.py         window assembly and entry point
dpc/controllers/
    __init__.py    package discovery
    basic.py       ZeroController, ConstantController
```

`dpc/ui/` is host-only and never crosses to the MCU. `dpc/controllers/` is code
that eventually does, and keeps the existing C-transcription constraints.
PySide6 and pyqtgraph go in an optional dependency group, so `pip install -e .`
still works headless and the physics suite runs without them.

## Testing

Every piece of logic lives outside the widgets, so it is tested without Qt.

- `SampleBuffer`: append, window slicing, growth past its initial capacity.
- `SimSource`: produces exactly the samples the playback clock asks for; stops
  at scenario end; `truth` is populated; commands applied mid-run take effect on
  the following tick and not before.
- Registry: discovery finds every controller in the package; a module that
  raises on import yields a disabled entry carrying the message rather than
  propagating; `PARAMS` round-trips into constructor keyword arguments.
- Scenarios: every shipped scenario has a 6-vector, a positive duration, and
  runs without raising.
- Parameter caching: the cached vector equals `effective()` in
  `EFFECTIVE_NAMES` order for both default and perturbed parameter sets.
- One widget smoke test under `QT_QPA_PLATFORM=offscreen`: the window builds,
  holds the expected panels, and a Run produces samples. Skipped when PySide6 is
  absent.

The existing 152 tests keep passing untouched, apart from `tests/test_control.py`
following the controllers to their new module.

## Constraints carried forward

- No physical numeric value outside `params.py`. Scenario initial conditions are
  configuration and live in `scenarios.py`.
- State ordering `s = [x, th1, th2, xdot, w1, w2]`.
- `dpc/controllers/` keeps the C-transcription constraints: fixed-size arrays,
  explicit indexing, `info` dicts strictly diagnostic.
- The dashboard never reads `Sample.truth` for anything a controller does -- only
  for drawing.
