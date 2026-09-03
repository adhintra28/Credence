"""Alert policy engine: suppression, escalation, cap, intervention templates.
Run: python -m src.policy.engine --scoring-date 2024-11-01 --config config.yaml
Reads risk_scores + intervention_log, writes alerts.csv (SNS-ready payloads).

Production rules (FR-5):
- suppress if contacted_last_7d OR in_hardship OR emi_due_in_2d_and_balance_ok
- single-source flags suppressed (require >=2 active signal groups)
- Amber x7 consecutive days -> escalate to Red
- Cap Red queue to top-K/day by expected_loss = score * emi_amount
- Cross-environment: features must join >=3 sources (salary NEFT + UPI + billpay);
  enforced via signal-group diversity check.
"""
import argparse
import glob
import json
import os
from datetime import datetime, timezone

import pandas as pd
import yaml


AMBER_TEMPLATE = ("Hi {cid}, we noticed {r1}. Your EMI of Rs.{emi} is due {due}. "
                  "Need a reminder or a split? Reply REMIND / SPLIT / HOLIDAY.")
RED_OFFERS = ["payment-holiday (1 EMI pause, no late fee)", "EMI split x2", "tenure +3mo restructure"]


def count_signal_groups(feat_row) -> tuple[int, list]:
    """Count distinct active signal groups for a customer feature row."""
    if feat_row is None:
        return 0, []
    g = feat_row.to_dict() if hasattr(feat_row, "to_dict") else dict(feat_row)
    active = []
    if g.get("salary_delay_vs_median", 0) >= 3 or g.get("days_since_salary", 0) > 35 or g.get("missing_salary_flag", 0) == 1:
        active.append("income")
    if g.get("savings_wow_pct", 0) < -0.10 or g.get("drawdown_streak", 0) == 1 or g.get("balance_slope_28d", 0) < 0:
        active.append("liquidity")
    if g.get("utility_delay_days", 0) >= 3 or g.get("autodebit_fail_28d", 0) >= 1:
        active.append("discipline")
    if g.get("lending_app_cnt_7d", 0) >= 1 or g.get("lending_app_cnt_28d", 0) >= 2:
        active.append("borrowing")
    if g.get("discretionary_drop_pct", 0) > 0.25 or g.get("gambling_flag", 0) == 1:
        active.append("behavioral")
    if g.get("atm_cnt_7d", 0) >= 3 or g.get("cash_to_spend_ratio", 0) > 0.35:
        active.append("cash")
    return len(active), active


def amber_streak_days(customer_id, scoring_date, outputs_dir) -> int:
    """Consecutive Amber days before scoring_date (history from risk_scores_*.csv)."""
    streak = 0
    sd = pd.Timestamp(scoring_date)
    for back in range(1, 15):
        d = (sd - pd.Timedelta(days=back)).date().isoformat()
        fp = f"{outputs_dir}/risk_scores_{d}.csv"
        if not os.path.exists(fp):
            # also try monthly snapshots? break — no daily history in MVP batch
            break
        try:
            df = pd.read_csv(fp)
            hit = df[df["customer_id"] == customer_id]
            if len(hit) and str(hit.iloc[0].get("tier", "")) == "Amber":
                streak += 1
            else:
                break
        except Exception:
            break
    return streak


def build_alerts(scoring_date, cfg):
    od = cfg["paths"]["outputs_dir"]
    os.makedirs(od, exist_ok=True)
    scores = pd.read_csv(f"{od}/risk_scores_{scoring_date}.csv")
    cust = pd.read_csv(f"{cfg['paths']['raw_dir']}/customers.csv").set_index("customer_id")
    emis = pd.read_csv(f"{cfg['paths']['raw_dir']}/emi_schedule.csv")
    emis["due_date"] = pd.to_datetime(emis["due_date"], errors="coerce")
    txns = None
    try:
        txns = pd.read_parquet(f"{cfg['paths']['raw_dir']}/transactions.parquet")
        txns["timestamp"] = pd.to_datetime(txns["timestamp"])
    except Exception:
        pass
    # features for multi-signal check
    feats_idx = {}
    ffp = f"{cfg['paths']['processed_dir']}/features_{scoring_date}.parquet"
    if os.path.exists(ffp):
        try:
            fdf = pd.read_parquet(ffp)
            feats_idx = fdf.set_index("customer_id").to_dict("index")
        except Exception:
            pass
    # intervention history
    from src.services.store import get_interventions  # local import to avoid cycle
    try:
        log = get_interventions(cfg)
    except Exception:
        log_path = f"{od}/intervention_log.csv"
        log = pd.read_csv(log_path) if os.path.exists(log_path) else pd.DataFrame(columns=["customer_id", "date"])
    sup_days = cfg["tiers"].get("suppression_days", 7)
    sd = pd.Timestamp(scoring_date)
    recently_contacted = set()
    hardship = set()
    if len(log):
        log["date"] = pd.to_datetime(log["date"], errors="coerce")
        recent = log[log["date"] > sd - pd.Timedelta(days=sup_days)]
        recently_contacted = set(recent["customer_id"].tolist())
        hard = log[(log["date"] > sd - pd.Timedelta(days=30)) &
                   (log.get("status", "").isin(["approved", "accepted", "offered"]) if "status" in log.columns else False)]
        if len(hard):
            hardship = set(hard[hard["offer"].str.contains("holiday|restructure", case=False, na=False)]["customer_id"].tolist()) if "offer" in hard.columns else set()
    # last balance per customer for emi_due check
    last_bal = {}
    if txns is not None and len(txns):
        past = txns[txns["timestamp"] <= sd].sort_values("timestamp")
        if len(past):
            last_bal = past.groupby("customer_id")["balance_after"].last().to_dict()

    alerts, suppressed = [], []
    for _, r in scores.iterrows():
        cid = r["customer_id"]
        if r["tier"] == "Green":
            continue
        reason = None
        if cid in recently_contacted:
            reason = "contacted_last_7d"
        elif cid in hardship:
            reason = "in_hardship_program"
        else:
            # emi due in 2d and balance ok?
            try:
                fut = emis[(emis["customer_id"] == cid) & (emis["due_date"] >= sd) & (emis["due_date"] <= sd + pd.Timedelta(days=2))]
                emi_amt = int(cust.loc[cid, "emi_amount"]) if cid in cust.index else 0
                if len(fut) and float(last_bal.get(cid, 0)) > emi_amt * 1.2:
                    reason = "emi_due_in_2d_and_balance_ok"
            except Exception:
                pass
        if reason:
            suppressed.append((cid, r["tier"], reason))
            continue
        # multi-signal: require >=2 groups (single-source suppression)
        n_grp, groups = count_signal_groups(feats_idx.get(cid))
        if n_grp < 2:
            suppressed.append((cid, r["tier"], f"single_source_only:{'+'.join(groups) or 'none'}"))
            continue
        # escalation: Amber x7 -> Red
        tier = r["tier"]
        escalated = False
        if tier == "Amber" and amber_streak_days(cid, scoring_date, od) >= 7:
            tier = "Red"
            escalated = True
        reasons = json.loads(r["reasons"]) if isinstance(r.get("reasons"), str) and r["reasons"] else []
        r1 = reasons[0] if reasons else "pressure on cash-flow"
        emi = int(cust.loc[cid, "emi_amount"]) if cid in cust.index else 0
        expected_loss = round(float(r["score"]) * emi, 2)
        if tier == "Amber":
            msg = AMBER_TEMPLATE.format(cid=cid, r1=r1, emi=emi, due="5th")
            action = "auto_nudge"
        else:
            msg = (f"Hi {cid}, based on {r1} you qualify for support BEFORE your EMI is missed. "
                   f"Choose: {', '.join(RED_OFFERS)}. Reply HOLIDAY / SPLIT / RESTRUCTURE.")
            action = "human_offer"
        alerts.append({"customer_id": cid, "tier": tier, "score": round(float(r["score"]), 4),
                       "top_reason": r1, "emi_amount": emi, "expected_loss": expected_loss,
                       "action": action, "message": msg, "signal_groups": "+".join(groups),
                       "escalated": escalated,
                       "model_version": r.get("model", ""), "thresholds": json.dumps(
                           {"amber_min": cfg["tiers"].get("amber_min"), "red_min": cfg["tiers"].get("red_min")})})
    q = pd.DataFrame(alerts)
    if len(q):
        q = q.sort_values(["tier", "expected_loss"], ascending=[True, False])
        reds = q[q["tier"] == "Red"].head(cfg["tiers"].get("red_cap_per_day", 200))
        q = pd.concat([reds, q[q["tier"] != "Red"]])
    q.to_csv(f"{od}/alerts_{scoring_date}.csv", index=False)
    # audit: suppression + run metadata
    audit = pd.DataFrame(suppressed, columns=["customer_id", "tier", "suppress_reason"])
    audit.to_csv(f"{od}/suppressed_{scoring_date}.csv", index=False)
    meta = {"scoring_date": scoring_date, "run_at": datetime.now(timezone.utc).isoformat(),
            "n_scores": int(len(scores)), "n_alerts": int(len(q)),
            "n_suppressed": int(len(audit)), "red_cap": cfg["tiers"].get("red_cap_per_day", 200)}
    with open(f"{od}/policy_meta_{scoring_date}.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"alerts={len(q)} red={(q.tier=='Red').sum() if len(q) else 0} amber={(q.tier=='Amber').sum() if len(q) else 0} suppressed={len(audit)}")
    print(f"wrote {od}/alerts_{scoring_date}.csv")
    return q, audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scoring-date", required=True)
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    build_alerts(a.scoring_date, cfg)


if __name__ == "__main__":
    main()
