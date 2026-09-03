"""Synthetic transaction generator — exhibits all 7 pre-delinquency signals.
Outputs: customers.csv, transactions.parquet, emi_schedule.csv, labels.csv
Run: python -m src.generator.generate --config config.yaml
"""
import argparse
import os
import numpy as np
import pandas as pd
import yaml
from datetime import datetime
from dateutil.relativedelta import relativedelta


ARCHETYPES = ["salaried_stable", "salaried_stressed", "gig_worker", "sme_owner", "pensioner"]
ARCHETYPE_P = [0.50, 0.20, 0.12, 0.08, 0.10]
GEOS = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad", "Kolkata"]
PRODUCTS = ["personal", "home", "credit_card"]


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def gen_customers(n, rng):
    arch = rng.choice(ARCHETYPES, size=n, p=ARCHETYPE_P)
    df = pd.DataFrame({
        "customer_id": [f"C{i:06d}" for i in range(n)],
        "archetype": arch,
        "age_band": rng.choice(["25-35", "35-45", "45-55", "55+"], size=n),
        "geography": rng.choice(GEOS, size=n),
        "product_type": rng.choice(PRODUCTS, size=n),
        "emi_amount": rng.integers(5000, 40000, size=n),
        "emi_day": 5,
        "income_median": rng.integers(30000, 150000, size=n),
        "salary_day": rng.integers(1, 6, size=n),
    })
    # stressed archetypes default with higher probability
    stress_p = {"salaried_stable": 0.02, "salaried_stressed": 0.30,
                "gig_worker": 0.22, "sme_owner": 0.25, "pensioner": 0.05}
    df["will_stress"] = [rng.random() < stress_p[a] for a in arch]
    return df


def gen_for_customer(cust, months, start, rng):
    cid = cust["customer_id"]
    txns, emis = [], []
    balance = float(cust["income_median"] * 1.5)
    salary_day = int(cust["salary_day"])
    stressed = bool(cust["will_stress"])
    # stress starts ~3 months in so early history is clean
    stress_start = start + relativedelta(months=months - 4) if stressed else None
    tid = 0

    def add(ts, txn_type, amount, channel, mcc, status="success"):
        nonlocal balance, tid
        if txn_type in ("salary_credit", "savings_transfer") and status == "success":
            balance += amount
        elif status == "success":
            balance -= amount
        tid += 1
        txns.append((f"T{cid}{tid:05d}", cid, pd.Timestamp(ts), txn_type,
                     round(float(amount), 2), round(float(balance), 2),
                     channel, mcc, status))

    cur = start
    for m in range(months):
        month_start = start + relativedelta(months=m)
        in_stress = stressed and month_start >= stress_start
        # 1. salary (delayed +3..10d when stressed)
        delay = int(rng.integers(3, 11)) if in_stress else int(rng.integers(-1, 2))
        payday = month_start + relativedelta(days=max(0, salary_day - 1 + delay))
        amt = cust["income_median"] * (0.90 if in_stress and rng.random() < 0.5 else 1.0)
        amt *= (0.7 if cust["archetype"] == "gig_worker" and rng.random() < 0.3 else 1.0)
        add(payday, "salary_credit", amt * rng.normal(1.0, 0.03), "NEFT", "salary")
        # 2. lending-app borrowing (stress only)
        if in_stress:
            for _ in range(int(rng.integers(2, 5))):
                d = month_start + relativedelta(days=int(rng.integers(5, 27)))
                add(d, "upi_lending_app", rng.integers(2000, 15000), "UPI", "lending_app")
                balance += 0  # cash in then spent; keep ledger simple: credit then debit pair
                add(d, "upi_p2m", rng.integers(1000, 8000), "UPI", "retail")
        # 3. utility (day 12 normal -> 25 stressed, sometimes partial/fail)
        uday = 25 if in_stress else 12 + int(rng.integers(-2, 3))
        add(month_start + relativedelta(days=min(uday, 28)), "utility_bill",
            rng.integers(800, 4000), "billpay", "utility")
        # 4. discretionary (-40% when stressed)
        disc_n = int(rng.integers(6, 12) * (0.6 if in_stress else 1.0))
        for _ in range(max(disc_n, 2)):
            d = month_start + relativedelta(days=int(rng.integers(1, 28)))
            add(d, rng.choice(["dining", "entertainment"]),
                rng.integers(200, 2500), "UPI", "discretionary")
        # 5. ATM cash hoarding (2x when stressed)
        atm_n = int(rng.integers(2, 4) * (2.0 if in_stress else 1.0))
        for _ in range(atm_n):
            d = month_start + relativedelta(days=int(rng.integers(1, 28)))
            add(d, "atm_withdrawal", rng.integers(2000, 10000), "ATM", "cash")
        # 6. auto-debit fail events (stress only)
        if in_stress and rng.random() < 0.6:
            d = month_start + relativedelta(days=int(cust["emi_day"]) - 1)
            add(d, "emi_debit", cust["emi_amount"], "autodebit", "emi", status="fail")
        # 7. EMI due
        due = month_start + relativedelta(days=int(cust["emi_day"]) - 1)
        can_pay = balance > cust["emi_amount"] * 1.05
        missed = (not can_pay) or (in_stress and rng.random() < 0.45)
        if missed:
            paid, dpd, bounce = 0.0, int(rng.integers(5, 30)), 1
            add(due, "emi_debit", cust["emi_amount"], "autodebit", "emi", status="fail")
        else:
            paid, dpd, bounce = float(cust["emi_amount"]), 0, 0
            add(due, "emi_debit", cust["emi_amount"], "autodebit", "emi")
        emis.append((cid, pd.Timestamp(due).date().isoformat(),
                     (pd.Timestamp(due) + pd.Timedelta(days=dpd)).date().isoformat() if paid == 0 else pd.Timestamp(due).date().isoformat(),
                     float(cust["emi_amount"]), paid, dpd, bounce))
    return txns, emis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    cfg = load_config(a.config)
    rng = np.random.default_rng(cfg.get("seed", 42))
    n = cfg["data"]["n_customers"]
    months = cfg["data"]["months"]
    start = pd.Timestamp(cfg["data"]["start_date"])
    raw = cfg["paths"]["raw_dir"]
    os.makedirs(raw, exist_ok=True)

    cust = gen_customers(n, rng)
    all_tx, all_emi = [], []
    for _, row in cust.iterrows():
        t, e = gen_for_customer(row, months, start, rng)
        all_tx.extend(t)
        all_emi.extend(e)
    txn_cols = ["txn_id", "customer_id", "timestamp", "txn_type", "amount",
                "balance_after", "channel", "merchant_category", "status"]
    txns = pd.DataFrame(all_tx, columns=txn_cols).sort_values("timestamp").reset_index(drop=True)
    emis = pd.DataFrame(all_emi, columns=["customer_id", "due_date", "paid_date",
                                          "amount_due", "amount_paid", "dpd_days", "bounce_flag"])
    cust.drop(columns=["will_stress"]).to_csv(f"{raw}/customers.csv", index=False)
    txns.to_parquet(f"{raw}/transactions.parquet", index=False)
    emis.to_csv(f"{raw}/emi_schedule.csv", index=False)
    # labels at scoring_date: missed EMI in next 28d
    sd = pd.Timestamp(cfg["scoring"]["scoring_date"])
    emis["due_date"] = pd.to_datetime(emis["due_date"])
    fut = emis[(emis["due_date"] > sd) & (emis["due_date"] <= sd + pd.Timedelta(days=28))]
    bad = fut[fut["dpd_days"] > 0].groupby("customer_id").size()
    labels = pd.DataFrame({"customer_id": cust["customer_id"]})
    labels["label_28d"] = labels["customer_id"].map(lambda c: 1 if c in bad.index else 0)
    labels["scoring_date"] = sd.date().isoformat()
    labels.to_csv(f"{raw}/labels.csv", index=False)
    print(f"customers={len(cust)} txns={len(txns)} emis={len(emis)} pos_rate={labels.label_28d.mean():.3f}")
    print(f"wrote {raw}/")


if __name__ == "__main__":
    main()
