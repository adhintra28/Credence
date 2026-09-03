"""Production REST API (FastAPI) — serves all services/endpoints for portal + Dash + integrations.

Run: uvicorn src.serving.api:app --port 8000
Docs: http://127.0.0.1:8000/docs
"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.services import store
from src.services import risk_service, intervention_service, model_service

app = FastAPI(title="Pre-Delinquency Engine API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _clean(o):
    """Recursively replace NaN/Inf with None so JSON stays compliant."""
    import math
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k) if not isinstance(k, str) else k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    try:
        import numpy as np
        if isinstance(o, (np.floating,)):
            f = float(o)
            return f if math.isfinite(f) else None
        if isinstance(o, (np.integer,)):
            return int(o)
    except Exception:
        pass
    try:
        import pandas as pd
        if pd.isna(o):
            return None
    except Exception:
        pass
    return o


@app.get("/health")
def health():
    cfg = store.load_config()
    scores, sd = store.get_scores()
    return {"status": "ok", "scoring_date": sd, "n_scores": len(scores),
            "model": (store.get_model_bundle() or {}).get("name", None) if store.get_model_bundle() else None,
            "config_scoring_date": cfg["scoring"]["scoring_date"]}


# ---------- portfolio / customers / scores ----------
@app.get("/api/portfolio/summary")
def portfolio_summary(scoring_date: Optional[str] = None):
    return _clean(risk_service.portfolio_summary(scoring_date))


@app.get("/api/customers/search")
def customers_search(q: str = "", tier: Optional[str] = None, archetype: Optional[str] = None,
                     geography: Optional[str] = None, limit: int = 50,
                     scoring_date: Optional[str] = None):
    recs, sd = risk_service.search_customers(q, tier, archetype, geography, limit, scoring_date)
    return _clean({"scoring_date": sd, "count": len(recs), "results": recs})


@app.get("/api/customers/{customer_id}")
def customer_detail(customer_id: str, scoring_date: Optional[str] = None):
    out = risk_service.customer_360(customer_id, scoring_date)
    if not out["profile"] or out["profile"].get("customer_id") != customer_id:
        # still return score-only if customer unknown in customers.csv
        if not out["score"]:
            raise HTTPException(404, f"unknown customer {customer_id}")
    return _clean(out)


class ScoreReq(BaseModel):
    customer_id: str
    scoring_date: Optional[str] = None


@app.post("/api/scores/single")
def score_single(req: ScoreReq):
    out = risk_service.score_single_customer(req.customer_id, req.scoring_date)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@app.get("/api/customers/{customer_id}/risk-payload")
def customer_risk_payload(customer_id: str, scoring_date: Optional[str] = None):
    """Presentation-ready risk contract for the frontend integration."""
    out = risk_service.presentation_payload(customer_id, scoring_date)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return _clean(out)


@app.get("/api/scores")
def list_scores(scoring_date: Optional[str] = None, tier: Optional[str] = None, limit: int = 200):
    df, sd = store.get_scores(scoring_date)
    if tier:
        df = df[df["tier"] == tier]
    recs = df.head(limit).to_dict("records")
    for r in recs:
        r.pop("_reasons_list", None)
    return _clean({"scoring_date": sd, "count": len(recs), "total": len(df), "results": recs})


# ---------- alerts queue ----------
@app.get("/api/alerts")
def list_alerts(scoring_date: Optional[str] = None, tier: Optional[str] = None,
                view: str = "open", limit: int = 200):
    recs, sd = intervention_service.queue_with_actions(scoring_date, tier, view, limit)
    return _clean({"scoring_date": sd, "count": len(recs), "results": recs})


class AlertActionReq(BaseModel):
    action: str  # approved | snoozed | reopened
    action_by: str = "analyst"
    note: str = ""
    scoring_date: Optional[str] = None


@app.post("/api/alerts/{customer_id}/action")
def alert_action(customer_id: str, req: AlertActionReq):
    out = intervention_service.analyst_action(customer_id, req.action, req.scoring_date,
                                              req.action_by, req.note)
    if isinstance(out, dict) and "error" in out:
        raise HTTPException(400, out["error"])
    return out


# ---------- interventions ----------
@app.get("/api/interventions")
def list_interventions(customer_id: Optional[str] = None, status: Optional[str] = None, limit: int = 200):
    return _clean({"count": len(intervention_service.list_interventions(customer_id, status, limit)),
            "results": intervention_service.list_interventions(customer_id, status, limit),
            "stats": intervention_service.acceptance_stats()})


class OfferReq(BaseModel):
    customer_id: str
    offer: str
    channel: str = "app"
    action_by: str = "analyst"
    note: str = ""
    scoring_date: Optional[str] = None


@app.post("/api/interventions")
def create_offer(req: OfferReq):
    out = intervention_service.create_offer(req.customer_id, req.offer, req.channel,
                                            req.action_by, scoring_date=req.scoring_date, note=req.note)
    if isinstance(out, dict) and "error" in out:
        raise HTTPException(400, out["error"])
    return out


class RespondReq(BaseModel):
    customer_id: str
    decision: str  # accept | decline
    action_by: str = ""
    note: str = ""


@app.post("/api/interventions/respond")
def respond(req: RespondReq):
    out = intervention_service.respond_to_offer(req.customer_id, req.decision, req.action_by, req.note)
    if isinstance(out, dict) and "error" in out:
        raise HTTPException(400, out["error"])
    return out


# ---------- model ----------
@app.get("/api/model/health")
def model_health(scoring_date: Optional[str] = None):
    return _clean(model_service.model_health(scoring_date))


@app.get("/api/model/fairness")
def fairness(scoring_date: Optional[str] = None):
    return _clean(model_service.fairness_audit(scoring_date))


@app.get("/api/model/thresholds")
def thresholds():
    return store.get_thresholds()


@app.get("/api/model/acceptance")
def acceptance():
    h = model_service.model_health()
    f = model_service.fairness_audit()
    return _clean({"health": h, "fairness": f, "interventions": intervention_service.acceptance_stats(),
            "gates": {"recall_at_15_ge_70": (h.get("recall_at_15") or 0) >= 0.70,
                      "flagged_le_15": (h.get("flagged_rate") or 1) <= 0.15,
                      "fairness_80pct": all(v.get("passes_80pct_rule", True) for v in f.values() if isinstance(v, dict))}})
