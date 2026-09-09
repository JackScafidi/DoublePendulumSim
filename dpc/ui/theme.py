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
GRID = "#cbccd6"
BORDER = "#cfd0d8"
BORDER_INTERACTIVE = "#7a7d92"
"""Shadow sits near 1.2:1 and cannot carry affordance under WCAG 1.4.11. Any
control that is not a colour fill takes this border instead."""

TEXT = "#2b2d42"
TEXT_2 = "#5c5f72"
TEXT_3 = "#7a7d92"
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

CART_EDGE = "#a9abb8"
RAIL = "#b9bac4"

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
SIZE_READOUT = 15
SIZE_TICK = 9

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
SHADOW_BAR = 5
"""Extrusion offsets. Blur is twice the offset. A light theme has the easier
job -- pure white is available for the light half -- so these stay modest."""
GAP_SECTION = 6
RADIUS_PANEL = 16
RADIUS_CTRL = 12
"""The shadow needs curvature to wrap around; sharp corners break it."""
CONSTANTS_WIDTH = 300

TRACE_W = 1.6
LIMIT_W = 0.9
LINK_W = 7
JOINT_R = 5.5
JOINT_RING = 2.5
TRAIL_ALPHA = 74
"""0-255. A touch heavier than the dark theme's: a faint trace disappears
against a light ground long before it does against a dark one."""


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
    QLabel#value {{
        color: {TEXT};
        font-family: "{mono}";
        font-size: {SIZE_VALUE}px;
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
    QLabel#status {{
        color: {TEXT_3};
        font-family: "{mono}";
        font-size: {SIZE_VALUE}px;
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
    }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QComboBox QAbstractItemView {{
        background: {SURFACE_SUNKEN};
        border: 1px solid {BORDER_INTERACTIVE};
        selection-background-color: {ACCENT};
        color: {TEXT};
    }}

    /* The one primary fill in the view. */
    /* Secondary controls: raised surface plus an interactive border. */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {BORDER_INTERACTIVE}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
