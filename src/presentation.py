"""Stable, UI-independent representation of one customer risk decision."""


def stress_velocity(features: dict | None) -> float:
    """Return a 0..1 intensity based on recent, explainable stress signals."""
    f = features or {}
    factors = [
        min(max(float(f.get("salary_delay_vs_median", 0)) / 10, 0), 1),
        min(max(-float(f.get("savings_wow_pct", 0)) / 0.30, 0), 1),
        min(max(float(f.get("autodebit_fail_28d", 0)) / 2, 0), 1),
        min(max(float(f.get("lending_app_cnt_7d", 0)) / 2, 0), 1),
        min(max(float(f.get("discretionary_drop_pct", 0)) / 0.40, 0), 1),
        min(max(float(f.get("atm_cnt_7d", 0)) / 4, 0), 1),
    ]
    return round(sum(factors) / len(factors), 4)


def recommended_action(tier: str) -> str:
    return {"Red": "Offer Payment Holiday", "Amber": "Offer EMI Split or Reminder"}.get(
        tier, "No outreach required"
    )


def risk_payload(customer_id: str, score: float, tier: str, top_reason: str, features: dict | None = None) -> dict:
    """Return the Phase-10 frontend/API contract for a risk decision."""
    return {
        "customer_id": customer_id,
        "risk_score": round(float(score), 4),
        "risk_level": {"Red": "HIGH", "Amber": "MEDIUM", "Green": "LOW"}.get(tier, str(tier).upper()),
        "stress_velocity": stress_velocity(features),
        "top_reason": top_reason or "Cash-flow pressure",
        "recommended_action": recommended_action(tier),
    }
