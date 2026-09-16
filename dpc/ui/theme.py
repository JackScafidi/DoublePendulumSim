"""The one place the dashboard's visual values live.

Every colour and size here comes from docs/dashboard-visual-design.md. Nothing
in a panel invents one -- if a widget needs a colour it takes it from this
module, so restyling is a change here rather than a search through five files.

Signal colours are the categorical palette re-stepped for a LIGHT surface: a
signal's colour belongs to the signal, never to its position in a plot. Clearing
3:1 against a near-white ground forces every hue darker than its dark-theme
step, and naive darkening collapses aqua and amber into neighbouring browns --
so those two were pushed apart in hue until the pair separated. The step count
is dashed as well, so identity never rests on colour alone.
"""

# Surfaces and ink
#
# Neumorphic dark base. Every neumorphic element is the SAME colour as what it
# sits on -- depth comes only from the shadow, so there is one surface value,
# not a ladder of them. The only other surface is the sunken well that data
# lives in, which is darker because traces need the contrast.

SURFACE = "#e6e7ee"
SURFACE_SUNKEN = "#dcdde5"
SHADOW_LIGHT = "#ffffff"
SHADOW_DARK = "#c3c4ca"

WINDOW = SURFACE
PANEL = SURFACE
RAISED = SURFACE
GRID = "#b3b4c4"
"""The plot grid. The old #cbccd6 measured 1.18:1 on the well -- a gridline
nobody could see. This is 1.5:1, which is a reference you can follow across a
plot without it competing with a 1.6 px trace."""
BORDER = "#cfd0d8"
"""A hairline on the page surface, for edges that separate rather than
enclose. Never an axis or a plot frame: at 1.14:1 on the well it vanishes."""
BORDER_INTERACTIVE = "#63667b"
"""Shadow sits near 1.2:1 and cannot carry affordance under WCAG 1.4.11. Any
control that is not a colour fill takes this border instead. Stepped from
#7a7d92, which cleared the 3:1 non-text floor with no margin on the well."""

TEXT = "#2b2d42"
TEXT_2 = "#4a4d5e"
TEXT_3 = "#5c5f72"
INK_FAINT = "#7a7d92"
"""The ink ramp, re-stepped so every step clears WCAG 1.4.3 at 9-11 px on both
surfaces: 10.94/9.97, 6.77/6.17 and 5.11/4.65 against surface and well.

INK_FAINT is the old TEXT_3 and is reserved for NON-TEXT use -- the scrollbar
handle and the section hairline. At 3.29/3.00 it passes 1.4.11 for a boundary
and fails 1.4.3 for a label, so it must never carry a word."""

MODIFIED = "#9a6700"
"""Amber, after FTC Dashboard's marker for a variable moved off its default.
Stepped dark enough to read on this surface -- their #fbbf24 sits near 1.7:1
here. It marks a diff, never data, so it is not a series colour."""

ACCENT = "#5057e8"
ACCENT_SHADE = "#3b41c4"
"""Indigo, distinct from the theta-1 blue: chrome must never wear a signal's
colour, or the same hue would mean two things."""

# Signals
TH1 = "#2a78d6"
TH2 = "#b4531f"
X_TRUE = "#12795a"
X_COUNT = "#a35400"
A_CMD = "#b03a67"
A_DEL = "#008300"
TAU = "#4a3aa7"
LIMIT = "#a82b3f"
"""Reserved status value, not a ninth series: it marks a threshold, never data,
which is why it may repeat across plots without implying a relationship."""

CART_FILL = "#2c2f36"
CART_EDGE = "#454b57"
RAIL = "#3b414c"
"""The documented mechanism values, restored. The lightened pair that shipped
measured 1.43:1 and 1.69:1 on the well, which made the cart -- the driven mass
this whole project is about -- the faintest object on the canvas. These measure
7.58 and 6.47, and a dark filled cart makes it the focal object."""

# Type
#
# Qt stylesheets do NOT honour a comma-separated font-family fallback list the
# way CSS does: an absent family resolves to whatever Qt picks (Tahoma on
# Windows), silently losing the monospaced digits the readouts depend on. So the
# family is resolved against what is actually installed, once, at startup.

SANS_PREF = ("IBM Plex Sans", "Segoe UI Variable Text", "Segoe UI",
             "DejaVu Sans", "Helvetica Neue")
MONO_PREF = ("IBM Plex Mono", "Cascadia Mono", "Consolas",
             "DejaVu Sans Mono", "Menlo")

_resolved: tuple[str, str] | None = None


def _first_installed(prefs: tuple[str, ...], fallback: str) -> str:
    try:
        from PySide6.QtGui import QFontDatabase
        families = set(QFontDatabase.families())
    except Exception:
        return fallback
    for name in prefs:
        if name in families:
            return name
    return fallback


def fonts() -> tuple[str, str]:
    """(sans, mono) actually available. Needs a QApplication to exist."""
    global _resolved
    if _resolved is None:
        _resolved = (_first_installed(SANS_PREF, "sans-serif"),
                     _first_installed(MONO_PREF, "monospace"))
    return _resolved


FONT = SANS_PREF[0]
MONO = MONO_PREF[0]
"""Preferred names, kept for documentation. Use fonts() for anything drawn."""

SIZE_TITLE = 13
SIZE_PANEL = 11
SIZE_SECTION = 11
SIZE_LABEL = 11
SIZE_VALUE = 11
SIZE_TICK = 10
"""Axis ticks, units, notes and legend labels. Mono where it carries a number.
10 rather than 9 because the ink ramp above only clears 1.4.3 for real text
sizes, and the design doc asked for 10 all along."""

# Spacing and shape
PAD_ICON = 4
PAD_PANEL = 8
GAP_PANEL = 2
PAD_WINDOW = 2
"""Small, because each raised frame already reserves its own shadow margin --
about 23 px a side at SHADOW_CARD. The visible gap between two cards is that
margin twice over, which lands in the 24-32 px the style wants."""

SHADOW_CARD = 5
SHADOW_WELL = 3
SHADOW_PRIMARY = 4
SHADOW_CTRL = 3
"""Extrusion offsets. Blur is twice the offset. A light theme has the easier
job -- pure white is available for the light half -- so these stay modest.

Three numbers, not two. A card is the deepest thing on the page; a well and a
secondary control are the shallowest; and the ONE primary fill in the view --
Run -- sits between them, because the button that starts the run should stand
off the surface further than the icon button beside it. The transport bar is a
card, so it takes SHADOW_CARD like every other card.
"""

CARD_INSET = SHADOW_CARD * 3 + 2 + 4
"""px from a card's outer edge to its content. Anything that sits OUTSIDE a
card but has to line up with what is inside one -- the window title above the
mechanism -- takes the same inset, or the eye catches the mismatch before it
reads a word."""

GAP_SECTION_BEFORE = 14
GAP_SECTION_AFTER = 4
"""A section header belongs to the rows beneath it, so the space above it is
roughly three times the space below. Equal gaps read as one undifferentiated
run of rows."""

ROW_PITCH = 26
"""px. One rhythm for every constants row, editable or not. A raised control
in a row reserves its own shadow margin and makes that row twice as tall as a
read-only one, which reads as two lists spliced together."""

FIELD_W = 88
ARROW_W = 14
UNIT_W = 40
"""The constants column's value grid: a field of FIELD_W with ARROW_W of it
reserved for the stepper chevrons, then the unit in a column of its own. Both
row kinds use it, so every number on the column shares one right edge."""

SCROLLBAR_W = 8
FADE_H = 12
"""The scroll handle's width. The sheet below gives the bar a width and a
background but no absolute position, so Qt lays it out BESIDE the viewport and
takes these 8 px out of the viewport itself -- the handle is never painted over
the unit column, and nothing may reserve the width a second time as a margin.
FADE_H is the fade at the foot of the viewport -- a cut row with no fade reads
as broken, a cut row under a fade reads as scrollable."""

RADIUS_PANEL = 16
RADIUS_WELL = RADIUS_PANEL - 4
RADIUS_CTRL = 12
RADIUS_CHECK = 6
"""The shadow needs curvature to wrap around; sharp corners break it. The well
is 4 less than the card it is pressed into, because concentric corners whose
radii are equal read as a corner drawn twice; the checkbox is the one real
exception at 6, since 12 on a 17 px square is a circle."""
CONSTANTS_WIDTH = 300

SWATCH_W = 14
SWATCH_H = 8
SWATCH_PEN = 2.0
GAP_LEGEND = 12
PAD_LEGEND = 6
"""The legend row under each plot. A swatch drawn in the trace's own pen,
dash included, so the key and the data are the same mark."""

GROOVE_H = 4
GROOVE_FILL_A = 0.45
THUMB_D = 18
SCRUB_PAD = 11
"""The scrub bar. SCRUB_PAD is the inset at each end of the groove: the thumb
is THUMB_D across and is centred on the end of the groove at the extremes, so
anything less than half of it clips the thumb against the widget edge. A
full-strength 8 px track becomes the largest coloured mass on the page by the
end of a run while carrying the least information on it, so the groove is thin
and part-strength and the thumb keeps the full accent."""

PAD_PILL_X = 9
PAD_PILL_Y = 3
"""Inside the status pill. Wider than it is tall, because a pill whose radius
is half its height needs horizontal room before the text clears the curve."""

TRACE_W = 1.6
LIMIT_W = 0.9
LIMIT_HEADROOM = 1.15
"""How far past a limit the y range reaches. A threshold drawn flush with the
frame shows no headroom, which is the only thing it exists to show."""
RAIL_W = 3
"""px. The rail and its end stops are one piece of hardware in one pen."""
LINK_W = 7
JOINT_R = 5.5
JOINT_RING = 2.5
STOP_H = 12
"""px. Half height of the end-stop cap at each end of the rail."""
CART_MIN_W = 22
CART_ASPECT = 0.42
CART_RADIUS = 4
CART_EDGE_W = 1.5
"""The cart is drawn at its real length in metres, like everything else on the
canvas, down to a floor where it would stop being legible. The ghost outline
is the same rectangle in the same stroke width, so the two read as one part
drawn twice rather than as two different objects."""
TIP_R = 4
"""px. The filled dot on the end of link 2 -- the point the trail traces."""
TRAIL_ALPHA = 74
GHOST_ALPHA = 166
"""0-255. TRAIL_ALPHA is a touch heavier than the dark theme's: a faint trace
disappears against a light ground long before it does against a dark one.
GHOST_ALPHA is the documented 65% of the step-counter outline."""


def stylesheet() -> str:
    """Application-wide Qt stylesheet.

    Shadow is not in here: Qt discards `box-shadow`, so every extrusion is
    painted by NeumorphicFrame. What is here is colour, type and the borders
    that carry affordance -- because a neumorphic shadow sits near 1.2:1 and
    cannot tell anyone that a thing is clickable. Colour has to.
    """
    sans, mono = fonts()
    return f"""
    QWidget {{
        background: transparent;
        color: {TEXT};
        font-family: "{sans}";
        font-size: {SIZE_LABEL}px;
    }}
    QMainWindow, QWidget#root {{ background: {SURFACE}; }}

    /* Small labels: 11px, weight 500, 0.06em, muted -- quiet, not cramped. */
    QLabel#panelTitle {{
        color: {TEXT_3};
        font-size: {SIZE_PANEL}px;
        font-weight: 500;
        letter-spacing: 0.66px;
    }}
    QLabel#sectionTitle {{
        color: {TEXT_3};
        font-size: {SIZE_SECTION}px;
        font-weight: 500;
        letter-spacing: 0.66px;
    }}
    QLabel#label {{ color: {TEXT_2}; }}
    /* A read-only value is the SAME box as the field beside it, minus the
       fill and the edge -- same border width, same padding, same chevron
       gutter -- so both row kinds put their last digit on one right edge. */
    QLabel#value {{
        color: {TEXT};
        font-family: "{mono}";
        font-size: {SIZE_VALUE}px;
        border: 1px solid transparent;
        padding: 3px {8 + ARROW_W}px 3px 8px;
    }}
    QLabel#unit {{
        color: {TEXT_3};
        font-family: "{mono}";
        font-size: {SIZE_TICK}px;
    }}
    QLabel#note {{ color: {TEXT_3}; font-size: {SIZE_TICK}px; }}
    QLabel#baseline {{
        color: {TEXT_3};
        font-family: "{mono}";
        font-size: {SIZE_TICK}px;
    }}
    QLabel#headUnit {{
        color: {TEXT_3};
        font-family: "{mono}";
        font-size: {SIZE_TICK}px;
    }}

    /* Inputs are wells: sunken fill plus a visible edge, never shadow alone. */
    QComboBox, QDoubleSpinBox {{
        background: {SURFACE_SUNKEN};
        border: 1px solid {BORDER_INTERACTIVE};
        border-radius: {RADIUS_CTRL}px;
        padding: 4px 8px;
        color: {TEXT};
        selection-background-color: {ACCENT};
    }}
    QComboBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {ACCENT}; }}
    QDoubleSpinBox {{
        font-family: "{mono}";
        font-size: {SIZE_VALUE}px;
        padding: 3px {8 + ARROW_W}px 3px 8px;
    }}
    /* Zero-sized, not restyled. Windows draws its own framed arrow block for
       any subcontrol the sheet leaves alone, which is what put a second set
       of arrows on top of every suffix. The chevrons that replace them are
       painted by FlatSpinBox into the gutter this padding reserves. */
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 0px; height: 0px; border: none; background: none;
    }}
    /* Same bargain on the picker: the frame goes, the width stays, and
       FlatCombo paints the chevron the native arrow never drew. */
    QComboBox::drop-down {{ border: none; width: {ARROW_W + 6}px; }}
    QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
    QComboBox QAbstractItemView {{
        background: {SURFACE_SUNKEN};
        border: 1px solid {BORDER_INTERACTIVE};
        selection-background-color: {ACCENT};
        color: {TEXT};
    }}

    /* The one primary fill in the view. */
    /* Secondary controls: raised surface plus an interactive border. */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: transparent; width: {SCROLLBAR_W}px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {INK_FAINT}; border-radius: {SCROLLBAR_W // 2}px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
