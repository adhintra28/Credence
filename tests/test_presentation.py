from src.presentation import risk_payload, stress_velocity


def test_high_risk_payload_matches_frontend_contract():
    payload = risk_payload(
        "CUST001", 0.82, "Red", "Salary Delay",
        {"savings_wow_pct": -0.15, "lending_app_cnt_7d": 2},
    )
    assert payload == {
        "customer_id": "CUST001",
        "risk_score": 0.82,
        "risk_level": "HIGH",
        "stress_velocity": 0.25,
        "top_reason": "Salary Delay",
        "recommended_action": "Offer Payment Holiday",
    }


def test_stress_velocity_is_bounded():
    assert stress_velocity({"salary_delay_vs_median": 1000}) == round(1 / 6, 4)
