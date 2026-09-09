# Dashboard visual design

*2026-09-09*

The values the Qt implementation is built from. Design canvas:
`docs/design/` (artboards) — published at
https://claude.ai/code/artifact/541df8a0-7adb-4750-b29e-958eb761fd83

## Surfaces and ink

| Role | Hex |
|---|---|
| window | `#0D1014` |
| panel / plot surface | `#12161B` |
| raised (cart body, chips) | `#171C22` |
| border | `#232A33` |
| plot grid | `#1E252E` |
| text primary | `#E6EAF0` |
| text secondary | `#8A94A3` |
| text muted | `#5A6472` |
| accent (Run, focus, scrub fill) | `#3987e5` |

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

Validated against surface `#12161B` in dark mode: lightness band, chroma floor,
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

- Scale: 4 (icon gaps, chip padding), 8 (inside panels), 12 (between panels),
  16 (window padding), 18 (constants sections).
- Radius 4 on panels, 3 on controls. Border 1 px `#232A33`.
- Constants column 300 px fixed.
- Plot trace 1.6 px; limit lines 0.9 px dashed.

## Mechanism rendering

- Rail 3 px `#2A323C`, round caps, with end stops in text-muted.
- Cart: 72x32 rounded rect, fill `#171C22`, 1.5 px stroke `#3D4754`.
- Links 7 px round cap, each in its own plot colour, so the animation and the
  angle plot name the same thing the same way.
- Joints: hollow -- window-ground fill with a 2.5 px ring in the link colour, so
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
