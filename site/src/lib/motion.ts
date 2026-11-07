import { useEffect, useRef, useState } from "react";

export function easeOutCubic(t: number): number {
  const c = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - c, 3);
}

/** Value shown `elapsedMs` into a count-up from zero to `target`. */
export function countAt(target: number, elapsedMs: number, durationMs: number): number {
  if (durationMs <= 0) return target;
  return target * easeOutCubic(elapsedMs / durationMs);
}

/** Where a count-up starts, as a share of its target: never from zero, because a
 *  reveal fades the number in and a faded "0 %" is the first thing the eye catches. */
export const COUNT_FROM = 0.7;

/** Value `elapsedMs` into a settle from COUNT_FROM x target up to `target`. */
export function settleAt(target: number, elapsedMs: number, durationMs: number): number {
  const from = target * COUNT_FROM;
  return from + (target - from) * easeOutCubic(durationMs <= 0 ? 1 : elapsedMs / durationMs);
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : true;
}

/** True once the element has scrolled into view. Where IntersectionObserver is
 *  missing (tests, very old browsers) or motion is reduced, it is true at once,
 *  so content is never hidden behind an animation that cannot run. */
export function useInView<T extends Element>(threshold = 0.2): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const instant = prefersReducedMotion() || typeof IntersectionObserver === "undefined";
  const [seen, setSeen] = useState(instant);
  useEffect(() => {
    const el = ref.current;
    if (seen || !el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen, threshold]);
  return [ref, seen];
}

/** Settles from 70% of `target` up to it once `active`; returns the final value immediately
 *  when motion is reduced. */
export function useCountUp(target: number, active: boolean, durationMs = 900, delayMs = 0): number {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : target * COUNT_FROM));
  useEffect(() => {
    if (!active) return;
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let raf = 0;
    let start = 0;
    const tick = (now: number) => {
      if (!start) start = now + delayMs;
      const elapsed = now - start;
      setValue(settleAt(target, Math.max(0, elapsed), durationMs));
      if (elapsed < durationMs) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, active, durationMs, delayMs]);
  return value;
}
