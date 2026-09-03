"""Business logic for risk: portfolio, customer 360, single-customer scoring."""
import json

import numpy as np
import pandas as pd

from src.features.build import FEATURE_COLS, build_snapshot
from src.presentation import risk_payload
from src.services import store


def portfolio_summary(scoring_date=None):
    scores, sd = store.get_scores(scoring_date)
    alerts, _ = store.get_alerts(sd)
    cust = store.get_customers()
    if len(scores) == 0:
        return {"scoring_date": sd, "n": 0, "mix": {}, "alerts": 0, "red": 0, "amber": 0}
    mix = scores["tier"].value_counts().to_dict()
    flagged = float((scores["tier"] != "Green").mean()) if len(scores) else 0.0
    out = {
        "scoring_date": sd,
        "n": int(len(scores)),
        "mix": {k: int(v) for k, v in mix.items()},
        "flagged_rate": round(flagged, 4),
        "alerts": int(len(alerts)),
        "red": int((alerts["tier"] == "Red").sum()) if len(alerts) and "tier" in alerts else 0,
        "amber": int((alerts["tier"] == "Amber").sum()) if len(alerts) and "tier" in alerts else 0,
        "avg_score": round(float(scores["score"].mean()), 4) if "score" in scores else 0.0,
    }
    if len(alerts) and "expected_loss" in alerts.columns:
        out["expected_loss_total"] = round(float(alerts["expected_loss"].sum()), 2)
        out["expected_loss_avg"] = round(float(alerts["expected_loss"].mean()), 2)
    # lift vs base default rate (labels file at scoring date)
    labels = store.get_labels()
    if len(labels) and "label_28d" in labels.columns:
        out["base_default_rate"] = round(float(labels["label_28d"].mean()), 4)
        if len(scores):
            red_ids = set(scores[scores["tier"] == "Red"]["customer_id"]) if "tier" in scores else set()
            lab = labels.set_index("customer_id")["label_28d"].to_dict() if "customer_id" in labels else {}
            red_hits = [lab.get(c, 0) for c in red_ids]
            out["red_precision_proxy"] = round(float(np.mean(red_hits)), 4) if red_hits else 0.0
    _ = cust  # reserved for future joins
    return out


def search_customers(q="", tier=None, archetype=None, geography=None, limit=50, scoring_date=None):
    scores, sd = store.get_scores(scoring_date)
    cust = store.get_customers()
    if len(scores) == 0:
        return [], sd
    df = scores.merge(cust, on="customer_id", how="left") if len(cust) else scores
    if q:
        ql = q.lower()
        df = df[df["customer_id"].str.lower().str.contains(ql, na=False)]
    if tier:
        df = df[df["tier"] == tier]
    if archetype and "archetype" in df.columns:
        df = df[df["archetype"] == archetype]
    if geography and "geography" in df.columns:
        df = df[df["geography"] == geography]
    df = df.head(limit)
    recs = df.to_dict("records")
    for r in recs:
        r.pop("_reasons_list", None)
    return recs, sd


def customer_360(customer_id, scoring_date=None):
    scores, sd = store.get_scores(scoring_date)
    cust = store.get_customers()
    txns = store.get_transactions()
    emis = store.get_emi()
    feats, _ = store.get_features(sd)
    alerts, _ = store.get_alerts(sd)
    interventions = store.get_interventions()
    actions = store.get_alert_actions()

    srow = scores[scores["customer_id"] == customer_id]
    score = srow.iloc[0].to_dict() if len(srow) else {}
    if "_reasons_list" in score:
        score["reasons_list"] = score.pop("_reasons_list")
    elif isinstance(score.get("reasons"), str):
        try:
            score["reasons_list"] = json.loads(score["reasons"])
        except Exception:
            score["reasons_list"] = []

    crow = cust[cust["customer_id"] == customer_id]
    profile = crow.iloc[0].to_dict() if len(crow) else {"customer_id": customer_id}
    # feature row
    frow = feats[feats["customer_id"] == customer_id] if len(feats) else pd.DataFrame()
    features = frow.iloc[0].to_dict() if len(frow) else {}
    # timeline: balance curve (last 120d), salary markers, utility strip, discretionary
    timeline = {}
    if len(txns):
        g = txns[txns["customer_id"] == customer_id].copy()
        if len(g):
            g = g.sort_values("timestamp")
            cutoff = pd.Timestamp(sd) - pd.Timedelta(days=120)
            g120 = g[g["timestamp"] >= cutoff]
            timeline["balance"] = [
                {"t": ts.isoformat(), "balance": float(b)}
                for ts, b in zip(pd.to_datetime(g120["timestamp"]), g120["balance_after"])
            ][-200:]
            sal = g120[g120["txn_type"] == "salary_credit"]
            timeline["salary_markers"] = [
                {"t": pd.Timestamp(ts).isoformat(), "amount": float(a)}
                for ts, a in zip(sal["timestamp"], sal["amount"])
            ]
            util = g120[g120["txn_type"] == "utility_bill"]
            timeline["utility"] = [
                {"t": pd.Timestamp(ts).isoformat(), "amount": float(a), "day": int(pd.Timestamp(ts).day)}
                for ts, a in zip(util["timestamp"], util["amount"])
            ]
            disc = g120[g120["txn_type"].isin(["dining", "entertainment"])]
            timeline["discretionary_weekly"] = len(disc)
            timeline["discretionary_amt_28d"] = float(
                disc[disc["timestamp"] > pd.Timestamp(sd) - pd.Timedelta(days=28)]["amount"].sum()
            ) if len(disc) else 0.0
    # emi table
    emi_rows = []
    if len(emis):
        e = emis[emis["customer_id"] == customer_id].copy()
        if len(e):
            e = e.sort_values("due_date").tail(12)
            emi_rows = e.astype(str).to_dict("records")
    # interventions + actions for this customer
    hist = interventions[interventions["customer_id"] == customer_id].to_dict("records") if len(interventions) else []
    acts = actions[actions["customer_id"] == customer_id].to_dict("records") if len(actions) else []
    my_alerts = alerts[alerts["customer_id"] == customer_id].to_dict("records") if len(alerts) and "customer_id" in alerts.columns else []
    return {
        "scoring_date": sd, "profile": profile, "score": score,
        "features": features, "timeline": timeline, "emi": emi_rows,
        "interventions": hist, "alert_actions": acts, "alerts": my_alerts,
    }


def score_single_customer(customer_id, scoring_date=None):
    """Point-in-time scoring for one customer (used by API + portal)."""
    bundle = store.get_model_bundle()
    if bundle is None:
        return {"error": "no model trained — run pipeline first"}
    sd = scoring_date or store.latest_scoring_date()
    txns = store.get_transactions()
    emis = store.get_emi()
    cust = store.get_customers()
    if len(cust) == 0 or customer_id not in set(cust["customer_id"]):
        return {"error": f"unknown customer {customer_id}"}
    feats = build_snapshot(txns, emis, cust[cust["customer_id"] == customer_id], sd)
    X = feats[FEATURE_COLS].fillna(0).values
    clf, iso = bundle["model"], bundle.get("calibrator")
    raw = float(clf.predict_proba(X)[0, 1])
    score = float(iso.predict([np.clip(raw, 0, 1)])[0]) if iso is not None else raw
    th = store.get_thresholds()
    tier = "Red" if score >= th.get("red_min", 0.6) else ("Amber" if score >= th.get("amber_min", 0.3) else "Green")
    return {"customer_id": customer_id, "scoring_date": sd, "score": round(score, 4),
            "tier": tier, "model": bundle.get("name")}


def presentation_payload(customer_id, scoring_date=None):
    """Return the compact Phase-10 payload used by non-Python frontends."""
    scores, sd = store.get_scores(scoring_date)
    row = scores[scores["customer_id"] == customer_id] if len(scores) else pd.DataFrame()
    feats, _ = store.get_features(sd)
    feat = feats[feats["customer_id"] == customer_id] if len(feats) else pd.DataFrame()
    if len(row):
        item = row.iloc[0]
        reasons = item.get("_reasons_list", [])
        return risk_payload(customer_id, item["score"], item["tier"],
                            item.get("top_reason") or (reasons[0] if reasons else ""),
                            feat.iloc[0].to_dict() if len(feat) else {})
    scored = score_single_customer(customer_id, sd)
    if "error" in scored:
        return scored
    return risk_payload(customer_id, scored["score"], scored["tier"], "Cash-flow pressure",
                        feat.iloc[0].to_dict() if len(feat) else {})
