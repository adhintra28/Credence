"""Central data-access layer for production services.

All reads go through here so API, Flask portal, Dash and batch jobs
see identical data. Backed by CSV/Parquet on disk (MVP store);
swap internals for Postgres/DynamoDB without changing callers.
"""
import glob
import json
import os
from functools import lru_cache

import pandas as pd
import yaml

from src.services import db

CONFIG_PATH = os.environ.get("PREDELINQ_CONFIG", "config.yaml")


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return yaml.safe_load(f)


def _latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def paths(cfg=None):
    cfg = cfg or load_config()
    return cfg["paths"], cfg


def get_customers(cfg=None):
    p, _ = paths(cfg)
    fp = f"{p['raw_dir']}/customers.csv"
    if not os.path.exists(fp):
        return pd.DataFrame()
    return pd.read_csv(fp)


def get_transactions(cfg=None):
    p, _ = paths(cfg)
    fp = f"{p['raw_dir']}/transactions.parquet"
    if not os.path.exists(fp):
        return pd.DataFrame()
    df = pd.read_parquet(fp)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def get_emi(cfg=None):
    p, _ = paths(cfg)
    fp = f"{p['raw_dir']}/emi_schedule.csv"
    if not os.path.exists(fp):
        return pd.DataFrame()
    df = pd.read_csv(fp)
    for c in ("due_date", "paid_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def get_labels(cfg=None):
    p, _ = paths(cfg)
    fp = f"{p['raw_dir']}/labels.csv"
    if not os.path.exists(fp):
        return pd.DataFrame()
    return pd.read_csv(fp)


def latest_scoring_date(cfg=None):
    p, _ = paths(cfg)
    f = _latest(f"{p['outputs_dir']}/risk_scores_*.csv")
    if f:
        base = os.path.basename(f)
        return base.replace("risk_scores_", "").replace(".csv", "")
    cfgd = (cfg or load_config())
    return cfgd["scoring"]["scoring_date"]


def get_scores(scoring_date=None, cfg=None):
    p, _ = paths(cfg)
    scoring_date = scoring_date or latest_scoring_date(cfg)
    if db.enabled():
        df = db.read("scores", scoring_date)
        if len(df) == 0:
            _seed_scores(scoring_date, p)
            df = db.read("scores", scoring_date)
    else:
        fp = f"{p['outputs_dir']}/risk_scores_{scoring_date}.csv"
        if not os.path.exists(fp):
            # fall back to latest available
            fp = _latest(f"{p['outputs_dir']}/risk_scores_*.csv")
        if not fp or not os.path.exists(fp):
            return pd.DataFrame(), scoring_date
        df = pd.read_csv(fp)
    # normalise reasons column -> list
    if "reasons" in df.columns:
        def _parse(v):
            try:
                return json.loads(v) if isinstance(v, str) else (v or [])
            except Exception:
                return []
        df["_reasons_list"] = df["reasons"].apply(_parse)
    else:
        df["_reasons_list"] = [[] for _ in range(len(df))]
    return df, scoring_date


def _seed_scores(scoring_date, p):
    fp = f"{p['outputs_dir']}/risk_scores_{scoring_date}.csv"
    if os.path.exists(fp) and len(db.read("scores", scoring_date)) == 0:
        db.seed("scores", pd.read_csv(fp), scoring_date)


def get_alerts(scoring_date=None, cfg=None):
    p, _ = paths(cfg)
    scoring_date = scoring_date or latest_scoring_date(cfg)
    if db.enabled():
        df = db.read("alerts", scoring_date)
        if len(df) == 0:
            fp = f"{p['outputs_dir']}/alerts_{scoring_date}.csv"
            if os.path.exists(fp):
                db.seed("alerts", pd.read_csv(fp), scoring_date)
                df = db.read("alerts", scoring_date)
        return df, scoring_date
    fp = f"{p['outputs_dir']}/alerts_{scoring_date}.csv"
    if not os.path.exists(fp):
        fp = _latest(f"{p['outputs_dir']}/alerts_*.csv")
    if not fp or not os.path.exists(fp):
        return pd.DataFrame(), scoring_date
    return pd.read_csv(fp), scoring_date


def get_features(scoring_date=None, cfg=None):
    p, _ = paths(cfg)
    scoring_date = scoring_date or latest_scoring_date(cfg)
    if db.enabled():
        df = db.read("features", scoring_date)
        if len(df) == 0:
            fp = f"{p['processed_dir']}/features_{scoring_date}.parquet"
            if os.path.exists(fp):
                db.seed("features", pd.read_parquet(fp), scoring_date)
                df = db.read("features", scoring_date)
        return df, scoring_date
    fp = f"{p['processed_dir']}/features_{scoring_date}.parquet"
    if not os.path.exists(fp):
        fp = _latest(f"{p['processed_dir']}/features_*.parquet")
    if not fp or not os.path.exists(fp):
        return pd.DataFrame(), scoring_date
    return pd.read_parquet(fp), scoring_date


def get_thresholds(cfg=None):
    import json as _json
    p, cfgd = paths(cfg)
    fp = f"{p['models_dir']}/thresholds.json"
    if os.path.exists(fp):
        with open(fp) as f:
            return _json.load(f)
    t = cfgd.get("tiers", {})
    return {"amber_min": t.get("amber_min", 0.30), "red_min": t.get("red_min", 0.60)}


def get_model_bundle(cfg=None):
    import pickle
    p, _ = paths(cfg)
    fp = f"{p['models_dir']}/production.pkl"
    if not os.path.exists(fp):
        return None
    with open(fp, "rb") as f:
        return pickle.load(f)


INTERVENTION_COLS = ["customer_id", "date", "tier", "reasons", "offer",
                     "channel", "status", "model_version", "action_by", "note"]


def _interventions_db(cfg=None):
    """DB-backed intervention log: seed once from the bundled CSV, then read DB."""
    df = db.read("interventions")
    if len(df) == 0:
        p, _ = paths(cfg)
        fp = f"{p['outputs_dir']}/intervention_log.csv"
        if os.path.exists(fp):
            db.seed("interventions", pd.read_csv(fp))
            df = db.read("interventions")
    for c in INTERVENTION_COLS:
        if c not in df.columns:
            df[c] = ""
    return df


def get_interventions(cfg=None):
    if db.enabled():
        return _interventions_db(cfg)
    p, _ = paths(cfg)
    fp = f"{p['outputs_dir']}/intervention_log.csv"
    if not os.path.exists(fp):
        return pd.DataFrame(columns=INTERVENTION_COLS)
    try:
        df = pd.read_csv(fp)
    except Exception:
        return pd.DataFrame(columns=INTERVENTION_COLS)
    for c in INTERVENTION_COLS:
        if c not in df.columns:
            df[c] = "" if c in ("reasons", "offer", "channel", "status",
                                "model_version", "action_by", "note", "tier") else df.get(c, "")
    return df


def append_intervention(row: dict, cfg=None):
    """Append one intervention row, creating header with full schema if needed."""
    if db.enabled():
        return db.append("interventions", {c: row.get(c, "") for c in INTERVENTION_COLS})
    p, _ = paths(cfg)
    os.makedirs(p["outputs_dir"], exist_ok=True)
    fp = f"{p['outputs_dir']}/intervention_log.csv"
    full = {c: row.get(c, "") for c in INTERVENTION_COLS}
    df = pd.DataFrame([full])
    header = not os.path.exists(fp) or os.path.getsize(fp) == 0
    # migrate legacy header (customer_id,date,offer,channel) by rewriting
    if not header:
        try:
            existing = pd.read_csv(fp, nrows=1)
            if list(existing.columns) != INTERVENTION_COLS:
                old = pd.read_csv(fp)
                for c in INTERVENTION_COLS:
                    if c not in old.columns:
                        old[c] = ""
                old = old[INTERVENTION_COLS]
                old.to_csv(fp, index=False)
        except Exception:
            header = True
    df.to_csv(fp, mode="a", header=header, index=False)
    return full


ACTION_COLS = ["customer_id", "scoring_date", "action", "action_by", "action_at", "note"]


def get_alert_actions(cfg=None):
    if db.enabled():
        df = db.read("alert_actions")
        if len(df) == 0:
            p, _ = paths(cfg)
            fp = f"{p['outputs_dir']}/alert_actions.csv"
            if os.path.exists(fp):
                db.seed("alert_actions", pd.read_csv(fp))
                df = db.read("alert_actions")
        return df
    p, _ = paths(cfg)
    fp = f"{p['outputs_dir']}/alert_actions.csv"
    if not os.path.exists(fp):
        return pd.DataFrame(columns=ACTION_COLS)
    try:
        return pd.read_csv(fp)
    except Exception:
        return pd.DataFrame(columns=ACTION_COLS)


def record_alert_action(customer_id, scoring_date, action, action_by="", note="", cfg=None):
    from datetime import datetime, timezone
    row = {"customer_id": customer_id, "scoring_date": scoring_date, "action": action,
           "action_by": action_by, "action_at": datetime.now(timezone.utc).isoformat(), "note": note}
    if db.enabled():
        return db.append("alert_actions", row)
    p, _ = paths(cfg)
    os.makedirs(p["outputs_dir"], exist_ok=True)
    fp = f"{p['outputs_dir']}/alert_actions.csv"
    header = not os.path.exists(fp) or os.path.getsize(fp) == 0
    pd.DataFrame([row]).to_csv(fp, mode="a", header=header, index=False)
    return row
