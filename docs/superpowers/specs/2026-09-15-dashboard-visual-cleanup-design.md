# Dashboard visual cleanup

*2026-09-15* — design pass. Nothing in `dpc/` is changed by this document.

Audited against renders of the current build at 1440x900 (the default window
size) and 1920x1080, the agreed values in `docs/dashboard-visual-design.md`,
the structure in `docs/superpowers/specs/2026-09-09-dashboard-design.md`
(layout B), the approved artboards in `docs/design/Main.dc.html`, and the
house neumorphic style guide.

Layout B is kept. Every item below is a change inside a panel, not a change to
the frame. The one structural suggestion is isolated at the end and marked
optional.

Renders the audit was made from:

- `scratchpad/before_1440_hidden.png` — default size, where the clipping is
- `scratchpad/before_1920_hidden.png` — where the empty space is
- `scratchpad/before_1440_shown.png` — same as the first, real window, DPR 1

The offscreen platform plugin has no font database on this machine and renders
every glyph as `.notdef`. The renders above use the `windows` plugin with
`WA_DontShowOnScreen`, which is faithful. **The constants-column clipping is
real, not an offscreen artifact** — it reproduces on the shown window at
1440x900 and disappears at 1920x1080.

Before/after mock of the top five: `scratchpad/mock.html`.

---

## Where the current build stands against the style guide

The style guide asks for two elevation levels at once, 24-32 px between raised
elements, one primary fill per view, and colour rather than shadow for
affordance. The build honours the first two. It has drifted on the last two:
there are five accent masses visible at rest (Run, the play button, the scrub
fill, the scrub thumb, the active speed chip), and three controls that carry
neither a fill nor a visible indicator (both combo boxes have no chevron; the
plot legend has a border but nothing to click).

Three deviations from the guide are deliberate and documented, and this
proposal keeps them:

- **2 px layout gaps.** Each raised frame reserves `3 * offset + 2` px of its
  own shadow margin, so the visible gap between two cards is already 24-34 px.
  Adding a layout gap on top would double it.
- **The sunken well as a second surface.** The guide wants one base colour;
  the well `#dcdde5` exists because traces need contrast against something.
- **A checked toggle stays raised, and the fill carries the state.** A toggle
  left depressed reads as stuck.

Two undocumented deviations turn out to be regressions rather than decisions,
and are listed as fixes below: the rail and cart colours (F11) and the plot
legend (F5).

---

## Fixes

Things that are wrong: clipped, truncated, occluded, or below the contrast
floor the project set for itself.

### F1 — Re-step the ink ramp; every muted label fails AA today · S

**What.** `TEXT_2 #5c5f72` → `#4a4d5e`; `TEXT_3 #7a7d92` → `#5c5f72`; add
`INK_FAINT = #7a7d92` reserved for non-text use only (the scrollbar handle and
the row hairline).

**Why.** Measured against the two surfaces:

| token | vs surface `#e6e7ee` | vs well `#dcdde5` |
|---|---|---|
| `TEXT #2b2d42` | 10.94 | 9.97 |
| `TEXT_2 #5c5f72` | 5.11 | 4.65 |
| `TEXT_3 #7a7d92` | **3.29** | **3.00** |

`TEXT_3` carries the panel titles, the section titles, every unit, every note,
every axis tick and the transport status — all of them between 9 px and 11 px,
where WCAG 1.4.3 asks for 4.5:1. All of them fail. The project already argued
contrast for the signal palette and stepped the FTC amber marker darker for
exactly this reason, so failing on chrome text is an inconsistency rather than
a choice. The replacements measure 6.77 / 6.17 and 5.11 / 4.65, keeping three
visibly distinct ink steps while clearing AA at 9 px.

Reference: the neumorphism design guide's blunt version of the same rule —
"If gray-on-gray fails 7:1, darken the text"
(https://www.setproduct.com/blog/neumorphism-design-guide).

**Where.** `dpc/ui/theme.py`: `TEXT_2`, `TEXT_3`, new `INK_FAINT`; the
`#note`, `#unit`, `#baseline`, `#status`, `#panelTitle`, `#sectionTitle` rules
in `stylesheet()`; `QScrollBar::handle` moves to `INK_FAINT`.
`docs/dashboard-visual-design.md` table updated to match.

Note that `BORDER_INTERACTIVE` keeps `#7a7d92`. At 3.29 / 3.00 it is a
non-text boundary under 1.4.11, which asks 3:1 — it passes, but with no margin
on the well, so consider `#63667b` (4.17 on the well) while the file is open.

### F2 — The spin-box unit is truncated and the arrows are drawn twice · S

**What.** Style `QDoubleSpinBox::up-button` / `::down-button` flat (no frame,
`subcontrol-origin: border`, 14 px wide, a painted chevron), and size the
field from `fontMetrics` over the longest value-plus-suffix instead of
`setFixedWidth(118)`.

**Why.** This is the most visibly unfinished thing in the render. `m/s²` shows
as `m/s²▲` with the arrow on top of the glyph, `200.00 m/s³` loses the
exponent, `0.500 m/s` has the arrows overlapping the suffix — and because the
stylesheet sets a border and radius on `QDoubleSpinBox` but never touches the
up/down subcontrols, Windows draws its own framed arrow block *as well*, so
each field appears to have two sets of controls.

**Where.** `dpc/ui/panels/constants.py` `_spin` (drop `setFixedWidth(118)`);
`dpc/ui/theme.py` `stylesheet()` (new subcontrol rules).

### F3 — The constants column clips at the default window size · M

**What.** Three changes together: move the `LIVE` section above `PLANT`;
reserve the scrollbar width as a right margin on the scroll body so the handle
never lands on the values; add a 12 px fade at the bottom of the viewport.

**Why.** At 1440x900 the last row (`slipped … ticks`) is cut through the middle
of its glyphs, and the 8 px scrollbar handle is painted over the unit column
and across the card's rounded corner. Beyond the clipping, `LIVE` is the only
block that changes every frame and it is the first thing to go off-screen,
while `PLANT` — eight rows that never change — sits above it holding the space.
Hierarchy should follow rate of change.

A cut row with no fade reads as broken; a cut row under a fade reads as
scrollable. Combined with F4 the whole set fits 900 px and the scrollbar
mostly disappears.

**Where.** `dpc/ui/panels/constants.py` (`__init__` section order,
`_v` contentsMargins, a `paintEvent` fade on the viewport);
`dpc/ui/theme.py` `QScrollBar` rules.

### F4 — The constants column has two incompatible row rhythms · M

**What.** Take the extrusion off the spin boxes and the checkbox inside this
column — they become flat inset fields with the interactive border, which is
what the stylesheet already draws underneath. Set one 26 px row pitch. Give
read-only values and editable fields a shared right edge, with the unit in a
fixed-width column of its own.

**Why.** A read-only row is about 24 px tall; an editable row is about 46 px,
because `NeumorphicButton` / `NeumorphicSlider` reserve `3 * offset + 2` px of
shadow margin on every side. The column reads as two different lists spliced
together, the value column jumps left and right between row types, and the
extra height is what pushes the set past 900 px in the first place. It also
violates the guide's own composition rule — raised controls nested inside an
already-raised card, seven times in one column.

References: the style guide's dense-list rule ("Raised chips inside an
already-raised card nest extrusions and get noisy past three or four rows.
Dense lists carry status typographically"), and the neumorphism guide's
explicit "avoid for: data-dense dashboards where every value needs to be read
fast" (https://www.setproduct.com/blog/neumorphism-design-guide). Extrusion is
for the hero controls — Run, the transport — not for a 30-row parameter table.

**Where.** `dpc/ui/panels/constants.py` (`_spin`, `Row`, the slip checkbox);
`dpc/ui/widgets.py` gains a flat variant of `NeumorphicCheck`, or the panel
uses a plain styled `QCheckBox`.

### F5 — The plot legend sits on top of the data, and the limit lines have none · M

**What.** Replace `plot.addLegend(...)` with a legend row *under* each plot,
inside the card: 14x8 px line swatches at the trace's own pen (dash included),
10 px labels, 12 px gaps. Add the threshold entries the artboard specified —
`a_max` on the acceleration plot, `budget ±200` on torque — so the red dashes
are named. All four plots get a row; today the torque plot has no legend at
all.

**Why.** In the render the boxed legend occludes θ₂ from t≈4.6 to t=5.0 — the
end of the trace, which is the part you are watching during a live run. It is
also an opaque bordered rectangle floating over a well, a shape the language
has nowhere else.

This is not a new idea: it is what `docs/design/Main.dc.html` already
specifies. The approved artboard draws each plot card as a header row (title
left, unit right), the plot, then a `padding-top: 6px` swatch row. The Qt
build substituted pyqtgraph's default floating legend and dropped the limit
entries.

References: the artboard; Foxglove's plot-panel refit, which moved the legend
toggle and reset control into the panel toolbar, "freeing valuable space …
without overlapping the plot data"
(https://foxglove.dev/blog/refining-the-plot-panel-upgrades-to-a-core-tool);
and the EU data-visualisation guide, which prefers labels next to the elements
over a separate legend box
(https://data.europa.eu/apps/data-visualisation-guide/axes-grids-and-legends).

**Where.** `dpc/ui/panels/plots.py` (`_Plot`, `PlotPanel.__init__`), plus a
small `LegendRow(QWidget)` — either there or in `dpc/ui/widgets.py`.

### F6 — Limit lines are drawn on the frame edge, where they cannot be read · S

**What.** Set the y range from the limits rather than from the data: roughly
`setYRange(-lim * 1.15, +lim * 1.15, padding=0)` when a limit exists, and let
the data expand it if it exceeds the limit.

**Why.** On the acceleration plot the ±10 m/s² lines land exactly on the top
and bottom of the view and are half-clipped by the frame; the same on torque
at ±200 mN·m. The entire point of those lines is to show how much headroom is
left, and a line flush with the frame shows none. The trace also never gets to
visibly cross a limit, because crossing it would just re-scale the axis.

Reference: Grafana's soft min / soft max, which exists for exactly this —
bounding an axis so a flat signal is not magnified and a threshold keeps its
context (https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/time-series/).

**Where.** `dpc/ui/panels/plots.py` `set_limits`.

### F7 — The combo boxes have no drop-down indicator · S

**What.** Draw a chevron in `QComboBox::down-arrow`, `TEXT_3` weight,
9 px, 8 px from the right edge.

**Why.** `QComboBox::drop-down { border: none; width: 16px; }` removes the
native frame and nothing replaces the arrow, so "Constant acceleration" and
"Hanging at rest" look like read-only text fields. The approved artboard drew
a chevron on both. The guide's affordance rule is that a control must carry a
fill or an interactive border — these carry the border, but a picker also has
to say that it opens.

**Where.** `dpc/ui/theme.py` `stylesheet()`.

### F8 — The window title is misaligned with every card below it · S

**What.** Give `SelectorPanel` the same horizontal inset the cards use
(`NeumorphicFrame.pad + 4`).

**Why.** `SelectorPanel` sets `contentsMargins(0, 0, 0, 0)` while `card()`
insets its contents by the frame's shadow padding, so the window title starts
about 22 px to the left of the `MECHANISM` label directly beneath it. It is a
small thing that reads immediately as unconsidered, because the eye lines up a
left edge before it reads anything.

**Where.** `dpc/ui/panels/controls.py` `SelectorPanel.__init__`.

### F9 — The play button changes width when pressed · S

**What.** Fixed square size, and paint the play / pause glyphs instead of
setting them as text.

**Why.** `NeumorphicButton.sizeHint` measures the current label, and `❚❚` and
`▶` have different advance widths, so the whole transport row shifts sideways
every time playback is toggled. The artboard used drawn icons (two 4x16 bars,
a triangle) rather than text glyphs, which also renders consistently across
font fallbacks — the text glyphs are the first thing to break when IBM Plex is
absent.

**Where.** `dpc/ui/panels/controls.py` `TransportPanel`; a painted-icon
variant in `dpc/ui/widgets.py`.

### F10 — The animation's horizon lines mean nothing · S

**What.** Draw them at fixed metre intervals measured from the rail, derived
from the scale factor — or drop them.

**Why.** They are currently drawn at 25%, 50% and 75% of the *panel* height.
The 50% one is hidden underneath the rail, and the other two float at heights
that change whenever the window is resized, so they read as stray rules rather
than a reference. The artboard had three lines evenly spaced above the rail,
which is a height scale. As implemented they are decoration that the design
doc's own standard ("the only decoration on the canvas … earns its place")
does not license.

**Where.** `dpc/ui/panels/animation.py` `_draw_rail`.
*Coordinate with the in-flight rail-length work, which touches this file.*

### F11 — The rail and the cart are the faintest objects on the canvas · S

**What.** Restore the documented values: rail 3 px `#3b414c`; cart filled
`#2c2f36` with a 1.5 px `#454b57` stroke. Add a `CART_FILL` token rather than
reusing `SURFACE`.

**Why.** Measured on the well `#dcdde5`: `RAIL #b9bac4` is **1.43:1** and
`CART_EDGE #a9abb8` is **1.69:1**, with the cart filled in `SURFACE` — so the
cart, the driven mass this entire project is about, renders as an empty input
box on a hairline, and is the lowest-contrast element on screen. The
documented values measure 7.58 and 6.47, and a dark filled cart makes it the
focal object it should be, in the same way the classic Simulink cart-pendulum
animation draws the cart as a solid filled block on a light field.

`docs/dashboard-visual-design.md` already specifies these colours. The
implementation lightened them without recording why, so this is a regression
rather than a decision to preserve.

**Where.** `dpc/ui/theme.py` `RAIL`, `CART_EDGE`, new `CART_FILL`;
`dpc/ui/panels/animation.py` `_draw_mechanism`.
*Coordinate with the in-flight rail-length work.*

---

## Refinements

Not wrong, but the difference between a build and a finished instrument.

### R1 — Move the plot title into the card header · M

Each plot currently uses pyqtgraph's centred, title-case, ~15 px title while
every other panel on the page uses the left-aligned 11 px uppercase muted
`panelTitle`. The four plots therefore look like a different application from
`MECHANISM` sitting above them. The artboard specified the card header row —
title uppercase left, unit in mono right, hairline beneath — which unifies the
five cards and gives back about 28 px of plot height each.

`dpc/ui/panels/card.py` (`card()` gains a right-hand header slot),
`dpc/ui/panels/plots.py` (drop `setTitle`).

### R2 — Cut the tick density, and put the ticks in mono · S

The angles plot shows 11 x labels and 8 y labels. The EU data-visualisation
guide puts the ceiling at eight per axis, above which axes read as busy
(https://data.europa.eu/apps/data-visualisation-guide/axes-grids-and-legends).
Separately, `docs/dashboard-visual-design.md` specifies "axis ticks, units:
Mono 10 / 400, muted" and that was never applied — pyqtgraph is using the
application sans, so tick digits do not hold their column as the window
scrolls.

`axis.setTickFont(QFont(mono, 10))`, `setStyle(maxTickLevel=1, tickLength=3,
tickTextOffset=6)`, and `setTickSpacing(major=1.0, minor=0.5)` on the time
axis. `dpc/ui/panels/plots.py` `_Plot.__init__`; `SIZE_TICK` in `theme.py`.

### R3 — Give the plots a visible grid and drop the invisible frame · S

The axis pen is `BORDER #cfd0d8`, which is **1.14:1** against the well — the
axis lines are not visible at all, so the plots have no frame despite drawing
one. The grid is nominally the `GRID #cbccd6` token (1.18:1) but the plots
never use it; `showGrid(alpha=0.16)` derives a fainter line from the
foreground instead. Pick one: a horizontal-only grid at about 1.5:1
(`#b3b4c4`), and no axis line, which is what Carbon's "use gridlines sparingly
… too much visual noise makes the graph frame busy" resolves to in practice
(https://carbondesignsystem.com/data-visualization/axes-and-labels/).

`dpc/ui/theme.py` `GRID`, `BORDER`; `dpc/ui/panels/plots.py`.

### R4 — One accent mass in the transport, not four · M

At rest the transport strip carries the play fill, a full-width filled scrub
track, the thumb and the active speed chip — and Run makes five accent masses
in the view, against the design doc's own "the one primary fill in the view".
At the end of a run the indigo track is a ~1500 px bar, the largest coloured
area on the page, carrying the least information on it.

Thin the groove from 8 px to 4 px, fill it at about 45% accent, keep full
accent for the thumb alone, and make play a raised icon button with the
interactive border — the glyph already carries the state.

Reference: the restraint that gives the style its character — colour reserved
for a single accent, which is what reads as instrument-panel calm
(https://www.setproduct.com/blog/neumorphism-design-guide, and the same rule
in the house style guide's "One primary fill per view").

`dpc/ui/widgets.py` `NeumorphicSlider`; `dpc/ui/panels/controls.py`.

### R5 — Make the speed chips one segmented control · M

Three independently extruded pills of unequal width (`0.25×` wide, `1×` nearly
circular), separated by a 2 px layout gap plus each chip's own 11 px shadow
pad, so the spacing between them is not the spacing to their neighbours. The
style guide maps this pattern exactly: tab bar → inset track; active tab →
filled. One inset track, three equal-width chips measured from the widest
label, the active one filled.

`dpc/ui/panels/controls.py`, `dpc/ui/widgets.py`.

### R6 — Give the transport an honest status, and the clock a home · M

"falling behind" is the signal the whole pull-model run design exists to
report, and it renders as 11 px muted text at the far right end of a row where
nothing else lives. Make it a small pill: muted for `done`, `MODIFIED` amber
for `falling behind`, placed left of the speed chips. And move the run clock
into the Mechanism card header as the artboard had it (`t = 1.840 s · 1×`), so
the time sits beside the thing it is timing and the transport row loses two
labels.

`dpc/ui/panels/controls.py`, `dpc/ui/panels/card.py`, `dpc/ui/app.py`.

### R7 — Fill the animation's dead band · M

At 1920x1080 the mechanism occupies the lower third of a 1550x385 well: the
rail sits at exactly half height because "the links reach as far above it as
below", but in every shipped scenario except the upright ones they hang below
it, so the top half is permanently empty apart from three lines of readout
floating at (16, 24). The artboard put the rail at 75% height and drew the
upright case.

Frame vertically from the drawn extent rather than a fixed fraction — place
the rail so the swept reach is centred — move the readout into the card header
as a mono strip, and let the well take a shorter aspect so the plots gain the
height back.

`dpc/ui/panels/animation.py` `_scale`, `_draw_readout`; stretch factors in
`dpc/ui/app.py`. *Coordinate with the in-flight rail-length work.*

### R8 — Scale the cart with the view · S

The cart rect is a hard-coded `72x32` px while every other object is metres ×
`k`, so its apparent size means something different at every scale — at the
current one it is nearly as long as a link, and as the rail grows it becomes a
bus. Derive it from a cart length in metres (a plant or drive value, per the
no-numbers-outside-`params.py` rule) and draw `length * k`, clamped to a
legible minimum. The ghost cart follows.

`dpc/ui/panels/animation.py` `_draw_mechanism`, `_draw_ghost_cart`.
*Coordinate with the in-flight rail-length work.*

### R9 — Name the controller and scenario in their section headers · S

The artboard's headers read "Controller — constant acceleration" and
"Scenario — hanging at rest"; the build shows bare `CONTROLLER` and
`SCENARIO`, so the column never says whose numbers these are. Append the
current label in the muted weight after an em dash.

`dpc/ui/panels/constants.py` `_section`, `set_controller`, `set_scenario`.

### R10 — Give the constants sections a spacing rhythm · S

`GAP_SECTION` is 6 px both before and after a section header, so the header is
as close to the block above it as to its own rows, and the five sections read
as one undifferentiated run. Space before a header should be roughly three
times the space after it: 14 px before, 4 px after, plus a 1 px `INK_FAINT`
hairline above each header except the first.

`dpc/ui/panels/constants.py` `_section`; `GAP_SECTION` in `theme.py`.

### R11 — Show values in the unit you would actually type · S

`τ lag` is a 3-decimal spin box showing `0.003 s`, where a single step is a
rounding decision and the field reads as all zeros. The artboard had
`3.000 ms`. Same argument for `jerk_max`. Add a display scale to
`DRIVE_FIELDS` and convert on the way in and out.

`dpc/ui/panels/constants.py` `DRIVE_FIELDS`, `_spin`.

### R12 — Reconcile the doc with the code on radii and offsets · S

`docs/dashboard-visual-design.md` says "radius 16 on panels and 9 on controls"
in the Extrusion section and "Radius 16 on panels, 12 on controls" in Spacing
and shape; the code uses 12. The same section says "Offsets: 4 for cards, 3
for wells and controls" while `theme.py` has `SHADOW_CARD = 5`. And the doc's
border line reads "Border 1 px `#383c45`", a colour that appears nowhere in
`theme.py` — a leftover from the dark theme.

Settle on the code's values (12, 5), document the 6 px checkbox radius as a
deliberate exception for a 17 px square, and delete the stale border colour.
Nothing renders differently; the doc stops lying, which matters because it is
the file the next pass reads first.

`docs/dashboard-visual-design.md` only.

---

## Optional: structure

Not recommended for this pass. Layout B is working and the constants column
fits at 1440x900 once F3 and F4 land. Recorded so the idea is not lost.

- **Pin `LIVE` to the bottom of the constants column** as a fixed strip
  outside the scroll area, the way a telemetry viewer keeps the current values
  always visible while history scrolls. This is a stronger answer than F3's
  reordering, but it changes the column from one list into two regions.
- **Fold the transport into the Mechanism card footer.** It is a 40 px strip
  that belongs to the animation more than to the page, and merging saves one
  card and its 34 px of shadow margin. It would make the mechanism card tall
  enough to justify R7 on its own.
- **Two-column constants above 1600 px.** The column is fixed at 300 px, so at
  1920 it leaves a third of its height empty while at 1440 it overflows. A
  second column past a width threshold uses that space, at the cost of a
  responsive rule the rest of the layout does not have.

---

## References used

| Reference | What was taken |
|---|---|
| `docs/design/Main.dc.html` (approved artboards) | Legend as a swatch row under the plot with the limit entry included; plot card header with title left and unit right; combo chevron; drawn transport icons; section headers naming the controller and scenario; the mono readout in the Mechanism header |
| House neumorphic style guide (`anthropic-skills:neumorphic-ui`) | Two elevation levels at once; one primary fill per view; dense lists stay flat; tab bar = inset track with a filled active chip; shadow cannot carry affordance |
| https://www.setproduct.com/blog/neumorphism-design-guide | "If gray-on-gray fails 7:1, darken the text"; exactly one saturated accent, on interactive elements only; soft UI is the wrong tool for a dense table of values |
| https://foxglove.dev/blog/refining-the-plot-panel-upgrades-to-a-core-tool | Move plot chrome out of the plot area so it stops overlapping the data; shared tick alignment across stacked time plots |
| https://data.europa.eu/apps/data-visualisation-guide/axes-grids-and-legends | Two to eight tick labels per axis; prefer labels beside the elements over a legend box; gridlines light, thin, and never competing with the data |
| https://carbondesignsystem.com/data-visualization/axes-and-labels/ | Use gridlines sparingly; a busy frame costs interpretation |
| https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/time-series/ | Soft min / max so a threshold keeps its headroom instead of being clipped to the frame |
| https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/axisitem.html | `setTickFont`, `setStyle(maxTickLevel, tickLength, tickTextOffset)`, `setTickSpacing`, `setGrid`, `setTickPen` — the exact calls R2 and R3 need |
| https://github.com/acmerobotics/ftc-dashboard and https://acmerobotics.github.io/ftc-dashboard/features.html | Confirms the constants panel's existing model (live-editable config variables, modified markers) is faithful; no change proposed there |
| https://www.mathworks.com/help/simulink/slref/inverted-pendulum-with-animation.html | The convention this animation belongs to: a solid filled cart block on a light field, which F11 restores |

## Cost summary

| | S | M | L |
|---|---|---|---|
| Fixes | F1, F2, F6, F7, F8, F9, F10, F11 | F3, F4, F5 | — |
| Refinements | R2, R3, R8, R9, R10, R11, R12 | R1, R4, R5, R6, R7 | — |

Nothing here is an L. The whole proposal is a day of work, and F1, F2, F7, F8
together are about an hour for most of the visible gain.
