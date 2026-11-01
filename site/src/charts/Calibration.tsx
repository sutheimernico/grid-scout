import { fmtNum } from "../lib/format";
import { useInView } from "../lib/motion";

interface Props {
  raw: number;
  calibrated?: number;
  target: number;
}

/** Where the p10-p90 band's real coverage sits against the 80% it promises.
 *  Both figures are shown: the raw band is too narrow, the conformal one is closer. */
export function Calibration({ raw, calibrated, target }: Props) {
  const [ref, seen] = useInView<HTMLDivElement>(0.3);
  const pct = (v: number) => `${v * 100}%`;
  return (
    <div className={`calib ${seen ? "is-in" : ""}`} ref={ref} role="img"
      aria-label={`Band coverage: raw ${fmtNum(raw * 100, 0)} percent${calibrated != null ? `, calibrated ${fmtNum(calibrated * 100, 0)} percent` : ""}, target ${fmtNum(target * 100, 0)} percent`}>
      <div className="calib-track">
        <i className="rail" />
        <i className="fill grow-x" style={{ width: pct(calibrated ?? raw) }} />
        <i className="target" style={{ left: pct(target) }} />
        <span className="lab" style={{ left: pct(target) }}>
          <b>{fmtNum(target * 100, 0)}%</b>target
        </span>
        <i className="dot fade-in" style={{ left: pct(raw), ["--delay" as string]: "300ms" }} />
        <span className="lab below" style={{ left: pct(raw) }}>
          raw {fmtNum(raw * 100, 0)}%
        </span>
        {calibrated != null && (
          <>
            <i className="dot cal fade-in" style={{ left: pct(calibrated), ["--delay" as string]: "500ms" }} />
            <span className="lab below2" style={{ left: pct(calibrated) }}>
              calibrated {fmtNum(calibrated * 100, 0)}%
            </span>
          </>
        )}
      </div>
      <div className="calib-scale" aria-hidden="true">
        <span>0%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
