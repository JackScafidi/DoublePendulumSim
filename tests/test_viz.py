import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from dpc.model import ModelConfig, build  # noqa: E402
from dpc.params import Params  # noqa: E402
from dpc.simulate import simulate  # noqa: E402
from dpc.viz import plot_trajectory  # noqa: E402

M = build(ModelConfig())
P = Params()


def _run():
    return simulate(M, np.array([0.0, 2.5, 2.7, 0.0, 0.0, 0.0]),
                    lambda t, s: 0.0, t_end=1.0, dt=1e-3, p=P)


def test_plot_returns_a_four_panel_figure():
    fig = plot_trajectory(_run(), M, P, title="free swing")
    assert len(fig.axes) == 4
    assert fig.axes[0].get_title() == "free swing"


def test_panels_carry_the_expected_labels():
    fig = plot_trajectory(_run(), M, P)
    labels = [a.get_ylabel() for a in fig.axes]
    assert "angle [deg]" in labels[0]
    assert "force [N]" in labels[2]
    assert "energy drift [J]" in labels[3]


def test_plot_works_without_a_title():
    fig = plot_trajectory(_run(), M, P)
    assert fig.axes[0].get_title() == ""
