"""Feast feature definitions — mirrors src/features/build.py outputs for real-time serving.
Offline source = processed parquet; online = Redis (see feature_store.yaml).
"""
from datetime import timedelta
from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float64, String

customer = Entity(name="customer_id", description="Borrower")

source = FileSource(path="data/processed/features_2024-11-01.parquet",
                    timestamp_field="scoring_date" if False else "scoring_date")

risk_features = FeatureView(
    name="risk_features",
    entities=[customer],
    ttl=timedelta(days=60),
    schema=[
        Field(name="savings_wow_pct", dtype=Float64),
        Field(name="salary_delay_vs_median", dtype=Float64),
        Field(name="lending_app_cnt_7d", dtype=Float64),
        Field(name="utility_delay_days", dtype=Float64),
        Field(name="autodebit_fail_28d", dtype=Float64),
        Field(name="discretionary_drop_pct", dtype=Float64),
        Field(name="atm_cnt_7d", dtype=Float64),
        Field(name="archetype", dtype=String),
    ],
    source=source,
)
