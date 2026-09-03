"""Daily batch scoring -> risk_scores.csv with tiers + SHAP top-3 reasons.
Run: python -m src.scoring.score --scoring-date 2024-11-01 --config config.yaml
"""
import argparse
import json
import os
import pickle
import numpy as np
import pandas as pd
import yaml

from src.features.build import build_snapshot, FEATURE_COLS
from src.presentation import recommended_action, stress_velocity

REASON_TEMPLATES = {
    "salary_delay_vs_median": "Salary {v:.0f} days late vs usual",
    "days_since_salary": "{v:.0f} days since salary",
    "savings_wow_pct": "Savings {v:.0%} WoW",
    "lending_app_cnt_7d": "{v:.0f} short-term borrowing txns this week",
    "lending_app_cnt_28d": "{v:.0f} borrowing txns in 28d",
    "utility_delay_days": "Utility {v:.0f}d late in cycle",
    "autodebit_fail_28d": "{v:.0f} failed auto-debit(s)",
    "discretionary_drop_pct": "Discretionary spend down {v:.0%}",
    "atm_cnt_7d": "{v:.0f} ATM withdrawals this week",
    "drawdown_streak": "Savings drawdown streak",
    "min_balance_14d": "Low 14d balance Rs.{v:.0f}",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scoring-date", required=True)
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    txns = pd.read_parquet(f"{cfg['paths']['raw_dir']}/transactions.parquet")
    txns["timestamp"] = pd.to_datetime(txns["timestamp"])
    emis = pd.read_csv(f"{cfg['paths']['raw_dir']}/emi_schedule.csv")
    cust = pd.read_csv(f"{cfg['paths']['raw_dir']}/customers.csv")
    feats = build_snapshot(txns, emis, cust, a.scoring_date)
    with open(f"{cfg['paths']['models_dir']}/production.pkl", "rb") as f:
        bundle = pickle.load(f)
    clf, iso = bundle["model"], bundle.get("calibrator")
    X = feats[FEATURE_COLS].fillna(0).values
    raw = clf.predict_proba(X)[:, 1]
    scores = iso.predict(np.clip(raw, 0, 1)) if iso is not None else raw
    # SHAP top-3 per customer (guarded)
    top3 = [[] for _ in range(len(feats))]
    try:
        import shap
        ev = shap.TreeExplainer(clf).shap_values(pd.DataFrame(X, columns=FEATURE_COLS).iloc[:500])
        vals = (ev[1] if isinstance(ev, list) else ev)
        order = np.argsort(-np.abs(vals), axis=1)[:, :3]
        for i in range(min(len(feats), 500)):
            reasons = []
            for j in order[i]:
                fn = FEATURE_COLS[j]
                tpl = REASON_TEMPLATES.get(fn, fn + "={v:.2f}")
                try:
                    reasons.append(tpl.format(v=float(feats.iloc[i][fn])))
                except Exception:
                    reasons.append(fn)
            top3[i] = reasons
    except Exception as e:
        print(f"shap per-row skipped: {e}")
    red, amber = cfg["tiers"]["red_min"], cfg["tiers"]["amber_min"]
    tiers = np.where(scores >= red, "Red", np.where(scores >= amber, "Amber", "Green"))
    velocities = [stress_velocity(row) for row in feats[FEATURE_COLS].to_dict("records")]
    primary_reasons = [items[0] if items else "Cash-flow pressure" for items in top3]
    out = pd.DataFrame({"customer_id": feats["customer_id"], "scoring_date": a.scoring_date,
                        "score": np.round(scores, 4), "tier": tiers,
                        "reasons": [json.dumps(r) for r in top3],
                        "top_reason": primary_reasons, "stress_velocity": velocities,
                        "recommended_action": [recommended_action(tier) for tier in tiers],
                        "model": bundle.get("name", "?")})
    od = cfg["paths"]["outputs_dir"]
    os.makedirs(od, exist_ok=True)
    out.to_csv(f"{od}/risk_scores_{a.scoring_date}.csv", index=False)
    print(out["tier"].value_counts().to_string())
    print(f"wrote {od}/risk_scores_{a.scoring_date}.csv")


if __name__ == "__main__":
    main()
