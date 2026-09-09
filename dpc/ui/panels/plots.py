"""The four plots.

Each pairs the numbers that make each other mean something: commanded against
delivered, because the gap between them is the whole actuator model; torque
against its budget, because the torque alone says nothing; true position against
the step count, because their divergence is the failure this project exists to
design against.

Curves are created once and updated with setData. Recreating them per frame
allocates on every repaint, which is what makes a live plot stutter.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QGridLayout, QWidget

from dpc.params import Params
from dpc.ui import theme as T

pg.setConfigOption("background", T.PANEL)
pg.setConfigOption("foreground", T.TEXT_3)
pg.setConfigOption("antialias", True)


def _pen(colour: str, width: float = T.TRACE_W, dash: bool = False):
    pen = pg.mkPen(colour, width=width)
    if dash:
        pen.setDashPattern([4, 3])
    return pen


class _Plot(pg.PlotWidget):
    """One plot with the project's chrome already applied."""

    def __init__(self, title: str, unit: str):
        super().__init__()
        self.setTitle(f"{title}  <span style='color:{T.TEXT_3}'>{unit}</span>",
                      color=T.TEXT_2, size=f"{T.SIZE_PANEL}pt")
        self.showGrid(x=False, y=True, alpha=0.16)
        self.getAxis("bottom").setPen(T.BORDER)
        self.getAxis("left").setPen(T.BORDER)
        self.getAxis("bottom").setTextPen(T.TEXT_3)
        self.getAxis("left").setTextPen(T.TEXT_3)
        self.setMenuEnabled(False)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()

    def limit_line(self, colour: str = T.LIMIT):
        line = pg.InfiniteLine(angle=0, pen=_pen(colour, T.LIMIT_W, dash=True))
        self.addItem(line)
        return line


class PlotPanel(QWidget):
    """The 2x2 grid. Renders what it is handed and computes nothing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(T.GAP_PANEL)

        self.angles = _Plot("Link angles", "deg")
        self.cart = _Plot("Cart position", "m")
        self.accel = _Plot("Acceleration", "m/s²")
        self.torque = _Plot("Motor torque", "mN·m")

        grid.addWidget(self.angles, 0, 0)
        grid.addWidget(self.cart, 0, 1)
        grid.addWidget(self.accel, 1, 0)
        grid.addWidget(self.torque, 1, 1)

        # Legends: two or more series are never distinguished by colour alone.
        for plot in (self.angles, self.cart, self.accel):
            plot.addLegend(offset=(-8, 6), labelTextColor=T.TEXT_2,
                           brush=pg.mkBrush(T.PANEL), pen=pg.mkPen(T.BORDER))

        self.c_th1 = self.angles.plot(pen=_pen(T.TH1), name="θ₁")
        self.c_th2 = self.angles.plot(pen=_pen(T.TH2), name="θ₂")

        self.c_xtrue = self.cart.plot(pen=_pen(T.X_TRUE), name="true")
        self.c_xcount = self.cart.plot(pen=_pen(T.X_COUNT, dash=True),
                                       name="step count")

        self.c_acmd = self.accel.plot(pen=_pen(T.A_CMD), name="commanded")
        self.c_adel = self.accel.plot(pen=_pen(T.A_DEL), name="delivered")
        self.l_amax = self.accel.limit_line()
        self.l_amin = self.accel.limit_line()

        self.c_tau = self.torque.plot(pen=_pen(T.TAU))
        self.l_taup = self.torque.limit_line()
        self.l_taum = self.torque.limit_line()

    def set_limits(self, p: Params) -> None:
        """The threshold lines. Set on run rather than per frame -- they only
        move when a drive parameter is edited."""
        self.l_amax.setValue(p.drive.a_max)
        self.l_amin.setValue(-p.drive.a_max)
        self.l_taup.setValue(p.drive.tau_budget * 1e3)
        self.l_taum.setValue(-p.drive.tau_budget * 1e3)

    def clear_traces(self) -> None:
        for curve in (self.c_th1, self.c_th2, self.c_xtrue, self.c_xcount,
                      self.c_acmd, self.c_adel, self.c_tau):
            curve.setData([], [])

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
        self.c_tau.setData(t, w["tau"] * 1e3)
