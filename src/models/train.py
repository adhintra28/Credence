"""Train champion (LightGBM) + challenger (XGBoost) with calibration + SHAP + MLflow.
Run: python -m src.models.train --config config.yaml
Builds monthly snapshots for train/valid/test windows, time-split, no leakage.
"""
import argparse
import json
import os
import numpy as np
import pandas as pd
import yaml

from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, roc_auc_score, recall_score

from src.features.build import build_snapshot, FEATURE_COLS


def snapshots_for_months(txns, emis, cust, start, months_list):
    frames = []
    for m in months_list:
        sd = (pd.Timestamp(start) + pd.DateOffset(months=m)).date().isoformat()
        f = build_snapshot(txns, emis, cust, sd)
        due = pd.to_datetime(emis["due_date"])
        sdt = pd.Timestamp(sd)
        fut = emis[(due > sdt) & (due <= sdt + pd.Timedelta(days=28))]
        bad = set(fut[fut["dpd_days"] > 0]["customer_id"])
        f["label"] = f["customer_id"].map(lambda c: 1 if c in bad else 0)
        f["scoring_date"] = sd
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def pr_at_recall(y, p, target=0.70):
    ths = np.unique(np.quantile(p, np.linspace(0.5, 0.99, 50)))
    best = (0, 1.0, 0.0)  # precision, thresh, flagged
    for t in ths:
        pred = (p >= t).astype(int)
        rec = recall_score(y, pred, zero_division=0)
        if rec >= target:
            prec = (y[pred == 1].mean() if pred.sum() else 0.0)
            if prec > best[0]:
                best = (prec, float(t), float(pred.mean()))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = yaml.safe_load(f)
    txns = pd.read_parquet(f"{cfg['paths']['raw_dir']}/transactions.parquet")
    txns["timestamp"] = pd.to_datetime(txns["timestamp"])
    emis = pd.read_csv(f"{cfg['paths']['raw_dir']}/emi_schedule.csv")
    cust = pd.read_csv(f"{cfg['paths']['raw_dir']}/customers.csv")
    start = cfg["data"]["start_date"]

    train = snapshots_for_months(txns, emis, cust, start, [2, 5, 7])
    valid = snapshots_for_months(txns, emis, cust, start, [8, 9])
    test = snapshots_for_months(txns, emis, cust, start, [10, 11])
    Xtr, ytr = train[FEATURE_COLS].fillna(0).values, train["label"].values
    Xv, yv = valid[FEATURE_COLS].fillna(0).values, valid["label"].values
    Xt, yt = test[FEATURE_COLS].fillna(0).values, test["label"].values
    print(f"train={Xtr.shape} pos={ytr.mean():.3f} | valid pos={yv.mean():.3f} | test pos={yt.mean():.3f}")

    # scale for linear-probe parity (trees don't need it, kept for API compat)
    scaler = StandardScaler().fit(Xtr)
    os.makedirs(cfg["paths"]["models_dir"], exist_ok=True)

    results, models = {}, {}
    # Champion: LightGBM (Open-Source Stack)
    try:
        import lightgbm as lgb
        neg, pos = (ytr == 0).sum(), max((ytr == 1).sum(), 1)
        clf = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                                 min_child_samples=100, scale_pos_weight=neg / pos,
                                 random_state=42, verbose=-1)
        clf.fit(Xtr, ytr, eval_set=[(Xv, yv)])
        models["lightgbm"] = clf
        results["lightgbm_raw"] = clf.predict_proba(Xv)[:, 1]
    except Exception as e:
        print(f"lightgbm skipped: {e}")
    # Challenger: XGBoost (Open-Source Stack)
    try:
        from xgboost import XGBClassifier
        neg, pos = (ytr == 0).sum(), max((ytr == 1).sum(), 1)
        xgb = XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=5,
                            scale_pos_weight=neg / pos, tree_method="hist",
                            random_state=42, eval_metric="logloss")
        xgb.fit(Xtr, ytr, eval_set=[(Xv, yv)], verbose=False)
        models["xgboost"] = xgb
        results["xgboost_raw"] = xgb.predict_proba(Xv)[:, 1]
    except Exception as e:
        print(f"xgboost skipped: {e}")
    # Fallback: sklearn (always available)
    if not models:
        from sklearn.ensemble import HistGradientBoostingClassifier
        hgb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=42)
        hgb.fit(Xtr, ytr)
        models["sklearn_hgb"] = hgb
        results["sklearn_hgb_raw"] = hgb.predict_proba(Xv)[:, 1]

    # pick champion by valid PR-AUC
    champ, best_pr = None, -1
    for name, pv in results.items():
        pr = average_precision_score(yv, pv)
        print(f"{name}: valid PR-AUC={pr:.4f} ROC={roc_auc_score(yv, pv):.4f}")
        if pr > best_pr:
            best_pr, champ = pr, name.replace("_raw", "")
    clf = models[champ]
    pv = results[champ + "_raw"]
    # isotonic calibration on valid
    iso = IsotonicRegression(out_of_bounds="clip").fit(pv, yv)
    pt = iso.predict(np.clip(clf.predict_proba(Xt)[:, 1], 0, 1))
    prec, thr, flagged = pr_at_recall(yv, iso.predict(np.clip(pv, 0, 1)), 0.70)
    print(f"CHAMPION={champ} test PR-AUC={average_precision_score(yt, pt):.4f} "
          f"ROC={roc_auc_score(yt, pt):.4f} thr@R70={thr:.3f} prec={prec:.3f} flagged={flagged:.3f}")

    import pickle
    with open(f"{cfg['paths']['models_dir']}/production.pkl", "wb") as f:
        pickle.dump({"model": clf, "name": champ, "features": FEATURE_COLS,
                     "calibrator": iso, "scaler_mean": scaler.mean_.tolist()}, f)
    with open(f"{cfg['paths']['models_dir']}/thresholds.json", "w") as f:
        json.dump({"amber_min": 0.30, "red_min": 0.60, "tuned_red": float(thr),
                   "champion": champ, "valid_pr_auc": float(best_pr)}, f, indent=2)
    # SHAP (guarded — explainability requirement)
    try:
        import shap
        bg = shap.sample(pd.DataFrame(Xtr, columns=FEATURE_COLS), 100)
        ex = shap.TreeExplainer(clf).shap_values(bg)
        vals = ex[1] if isinstance(ex, list) else ex
        imp = pd.Series(np.abs(vals).mean(axis=0), index=FEATURE_COLS).sort_values(ascending=False)
        imp.head(10).to_csv(f"{cfg['paths']['models_dir']}/global_shap.csv")
        print("top SHAP:\n", imp.head(5).to_string())
    except Exception as e:
        print(f"shap skipped: {e}")
    # MLflow (guarded — model serving requirement)
    try:
        import mlflow
        mlflow.set_tracking_uri(f"file:///{os.path.abspath(cfg['paths']['models_dir'])}/mlruns")
        mlflow.set_experiment("pre-delinquency")
        with mlflow.start_run(run_name=champ):
            mlflow.log_params({"champion": champ, "threshold": thr})
            mlflow.log_metrics({"valid_pr_auc": best_pr, "test_pr_auc": float(average_precision_score(yt, pt))})
    except Exception as e:
        print(f"mlflow skipped: {e}")
    print("saved production.pkl + thresholds.json")


if __name__ == "__main__":
    main()
