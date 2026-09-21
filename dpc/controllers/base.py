"""A blank control law, ready to be filled in.

Not a control law, and deliberately not registered: it carries no @register
decorator, so discover() imports it, finds nothing, and the dashboard never
offers it. Copy this module to start a new law -- the copy registers itself and
appears in the dashboard with no UI changes.

What a controller is allowed to see is fixed by Measurement, and what it is
allowed to say is fixed by ControlOutput. Both are imported below so the
signatures are already correct; everything between them is the law.

Like the rest of this package it is destined for the MCU, so it keeps the
project's C-transcription constraints: fixed-size arrays, explicit indexing, no
Python-specific constructs, and no import from dpc.ui.
"""

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register  # noqa: F401
from dpc.params import Params
from dpc.sensors import Measurement


class BaseController:
    """Commands nothing, and says so.

    To make this a real law: rename the class, add @register("Some label")
    above it, declare PARAMS, take those parameters in __init__, and compute
    a_cmd in update().
    """

    PARAMS: tuple[ParamSpec, ...] = ()
    """One entry per tunable number. Each becomes a dashboard widget and is
    passed to __init__ as the keyword named in the spec, e.g.

        PARAMS = (
            ParamSpec("k", "gain", "1/s", 1.0, 0.0, 50.0, step=0.1),
        )
    """

    __slots__ = ("p",)

    p: Params
    """Set by reset(). Unset before the first reset, so read it in update()
    only -- which is the only place it is needed."""

    def __init__(self) -> None:
        """Takes one keyword per PARAMS entry, all floats. Store them and any
        state the law carries between ticks -- integral terms, previous angles,
        mode flags -- naming each in __slots__ above."""
        pass

    def reset(self, p: Params) -> None:
        """Return to a blank internal state, and take the parameter set.

        Called once before the run starts. It is not given the initial state:
        the controller is never handed truth, it learns where the system is
        from its first update, exactly as it does on power-up. So zero every
        accumulator here and treat the first update() as the first thing this
        controller has ever seen.

        `p` carries the plant and drive constants -- p.effective() for masses
        and lengths, p.drive.a_max for the acceleration ceiling, p.x_lim for
        how far the cart may travel either side of centre.
        """
        self.p = p

    def update(self, m: Measurement) -> ControlOutput:
        """One control tick. Everything the hardware knows is on `m`:

            m.t        s since start
            m.th1      rad, cart joint encoder
            m.th2      rad, elbow encoder
            m.x_count  m, cart position implied by the steps commanded
            m.dt       s, the control period this reading belongs to

        There are no rates. A law that needs th1dot differences the angles
        itself against a value it kept from the previous tick, and filters that
        difference itself -- the same arithmetic it will do on the bench.

        Return an acceleration setpoint, because that is what a step/dir
        stepper can be told. `mode` labels which branch of the law produced it
        so a trace can be read after the fact; `info` is diagnostics only and
        does not survive transcription to C++.
        """
        return ControlOutput(a_cmd=0.0, mode="base", info={})
