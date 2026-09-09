# Dashboard visual design

*2026-09-09*

The values the Qt implementation is built from. Design canvas:
`docs/design/` (artboards) — published at
https://claude.ai/code/artifact/541df8a0-7adb-4750-b29e-958eb761fd83

## Surfaces and ink

Neumorphic dark. The defining rule is that a raised element is the **same
colour** as what it sits on -- depth comes only from the shadow -- so there is
one surface value, not a ladder of them. The only second surface is the sunken
well that data lives in, which is darker because traces need the contrast.

| Role | Hex |
|---|---|
| surface (page, cards, chips) | `#2c2f36` |
| sunken well (plots, inputs, animation) | `#24272d` |
| shadow light (up-left) | `#3d424d` |
| shadow dark (down-right) | `#191b20` |
| plot grid | `#31353d` |
| border | `#383c45` |
| border interactive | `#6a7080` |
| text primary | `#E6EAF0` |
| text secondary | `#9aa2b1` |
| text muted | `#6f7686` |
| accent (Run, focus, scrub fill) | `#5057e8` |
| accent pressed | `#3b41c4` |

The accent is indigo rather than the theta-1 blue it used to be: chrome must
never wear a signal's colour, or the same hue would carry two meanings.

### Extrusion

One light source, top left. Negative offsets carry the light shadow, positive
the dark one, on every element including inset ones. Blur is twice the offset.
Offsets: 5 for cards, 3 for wells, radius 16 on panels and 9 on controls -- the
shadow needs curvature to wrap around.

**Qt has no `box-shadow`.** Stylesheets parse and discard it (verified: the same
frame renders pixel-identical with and without), and `QGraphicsDropShadowEffect`
casts exactly one shadow. So `dpc/ui/neumorphic.py` rasterises the pair itself
and caches them per size. A raised frame reserves `3 * offset + 2` px of margin
for its own shadow, because Qt clips painting to the widget rectangle and an
unreserved shadow is cropped into a bevel.

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
| theta1 | `#3987e5` | solid |
| theta2 | `#d95926` | solid |
| cart x, true | `#199e70` | solid |
| cart x, step count | `#c98500` | dashed |
| acceleration, commanded | `#d55181` | solid |
| acceleration, delivered | `#008300` | solid |
| motor torque | `#9085e9` | solid |
| limits: a_max, tau budget | `#d03b3b` | dashed, 0.9 px |

Validated against the sunken well `#24272d` in dark mode: lightness band, chroma floor,
adjacent-pair colour-blind separation, normal-vision floor and contrast all
pass. The tightest adjacent pair is aqua/yellow at CVD dE 8.4, which is inside
the band that requires secondary encoding -- those two are the cart traces, and
the step count is dashed, so identity never rests on colour alone.

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
| panel title | Sans | 10 / 600 / 0.09em, uppercase |
| section heading | Sans | 9.5 / 600 / 0.11em, uppercase |
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
- Radius 16 on panels, 9 on controls. Border 1 px `#383c45`.
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
