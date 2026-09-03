"""Point-in-time feature builder. No future leakage: only txns with timestamp <= scoring_date.
Run: python -m src.features.build --scoring-date 2024-11-01 --config config.yaml
"""
import argparse
import os
import numpy as np
import pandas as pd
import yaml


FEATURE_COLS = [
    "days_since_salary", "salary_delay_vs_median", "salary_cv_3m", "missing_salary_flag",
    "savings_wow_pct", "avg_balance_28d", "balance_slope_28d", "drawdown_streak",
    "min_balance_14d", "utility_pay_day", "utility_delay_days", "utility_partial_ratio",
    "autodebit_fail_28d", "lending_app_cnt_7d", "lending_app_cnt_28d", "lending_app_amt_ratio",
    "discretionary_ratio_28d", "discretionary_drop_pct", "gambling_flag", "night_txn_ratio",
    "atm_cnt_7d", "atm_amt_avg", "cash_to_spend_ratio",
    "emi_to_income", "tenure_months",
]


def build_snapshot(txns, emis, customers, scoring_date):
    sd = pd.Timestamp(scoring_date)
    past = txns[txns["timestamp"] <= sd].copy()
    # group once for speed (was per-customer full-frame filter)
    groups = dict(tuple(past.groupby("customer_id"))) if len(past) else {}
    cust_idx = customers.set_index("customer_id")
    rows = []
    for cid in cust_idx.index:
        cust = cust_idx.loc[cid]
        g = groups.get(cid)
        if g is None or len(g) == 0:
            rows.append((cid, *([0.0] * len(FEATURE_COLS))))
            continue
        g = g.sort_values("timestamp")
        w7 = g[g["timestamp"] > sd - pd.Timedelta(days=7)]
        w14 = g[g["timestamp"] > sd - pd.Timedelta(days=14)]
        w28 = g[g["timestamp"] > sd - pd.Timedelta(days=28)]
        prev28 = g[(g["timestamp"] <= sd - pd.Timedelta(days=28)) & (g["timestamp"] > sd - pd.Timedelta(days=56))]
        sal = g[g["txn_type"] == "salary_credit"].sort_values("timestamp")
        days_since = (sd - sal["timestamp"].max()).days if len(sal) else 999
        sal_day = sal["timestamp"].dt.day.median() if len(sal) else float(cust.get("salary_day", 2))
        salary_delay = max(0.0, float(days_since - 31))
        salary_cv = float(sal.tail(3)["amount"].std() / (sal.tail(3)["amount"].mean() + 1)) if len(sal) >= 2 else 0.0
        missing_sal = 1.0 if days_since > 35 else 0.0
        bal_now = float(g.iloc[-1]["balance_after"])
        bal_7ago = float(g[g["timestamp"] <= sd - pd.Timedelta(days=7)]["balance_after"].iloc[-1]) if len(g[g["timestamp"] <= sd - pd.Timedelta(days=7)]) else bal_now
        wow = (bal_now - bal_7ago) / (abs(bal_7ago) + 1)
        avg28 = float(w28["balance_after"].mean()) if len(w28) else bal_now
        slope = float(np.polyfit(np.arange(len(w28)), w28["balance_after"].values, 1)[0]) if len(w28) > 2 else 0.0
        drawdown = 1.0 if wow < -0.15 else 0.0
        min14 = float(w14["balance_after"].min()) if len(w14) else bal_now
        util = w28[w28["txn_type"] == "utility_bill"]
        uday = float(util["timestamp"].dt.day.median()) if len(util) else 12.0
        udelay = max(0.0, uday - 12.0)
        fails = float(((g["txn_type"] == "emi_debit") & (g["status"] == "fail") & (g["timestamp"] > sd - pd.Timedelta(days=28))).sum())
        lend7 = int(((w7["txn_type"] == "upi_lending_app")).sum())
        lend28 = int(((w28["txn_type"] == "upi_lending_app")).sum())
        lend_amt = float(w28[w28["txn_type"] == "upi_lending_app"]["amount"].sum())
        spend28 = float(w28["amount"].sum()) + 1
        disc = float(w28[w28["txn_type"].isin(["dining", "entertainment"])]["amount"].sum())
        disc_prev = float(prev28[prev28["txn_type"].isin(["dining", "entertainment"])]["amount"].sum()) + 1
        disc_drop = (disc_prev - disc) / disc_prev
        gamb = 1.0 if (w28["txn_type"] == "gambling").any() else 0.0
        night = float(((g["timestamp"].dt.hour >= 22) | (g["timestamp"].dt.hour <= 4)).mean()) if len(g) else 0.0
        atm7 = int((w7["txn_type"] == "atm_withdrawal").sum())
        atm_avg = float(w28[w28["txn_type"] == "atm_withdrawal"]["amount"].mean()) if (w28["txn_type"] == "atm_withdrawal").any() else 0.0
        cash_ratio = float(w28[w28["txn_type"] == "atm_withdrawal"]["amount"].sum()) / spend28
        emi_inc = float(cust["emi_amount"]) / (float(cust["income_median"]) + 1)
        tenure = max(0, (sd.year - 2024) * 12 + sd.month - 1)
        rows.append((cid, days_since, salary_delay, salary_cv, missing_sal, wow, avg28,
                     slope, drawdown, min14, uday, udelay, 0.0, fails, lend7, lend28,
                     lend_amt / spend28, disc / spend28, disc_drop, gamb, night,
                     atm7, atm_avg, cash_ratio, emi_inc, float(tenure)))
    cols = ["customer_id"] + FEATURE_COLS
    feats = pd.DataFrame(rows, columns=cols)
    # attach context for slicing (not all used as model inputs)
    ctx = customers[["customer_id", "archetype", "geography", "product_type"]].copy()
    return feats.merge(ctx, on="customer_id", how="left")


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
    out = cfg["paths"]["processed_dir"]
    os.makedirs(out, exist_ok=True)
    feats.to_parquet(f"{out}/features_{a.scoring_date}.parquet", index=False)
    print(f"features shape={feats.shape} -> {out}/features_{a.scoring_date}.parquet")


if __name__ == "__main__":
    main()
