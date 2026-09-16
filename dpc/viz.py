"""Time-series plots.

Animation is deliberately out of scope for this milestone: the point is to
prove the physics, and a plot of energy drift proves more than a picture of a
swinging pendulum does.
"""

import matplotlib.pyplot as plt
import numpy as np

from dpc.model import NumericModel
from dpc.params import Params
from dpc.simulate import Run, Trajectory


def plot_trajectory(tr: Trajectory, model: NumericModel, p: Params,
                    title: str | None = None):
    """Angles, cart position, applied force, and energy drift.

    Energy drift gets its own panel rather than being folded into a summary
    number: its shape distinguishes integrator truncation error, which
    oscillates and stays bounded, from a modelling fault, which grows.

    The end stops are drawn on the position panel the way a_max and the torque
    budget are drawn on theirs: a number against the limit that bounds it.
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
    for lim in (p.x_lim, -p.x_lim):
        ax[1].axhline(lim, lw=0.5, ls=":", color="k")
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


def plot_run(r: Run, p: Params, title: str | None = None):
    """The four panels a closed-loop trace is read from.

    Commanded against delivered acceleration gets a panel of its own because
    the gap between them is the whole actuator model: where the two separate
    tells you which limit is binding. Torque is drawn against the budget rather
    than alone, since the number means nothing except relative to what the
    motor actually has.

    True cart position is drawn against the step count so the two can be seen
    to agree -- or, once slip is enabled, to come apart. On hardware only the
    dashed line exists. Both are drawn against the end stops, because a cart
    position means nothing without the length of rail it has to move in.
    """
    fig, ax = plt.subplots(4, 1, figsize=(9, 10), sharex=True)

    ax[0].plot(r.t, np.degrees(r.s[:, 1]), label=r"$\theta_1$")
    ax[0].plot(r.t, np.degrees(r.s[:, 2]), label=r"$\theta_2$")
    ax[0].axhline(0.0, lw=0.5, color="k")
    ax[0].set_ylabel("angle [deg]")
    ax[0].legend(loc="upper right")
    if title:
        ax[0].set_title(title)

    ax[1].plot(r.t, r.s[:, 0], label="true")
    ax[1].plot(r.t, r.x_count, ls="--", label="step count")
    ax[1].axhline(0.0, lw=0.5, color="k")
    for lim in (p.x_lim, -p.x_lim):
        ax[1].axhline(lim, lw=0.5, ls=":", color="k")
    ax[1].set_ylabel("cart $x$ [m]")
    ax[1].legend(loc="upper right")

    ax[2].plot(r.t, r.a_cmd, label="commanded")
    ax[2].plot(r.t, r.a_del, label="delivered")
    for lim in (p.drive.a_max, -p.drive.a_max):
        ax[2].axhline(lim, lw=0.5, ls=":", color="k")
    ax[2].set_ylabel(r"$\ddot{x}$ [m/s$^2$]")
    ax[2].legend(loc="upper right")

    ax[3].plot(r.t, r.tau)
    for lim in (p.drive.tau_budget, -p.drive.tau_budget):
        ax[3].axhline(lim, lw=0.5, ls=":", color="k")
    ax[3].set_ylabel(r"$\tau_{motor}$ [N m]")
    ax[3].set_xlabel("time [s]")

    for a in ax:
        a.grid(alpha=0.3)

    fig.tight_layout()
    return fig
