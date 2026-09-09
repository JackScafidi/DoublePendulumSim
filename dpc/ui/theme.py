"""The one place the dashboard's visual values live.

Every colour and size here comes from docs/dashboard-visual-design.md. Nothing
in a panel invents one -- if a widget needs a colour it takes it from this
module, so restyling is a change here rather than a search through five files.

Signal colours are the validated dark categorical palette, assigned in fixed
slot order: a signal's colour belongs to the signal, never to its position in a
plot. The two cart traces sit closest together in colour-blind separation, which
is why the step count is also dashed -- identity never rests on colour alone.
"""

# Surfaces and ink
#
# Neumorphic dark base. Every neumorphic element is the SAME colour as what it
# sits on -- depth comes only from the shadow, so there is one surface value,
# not a ladder of them. The only other surface is the sunken well that data
# lives in, which is darker because traces need the contrast.

SURFACE = "#2c2f36"
SURFACE_SUNKEN = "#24272d"
SHADOW_LIGHT = "#3d424d"
SHADOW_DARK = "#191b20"

WINDOW = SURFACE
PANEL = SURFACE
RAISED = SURFACE
GRID = "#31353d"
BORDER = "#383c45"
BORDER_INTERACTIVE = "#6a7080"
"""Shadow sits near 1.2:1 and cannot carry affordance under WCAG 1.4.11. Any
control that is not a colour fill takes this border instead."""

TEXT = "#E6EAF0"
TEXT_2 = "#9aa2b1"
TEXT_3 = "#6f7686"
ACCENT = "#5057e8"
ACCENT_SHADE = "#3b41c4"
"""Indigo, distinct from the theta-1 blue: chrome must never wear a signal's
colour, or the same hue would mean two things."""

# Signals
TH1 = "#3987e5"
TH2 = "#d95926"
X_TRUE = "#199e70"
X_COUNT = "#c98500"
A_CMD = "#d55181"
A_DEL = "#008300"
TAU = "#9085e9"
LIMIT = "#d03b3b"
"""Reserved status value, not a ninth series: it marks a threshold, never data,
which is why it may repeat across plots without implying a relationship."""

CART_EDGE = "#454b57"
RAIL = "#3b414c"

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
SIZE_PANEL = 10
SIZE_SECTION = 9
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
"""Extrusion offsets. Blur is twice the offset. Dark neumorphism has little
headroom before the dark shadow hits black, so these run larger than the light
theme's to stay findable."""
GAP_SECTION = 6
RADIUS_PANEL = 16
RADIUS_CTRL = 9
"""The shadow needs curvature to wrap around; sharp corners break it."""
CONSTANTS_WIDTH = 300

TRACE_W = 1.6
LIMIT_W = 0.9
LINK_W = 7
JOINT_R = 5.5
JOINT_RING = 2.5
TRAIL_ALPHA = 56
"""0-255. 22% of full, per the design."""


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

    QLabel#panelTitle {{
        color: {TEXT_2};
        font-size: {SIZE_PANEL}px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#sectionTitle {{
        color: {TEXT_3};
        font-size: {SIZE_SECTION}px;
        font-weight: 600;
        letter-spacing: 1px;
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
    QPushButton#run {{
        background: {ACCENT};
        color: #ffffff;
        border: none;
        border-radius: {RADIUS_CTRL}px;
        padding: 7px 18px;
        font-weight: 600;
    }}
    QPushButton#run:hover {{ background: #5f66ef; }}
    QPushButton#run:pressed {{ background: {ACCENT_SHADE}; }}

    /* Secondary controls: raised surface plus an interactive border. */
    QPushButton#transport {{
        background: {SURFACE};
        border: 1px solid {BORDER_INTERACTIVE};
        border-radius: {RADIUS_CTRL}px;
        padding: 4px 11px;
        color: {TEXT_2};
    }}
    QPushButton#transport:hover {{ color: {TEXT}; }}
    QPushButton#transport:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: #ffffff;
    }}

    QCheckBox {{ color: {TEXT_2}; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px;
        border-radius: {RADIUS_CTRL}px;
        border: 1px solid {BORDER_INTERACTIVE};
        background: {SURFACE_SUNKEN};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    QSlider::groove:horizontal {{
        background: {SURFACE_SUNKEN}; height: 6px; border-radius: 3px;
        border: 1px solid {BORDER};
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT}; height: 6px; border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {ACCENT}; width: 12px; height: 12px;
        margin: -4px 0; border-radius: 6px;
        border: 2px solid {SURFACE};
    }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {BORDER_INTERACTIVE}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
