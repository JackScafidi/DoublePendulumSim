"""The controller that proves the plumbing.

Not a control law. It exists so the whole chain -- measurement, controller,
motor, plant -- can be run without perturbing the physics, which is how the
plumbing gets tested separately from anything that steers.
"""

from dpc.control import ControlOutput
from dpc.controllers.registry import ParamSpec, register
from dpc.params import Params
from dpc.sensors import Measurement


@register("Zero command")
class ZeroController:
    """Commands nothing, ever.

    Lets the whole chain -- measurement, controller, motor, plant -- run without
    perturbing the physics, which is how the plumbing gets tested separately
    from any control law.
    """

    PARAMS: tuple[ParamSpec, ...] = ()

    def reset(self, p: Params) -> None:
        pass

    def update(self, m: Measurement) -> ControlOutput:
        return ControlOutput(a_cmd=0.0, mode="idle")
