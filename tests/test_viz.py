import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from dpc.model import ModelConfig, build  # noqa: E402
from dpc.params import Params  # noqa: E402
from dpc.controllers.constant import ConstantController  # noqa: E402
from dpc.simulate import run, simulate  # noqa: E402
from dpc.viz import plot_run, plot_trajectory  # noqa: E402

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


def _run_closed():
    return run(M, np.array([0.0, np.pi, np.pi, 0.0, 0.0, 0.0]),
               ConstantController(1.0), P, t_end=0.05)


def test_plot_run_builds_four_panels():
    fig = plot_run(_run_closed(), P)
    assert len(fig.axes) == 4


def test_run_panels_carry_the_expected_labels():
    labels = [a.get_ylabel() for a in plot_run(_run_closed(), P).axes]
    assert "angle [deg]" in labels[0]
    assert "cart $x$ [m]" in labels[1]
    assert "[m/s$^2$]" in labels[2]
    assert "[N m]" in labels[3]


def test_position_panel_draws_truth_against_the_step_count():
    """Two lines, because the difference between them is the point."""
    ax = plot_run(_run_closed(), P).axes[1]
    assert len(ax.get_lines()) >= 2
    legend = ax.get_legend()
    assert legend is not None
    assert {t.get_text() for t in legend.get_texts()} == {"true", "step count"}


def test_latex_labels_survive_as_backslash_escapes():
    r"""A stray unescaped backslash turns \theta into a tab and matplotlib
    renders the panel legend as nonsense rather than failing."""
    fig = plot_run(_run_closed(), P)
    legend = fig.axes[0].get_legend()
    assert legend is not None
    names = {t.get_text() for t in legend.get_texts()}
    assert names == {r"$\theta_1$", r"$\theta_2$"}
    assert r"$\tau_{motor}$" in fig.axes[3].get_ylabel()
