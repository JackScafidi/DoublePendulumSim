import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dpc.ui import theme as T  # noqa: E402
from dpc.ui.widgets import (NeumorphicButton, NeumorphicCheck,  # noqa: E402
                            NeumorphicSlider)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _event(kind, x, y):
    return QMouseEvent(kind, QPointF(x, y), QPointF(x, y), QPointF(x, y),
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
                       Qt.MouseEventNotSynthesized)


def _press(w, x=5, y=5):
    w.mousePressEvent(_event(QMouseEvent.Type.MouseButtonPress, x, y))


def _release(w, x=5, y=5):
    w.mouseReleaseEvent(_event(QMouseEvent.Type.MouseButtonRelease, x, y))


def test_a_filled_button_is_a_coloured_mass_with_its_own_inner_shade(qapp):
    """A colour fill with no inset shading is a flat rectangle wearing a
    shadow. The shade is what gives it internal form."""
    b = NeumorphicButton("Run", filled=True)
    fill, shade, ink = b._colours()
    assert fill.name() == T.ACCENT
    assert shade is not None
    assert shade.name() == T.ACCENT_SHADE
    assert ink.name() == "#ffffff"


def test_an_unfilled_button_is_surface_coloured_and_takes_a_border(qapp):
    """Same colour as what it sits on -- so a border, not a shadow, is what
    says it can be clicked."""
    b = NeumorphicButton("0.25x")
    fill, shade, _ = b._colours()
    assert fill.name() == T.SURFACE
    assert shade is None


def test_pressing_drives_the_extrusion_inward_and_release_lets_it_out(qapp):
    b = NeumorphicButton("Run", filled=True)
    b.resize(b.sizeHint())
    assert b._depth == 0.0

    _press(b)
    assert b._anim.endValue() == 1.0
    b._set_depth(1.0)

    _release(b)
    assert b._anim.endValue() == 0.0


def test_the_press_lasts_as_long_as_the_language_asks(qapp):
    assert 150 <= NeumorphicButton("x")._anim.duration() <= 200


def test_a_checked_toggle_stays_raised_and_carries_its_state_in_the_fill(qapp):
    """The travel is transient; the fill is what holds the state. A toggle
    left permanently depressed reads as stuck."""
    b = NeumorphicButton("1x")
    b.setCheckable(True)
    b.setChecked(True)
    assert b._depth == 0.0
    assert b._colours()[0].name() == T.ACCENT


def test_the_checkbox_carries_a_glyph_not_only_a_colour(qapp):
    c = NeumorphicCheck()
    assert c.isCheckable()
    c.setChecked(True)
    assert c._colours()[0].name() == T.ACCENT
    c.setChecked(False)
    assert c._colours()[0].name() == T.SURFACE


def test_clicking_the_scrub_bar_jumps_to_that_point(qapp):
    """A scrub bar you have to drag from the thumb is one nobody uses."""
    s = NeumorphicSlider()
    s.setRange(0, 1000)
    s.resize(211, 26)          # 11 px pad each side -> a 189 px groove
    _press(s, x=11 + 189 / 2, y=13)
    assert s.value() == pytest.approx(500, abs=15)


def test_the_scrub_bar_clamps_at_both_ends(qapp):
    s = NeumorphicSlider()
    s.setRange(0, 1000)
    s.resize(211, 26)
    _press(s, x=-50, y=13)
    assert s.value() == 0
    _press(s, x=9999, y=13)
    assert s.value() == 1000
