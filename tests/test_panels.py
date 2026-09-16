"""The panels' own arithmetic: framing, scale and the strings on the key.

Everything here is a pure projection from numbers to pixels, so it is tested
by calling it rather than by looking at it. What a screenshot cannot tell you
is whether the rail is drawn at exactly the rail's length, or whether the key
names the limit it is standing next to.
"""

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dpc.params import Params  # noqa: E402
from dpc.ui import theme as T  # noqa: E402
from dpc.ui.panels.animation import PAD_X, PAD_Y, AnimationPanel  # noqa: E402
from dpc.ui.panels.plots import PlotPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    p = AnimationPanel()
    # Wide and short, so the VERTICAL fit is the one that binds -- which is
    # the case the scale is built for: the drawn mechanism is roughly square
    # and the well is about five times wider than it is tall.
    p.resize(1200, 240)
    return p


def test_the_vertical_fit_puts_the_top_of_the_extent_on_the_padding(panel):
    """When height binds, the drawn extent fills the well exactly between the
    two paddings -- any other placement is height spent on nothing."""
    p = Params()
    lo, hi = panel._extent(p)
    k, cx, cy = panel._scale(p)

    sx = (panel.width() - 2 * PAD_X) / (2 * (p.x_lim + 0.06))
    assert k < sx, "this fixture is meant to be height-bound"

    assert cy - hi * k == pytest.approx(PAD_Y)
    assert cy - lo * k == pytest.approx(panel.height() - PAD_Y)


def test_the_rail_is_drawn_at_exactly_the_rail_length(panel):
    """A rail that is not rail_len long is a lie about where the cart stops."""
    seen: list[float] = []

    def to_px(x_m: float, y_m: float) -> QPointF:
        seen.append(x_m)
        return QPointF(600.0 + x_m * 1000.0, 120.0 - y_m * 1000.0)

    pm = QPixmap(1200, 240)
    q = QPainter(pm)
    panel._draw_rail(q, to_px, Params().x_lim)
    q.end()

    assert seen == [-0.25, 0.25]


def test_the_cart_is_drawn_at_its_real_length_until_it_would_vanish(qapp):
    p = Params()
    k = 4000.0                        # 0.09 m -> 360 px, well above the floor
    rect = AnimationPanel._cart_rect(QPointF(0.0, 0.0), p, k)
    assert rect.width() == pytest.approx(p.nominal.cart_len * k)
    assert rect.height() == pytest.approx(rect.width() * T.CART_ASPECT)

    k = 100.0                         # 0.09 m -> 9 px, below the floor
    small = AnimationPanel._cart_rect(QPointF(0.0, 0.0), p, k)
    assert small.width() == pytest.approx(T.CART_MIN_W)


def test_the_horizon_step_climbs_a_1_2_5_ladder(panel):
    """A step chosen off the ladder means the same thing after a resize; a
    fraction of the panel height means nothing at all."""
    from dpc.ui.panels.animation import HORIZON_MIN_PX

    for k in (10.0, 100.0, 340.0, 1000.0, 5000.0):
        step = AnimationPanel._horizon_step(k)
        assert step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)
        if step != 5.0:
            assert step * k >= HORIZON_MIN_PX


def test_every_threshold_entry_in_the_key_names_its_value(qapp):
    """"budget" alone is one more thing to go and look up."""
    plots = PlotPanel()
    plots.set_limits(Params())
    assert plots.key_cart.labels[2].text() == "rail ±250 mm"
    assert plots.key_accel.labels[2].text() == "a_max ±10"
    assert plots.key_torque.labels[1].text() == "budget ±200"


def test_the_y_range_never_shrinks_back_inside_a_run(qapp):
    """_peak comes off a sliding window, so the data's own span is not
    monotone: a transient leaving the window would otherwise snap the trace
    and both limit lines to a third of their height in one frame."""
    plots = PlotPanel()
    plots.set_limits(Params())
    accel = plots.accel

    settled = accel._vb.viewRange()[1][1]
    accel.fit(30.0)
    spiked = accel._vb.viewRange()[1][1]
    assert spiked > settled

    accel.fit(0.5)                    # the transient has left the window
    assert accel._vb.viewRange()[1][1] == pytest.approx(spiked)

    plots.clear_traces()              # a new run starts a new envelope
    accel.fit(0.5)
    assert accel._vb.viewRange()[1][1] == pytest.approx(settled)
