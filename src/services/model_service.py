"""Model health: metrics, drift (PSI), fairness (80% rule), SHAP importances."""
import numpy as np
import pandas as pd

from src.services import store


def _psi(expected, actual, buckets=10):
    e_hist, edges = np.histogram(expected, bins=buckets, range=(0, 1))
    a_hist, _ = np.histogram(actual, bins=edges)
    e = e_hist / max(e_hist.sum(), 1) + 1e-6
    a = a_hist / max(a_hist.sum(), 1) + 1e-6
    return float(np.sum((a - e) * np.log(a / e)))


def model_health(scoring_date=None):
    scores, sd = store.get_scores(scoring_date)
    feats, _ = store.get_features(sd)
    labels = store.get_labels()
    cust = store.get_customers()
    th = store.get_thresholds()
    out = {"scoring_date": sd, "thresholds": th, "n": int(len(scores))}
    if len(scores) == 0:
        return out
    out["score_mean"] = round(float(scores["score"].mean()), 4)
    out["score_std"] = round(float(scores["score"].std()), 4)
    out["flagged_rate"] = round(float((scores["tier"] != "Green").mean()), 4)
    # calibration proxy: mean score vs label base rate
    if len(labels) and "label_28d" in labels.columns:
        out["base_rate"] = round(float(labels["label_28d"].mean()), 4)
        try:
            from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
            lab = labels.set_index("customer_id")["label_28d"].to_dict()
            y, p = [], []
            for _, r in scores.iterrows():
                if r["customer_id"] in lab:
                    y.append(int(lab[r["customer_id"]]))
                    p.append(float(r["score"]))
            if len(set(y)) > 1:
                out["pr_auc_proxy"] = round(float(average_precision_score(y, p)), 4)
                out["roc_auc_proxy"] = round(float(roc_auc_score(y, p)), 4)
                out["brier"] = round(float(brier_score_loss(y, p)), 4)
                # recall@15%
                order = np.argsort(-np.array(p))
                k = max(int(0.15 * len(p)), 1)
                topk = set(order[:k])
                pos = {i for i, v in enumerate(y) if v == 1}
                out["recall_at_15"] = round(len(topk & pos) / max(len(pos), 1), 4)
                # precision@Red
                red_idx = [i for i, (_, r) in enumerate(scores.iterrows()) if r["tier"] == "Red"]
                if red_idx:
                    out["precision_at_red"] = round(float(np.mean([y[i] for i in red_idx])), 4)
        except Exception as e:
            out["metrics_error"] = str(e)
    # drift: compare score distribution halves + PSI of top features vs global mean
    try:
        halves = np.array_split(scores["score"].values, 2)
        out["score_mean_shift"] = round(float(halves[1].mean() - halves[0].mean()), 4) if len(halves) == 2 else 0.0
        out["score_psi_halves"] = round(_psi(halves[0], halves[1]), 4) if len(halves) == 2 else 0.0
        out["retrain_signal"] = bool(out["score_psi_halves"] > 0.2 or abs(out.get("score_mean_shift", 0)) > 0.08)
    except Exception:
        pass
    # per-feature PSI placeholder (needs history; report null-rate health now)
    if len(feats):
        nulls = {c: round(float(feats[c].isna().mean()), 4) for c in feats.columns[:30]}
        out["null_rate"] = nulls
        out["null_violations"] = [c for c, v in nulls.items() if v > 0.05]
    # global shap
    import os
    p, _ = store.paths()
    gsh = f"{p['models_dir']}/global_shap.csv"
    if os.path.exists(gsh):
        try:
            df = pd.read_csv(gsh)
            out["global_shap"] = [
                {"feature": r.get("Unnamed: 0", ""), "importance": float(float(r.get("0", 0)))}
                for _, r in df.iterrows()]
        except Exception:
            pass
    return out


def fairness_audit(scoring_date=None):
    scores, sd = store.get_scores(scoring_date)
    cust = store.get_customers()
    if len(scores) == 0 or len(cust) == 0:
        return {"scoring_date": sd, "error": "no data"}
    df = scores.merge(cust, on="customer_id", how="left")
    df["flagged"] = (df["tier"] != "Green").astype(int)
    result = {"scoring_date": sd}
    for col in ("geography", "archetype", "product_type"):
        if col not in df.columns:
            continue
        rates = df.groupby(col)["flagged"].mean()
        max_r, min_r = float(rates.max()), float(rates.min())
        ratio = (min_r / max_r) if max_r > 0 else 1.0
        result[col] = {
            "flagged_rate": {k: round(float(v), 4) for k, v in rates.items()},
            "min_max_ratio": round(ratio, 4),
            "passes_80pct_rule": bool(ratio >= 0.8),
        }
    return result
