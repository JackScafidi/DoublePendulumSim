"""The one card shape everything on the page uses.

A raised surface carrying a header, with its content pressed into a well. Two
elevations and no more: the page, and this. The well is not a third level -- it
is the same card, pushed in where the data goes.

The header is a row rather than a lone title: the name on the left, and a mono
slot on the right for whatever that card measures in. That slot is why the
plots can drop pyqtgraph's own centred, title-case title -- which was the one
thing on the page that looked like a different application -- and why the run
clock and the mechanism readout have somewhere to live besides floating over
the canvas.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from dpc.ui import theme as T
from dpc.ui.neumorphic import NeumorphicFrame

HEAD_MIN_CHARS = 8
"""How much of the header slot survives a narrow window. Enough to keep a unit
or the leading field of a readout, and little enough that the card can still be
made narrow."""


class HeadSlot(QLabel):
    """The card header's right slot: a live readout that may not set the card's
    minimum width.

    A QLabel reports its whole text as both its preferred AND its minimum size,
    so the mechanism card's clock plus angle readout -- about 390 px of mono
    10 -- became a floor the window could not be narrowed past. The preferred
    size is still the full string, so nothing looks different at a size that
    fits; below that the slot elides instead of holding the layout open.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
        self._full = ""
        self.set_full(text)

    def set_full(self, text: str) -> None:
        """The text this slot carries. Called every frame by the window."""
        if text == self._full:
            return
        self._full = text
        self._elide()

    @property
    def full(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full), fm.height())

    def minimumSizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.averageCharWidth() * HEAD_MIN_CHARS, fm.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(self.width(), 0)))


class Card(NeumorphicFrame):
    """A raised frame with a header row, a well, and an optional footer.

    `head_right` is a real attribute rather than something bolted on after
    construction, so a caller that updates it every frame is part of the type.
    """

    def __init__(self, title: str | None, body: QWidget, well: bool = True,
                 unit: str = "", footer: QWidget | None = None):
        super().__init__(offset=T.SHADOW_CARD)
        m = self.pad
        v = QVBoxLayout(self)
        v.setContentsMargins(m + 4, m + 2, m + 4, m + 4)
        v.setSpacing(5)

        self.head_left = QLabel((title or "").upper())
        self.head_left.setObjectName("panelTitle")
        self.head_right = HeadSlot(unit)
        self.head_right.setObjectName("headUnit")

        if title or unit:
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(T.PAD_PANEL)
            head.addWidget(self.head_left)
            head.addStretch(1)
            head.addWidget(self.head_right)
            v.addLayout(head)

        if well:
            sunk = NeumorphicFrame(inset=True, offset=T.SHADOW_WELL,
                                   radius=T.RADIUS_WELL)
            wv = QVBoxLayout(sunk)
            wv.setContentsMargins(4, 4, 4, 4)
            wv.addWidget(body)
            v.addWidget(sunk, 1)
        else:
            v.addWidget(body, 1)

        if footer is not None:
            v.addWidget(footer)


def card(title: str | None, body: QWidget, well: bool = True,
         unit: str = "", footer: QWidget | None = None) -> Card:
    return Card(title, body, well=well, unit=unit, footer=footer)
