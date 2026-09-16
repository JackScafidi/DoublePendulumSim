# Dashboard visual design

*2026-09-09*, reconciled with the code *2026-09-16*

The values the Qt implementation is built from. Design canvas:
`docs/design/` (artboards) — published at
https://claude.ai/code/artifact/541df8a0-7adb-4750-b29e-958eb761fd83

## Surfaces and ink

Neumorphic light. The defining rule is that a raised element is the **same
colour** as what it sits on -- depth comes only from the shadow -- so there is
one surface value, not a ladder of them. The only second surface is the sunken
well that data lives in.

The base is deliberately not pure white: a white ground leaves no room for the
light half of the shadow, and the extrusion collapses into a single drop shadow.

| Role | Hex |
|---|---|
| surface (page, cards, chips) | `#e6e7ee` |
| sunken well (plots, inputs, animation) | `#dcdde5` |
| shadow light (up-left) | `#ffffff` |
| shadow dark (down-right) | `#c3c4ca` |
| plot grid | `#b3b4c4` |
| border (on the page surface only) | `#cfd0d8` |
| border interactive | `#63667b` |
| text primary | `#2b2d42` |
| text secondary | `#4a4d5e` |
| text muted | `#5c5f72` |
| ink faint, NON-TEXT only | `#7a7d92` |
| accent (Run, focus, scrub thumb) | `#5057e8` |
| accent pressed | `#3b41c4` |

The accent is indigo rather than the theta-1 blue it used to be: chrome must
never wear a signal's colour, or the same hue would carry two meanings.

The ink ramp is stepped so that every step clears WCAG 1.4.3 at the 9-11 px
sizes the chrome actually uses -- 10.94/9.97, 6.77/6.17 and 5.11/4.65 against
the surface and the well. The old muted step measured 3.29/3.00 and carried
every panel title, unit, note, axis tick and status label on the page. It
survives as `ink faint`, which passes 1.4.11 as a boundary and fails 1.4.3 as
a label, so it draws the scrollbar handle and the section hairline and never
carries a word.

`border` is a hairline for the page surface. It is never an axis or a plot
frame: at 1.14:1 on the well it cannot be seen, which is why the plots have no
frame at all and a visible grid instead.

### Extrusion

One light source, top left. Negative offsets carry the light shadow, positive
the dark one, on every element including inset ones. Blur is twice the offset.
Outer shadows are clipped to OUTSIDE the element, as a CSS box-shadow is;
without that the blurred shape stays near-opaque across its middle and the
offset leaves a hard-edged sliver reading as a second shape. Controls also dial
the light half back to 0.5 when filled -- white against the surface is nearly
invisible, but white against indigo is a bright band.

Offsets, all four of them: **5** for cards -- the transport bar is a card, so it
is 5 as well -- **4** for the one primary fill in the view, and **3** for wells
and for every secondary control (the icon buttons, the constants column's header
buttons, the checkbox, the segmented track). Run extrudes a step further than
the icon button beside it because it is the button that starts the run; that is
the whole of the split, and there is no other 4 on the page.

Radius 16 on panels, 12 on the well pressed into one, 12 on controls -- the
shadow needs curvature to wrap around, and concentric corners at equal radii
read as one corner drawn twice. The 17 px checkbox is the one real exception at
6, because 12 on a 17 px square is a circle.

An inner shade is built at one less than the outer offset, floored at 2, and
every shadow pixmap carries `3 * offset + 2` px of transparent border with its
shape at that inset -- so a pixmap is drawn that far before the shape it belongs
to, and a shade built at a different offset from the body is drawn at a
different inset. Drawing both at the body's inset composites the shade two to
three pixels down and right of the fill it is shading.

**Qt has no `box-shadow`.** Stylesheets parse and discard it (verified: the same
frame renders pixel-identical with and without), and `QGraphicsDropShadowEffect`
casts exactly one shadow. So `dpc/ui/neumorphic.py` rasterises the pair itself
and caches them per size. A raised frame reserves `3 * offset + 2` px of margin
for its own shadow, because Qt clips painting to the widget rectangle and an
unreserved shadow is cropped into a bevel.

### Constants panel

Laid out after FTC Dashboard's configuration panel, which solves the same
problem: a long list of live-editable values where what you most need to see is
which ones you have moved.

- **Modified marker** -- an amber `#9a6700` bullet in its own leading column,
  drawn transparent when unmodified rather than omitted, so the name column
  never shifts. FTC uses `#fbbf24`; that sits near 1.7:1 on this surface, so it
  is stepped darker.
- **Inline baseline** -- the default value, dimmed and parenthesised, beside
  anything edited.
- **Filter** -- collapses the panel to only the modified rows.
- **Copy** -- FTC's Save writes back to the robot; here `params.py` is the
  source of truth, so the equivalent hands you a snippet to paste into it.
- **Reset** -- re-emits every modified value at its baseline, through the
  ordinary edit path, so a reset reaches the source exactly as a keystroke does.

Read-only rows carry no baseline and can never be marked: plant values and
scenario initial conditions are facts, not settings.

The column is a dense list, so **nothing in it extrudes**. Raised spin boxes
and a raised checkbox reserve `3 * offset + 2` px of shadow margin a side,
which made an editable row twice the height of a read-only one and the column
read as two lists spliced together -- and it nested raised controls inside an
already-raised card seven times over. The fields are flat instead: sunken
fill, interactive border, and a painted chevron pair in a right gutter of
14 px. One 26 px row pitch for both kinds of row.

Every row shares one value grid: a field of at least 88 px with that 14 px
gutter reserved inside it, then the unit in a 40 px column of its own. The
width is a minimum rather than a fixed size, because the live and plant blocks
carry composite `a / b` values that are wider than a single number, and a
fixed field clips them from the left. Live values are padded to a constant
width so the column does not shuffle sideways at 50 Hz.

Sections are spaced 14 px before a header and 4 px after it, with a 1 px ink
faint hairline above every header but the first. Equal gaps read as one
undifferentiated run of rows. Each header names what it is describing --
"CONTROLLER -- Constant acceleration" -- so the column always says whose
numbers these are. Fields are shown and typed in the unit a person would
actually use: `3.000 ms`, not `0.003 s`.

The scroll bar is not an overlay: the sheet gives it a width and a background
but no position, so Qt lays it out beside the viewport and its 8 px come out of
the viewport itself. Nothing reserves that width a second time -- the body's
right margin is 8 px of panel padding and no more, and the note wrapping width
subtracts the bar exactly once. Reserved twice, the body is 2 px wider than the
viewport it sits in with horizontal scrolling off, and the right edge of every
row clips. The foot of the viewport carries a 12 px fade: a row cut through the
middle of its glyphs reads as broken; the same row under a fade reads as
scrollable.

### Coloured masses

A colour fill is not a flat pill. It extrudes from the same surface under the
same light -- the outer dual shadow does that -- and carries one inset layer in a
darker step of its **own** hue, gathered along the lower-right interior, so it
reads as a solid object rather than a rectangle wearing a shadow. Never a
coloured drop shadow (that floats the element above the page instead of out of
it), and never a white sheen (it reads as a different material and composites
over the label).

Applies to Run, the active speed chip and the scrub thumb. Painted by
`dpc/ui/widgets.py`, since a stylesheet can express none of it.

### Press

Raised to inset over 170 ms, `OutCubic`, with the label travelling one pixel
with the surface it sits on. The two shadows cross-fade rather than swap, so a
press reads as travel. A checked toggle returns to raised -- the fill carries
the state, and a toggle left depressed reads as stuck.

### Affordance

A neumorphic shadow sits near 1.2:1 and cannot satisfy WCAG 1.4.11, so it never
signals "clickable". Every control carries either the accent fill (Run, the
active speed, a checked box, the scrub handle) or the interactive border
(spin boxes, combo boxes, transport buttons). There is no third case.

Qt draws no indicator for a subcontrol a stylesheet has not styled, and draws
its own framed native one for a subcontrol the sheet leaves alone. Both the
spin steppers and the combo arrow are therefore zero-sized in the sheet and
the chevron is painted in `widgets.py` -- a stylesheet can only put a glyph in
a subcontrol from a file on disk, and a dashboard that needs an icon cache to
look finished is worse than one that draws seven pixels itself.

## Signals

Taken from the validated dark categorical palette and assigned in fixed slot
order, so a signal's colour is a property of the signal and never of its rank in
a plot.

| Signal | Hex | Style |
|---|---|---|
| theta1 | `#2a78d6` | solid |
| theta2 | `#b4531f` | solid |
| cart x, true | `#12795a` | solid |
| cart x, step count | `#a35400` | dashed |
| acceleration, commanded | `#b03a67` | solid |
| acceleration, delivered | `#008300` | solid |
| motor torque | `#4a3aa7` | solid |
| limits: a_max, tau budget | `#a82b3f` | dashed, 0.9 px |

Re-stepped for the light ground. Clearing 3:1 against a near-white surface
forces every hue darker than its dark-theme step, and darkening naively
collapses aqua and amber into neighbouring browns -- so those two were pushed
apart in hue until the pair separated.

Validated against the sunken well `#dcdde5`. Every per-slot check passes for all
seven: lightness band, chroma floor and contrast. Separation is checked on the
pairs that actually co-occur in a plot, which is what the pairlist is for:

| Pair | CVD dE | Normal-vision dE |
|---|---|---|
| theta1 / theta2 | 26.3 | 29.3 |
| cart true / step count | 9.0 | 19.1 |
| commanded / delivered | 8.6 | 31.9 |

Motor torque is a lone series and needs no pair. The two combinations the
whole-list check flags -- theta2 against cart-true, and step-count against
commanded -- are colours that never appear in the same plot.

The cart pair sits in the band that requires secondary encoding, and the step
count is dashed, so identity never rests on colour alone.

The limit colour is a reserved *status* value, not a ninth series. It never
labels data, only a threshold, which is why it may repeat across two plots
without implying a relationship.

## Type

Two faces: IBM Plex Sans for language, IBM Plex Mono for every number. Numbers
are monospaced so digits hold their column while values change -- a readout that
jitters its width during a run is unreadable.

Families are resolved at startup against what is actually installed --
Qt stylesheets do not honour a comma-separated fallback list, and an absent
family silently resolves to Tahoma, losing the monospaced digits the readouts
depend on. Preference order is IBM Plex, then the platform's own faces.

| Use | Face | Size / weight / tracking |
|---|---|---|
| window title | Sans | 13 / 600 |
| panel title | Sans | 11 / 500 / 0.06em, uppercase, muted |
| section heading | Sans | 11 / 500 / 0.06em, uppercase, muted |
| constant label | Sans | 11 / 400 |
| constant value | Mono | 11 / 400 |
| card header slot (clock, readout, unit) | Mono | 10 / 400, muted |
| axis ticks, horizon labels, legend labels, notes | Mono / Sans | 10 / 400, muted |

## Spacing and shape

- Scale: 4 (icon gaps), 8 (inside panels).
- Layout gaps are small -- 2 px between cards, 2 px window padding -- because
  each raised frame already reserves its own 17 px shadow margin on every side.
  The visible gap between two cards is that margin twice over, which lands in
  the 24-32 px the style asks for. Adding a layout gap on top would double it.
- Radius 16 on panels, 12 on the well inside a panel, 12 on controls, 6 on
  the checkbox.
- Constants column 300 px fixed; 26 px row pitch; 14 px before a section
  header and 4 px after it.
- Anything that sits outside a card but has to line up with what is inside one
  -- the window title above the mechanism -- takes the card's own content
  inset, `3 * 5 + 2 + 4`. The eye lines up a left edge before it reads a word.
- Plot trace 1.6 px; limit lines 0.9 px dashed.

## Cards and plots

One card shape carries everything: a raised surface with a header row -- name
left, a mono slot right -- its content pressed into a well, and an optional
footer. Two elevations and no more. The well is not a third level; it is the
same card, pushed in where the data goes.

The header's right slot is why the plots can drop pyqtgraph's centred,
title-case title, which was the one thing on the page that looked like a
different application, and why the run clock and the mechanism readout have
somewhere to live besides floating over the canvas.

Plot chrome is the card's, not pyqtgraph's:

- No axis line and no frame, a horizontal grid only, in the grid colour at
  full strength. `tickAlpha` is pinned, or pyqtgraph derives a per-level alpha
  and fades the line back out.
- Ticks in Mono 10, `maxTickLevel=1`, and 1.0 s major spacing on the time
  axis: two to eight labels an axis, and time is the one axis whose spacing is
  known in advance.
- The key is a swatch row in the card footer, under the plot, drawn with the
  trace's own pen including its dash -- so the key and the data are one mark.
  A boxed legend floating over the well is a shape this language has nowhere
  else, and in a live run it sits exactly on the end of the trace. Every
  threshold gets an entry naming its value: `rail ±250 mm`, `a_max ±10`.
- The y range is framed from the threshold, not from the data: ±1.15 × the
  limit, widened only if the data outgrows it. A limit line flush with the top
  of the view shows no headroom, which is the only thing it is there to show.

## Transport

One accent mass, not four. The scrub groove is 4 px at 45% accent and the
thumb keeps the full fill; play is a raised icon button with the interactive
border, its glyph painted rather than set as text, at a fixed square size --
`❚❚` and `▶` have different advance widths, so a text glyph moved the whole
row sideways on every toggle. The three speeds are one segmented control:
inset track, equal chips measured from the widest label, the active one
filled. Status is a pill -- muted for `done`, modified amber for
`falling behind`, the one status the whole pull-model run design exists to
report.

Everything in the row but the slider holds a fixed width, because the slider is
the only thing that stretches and every pixel a neighbour gains or loses comes
straight out of the scrub groove. That is why the play glyph is painted into a
fixed square, and why the status pill is measured once from the longest status
it can ever carry and keeps that width while empty, painting nothing. A pill
sized to its own text shortens the groove by its own width the moment a run
falls behind, and the thumb jumps by that much under the finger dragging it.

## Mechanism rendering

- Rail 3 px `#3b414c`, round caps, drawn at exactly ±`rail_len / 2`. The end
  stops are vertical caps 12 px either side of the rail, in the rail's own
  pen: they are the same piece of hardware, and they are where the cart
  actually stops. The view never grows to follow the cart, because the plant
  will not let it out of frame.
- Cart: the real `cart_len` in metres times the scale factor, aspect 0.42,
  floored at 22 px where it would stop being legible; fill `#2c2f36`, 1.5 px
  stroke `#454b57`. Everything on the canvas is metres times one scale factor;
  a cart at a fixed pixel size means something different at every scale.
- Links 7 px round cap, each in its own plot colour, so the animation and the
  angle plot name the same thing the same way.
- Joints: hollow -- sunken-well fill with a 2.5 px ring in the link colour, so
  crossing links stay readable. Tip is a 4 px filled dot.
- Step-count ghost: the cart outline repeated in `#a35400`, dashed, 65% opacity,
  positioned at `x_count`. With slip disabled it sits on the cart; with slip
  enabled the two part, and the counting error becomes something watched rather
  than inferred.
- Trail: the link-2 tip's recent path at 29% opacity, 90 samples. The only
  decoration on the canvas; it earns its place by making the phase of a swing
  legible in a still frame. A faint trace disappears against a light ground
  long before it does against a dark one, hence the heavier alpha.
- Horizon lines: a height scale in metres measured from the rail, at a round
  step off a 1-2-5 ladder chosen so consecutive lines clear 34 px, drawn the
  full width of the well with the height labelled in the left gutter. They
  used to sit at 25%, 50% and 75% of the panel height, where the middle one
  hid under the rail and the other two moved on every resize. The rail is the
  zero line and is not repeated.
- Framing: horizontally the rail plus a 0.06 m margin, fixed. Vertically the
  swept extent, expand-only, plus 0.02 m -- a frame that shrinks back as the
  pendulum passes through the bottom of its swing rescales the whole drawing
  twice a period. The drawn mechanism is roughly square while the well is
  about five times wider than tall, so the vertical fit is what sets the scale
  of everything on the canvas. That is also why the well cannot be filled
  edge to edge without distorting the drawing, and why the mechanism card
  carries more of the left column's height than its single plot-sized area
  would suggest.

## Regenerating the canvas

`docs/design/_build_artboards.py` writes `Main.dc.html` from
`_series.json`, which is real simulator output rather than drawn curves. Edit
the artboards, re-seed with the design skill's helper, republish to the same
artifact URL.
