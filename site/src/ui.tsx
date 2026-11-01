import type { ReactNode } from "react";
import { fmtNum } from "./lib/format";
import { useCountUp, useInView } from "./lib/motion";

/** Fades a block up once it enters the viewport. Children can hook into the
 *  `.is-in` class to start their own draw-ins. */
export function Reveal({
  children,
  className = "",
  as: Tag = "div",
  threshold = 0.12,
  id,
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "header" | "li";
  threshold?: number;
  id?: string;
}) {
  const [ref, seen] = useInView<HTMLElement>(threshold);
  return (
    <Tag ref={ref as never} id={id} className={`reveal ${seen ? "is-in" : ""} ${className}`.trim()}>
      {children}
    </Tag>
  );
}

/** A number that counts up once `active`, formatted like its final value. */
export function CountUp({
  value,
  digits = 0,
  active,
  delayMs = 0,
  format,
}: {
  value: number;
  digits?: number;
  active: boolean;
  delayMs?: number;
  format?: (v: number) => string;
}) {
  const v = useCountUp(value, active, 900, delayMs);
  return <>{format ? format(v) : fmtNum(v, digits)}</>;
}

export function Pending({ what, state }: { what: string; state: "loading" | "missing" }) {
  return (
    <p className="pending">
      {state === "loading" ? `loading ${what}…` : `${what} not produced yet — the pipeline will fill this in.`}
    </p>
  );
}
