# Design brief: the clearing sheet

- **Concept.** The page is the trading desk's sheet for one delivery day: 24 hourly prices that are cleared once at 12:00. A forecast is a line that has to exist before the cleared price does, so every chart separates "forecast" from "cleared" and the ledger section shows the gate at 12:00 as its own event.
- **Taken from.** The day-ahead clearing-result view of EPEX SPOT (<https://www.epexspot.com/en/market-results>) and the ENTSO-E Transparency Platform (<https://transparency.entsoe.eu/>): hourly rows, a hard zero line, tabular figures, no decoration. Energy-Charts (<https://www.energy-charts.info/>) for the negative-price hours as a first-class event (tinted red here). FT and Bloomberg data graphics for the rule that the annotation sits on the chart and the headline states the finding, not the topic.
- **Type.** Archivo (variable, wide and heavy) for headlines and figures, like substation signage; IBM Plex Sans with tabular figures for text and chart labels. No monospace for labels.
- **Colour.** Cool paper (`#f1f3f2`), one green-black ink, one signal green for the model, red only for negative prices and losses, amber only for the 12:00 gate. One inverse band (the ledger) because it is the evidence the page rests on.
- **Motion 1: the forecast is drawn before the price.** In the hero the p10 to p90 band wipes in, then the forecast line draws, then the cleared price (about 1.1 s, once).
- **Motion 2: numbers settle.** The headline figure (pre-auction skill) and the ruler values count up while the ruler bars grow from zero, 80 ms apart.
- **Motion 3: the clearing protocol builds in order.** Each step's rail draws, then its dot lands (before 12:00, gate, delivery, scored; 220 ms steps). All of it is transform, opacity or clip-path, and switches off under `prefers-reduced-motion`.
- **Limits.** The reference pages were not scraped for assets; they informed structure and tone only. No mock data anywhere.
