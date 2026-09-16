"""The controller that walks the motor through its limits.

Not a control law either. A fixed acceleration command is the shortest input
that drives the step generator through its jerk limit, then its saturation,
then its velocity ceiling, in that order -- so the motor model can be read off
one trace.
"""

import math

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register
from dpc.params import Params
from dpc.sensors import Measurement


@register("Constant acceleration")
class ConstantController:
    """Push at a fixed acceleration for a while, then stop pushing.

    `hold` is a controller parameter, not a scenario one: it is how long to
    push, whereas scenario duration is how long to watch. Pushing for one second
    and watching for five is the normal way to see what the mechanism does once
    you stop driving it.
    """

    PARAMS = (
        ParamSpec("a", "acceleration", "m/s²", 2.0, -10.0, 10.0, step=0.1),
        ParamSpec("hold", "hold for", "s", 1.0, 0.0, 30.0, step=0.1),
    )

    __slots__ = ("a", "hold")

    def __init__(self, a: float, hold: float = math.inf):
        self.a = a
        self.hold = hold
        """s. The constructor default is infinite while the declared default is
        one second: existing tests construct this directly and expect a command
        that never stops, whereas a dashboard user wants a finite push."""

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        if m.t >= self.hold:
            return ControlOutput(a_cmd=0.0, mode="coast")
        return ControlOutput(a_cmd=self.a, mode="constant")
