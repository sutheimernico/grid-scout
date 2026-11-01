# Dashboard redesign, November 2026

## Concept: the clearing sheet

The German day-ahead market clears 24 hourly prices at 12:00 for the next day.
The dashboard is built around that unit: a delivery day is 24 columns, and the
forecast is a line that has to be drawn *before* the prices are known. The page
reads like a trading desk's sheet for the day, not like an analytics template:

- The hero is the forecast curve against the cleared prices for the last three
  delivery days of the backtest, with the p10-p90 band, the zero line and the
  negative-price hours (the market's most characteristic event) tinted red.
- The evidence is a ruler, not a tile row: one horizontal scale in EUR/MWh with
  every model on it, so "19.65 vs 30.59" is a distance you can see.
- The proof is a ledger: one row per delivery day, forecast recorded before the
  auction, scored afterwards. Its empty state is a diagram of the protocol, not a
  placeholder.

No mock data anywhere. Everything is the exported JSON. The one place where the
dashboard shows a *process* rather than a measurement (the clearing timeline in
the empty ledger) is labelled "protocol", not "data".

## Type

- Display and numerals: Archivo (variable, width axis), set expanded and heavy
  for the H1 and the large figures, like transit and substation signage.
  Self-hosted via `@fontsource-variable/archivo`.
- Text and chart labels: IBM Plex Sans 400/500/600, self-hosted via
  `@fontsource/ibm-plex-sans`. A plain grotesque built for dense technical
  reading; tabular figures for every number.
- Why a dependency: the previous page used the system font stack, which is the
  default every dashboard has. Two small woff2 files (latin subset only is
  fetched by the browser) are the cheapest way to get a real voice and the width
  axis. No monospace for labels.

## Palette

Light, cool paper, one deep green-black ink, one signal colour.

| Token | Value | Use |
|---|---|---|
| `--paper` | `#f1f3f2` | page |
| `--plate` | `#ffffff` | chart plates, table rows |
| `--ink` | `#11201e` | text, actual prices |
| `--ink-2` | `#41504d` | secondary text (7.9:1 on paper) |
| `--ink-3` | `#5c6b68` | captions (5.0:1) |
| `--volt` | `#00806b` | the model, forecast, "good" |
| `--volt-wash` | `#00806b` at 14% | confidence band |
| `--neg` | `#c8321f` | negative prices, losses, failures |
| `--gate` | `#e0a100` | gate closure 12:00 marker |
| `--naive` | `#7b8784` | baselines (dashed) |

The ledger section is the single inverse band (ink ground) because it is the
evidence the page rests on. No gradients, no glow, no glass.

## Layout

- 1440: 12-column grid, content width 1240. Hero text left (7 cols), a short
  deck right (4 cols), then the hero chart over the full width. Evidence is a
  5/7 split (ruler left, interval-calibration and hour-by-hour strip right).
  Sections alternate between full-width and split so no two neighbours have the
  same shape.
- 820: single column, charts full width, splits stack.
- 390: single column with a 16 px gutter. The hero chart keeps its aspect and
  switches to a 2-day window with larger labels; tables become label/value rows;
  the sensitivity matrix keeps its 2 x 3 shape.

## Motion (150-400 ms, transform and opacity, plus chart draw-ins)

- Sections fade up 12 px once, when they enter the viewport.
- Hero: the band wipes in left to right, then the forecast line draws, then the
  actual line. About 1.1 s in total, once.
- Ruler: bars grow from zero with a 70 ms stagger, values count up.
- Hover and keyboard: a crosshair with a readout row above the chart (never a
  floating box over the data).
- `prefers-reduced-motion`: everything is static, count-ups show the final value.
- Content is never hidden if JavaScript or IntersectionObserver is missing.

## Structure of the code

Pure modules with vitest tests: number/date formatting, hero window selection
(local Europe/Berlin delivery days, DST aware), scoreboard shaping, ledger
shaping, sensitivity matrix, easing. Components stay thin.
