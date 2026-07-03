export interface Scale {
  (v: number): number;
  domain: [number, number];
  range: [number, number];
}

export function linearScale(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  const scale = ((v: number) => r0 + ((v - d0) / span) * (r1 - r0)) as Scale;
  scale.domain = domain;
  scale.range = range;
  return scale;
}

/** ~n nicely-rounded tick values covering the domain. */
export function ticks(domain: [number, number], n = 5): number[] {
  const [min, max] = domain;
  const span = max - min || 1;
  const step = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = (span / n) / step;
  const factor = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const inc = step * factor;
  const start = Math.ceil(min / inc) * inc;
  const out: number[] = [];
  for (let v = start; v <= max + 1e-9; v += inc) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

export function extent(values: (number | null)[][]): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const series of values)
    for (const v of series) {
      if (v == null) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
  if (!isFinite(min)) return [0, 1];
  return [min, max];
}

/** SVG path through non-null points; gaps in the data break the line. */
export function linePath(
  values: (number | null)[],
  x: (i: number) => number,
  y: (v: number) => number,
): string {
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

/** Closed path between an upper and lower series (confidence band). */
export function bandPath(
  upper: (number | null)[],
  lower: (number | null)[],
  x: (i: number) => number,
  y: (v: number) => number,
): string {
  const up: string[] = [];
  const down: string[] = [];
  upper.forEach((v, i) => {
    const lo = lower[i];
    if (v == null || lo == null) return;
    up.push(`${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    down.unshift(`${x(i).toFixed(1)},${y(lo).toFixed(1)}`);
  });
  if (!up.length) return "";
  return `M${up.join("L")}L${down.join("L")}Z`;
}
