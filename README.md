# Pre-Delinquency Engine

Batch-first build per `IMPLEMENTATION_PLAN.md` + `PRD.md`. AWS fully stubbed/commented until backend configured.

## Quickstart
```powershell
pip install -r requirements.txt
python run_all.py
python frontend/app.py        # basic portal: bank@bank.com/bank123, customer@customer.com/cust123
python -m src.dashboard.risk_dashboard   # Plotly Dash analytics
```

## Layout
`src/generator|features|models|scoring|policy|dashboard|streaming|serving` · `frontend/` (basic login→bank/customer) · `feature_repo/` (Feast) · `dags/` (Airflow) · `aws/` (SageMaker/Kinesis/FeatureStore/Redshift/DynamoDB/SNS/QuickSight — commented TODOs) · `tests/`

## Tech coverage
OSS: XGBoost/LightGBM/sklearn, PyTorch LSTM (`sequence_model.py`), Feast, Airflow DAG, Kafka stub, MLflow, BentoML, Plotly/Dash. AWS: all templates in `aws/` awaiting backend values.
