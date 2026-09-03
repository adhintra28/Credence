"""Model Serving (BentoML + MLflow — Open-Source Stack). Install: pip install bentoml mlflow
Run: bentoml serve src.serving.bento_service:svc --port 3000
"""
try:
    import bentoml
    import pickle
    import numpy as np

    with open("models/production.pkl", "rb") as f:
        BUNDLE = pickle.load(f)

    svc = bentoml.Service("predelinq")

    @svc.api
    def score(features: list) -> dict:
        import numpy as np
        X = np.array(features).reshape(1, -1)
        p = float(BUNDLE["model"].predict_proba(X)[0, 1])
        return {"score": p, "tier": "Red" if p >= 0.6 else ("Amber" if p >= 0.3 else "Green"),
                "model": BUNDLE.get("name")}
except ImportError:
    pass  # bentoml optional until serving phase
