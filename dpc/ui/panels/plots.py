"""The four plots.

Each pairs the numbers that make each other mean something: commanded against
delivered, because the gap between them is the whole actuator model; torque
against its budget, because the torque alone says nothing; true position against
the step count, because their divergence is the failure this project exists to
design against, and both against the ends of the rail they have to live
within.

Curves are created once and updated with setData. Recreating them per frame
allocates on every repaint, which is what makes a live plot stutter.

All the chrome is the card's, not pyqtgraph's. The title lives in the card
header, the key lives in a swatch row under the plot, and the plot area holds
nothing but the data and a horizontal grid -- a boxed legend floating over a
well is a shape this language has nowhere else, and in a live run it sits
exactly on the end of the trace, which is the part you are watching.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from dpc.params import Params
from dpc.ui import theme as T
from dpc.ui.panels.card import card

pg.setConfigOption("background", T.SURFACE_SUNKEN)
pg.setConfigOption("foreground", T.TEXT_3)
pg.setConfigOption("antialias", True)

DASH = [4, 3]
"""The dash pattern every non-solid trace and every limit line uses, so a
legend swatch can be drawn with the trace's own pen and still be one mark."""


def _pen(colour: str, width: float = T.TRACE_W, dash: bool = False):
    pen = pg.mkPen(colour, width=width)
    if dash:
        pen.setDashPattern(DASH)
    return pen


class Swatch(QWidget):
    """One legend mark: a line in the trace's own colour and dash."""

    def __init__(self, colour: str, dash: bool, parent=None):
        super().__init__(parent)
        self.colour = colour
        self.dash = dash
        self.setFixedSize(T.SWATCH_W, T.SWATCH_H)

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self.colour), T.SWATCH_PEN)
        if self.dash:
            # Qt dash lengths are in pen widths, pyqtgraph's in pixels, so the
            # same [4, 3] has to be halved here to draw the same mark.
            pen.setDashPattern([d / 2.0 for d in DASH])
        q.setPen(pen)
        y = self.height() / 2.0
        q.drawLine(0, int(y), self.width(), int(y))
        q.end()


class LegendRow(QWidget):
    """The key, under the plot and inside the card.

    The approved artboard drew it here all along -- swatch, label, 12 px gap --
    and the Qt build substituted pyqtgraph's floating box, which occludes the
    end of the trace and drops the threshold entries entirely. A limit line
    nobody can name is a red dash of unknown meaning.
    """

    def __init__(self, entries: tuple[tuple[str, str, bool], ...], parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(T.PAD_LEGEND, T.PAD_LEGEND, T.PAD_LEGEND, 0)
        h.setSpacing(T.GAP_LEGEND)
        self.labels: list[QLabel] = []
        for colour, text, dash in entries:
            item = QWidget()
            hv = QHBoxLayout(item)
            hv.setContentsMargins(0, 0, 0, 0)
            hv.setSpacing(5)
            hv.addWidget(Swatch(colour, dash))
            lab = QLabel(text)
            lab.setObjectName("note")
            hv.addWidget(lab)
            self.labels.append(lab)
            h.addWidget(item)
        h.addStretch(1)

    def set_text(self, index: int, text: str) -> None:
        self.labels[index].setText(text)


class _Plot(pg.PlotWidget):
    """One plot with the project's chrome already applied."""

    def __init__(self):
        super().__init__()
        mono = T.fonts()[1]
        self._lim: float | None = None
        self._peak = 0.0
        """The largest magnitude seen since the run began, expand-only.

        `_peak` is handed to fit() over a sliding 6 s window, so the data's own
        span is NOT monotone: a 30 m/s^2 transient at t = 1 s leaves the window
        at t = 7 s and the span would collapse to a third of its height in one
        frame, taking the trace and both limit lines with it. Latching it is
        the same envelope the animation's vertical frame uses, for the same
        reason, and it is what the design doc already claims happens."""
        # The view box, held rather than reached for. PlotWidget inherits a
        # DIFFERENT setYRange(r, padding) from GraphicsView and shadows it at
        # construction with a bound PlotItem method, so calling self.setYRange
        # works but reads as the wrong signature; going to the view box says
        # which one is meant.
        self._vb: pg.ViewBox = self.getViewBox()

        for name in ("bottom", "left"):
            axis = self.getAxis(name)
            # No axis line. The old BORDER pen measured 1.14:1 on the well, so
            # the frame was drawn and never seen; a grid you can follow is a
            # better answer than a frame you cannot.
            axis.setPen(pg.mkPen(color=(0, 0, 0, 0)))
            axis.setTickPen(pg.mkPen(T.GRID, width=1))
            axis.setTextPen(T.TEXT_3)
            axis.setTickFont(QFont(mono, T.SIZE_TICK))
            # tickAlpha pins the grid to the pen's own strength; left alone,
            # pyqtgraph derives an alpha per level and the line fades out.
            axis.setStyle(maxTickLevel=1, tickLength=3, tickTextOffset=6,
                          tickAlpha=255)
        self.getAxis("left").setGrid(255)
        # Two to eight labels an axis. Time is the one axis whose spacing is
        # known in advance, so it is set rather than negotiated.
        self.getAxis("bottom").setTickSpacing(major=1.0, minor=0.5)

        self.setMenuEnabled(False)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()

    def limit_line(self, colour: str = T.LIMIT):
        line = pg.InfiniteLine(angle=0, pen=_pen(colour, T.LIMIT_W, dash=True))
        self.addItem(line)
        return line

    def set_limit(self, lim: float) -> None:
        """Frame the y axis from the threshold, not from the data.

        A limit line drawn flush with the top of the view shows no headroom,
        which is the only thing it is there to show -- and the trace can never
        visibly cross it, because crossing would just rescale the axis.
        """
        self._lim = abs(lim)
        self.fit(0.0)

    def reset_peak(self) -> None:
        """A new run starts a new envelope. Called from clear_traces."""
        self._peak = 0.0

    def fit(self, peak: float) -> None:
        """Hold the limit-derived range unless the data has outgrown it.

        One headroom for both halves of the max: the threshold and the data
        are framed by the same rule, and two different multipliers in one
        expression means the axis silently changes its margin the moment the
        data wins.
        """
        if self._lim is None:
            return
        self._peak = max(self._peak, abs(peak))
        span = max(self._lim, self._peak) * T.LIMIT_HEADROOM
        self._vb.setYRange(-span, span, padding=0)


def _peak(values) -> float:
    if len(values) == 0:
        return 0.0
    finite = values[np.isfinite(values)]
    return float(np.max(np.abs(finite))) if finite.size else 0.0


class PlotPanel(QWidget):
    """The 2x2 grid. Renders what it is handed and computes nothing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(T.GAP_PANEL)

        self.angles = _Plot()
        self.cart = _Plot()
        self.accel = _Plot()
        self.torque = _Plot()

        # Two or more series are never distinguished by colour alone, and a
        # threshold is a series as far as the key is concerned.
        self.key_angles = LegendRow(((T.TH1, "θ₁", False),
                                     (T.TH2, "θ₂", False)))
        self.key_cart = LegendRow(((T.X_TRUE, "true", False),
                                   (T.X_COUNT, "step count", True),
                                   (T.LIMIT, "rail ends", True)))
        self.key_accel = LegendRow(((T.A_CMD, "commanded", False),
                                    (T.A_DEL, "delivered", False),
                                    (T.LIMIT, "a_max", True)))
        self.key_torque = LegendRow(((T.TAU, "τ motor", False),
                                     (T.LIMIT, "budget", True)))

        # Each plot is its own raised card sitting on the page, rather than
        # four plots inside one card: nesting a raised surface in a raised
        # surface of the same colour cancels both.
        for col, (title, unit, plot, key) in enumerate((
            ("Link angles", "deg", self.angles, self.key_angles),
            ("Cart position", "m", self.cart, self.key_cart),
            ("Acceleration", "m/s²", self.accel, self.key_accel),
            ("Motor torque", "mN·m", self.torque, self.key_torque),
        )):
            grid.addWidget(card(title, plot, unit=unit, footer=key),
                           col // 2, col % 2)

        self.c_th1 = self.angles.plot(pen=_pen(T.TH1))
        self.c_th2 = self.angles.plot(pen=_pen(T.TH2))

        self.c_xtrue = self.cart.plot(pen=_pen(T.X_TRUE))
        self.c_xcount = self.cart.plot(pen=_pen(T.X_COUNT, dash=True))
        self.l_xpos = self.cart.limit_line()
        self.l_xneg = self.cart.limit_line()

        self.c_acmd = self.accel.plot(pen=_pen(T.A_CMD))
        self.c_adel = self.accel.plot(pen=_pen(T.A_DEL))
        self.l_amax = self.accel.limit_line()
        self.l_amin = self.accel.limit_line()

        self.c_tau = self.torque.plot(pen=_pen(T.TAU))
        self.l_taup = self.torque.limit_line()
        self.l_taum = self.torque.limit_line()

    def set_limits(self, p: Params) -> None:
        """The threshold lines. Set on run rather than per frame -- they only
        move when a drive or plant limit is edited."""
        tau_mnm = p.drive.tau_budget * 1e3
        self.l_xpos.setValue(p.x_lim)
        self.l_xneg.setValue(-p.x_lim)
        self.l_amax.setValue(p.drive.a_max)
        self.l_amin.setValue(-p.drive.a_max)
        self.l_taup.setValue(tau_mnm)
        self.l_taum.setValue(-tau_mnm)

        self.cart.set_limit(p.x_lim)
        self.accel.set_limit(p.drive.a_max)
        self.torque.set_limit(tau_mnm)

        # The key names the number, not just the colour: "budget" alone is one
        # more thing to go and look up.
        self.key_cart.set_text(2, f"rail ±{p.x_lim * 1e3:.0f} mm")
        self.key_accel.set_text(2, f"a_max ±{p.drive.a_max:g}")
        self.key_torque.set_text(1, f"budget ±{tau_mnm:.0f}")

    def clear_traces(self) -> None:
        for curve in (self.c_th1, self.c_th2, self.c_xtrue, self.c_xcount,
                      self.c_acmd, self.c_adel, self.c_tau):
            curve.setData([], [])
        for plot in (self.cart, self.accel, self.torque):
            plot.reset_peak()

    def redraw(self, w: dict) -> None:
        t = w["t"]
        if len(t) == 0:
            self.clear_traces()
            return

        self.c_th1.setData(t, np.degrees(w["th1"]))
        self.c_th2.setData(t, np.degrees(w["th2"]))

        truth = w["truth"]
        # All-NaN means hardware: there is no true position to draw, so the
        # trace simply does not appear. No branch anywhere else.
        if truth.size and not np.isnan(truth[:, 0]).all():
            self.c_xtrue.setData(t, truth[:, 0])
        else:
            self.c_xtrue.setData([], [])
        self.c_xcount.setData(t, w["x_count"])

        self.c_acmd.setData(t, w["a_cmd"])
        self.c_adel.setData(t, w["a_del"])
        tau = w["tau"] * 1e3
        self.c_tau.setData(t, tau)

        # The limit frames the axis; the data is only allowed to widen it.
        self.cart.fit(max(_peak(w["x_count"]),
                          _peak(truth[:, 0]) if truth.size else 0.0))
        self.accel.fit(max(_peak(w["a_cmd"]), _peak(w["a_del"])))
        self.torque.fit(_peak(tau))
