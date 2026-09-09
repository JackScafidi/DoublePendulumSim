# Dashboard visual design

*2026-09-09*

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
| plot grid | `#cbccd6` |
| border | `#cfd0d8` |
| border interactive | `#7a7d92` |
| text primary | `#2b2d42` |
| text secondary | `#5c5f72` |
| text muted | `#7a7d92` |
| accent (Run, focus, scrub fill) | `#5057e8` |
| accent pressed | `#3b41c4` |

The accent is indigo rather than the theta-1 blue it used to be: chrome must
never wear a signal's colour, or the same hue would carry two meanings.

### Extrusion

One light source, top left. Negative offsets carry the light shadow, positive
the dark one, on every element including inset ones. Blur is twice the offset.
Outer shadows are clipped to OUTSIDE the element, as a CSS box-shadow is;
without that the blurred shape stays near-opaque across its middle and the
offset leaves a hard-edged sliver reading as a second shape. Controls also dial
the light half back to 0.5 when filled -- white against the surface is nearly
invisible, but white against indigo is a bright band.

Offsets: 4 for cards, 3 for wells and controls, radius 16 on panels and 9 on controls -- the
shadow needs curvature to wrap around.

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

### Coloured masses

A colour fill is not a flat pill. It extrudes from the same surface under the
same light -- the outer dual shadow does that -- and carries one inset layer in a
darker step of its **own** hue, gathered along the lower-right interior, so it
reads as a solid object rather than a rectangle wearing a shadow. Never a
coloured drop shadow (that floats the element above the page instead of out of
it), and never a white sheen (it reads as a different material and composites
over the label).

Applies to Run, the active speed chip, the checked slip box and the scrub thumb.
Painted by `dpc/ui/widgets.py`, since a stylesheet can express none of it.

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
| constant value | Mono | 11.5 / 400 |
| canvas readout | Mono | 15 / 400 |
| axis ticks, units | Mono | 10 / 400, muted |

## Spacing and shape

- Scale: 4 (icon gaps), 8 (inside panels), 6 (constants sections).
- Layout gaps are small -- 2 px between cards, 2 px window padding -- because
  each raised frame already reserves its own 17 px shadow margin on every side.
  The visible gap between two cards is that margin twice over, which lands in
  the 24-32 px the style asks for. Adding a layout gap on top would double it.
- Radius 16 on panels, 12 on controls. Border 1 px `#383c45`.
- Constants column 300 px fixed.
- Plot trace 1.6 px; limit lines 0.9 px dashed.

## Mechanism rendering

- Rail 3 px `#3b414c`, round caps, with end stops in text-muted.
- Cart: 72x32 rounded rect, fill `#2c2f36`, 1.5 px stroke `#454b57`.
- Links 7 px round cap, each in its own plot colour, so the animation and the
  angle plot name the same thing the same way.
- Joints: hollow -- sunken-well fill with a 2.5 px ring in the link colour, so
  crossing links stay readable. Tip is a 4 px filled dot.
- Step-count ghost: the cart outline repeated in `#c98500`, dashed, 65% opacity,
  positioned at `x_count`. With slip disabled it sits on the cart; with slip
  enabled the two part, and the counting error becomes something watched rather
  than inferred.
- Trail: the link-2 tip's recent path at 22% opacity. The only decoration on the
  canvas; it earns its place by making the phase of a swing legible in a still
  frame.

## Regenerating the canvas

`docs/design/_build_artboards.py` writes `Main.dc.html` from
`_series.json`, which is real simulator output rather than drawn curves. Edit
the artboards, re-seed with the design skill's helper, republish to the same
artifact URL.
