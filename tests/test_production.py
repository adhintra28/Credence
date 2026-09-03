"""Production tests: services, policy rules, REST API, portal."""
import json


def test_store_loads():
    from src.services import store
    cust = store.get_customers()
    assert len(cust) > 0 and "emi_amount" in cust.columns
    scores, sd = store.get_scores()
    assert len(scores) > 0 and set(["customer_id", "score", "tier"]).issubset(scores.columns)


def test_portfolio_and_360():
    from src.services import risk_service, store
    s = risk_service.portfolio_summary()
    assert s["n"] > 0 and "mix" in s and s["flagged_rate"] <= 1.0
    scores, _ = store.get_scores()
    cid = scores.iloc[0]["customer_id"]
    ctx = risk_service.customer_360(cid)
    assert ctx["profile"]["customer_id"] == cid
    assert "timeline" in ctx and "emi" in ctx


def test_single_score():
    from src.services import risk_service, store
    scores, _ = store.get_scores()
    cid = scores.iloc[0]["customer_id"]
    out = risk_service.score_single_customer(cid)
    assert out["tier"] in ("Green", "Amber", "Red")
    assert 0 <= out["score"] <= 1


def test_policy_rules():
    from src.policy.engine import count_signal_groups
    n, groups = count_signal_groups({"salary_delay_vs_median": 7, "savings_wow_pct": -0.2,
                                     "lending_app_cnt_7d": 2, "utility_delay_days": 0,
                                     "autodebit_fail_28d": 0, "discretionary_drop_pct": 0.0,
                                     "gambling_flag": 0, "atm_cnt_7d": 0, "cash_to_spend_ratio": 0.0,
                                     "days_since_salary": 40, "missing_salary_flag": 1,
                                     "drawdown_streak": 1, "balance_slope_28d": -5,
                                     "lending_app_cnt_28d": 3})
    assert n >= 3 and "income" in groups and "borrowing" in groups
    n2, _ = count_signal_groups({"salary_delay_vs_median": 0, "savings_wow_pct": 0.01,
                                 "lending_app_cnt_7d": 0, "utility_delay_days": 0,
                                 "autodebit_fail_28d": 0, "discretionary_drop_pct": 0.0,
                                 "gambling_flag": 0, "atm_cnt_7d": 0, "cash_to_spend_ratio": 0.0,
                                 "days_since_salary": 5, "missing_salary_flag": 0,
                                 "drawdown_streak": 0, "balance_slope_28d": 10,
                                 "lending_app_cnt_28d": 0})
    assert n2 < 2  # single/zero-source -> suppressed


def test_intervention_flow():
    from src.services import intervention_service, store
    scores, _ = store.get_scores()
    cid = scores.iloc[0]["customer_id"]
    off = intervention_service.create_offer(cid, "EMI split x2", "app", "pytest")
    assert off["status"] == "offered"
    resp = intervention_service.respond_to_offer(cid, "accept", "pytest")
    assert resp["status"] == "accepted"
    act = intervention_service.analyst_action(cid, "snoozed", None, "pytest", "test")
    assert act["action"] == "snoozed"
    stats = intervention_service.acceptance_stats()
    assert stats["n"] > 0


def test_model_services():
    from src.services import model_service
    h = model_service.model_health()
    assert h["n"] > 0 and "flagged_rate" in h
    f = model_service.fairness_audit()
    assert "geography" in f or "archetype" in f


def test_api_endpoints():
    from fastapi.testclient import TestClient
    from src.serving.api import app
    from src.services import store
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/portfolio/summary").status_code == 200
    scores, _ = store.get_scores()
    cid = scores.iloc[0]["customer_id"]
    assert c.get(f"/api/customers/{cid}").status_code == 200
    assert c.get("/api/alerts?limit=5").status_code == 200
    assert c.get("/api/model/health").status_code == 200
    assert c.get("/api/model/fairness").status_code == 200
    r = c.post("/api/scores/single", json={"customer_id": cid})
    assert r.status_code == 200 and r.json()["tier"] in ("Green", "Amber", "Red")
    r = c.post("/api/interventions", json={"customer_id": cid, "offer": "EMI split x2"})
    assert r.status_code == 200


def test_portal_routes():
    from frontend.app import app
    c = app.test_client()
    assert c.get("/").status_code == 200
    # login as bank
    r = c.post("/", data={"email": "bank@bank.com", "password": "bank123"}, follow_redirects=True)
    assert r.status_code == 200 and b"Portfolio" in r.data
    assert c.get("/bank/queue").status_code == 200
    assert c.get("/bank/model").status_code == 200
    assert c.get("/bank/interventions").status_code == 200
