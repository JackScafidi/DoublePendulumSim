"""The mechanism, drawn.

Renders one sample. It computes nothing about the physics -- link lengths come
from the parameters, angles from the sample -- so this file stays a projection
from state to pixels and nothing else.
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


class AnimationPanel(QWidget):
    """Cart on a rail with two links, plus the step counter's belief.

    Angles are measured from straight up, positive toward +x, so a link at
    theta is the unit vector (sin, cos) in world coordinates -- and the y axis
    is flipped on the way to screen coordinates, where y grows downward.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._sample: Sample | None = None
        self._params = Params()
        self._trail: deque[tuple[float, float]] = deque(maxlen=TRAIL_LEN)
        self._x_seen = 0.0
        """Largest |cart x| this run. The rail is sized to it, so the view
        widens as the cart travels rather than letting it run off the end."""

    def clear(self) -> None:
        self._sample = None
        self._trail.clear()
        self._x_seen = 0.0
        self.update()

    def show_sample(self, s: Sample | None, p: Params) -> None:
        self._params = p
        self._sample = s
        if s is not None:
            self._x_seen = max(self._x_seen, abs(self._cart_x(s)),
                               abs(s.x_count))
            self._trail.append(self._tip(s, p))
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

    def _tip(self, s: Sample, p: Params) -> tuple[float, float]:
        th1, th2 = self._angles(s)
        e = p.effective()
        x = self._cart_x(s)
        ex = x + e["l1"] * math.sin(th1)
        ey = e["l1"] * math.cos(th1)
        return ex + e["l2"] * math.sin(th2), ey + e["l2"] * math.cos(th2)

    def _scale(self, p: Params):
        """Metres to pixels, plus the origin.

        The rail has to cover wherever the cart has actually gone -- a cart
        drawn past the end of its own rail is worse than no rail at all -- and
        the pivot sits at mid height because the links reach as far above it as
        below.
        """
        e = p.effective()
        reach = e["l1"] + e["l2"]
        half_x = max(0.30, self._x_seen + 0.06)
        w, h = self.width(), self.height()
        sx = (w - 2 * 46) / (2 * half_x)
        sy = (h - 2 * 26) / (2 * reach)
        k = max(1.0, min(sx, sy))
        return k, w / 2.0, h / 2.0, half_x

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)
        q.fillRect(self.rect(), QColor(T.SURFACE_SUNKEN))

        p = self._params
        k, cx, cy, half_rail = self._scale(p)
        e = p.effective()

        def to_px(x_m: float, y_m: float) -> QPointF:
            return QPointF(cx + x_m * k, cy - y_m * k)

        self._draw_rail(q, to_px, half_rail)

        s = self._sample
        if s is None:
            self._draw_hint(q)
            q.end()
            return

        self._draw_trail(q, to_px)
        self._draw_ghost_cart(q, to_px, s)
        self._draw_mechanism(q, to_px, s, e)
        self._draw_readout(q, s)
        q.end()

    def _draw_rail(self, q, to_px, half_rail) -> None:
        # Grid spans exactly the rail, not the panel: a horizon wider than the
        # track it belongs to reads as a second, unexplained extent.
        a, b = to_px(-half_rail, 0.0), to_px(half_rail, 0.0)
        q.setPen(QPen(QColor(T.GRID), 1))
        for frac in (0.25, 0.5, 0.75):
            y = int(self.height() * frac)
            q.drawLine(int(a.x()), y, int(b.x()), y)

        q.setPen(QPen(QColor(T.RAIL), 3, Qt.SolidLine, Qt.RoundCap))
        q.drawLine(a, b)

        q.setPen(QPen(QColor(T.TEXT_3), 2, Qt.SolidLine, Qt.RoundCap))
        for end in (a, b):
            q.drawLine(QPointF(end.x(), end.y() - 12), QPointF(end.x(), end.y() + 12))

    def _draw_hint(self, q) -> None:
        q.setPen(QColor(T.TEXT_3))
        f = QFont(T.fonts()[0], T.SIZE_LABEL)
        q.setFont(f)
        q.drawText(self.rect(), Qt.AlignCenter, "Press Run")

    def _draw_trail(self, q, to_px) -> None:
        """The link-2 tip's recent path. The one decoration here, and it earns
        its place by making the phase of a swing legible in a still frame."""
        if len(self._trail) < 2:
            return
        col = QColor(T.TH2)
        col.setAlpha(T.TRAIL_ALPHA)
        q.setPen(QPen(col, 2, Qt.SolidLine, Qt.RoundCap))
        pts = [to_px(x, y) for x, y in self._trail]
        for i in range(1, len(pts)):
            q.drawLine(pts[i - 1], pts[i])

    def _draw_ghost_cart(self, q, to_px, s: Sample) -> None:
        """Where the step counter believes the cart is.

        With slip disabled this sits exactly on the cart. Enable slip and the
        two part -- which turns the counting error into something you watch
        rather than infer from a plot. On hardware this outline is the ONLY
        position anyone knows.
        """
        col = QColor(T.X_COUNT)
        col.setAlpha(166)
        pen = QPen(col, 1.5, Qt.DashLine)
        q.setPen(pen)
        q.setBrush(Qt.NoBrush)
        c = to_px(s.x_count, 0.0)
        q.drawRoundedRect(QRectF(c.x() - 36, c.y() - 16, 72, 32), 4, 4)

    def _draw_mechanism(self, q, to_px, s: Sample, e: dict) -> None:
        th1, th2 = self._angles(s)
        x = self._cart_x(s)

        cart = to_px(x, 0.0)
        q.setPen(QPen(QColor(T.CART_EDGE), 1.5))
        q.setBrush(QColor(T.SURFACE))
        q.drawRoundedRect(QRectF(cart.x() - 36, cart.y() - 16, 72, 32), 4, 4)
        q.setBrush(Qt.NoBrush)

        ex = x + e["l1"] * math.sin(th1)
        ey = e["l1"] * math.cos(th1)
        tx = ex + e["l2"] * math.sin(th2)
        ty = ey + e["l2"] * math.cos(th2)

        pivot, elbow, tip = to_px(x, 0.0), to_px(ex, ey), to_px(tx, ty)

        q.setPen(QPen(QColor(T.TH1), T.LINK_W, Qt.SolidLine, Qt.RoundCap))
        q.drawLine(pivot, elbow)
        q.setPen(QPen(QColor(T.TH2), T.LINK_W, Qt.SolidLine, Qt.RoundCap))
        q.drawLine(elbow, tip)

        # Hollow joints: a ring in the link colour over the window ground, so
        # crossing links stay readable where they overlap.
        q.setBrush(QColor(T.SURFACE_SUNKEN))
        for centre, colour in ((pivot, T.TH1), (elbow, T.TH2)):
            q.setPen(QPen(QColor(colour), T.JOINT_RING))
            q.drawEllipse(centre, T.JOINT_R, T.JOINT_R)

        q.setPen(Qt.NoPen)
        q.setBrush(QColor(T.TH2))
        q.drawEllipse(tip, 4, 4)
        q.setBrush(Qt.NoBrush)

    def _draw_readout(self, q, s: Sample) -> None:
        th1, th2 = self._angles(s)
        q.setFont(QFont(T.fonts()[1], T.SIZE_READOUT - 2))
        lines = [
            (QColor(T.TEXT), f"θ₁ {math.degrees(th1):8.1f}°"),
            (QColor(T.TEXT), f"θ₂ {math.degrees(th2):8.1f}°"),
            (QColor(T.TEXT_2), f"x  {self._cart_x(s):8.3f} m"),
        ]
        for i, (col, text) in enumerate(lines):
            q.setPen(col)
            q.drawText(16, 24 + i * 19, text)
