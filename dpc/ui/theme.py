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
WINDOW = "#0D1014"
PANEL = "#12161B"
RAISED = "#171C22"
BORDER = "#232A33"
GRID = "#1E252E"
TEXT = "#E6EAF0"
TEXT_2 = "#8A94A3"
TEXT_3 = "#5A6472"
ACCENT = "#3987e5"

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

CART_EDGE = "#3D4754"
RAIL = "#2A323C"

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
GAP_PANEL = 12
PAD_WINDOW = 12
GAP_SECTION = 9
RADIUS_PANEL = 4
RADIUS_CTRL = 3
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

    Kept as one string rather than scattered setStyleSheet calls so the whole
    look can be read at once.
    """
    sans, mono = fonts()
    return f"""
    QWidget {{
        background: {WINDOW};
        color: {TEXT};
        font-family: "{sans}";
        font-size: {SIZE_LABEL}px;
    }}
    QFrame#panel {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_PANEL}px;
    }}
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
    QComboBox, QDoubleSpinBox {{
        background: {WINDOW};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CTRL}px;
        padding: 3px 7px;
        color: {TEXT};
        selection-background-color: {ACCENT};
    }}
    QDoubleSpinBox {{
        font-family: "{mono}";
        font-size: {SIZE_VALUE}px;
    }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 13px; background: transparent; border: none;
    }}
    QDoubleSpinBox::up-arrow {{
        width: 7px; height: 7px;
        border-left: 3px solid transparent; border-right: 3px solid transparent;
        border-bottom: 4px solid {TEXT_3};
    }}
    QDoubleSpinBox::down-arrow {{
        width: 7px; height: 7px;
        border-left: 3px solid transparent; border-right: 3px solid transparent;
        border-top: 4px solid {TEXT_3};
    }}
    QComboBox QAbstractItemView {{
        background: {RAISED};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT};
        color: {TEXT};
    }}
    QPushButton#run {{
        background: {ACCENT};
        color: {WINDOW};
        border: none;
        border-radius: {RADIUS_CTRL}px;
        padding: 6px 16px;
        font-weight: 600;
    }}
    QPushButton#run:hover {{ background: #4f97ea; }}
    QPushButton#transport {{
        background: {WINDOW};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CTRL}px;
        padding: 3px 10px;
        color: {TEXT};
    }}
    QPushButton#transport:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: {WINDOW};
    }}
    QCheckBox {{ color: {TEXT_2}; }}
    QSlider::groove:horizontal {{
        background: {BORDER}; height: 4px; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT}; height: 4px; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {TEXT}; width: 3px; height: 12px;
        margin: -4px 0; border-radius: 1px;
    }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: {PANEL}; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {BORDER}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
