"""Starting conditions worth running from.

A scenario says where the mechanism begins and how long to watch. It says
nothing about how the mechanism is driven -- that is the controller's job. The
two are orthogonal on purpose: any controller runs from any scenario, and it is
the cross product that shows a control law's weaknesses.

Angles follow the project convention: measured from straight up, positive toward
+x. So pi is hanging and 0 is inverted.
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
        "The unstable equilibrium. Exactly balanced, so a controller that does "
        "nothing looks perfect -- which makes this a trap as well as a test.",
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
        "Maximum gravitational torque, far from any linearisation point. Where "
        "swing-up has to work and small-angle control cannot.",
    ),
)

_BY_KEY = {sc.key: sc for sc in SCENARIOS}


def by_key(key: str) -> Scenario:
    """Look a scenario up, raising KeyError if it is not one of ours."""
    return _BY_KEY[key]
