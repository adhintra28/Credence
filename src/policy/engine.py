"""Alert policy engine: suppression, escalation, cap, intervention templates.
Run: python -m src.policy.engine --scoring-date 2024-11-01 --config config.yaml
Reads risk_scores + intervention_log, writes alerts.csv (SNS-ready payloads).
"""
import argparse
import json
import os
import pandas as pd
import yaml


AMBER_TEMPLATE = ("Hi {cid}, we noticed {r1}. Your EMI of Rs.{emi} is due {due}. "
                  "Need a reminder or a split? Reply REMIND / SPLIT / HOLIDAY.")
RED_OFFERS = ["payment-holiday (1 EMI pause, no late fee)", "EMI split x2", "tenure +3mo restructure"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scoring-date", required=True)
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    od = cfg["paths"]["outputs_dir"]
    os.makedirs(od, exist_ok=True)
    scores = pd.read_csv(f"{od}/risk_scores_{a.scoring_date}.csv")
    cust = pd.read_csv(f"{cfg['paths']['raw_dir']}/customers.csv").set_index("customer_id")
    emis = pd.read_csv(f"{cfg['paths']['raw_dir']}/emi_schedule.csv")
    log_path = f"{od}/intervention_log.csv"
    log = pd.read_csv(log_path) if os.path.exists(log_path) else pd.DataFrame(columns=["customer_id", "date"])
    recently_contacted = set(log[pd.to_datetime(log["date"], errors="coerce") > pd.Timestamp(a.scoring_date) - pd.Timedelta(days=cfg["tiers"]["suppression_days"])]["customer_id"]) if len(log) else set()

    alerts = []
    for _, r in scores.iterrows():
        if r["tier"] == "Green" or r["customer_id"] in recently_contacted:
            continue
        reasons = json.loads(r["reasons"]) if r["reasons"] else []
        r1 = reasons[0] if reasons else "pressure on cash-flow"
        emi = int(cust.loc[r["customer_id"], "emi_amount"]) if r["customer_id"] in cust.index else 0
        expected_loss = round(float(r["score"]) * emi, 2)
        if r["tier"] == "Amber":
            msg = AMBER_TEMPLATE.format(cid=r["customer_id"], r1=r1, emi=emi, due="5th")
            action = "auto_nudge"
        else:
            msg = (f"Hi {r['customer_id']}, based on {r1} you qualify for support BEFORE your EMI is missed. "
                   f"Choose: {', '.join(RED_OFFERS)}. Reply HOLIDAY / SPLIT / RESTRUCTURE.")
            action = "human_offer"
        alerts.append((r["customer_id"], r["tier"], round(float(r["score"]), 4), r1,
                       emi, expected_loss, action, msg))
    q = pd.DataFrame(alerts, columns=["customer_id", "tier", "score", "top_reason",
                                      "emi_amount", "expected_loss", "action", "message"])
    if len(q):
        q = q.sort_values(["tier", "expected_loss"], ascending=[True, False])
        reds = q[q["tier"] == "Red"].head(cfg["tiers"]["red_cap_per_day"])
        q = pd.concat([reds, q[q["tier"] != "Red"]])
    q.to_csv(f"{od}/alerts_{a.scoring_date}.csv", index=False)
    # SNS payload preview (AWS SNS wiring is commented in aws/sns_notify.py until backend configured)
    print(f"alerts={len(q)} red={(q.tier=='Red').sum() if len(q) else 0} amber={(q.tier=='Amber').sum() if len(q) else 0}")
    print(f"wrote {od}/alerts_{a.scoring_date}.csv")


if __name__ == "__main__":
    main()
