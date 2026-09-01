"""Time-series plots.

Animation is deliberately out of scope for this milestone: the point is to
prove the physics, and a plot of energy drift proves more than a picture of a
swinging pendulum does.
"""

import matplotlib.pyplot as plt
import numpy as np

from dpc.model import NumericModel
from dpc.params import Params
from dpc.simulate import Trajectory


def plot_trajectory(tr: Trajectory, model: NumericModel, p: Params,
                    title: str | None = None):
    """Angles, cart position, applied force, and energy drift.

    Energy drift gets its own panel rather than being folded into a summary
    number: its shape distinguishes integrator truncation error, which
    oscillates and stays bounded, from a modelling fault, which grows.
    """
    fig, ax = plt.subplots(4, 1, figsize=(9, 10), sharex=True)

    ax[0].plot(tr.t, np.degrees(tr.s[:, 1]), label=r"$\theta_1$")
    ax[0].plot(tr.t, np.degrees(tr.s[:, 2]), label=r"$\theta_2$")
    ax[0].axhline(0.0, lw=0.5, color="k")
    ax[0].set_ylabel("angle [deg]")
    ax[0].legend(loc="upper right")
    if title:
        ax[0].set_title(title)

    ax[1].plot(tr.t, tr.s[:, 0])
    ax[1].axhline(0.0, lw=0.5, color="k")
    ax[1].set_ylabel("cart $x$ [m]")

    ax[2].plot(tr.t, tr.F)
    ax[2].axhline(0.0, lw=0.5, color="k")
    ax[2].set_ylabel("force [N]")

    energy = np.array([model.energy(s, p) for s in tr.s])
    ax[3].plot(tr.t, energy - energy[0])
    ax[3].set_ylabel("energy drift [J]")
    ax[3].set_xlabel("time [s]")

    for a in ax:
        a.grid(alpha=0.3)

    fig.tight_layout()
    return fig
