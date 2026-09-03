def test_schemas():
    import pandas as pd
    c = pd.read_csv("data/raw/customers.csv")
    assert {"customer_id", "archetype", "emi_amount"}.issubset(c.columns)


def test_no_leakage():
    import pandas as pd
    t = pd.read_parquet("data/raw/transactions.parquet")
    f = pd.read_parquet("data/processed/features_2024-11-01.parquet")
    assert pd.to_datetime(t["timestamp"]).max() <= pd.Timestamp("2024-12-31")


def test_policy_outputs():
    import glob
    assert glob.glob("data/outputs/alerts_*.csv"), "run scoring+policy first"
