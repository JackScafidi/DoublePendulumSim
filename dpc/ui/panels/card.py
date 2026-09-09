"""The one card shape everything on the page uses.

A raised surface carrying a title, with its content pressed into a well. Two
elevations and no more: the page, and this. The well is not a third level -- it
is the same card, pushed in where the data goes.
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from dpc.ui import theme as T
from dpc.ui.neumorphic import NeumorphicFrame


def card(title: str | None, body: QWidget, well: bool = True) -> NeumorphicFrame:
    frame = NeumorphicFrame(offset=T.SHADOW_CARD)
    m = frame.pad
    v = QVBoxLayout(frame)
    v.setContentsMargins(m + 4, m + 2, m + 4, m + 4)
    v.setSpacing(5)

    if title:
        head = QLabel(title.upper())
        head.setObjectName("panelTitle")
        v.addWidget(head)

    if well:
        sunk = NeumorphicFrame(inset=True, offset=T.SHADOW_WELL,
                               radius=T.RADIUS_PANEL - 4)
        wv = QVBoxLayout(sunk)
        wv.setContentsMargins(4, 4, 4, 4)
        wv.addWidget(body)
        v.addWidget(sunk, 1)
    else:
        v.addWidget(body, 1)
    return frame
