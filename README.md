# Pre-Delinquency Engine — production

Batch + services build per `IMPLEMENTATION_PLAN.md` + `PRD.md`. AWS fully stubbed/commented until backend configured.

## Quickstart
```powershell
pip install -r requirements.txt
python run_all.py
# services (3 consoles)
python frontend/app.py                    # portal :5000 — bank@bank.com/bank123, risk@bank.com/risk123, customer@customer.com/cust123
uvicorn src.serving.api:app --port 8000  # REST API + /docs
python -m src.dashboard.risk_dashboard    # Dash analytics :8050 (Portfolio | Customer 360 | Queue | Model health)
pytest -q
```

## Services, endpoints, pages
- `src/services/store.py` — single data-access layer (CSV/Parquet now, Postgres/DynamoDB later)
- `src/services/risk_service.py` — portfolio summary, customer search, 360 timeline, single-customer scoring
- `src/services/intervention_service.py` — offers, accept/decline, approve/snooze queue, acceptance stats
- `src/services/model_service.py` — health (PR-AUC/ROC/Recall@15/Precision@Red/Brier/PSI), fairness 80% rule
- `src/serving/api.py` (FastAPI :8000): `/health`, `/api/portfolio/summary`, `/api/customers/search`,
  `/api/customers/{id}`, `/api/scores`, `/api/scores/single`, `/api/alerts`, `/api/alerts/{id}/action`,
  `/api/interventions`, `/api/interventions/respond`, `/api/model/health|fairness|thresholds|acceptance`
- `frontend/app.py` (Flask :5000): `/` login, `/bank` portfolio, `/bank/queue` (approve/snooze),
  `/bank/customer/<id>` 360 + offers, `/bank/model` health+fairness, `/bank/interventions`, `/customer` self-service
- `src/dashboard/risk_dashboard.py` (Dash :8050): Portfolio (mix, drift, lift, PR) | Customer 360 | Queue (export CSV) | Model health
- `src/policy/engine.py` — full FR-5: contacted/hardship/balance-ok suppression, ≥2 signal-group gate,
  Amber-x7 escalation, top-K cap, `suppressed_*.csv` + `policy_meta_*.json` audit

## Current production snapshot (2000 customers, 2024-11-01)
Flagged 13.0% (≤15 ✓) · PR-AUC 0.69 (>0.45 ✓) · Precision@Red 0.86 (>0.35 ✓) ·
Recall@15% 0.67 (gate 0.70 — just under; tuned threshold 0.14 in thresholds.json) ·
Geography fairness 0.71 (investigate per FR-4.4) · no retrain signal (PSI 0.02).

## Layout
`src/generator|features|models|scoring|policy|dashboard|streaming|serving` · `src/services/` · `frontend/` (portal) · `feature_repo/` (Feast) · `dags/` (Airflow) · `aws/` (SageMaker/Kinesis/FeatureStore/Redshift/DynamoDB/SNS/QuickSight — commented TODOs) · `tests/`

## Tech coverage
OSS: XGBoost/LightGBM/sklearn, PyTorch LSTM (`sequence_model.py`), Feast, Airflow DAG, Kafka stub, MLflow, BentoML, Plotly/Dash. AWS: all templates in `aws/` awaiting backend values.
