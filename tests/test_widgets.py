import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dpc.ui import theme as T  # noqa: E402
from dpc.ui.widgets import (NeumorphicButton, NeumorphicCheck,  # noqa: E402
                            NeumorphicSlider, SegmentedControl)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _event(kind, x: float, y: float):
    return QMouseEvent(kind, QPointF(x, y), QPointF(x, y), QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       Qt.MouseEventSource.MouseEventNotSynthesized)


def _press(w, x: float = 5.0, y: float = 5.0):
    w.mousePressEvent(_event(QEvent.Type.MouseButtonPress, x, y))


def _release(w, x: float = 5.0, y: float = 5.0):
    w.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, x, y))


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


def test_each_chip_of_the_segmented_control_owns_its_own_span(qapp):
    """Probed at the boundaries, because a control whose chips are computed
    from the widget width and hit-tested from a different number is one that
    selects the neighbour of what you clicked."""
    seg = SegmentedControl(("0.25×", "1×", "2×"))
    seg.resize(seg.sizeHint())
    pad = seg.pad
    chip = (seg.width() - 2 * pad) / 3.0

    seen: list[int] = []
    seg.selected.connect(seen.append)

    for x, want in ((pad + 0.1, 0),
                    (pad + chip - 0.1, 0),
                    (pad + chip + 0.1, 1),
                    (seg.width() - 0.1, 2)):
        seg.set_active(0)
        _press(seg, x=x, y=seg.height() / 2.0)
        assert seg.active == want, x

    seg.set_active(1)
    _press(seg, x=0.0, y=seg.height() / 2.0)
    assert seg.active == 0, "clicks in the left shadow margin clamp"
    seg.set_active(1)
    _press(seg, x=seg.width() + 200.0, y=seg.height() / 2.0)
    assert seg.active == 2, "clicks past the right edge clamp"


def test_setting_the_active_chip_does_not_emit(qapp):
    """set_active is how the owner reflects state back; if it emitted, the
    reflection would be indistinguishable from a click."""
    seg = SegmentedControl(("0.25×", "1×", "2×"))
    seen: list[int] = []
    seg.selected.connect(seen.append)
    seg.set_active(2)
    assert seg.active == 2
    assert seen == []


def test_the_scrub_groove_never_changes_length_when_the_status_does(qapp):
    """The slider is the only thing in the transport row that stretches, so
    every pixel a neighbour gains comes out of the groove -- and a groove that
    shortens mid-run jumps the thumb out from under the finger dragging it."""
    from dpc.ui.panels.controls import BEHIND, DONE, TransportPanel

    bar = TransportPanel()
    bar.resize(900, bar.sizeHint().height())

    widths = []
    for text in ("", BEHIND, DONE, ""):
        bar.set_status(text)
        layout = bar.layout()
        assert layout is not None
        layout.activate()
        widths.append(bar.slider.width())

    assert bar.status.text() == ""
    assert len(set(widths)) == 1, widths
