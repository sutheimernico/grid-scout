"""Split-conformal calibration of the p10-p90 band (conformalised quantile
regression, Romano et al. 2019), applied walk-forward.

The raw LightGBM quantiles undercover (the band is too narrow). Each test block
is widened by the (1-alpha) quantile of the conformity scores of every block
that came before it, so the correction only ever uses outcomes that were already
known — the same no-lookahead rule as the point forecast. The first blocks have
no history to calibrate on and are reported separately, not folded into the
calibrated coverage.
"""

import numpy as np
import pandas as pd


def conformalize(
    frame: pd.DataFrame,
    alpha: float = 0.2,
    block_days: int = 7,
    min_calib_blocks: int = 4,
) -> pd.DataFrame:
    """Add `q_low_cal` / `q_high_cal` (NaN until enough history exists).

    frame: needs `target`, `pred_q10`, `pred_q90`, `local_day`; chronological blocks of
    `block_days` local days mirror the walk-forward refit cadence.
    """
    out = frame.copy()
    out["q_low_cal"] = np.nan
    out["q_high_cal"] = np.nan
    days = sorted(out["local_day"].unique())
    blocks = [days[i : i + block_days] for i in range(0, len(days), block_days)]
    scores = np.empty(0)
    for i, block in enumerate(blocks):
        rows = out["local_day"].isin(block)
        sub = out.loc[rows]
        if i >= min_calib_blocks and len(scores):
            n = len(scores)
            level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
            q = float(np.quantile(scores, level))
            out.loc[rows, "q_low_cal"] = sub["pred_q10"] - q
            out.loc[rows, "q_high_cal"] = sub["pred_q90"] + q
        scores = np.concatenate(
            [scores, np.maximum(sub["pred_q10"] - sub["target"], sub["target"] - sub["pred_q90"])]
        )
    return out
