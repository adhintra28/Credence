"""Intervention + alert-action business logic with full audit schema (FR-6)."""
from datetime import date

import pandas as pd

from src.services import store

OFFER_CHOICES = [
    "payment-holiday (1 EMI pause, no late fee)",
    "EMI split x2",
    "tenure +3mo restructure",
]
OFFER_SHORT = {"payment-holiday": OFFER_CHOICES[0], "split": OFFER_CHOICES[1],
               "restructure": OFFER_CHOICES[2]}
CHANNELS = ["app", "sms", "call", "email", "branch"]
STATUSES = ["offered", "accepted", "declined", "approved", "snoozed", "expired"]


def list_interventions(customer_id=None, status=None, limit=200):
    df = store.get_interventions()
    if customer_id:
        df = df[df["customer_id"] == customer_id]
    if status:
        df = df[df["status"] == status]
    return df.tail(limit).iloc[::-1].to_dict("records")


def create_offer(customer_id, offer, channel="app", action_by="", tier="", reasons="",
                 model_version="", note="", scoring_date=None):
    if offer in OFFER_SHORT:
        offer = OFFER_SHORT[offer]
    if offer not in OFFER_CHOICES:
        return {"error": f"offer must be one of {OFFER_CHOICES}"}
    if channel not in CHANNELS:
        return {"error": f"channel must be one of {CHANNELS}"}
    # enrich from current score if tier missing
    if not tier or not model_version:
        scores, sd = store.get_scores(scoring_date)
        hit = scores[scores["customer_id"] == customer_id] if len(scores) else pd.DataFrame()
        if len(hit):
            tier = tier or str(hit.iloc[0].get("tier", ""))
            model_version = model_version or str(hit.iloc[0].get("model", ""))
            reasons = reasons or str(hit.iloc[0].get("reasons", ""))
        scoring_date = scoring_date or (sd if len(scores) else store.latest_scoring_date())
    row = {"customer_id": customer_id, "date": date.today().isoformat(), "tier": tier,
           "reasons": reasons, "offer": offer, "channel": channel, "status": "offered",
           "model_version": model_version, "action_by": action_by, "note": note}
    return store.append_intervention(row)


def respond_to_offer(customer_id, decision, action_by="", note=""):
    """Customer accepts/declines the most recent open offer."""
    decision = decision.lower()
    if decision not in ("accepted", "declined", "accept", "decline"):
        return {"error": "decision must be accept/decline"}
    status = "accepted" if decision.startswith("accept") else "declined"
    df = store.get_interventions()
    # append a response row linked to latest offer (append-only audit)
    open_rows = df[df["customer_id"] == customer_id]
    base = open_rows.iloc[-1].to_dict() if len(open_rows) else {
        "tier": "", "reasons": "", "offer": "", "channel": "app", "model_version": ""}
    row = {"customer_id": customer_id, "date": date.today().isoformat(), "tier": base.get("tier", ""),
           "reasons": base.get("reasons", ""), "offer": base.get("offer", ""),
           "channel": base.get("channel", "app"), "status": status,
           "model_version": base.get("model_version", ""), "action_by": action_by or customer_id,
           "note": note or f"customer {status}"}
    return store.append_intervention(row)


def queue_with_actions(scoring_date=None, tier=None, action_filter="open", limit=200):
    """Alerts queue joined with analyst actions + intervention status."""
    alerts, sd = store.get_alerts(scoring_date)
    if len(alerts) == 0:
        return [], sd
    actions = store.get_alert_actions()
    interventions = store.get_interventions()
    latest_action = {}
    if len(actions):
        for _, r in actions.sort_values("action_at").iterrows():
            latest_action[r["customer_id"]] = r.to_dict()
    latest_status = {}
    if len(interventions):
        for _, r in interventions.iterrows():
            latest_status[r["customer_id"]] = r.get("status", "")
    alerts = alerts.copy()
    alerts["analyst_action"] = alerts["customer_id"].map(lambda c: latest_action.get(c, {}).get("action", ""))
    alerts["intervention_status"] = alerts["customer_id"].map(lambda c: latest_status.get(c, ""))
    if tier:
        alerts = alerts[alerts["tier"] == tier]
    if action_filter == "open":
        alerts = alerts[~alerts["analyst_action"].isin(["approved", "snoozed"])]
    elif action_filter in ("approved", "snoozed"):
        alerts = alerts[alerts["analyst_action"] == action_filter]
    # sort Red first then expected_loss desc
    if "expected_loss" in alerts.columns:
        alerts = alerts.sort_values(["tier", "expected_loss"], ascending=[True, False])
    return alerts.head(limit).to_dict("records"), sd


def analyst_action(customer_id, action, scoring_date=None, action_by="", note=""):
    if action not in ("approved", "snoozed", "reopened"):
        return {"error": "action must be approved/snoozed/reopened"}
    sd = scoring_date or store.latest_scoring_date()
    rec = store.record_alert_action(customer_id, sd, action, action_by, note)
    # mirror into intervention log for audit completeness (FR-6.4)
    if action in ("approved", "snoozed"):
        scores, _ = store.get_scores(sd)
        hit = scores[scores["customer_id"] == customer_id] if len(scores) else None
        tier = str(hit.iloc[0]["tier"]) if hit is not None and len(hit) else ""
        reasons = str(hit.iloc[0]["reasons"]) if hit is not None and len(hit) else ""
        model_v = str(hit.iloc[0]["model"]) if hit is not None and len(hit) else ""
        store.append_intervention({
            "customer_id": customer_id, "date": date.today().isoformat(), "tier": tier,
            "reasons": reasons, "offer": "", "channel": "console",
            "status": action, "model_version": model_v, "action_by": action_by, "note": note})
    return rec


def acceptance_stats():
    df = store.get_interventions()
    if len(df) == 0:
        return {"n": 0}
    by_status = df["status"].value_counts().to_dict()
    offered = int(((df["status"] == "offered") | (df["status"] == "approved")).sum())
    accepted = int((df["status"] == "accepted").sum())
    declined = int((df["status"] == "declined").sum())
    return {"n": int(len(df)), "by_status": {k: int(v) for k, v in by_status.items()},
            "accept_rate": round(accepted / max(offered + accepted + declined, 1), 4),
            "by_offer": df.groupby("offer")["status"].value_counts().to_dict() if "offer" in df else {}}
