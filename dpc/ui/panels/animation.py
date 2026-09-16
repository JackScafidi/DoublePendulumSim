"""The mechanism, drawn.

Renders one sample. It computes nothing about the physics -- link lengths come
from the parameters, angles from the sample -- so this file stays a projection
from state to pixels and nothing else.

Everything on the canvas is drawn at its real size in metres times one scale
factor: the rail, the links, the horizon lines and the cart. Anything drawn at
a fixed pixel size instead means something different at every scale, which is
how a 72 px cart ended up nearly as long as a link.
"""

import math
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from dpc.params import Params
from dpc.ui import theme as T
from dpc.ui.sample import Sample

TRAIL_LEN = 90
"""Samples of link-2 tip kept for the trail. About a second at 1 kHz decimated
to the frame rate -- long enough to show the phase of a swing, short enough not
to smear into a blob."""

VIEW_MARGIN_X = 0.06
VIEW_MARGIN_Y = 0.02
"""m of view beyond the end stops, and beyond the top and bottom of the drawn
extent, so nothing is flush with the edge of the panel when it is parked
against a stop or hanging straight down.

They differ because the two axes are differently scarce. The well is about
five times as wide as it is tall, so the horizontal fit never binds and can
afford a generous margin, while every vertical millimetre of view is a
millimetre off the scale of the whole drawing.
"""

PAD_X = 16
PAD_Y = T.STOP_H + 4
"""px reserved at the edges of the well. The vertical one has to clear the end
stops, which stick out above and below the rail, and nothing more: the
vertical fit is what sets the scale for everything on the canvas, so padding
spent here is subtracted from the size of the mechanism."""

HORIZON_MIN_PX = 34
"""Closest two horizon lines may be drawn. The step is chosen from a 1-2-5
ladder of metres so that the gap clears this -- a reference at 25% of the panel
height moves whenever the window is resized, and means nothing."""

HORIZON_LABEL_X = 6
"""px from the left edge of the well to the horizon labels. The lines run the
full width of the well rather than the width of the rail: a rule that stops
where the rail stops is a stub floating beside the mechanism, and the scale it
belongs to is a property of the canvas, not of the rail."""


class AnimationPanel(QWidget):
    """Cart on a rail with two links, plus the step counter's belief.

    Angles are measured from straight up, positive toward +x, so a link at
    theta is the unit vector (sin, cos) in world coordinates -- and the y axis
    is flipped on the way to screen coordinates, where y grows downward.

    The rail is a fixed physical extent: it is exactly rail_len long, with a
    stop at each end, and the cart cannot leave it. Nothing here has to grow to
    follow the cart any more -- the plant will not let it out of frame.

    Vertically there is no such constraint, so the frame comes from what has
    actually been drawn. A rail pinned to half height is right only for the
    upright scenarios; in everything else the links hang below it and the top
    half of the well stays permanently empty.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._sample: Sample | None = None
        self._params = Params()
        self._trail: deque[tuple[float, float]] = deque(maxlen=TRAIL_LEN)
        self._y_lo: float | None = None
        self._y_hi: float | None = None

    def clear(self) -> None:
        self._sample = None
        self._trail.clear()
        self._y_lo = self._y_hi = None
        self.update()

    def show_sample(self, s: Sample | None, p: Params) -> None:
        self._params = p
        self._sample = s
        if s is not None:
            self._trail.append(self._tip(s, p))
            self._grow(s, p)
        self.update()

    # -- geometry ---------------------------------------------------------

    @staticmethod
    def _angles(s: Sample) -> tuple[float, float]:
        """Truth when we have it, the measured angles otherwise.

        Identical today. On hardware truth is None and this silently falls back
        to what the encoders reported, with no branch anywhere else.
        """
        if s.truth is not None:
            return float(s.truth[1]), float(s.truth[2])
        return s.th1, s.th2

    @staticmethod
    def _cart_x(s: Sample) -> float:
        return float(s.truth[0]) if s.truth is not None else s.x_count

    def _joints(self, s: Sample, p: Params) -> tuple[float, float, float]:
        """(elbow y, tip x, tip y) in metres, with the rail at y = 0."""
        th1, th2 = self._angles(s)
        e = p.effective()
        x = self._cart_x(s)
        ex = x + e["l1"] * math.sin(th1)
        ey = e["l1"] * math.cos(th1)
        return ey, ex + e["l2"] * math.sin(th2), ey + e["l2"] * math.cos(th2)

    def _tip(self, s: Sample, p: Params) -> tuple[float, float]:
        _, tx, ty = self._joints(s, p)
        return tx, ty

    def _grow(self, s: Sample, p: Params) -> None:
        """Expand-only vertical envelope.

        Expand-only because a frame that shrinks back as the pendulum passes
        through the bottom of its swing rescales the whole drawing twice a
        period. It settles inside the first swing and then never moves.
        """
        ey, _, ty = self._joints(s, p)
        lo = min(0.0, ey, ty)
        hi = max(0.0, ey, ty)
        self._y_lo = lo if self._y_lo is None else min(self._y_lo, lo)
        self._y_hi = hi if self._y_hi is None else max(self._y_hi, hi)

    def _extent(self, p: Params) -> tuple[float, float]:
        if self._y_lo is None or self._y_hi is None:
            e = p.effective()
            reach = e["l1"] + e["l2"]
            return -reach, reach
        return self._y_lo - VIEW_MARGIN_Y, self._y_hi + VIEW_MARGIN_Y

    def _scale(self, p: Params):
        """Metres to pixels, plus the origin.

        Horizontally the view is the rail plus a margin and never changes
        during a run: the cart is physically confined to the rail, so a view
        sized to it cannot be outrun. Vertically the rail is placed so the
        swept reach is centred in the well.
        """
        lo, hi = self._extent(p)
        half_x = p.x_lim + VIEW_MARGIN_X
        w, h = self.width(), self.height()
        sx = (w - 2 * PAD_X) / (2 * half_x)
        sy = (h - 2 * PAD_Y) / max(hi - lo, 1e-6)
        k = max(1.0, min(sx, sy))
        cy = (h - (hi - lo) * k) / 2.0 + hi * k
        return k, w / 2.0, cy

    @staticmethod
    def _horizon_step(k: float) -> float:
        """A round number of metres whose spacing is legible at this scale."""
        for metres in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0):
            if metres * k >= HORIZON_MIN_PX:
                return metres
        return 5.0

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.fillRect(self.rect(), QColor(T.SURFACE_SUNKEN))

        p = self._params
        k, cx, cy = self._scale(p)
        e = p.effective()

        def to_px(x_m: float, y_m: float) -> QPointF:
            return QPointF(cx + x_m * k, cy - y_m * k)

        self._draw_horizons(q, to_px, p, k)
        self._draw_rail(q, to_px, p.x_lim)

        s = self._sample
        if s is None:
            self._draw_hint(q)
            q.end()
            return

        self._draw_trail(q, to_px)
        self._draw_ghost_cart(q, to_px, s, p, k)
        self._draw_mechanism(q, to_px, s, e, p, k)
        q.end()

    def _draw_horizons(self, q, to_px, p: Params, k: float) -> None:
        """A height scale in metres, measured from the rail, across the well.

        Three things had to be true before these earned their place. They are
        drawn at a round number of METRES rather than at 25%, 50% and 75% of
        the panel height, so they mean the same thing after a resize instead
        of sliding to a new nothing. The step comes off a 1-2-5 ladder chosen
        so consecutive lines clear HORIZON_MIN_PX, so the scale thins out
        rather than crowding when the drawing is small. And each one runs the
        full width of the well with its height labelled in the left gutter --
        as a stub the width of the rail, a rule with a number on it beside the
        mechanism reads as debris, and the empty space either side of a
        near-square drawing in a five-to-one well reads as a gap rather than
        as the canvas the scale is ruled on.

        The rail itself is the zero line, so it is not repeated here.
        """
        lo, hi = self._extent(p)
        step = self._horizon_step(k)
        # SIZE_TICK, not something smaller. The ink ramp's contrast
        # argument is built on the 9-11 px band, and an 8 px label on the
        # well is outside the range those ratios were measured for.
        q.setFont(QFont(T.fonts()[1], T.SIZE_TICK))
        left, right = 0.0, float(self.width())

        n = 1
        while True:
            drawn = False
            for y_m in (n * step, -n * step):
                if not lo <= y_m <= hi:
                    continue
                drawn = True
                y = to_px(0.0, y_m).y()
                q.setPen(QPen(QColor(T.GRID), 1))
                q.drawLine(QPointF(left, y), QPointF(right, y))
                q.setPen(QColor(T.TEXT_3))
                q.drawText(QPointF(HORIZON_LABEL_X, y - 3), f"{y_m:+.2f} m")
            if not drawn:
                return
            n += 1

    def _draw_rail(self, q, to_px, x_lim) -> None:
        a, b = to_px(-x_lim, 0.0), to_px(x_lim, 0.0)
        rail = QPen(QColor(T.RAIL), T.RAIL_W, Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap)
        q.setPen(rail)
        q.drawLine(a, b)

        # The end stops, in the rail's own pen: they are the same piece of
        # hardware, and they are where the cart actually stops.
        for end in (a, b):
            q.drawLine(QPointF(end.x(), end.y() - T.STOP_H),
                       QPointF(end.x(), end.y() + T.STOP_H))

    def _draw_hint(self, q) -> None:
        q.setPen(QColor(T.TEXT_3))
        f = QFont(T.fonts()[0], T.SIZE_LABEL)
        q.setFont(f)
        q.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Press Run")

    def _draw_trail(self, q, to_px) -> None:
        """The link-2 tip's recent path. The one decoration here, and it earns
        its place by making the phase of a swing legible in a still frame."""
        if len(self._trail) < 2:
            return
        col = QColor(T.TH2)
        col.setAlpha(T.TRAIL_ALPHA)
        q.setPen(QPen(col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pts = [to_px(x, y) for x, y in self._trail]
        for i in range(1, len(pts)):
            q.drawLine(pts[i - 1], pts[i])

    @staticmethod
    def _cart_rect(centre: QPointF, p: Params, k: float) -> QRectF:
        """The carriage at its real length, floored where it would stop being
        legible. Everything else on the canvas is metres times k; a cart that
        is not becomes a bus as soon as the rail is long."""
        w = max(T.CART_MIN_W, p.nominal.cart_len * k)
        h = w * T.CART_ASPECT
        return QRectF(centre.x() - w / 2.0, centre.y() - h / 2.0, w, h)

    def _draw_ghost_cart(self, q, to_px, s: Sample, p: Params,
                         k: float) -> None:
        """Where the step counter believes the cart is.

        With slip disabled this sits exactly on the cart. Enable slip and the
        two part -- which turns the counting error into something you watch
        rather than infer from a plot. On hardware this outline is the ONLY
        position anyone knows.
        """
        col = QColor(T.X_COUNT)
        col.setAlpha(T.GHOST_ALPHA)
        q.setPen(QPen(col, T.CART_EDGE_W, Qt.PenStyle.DashLine))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawRoundedRect(self._cart_rect(to_px(s.x_count, 0.0), p, k),
                          T.CART_RADIUS, T.CART_RADIUS)

    def _draw_mechanism(self, q, to_px, s: Sample, e: dict, p: Params,
                        k: float) -> None:
        th1, th2 = self._angles(s)
        x = self._cart_x(s)

        # A solid dark block on a light field, the convention this animation
        # belongs to. Filled in the surface colour it was the lowest-contrast
        # object on the page -- an empty input box on a hairline.
        q.setPen(QPen(QColor(T.CART_EDGE), T.CART_EDGE_W))
        q.setBrush(QColor(T.CART_FILL))
        q.drawRoundedRect(self._cart_rect(to_px(x, 0.0), p, k),
                          T.CART_RADIUS, T.CART_RADIUS)
        q.setBrush(Qt.BrushStyle.NoBrush)

        ey, tx, ty = self._joints(s, p)
        ex = x + e["l1"] * math.sin(th1)

        pivot, elbow, tip = to_px(x, 0.0), to_px(ex, ey), to_px(tx, ty)

        for a, b, colour in ((pivot, elbow, T.TH1), (elbow, tip, T.TH2)):
            q.setPen(QPen(QColor(colour), T.LINK_W, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            q.drawLine(a, b)

        # Hollow joints: a ring in the link colour over the window ground, so
        # crossing links stay readable where they overlap.
        q.setBrush(QColor(T.SURFACE_SUNKEN))
        for centre, colour in ((pivot, T.TH1), (elbow, T.TH2)):
            q.setPen(QPen(QColor(colour), T.JOINT_RING))
            q.drawEllipse(centre, T.JOINT_R, T.JOINT_R)

        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(T.TH2))
        q.drawEllipse(tip, T.TIP_R, T.TIP_R)
        q.setBrush(Qt.BrushStyle.NoBrush)

    # -- readout ----------------------------------------------------------

    def readout_text(self) -> str:
        """The three live angles, for the card header.

        Drawn at (16, 24) over the canvas they floated in the dead band above
        the mechanism with nothing to anchor them. In the header they sit
        beside the card's own name, and the canvas is left to the mechanism.
        """
        s = self._sample
        if s is None:
            return ""
        th1, th2 = self._angles(s)
        return (f"θ₁ {math.degrees(th1):7.1f}°   "
                f"θ₂ {math.degrees(th2):7.1f}°   "
                f"x {self._cart_x(s):7.3f} m")
