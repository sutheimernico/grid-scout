import { type RefObject, useEffect, useState } from "react";

const DEFAULT_WIDTH = 960;
const MIN_WIDTH = 300;

/** Pixel width of a chart's container, so the SVG viewBox matches the screen 1:1.
 *  With a fixed 960-unit viewBox the 11 px axis text shrank to ~4 px on a phone;
 *  drawing at the real width keeps text at its real size. Falls back to 960 where
 *  ResizeObserver does not exist (jsdom, very old browsers). */
export function useChartWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => setWidth(Math.max(MIN_WIDTH, Math.min(DEFAULT_WIDTH, Math.round(el.clientWidth))));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
