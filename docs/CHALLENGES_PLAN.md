# Credence — Challenges & How We Plan to Solve Them

> Companion to `docs/PRESENTATION.md`. Honest blockers we actually hit +
> the concrete plan behind each. For judges: pair every challenge with its
> **evidence** (what broke) and its **plan** (what we'll do next).

---

## 1. Model runtime portability
- **Challenge:** LightGBM and XGBoost could not load OpenMP (`libomp` missing)
  on the dev machine — training failed at import.
- **Solved:** automatic fallback in `train.py` to sklearn **HistGradientBoosting**
  → champion with **test PR-AUC 0.74 · ROC-AUC 0.88** (isotonic-calibrated).
- **Plan:** pin `libomp` in the Dockerfile/CI image, add LightGBM/XGBoost
  retrain as a challenge step in CI, compare and promote the best PR-AUC —
  the fallback becomes a safety net, not the default.

## 2. Synthetic → real data gap
- **Challenge:** generator data is purpose-built; real CBS distributions will
  shift features, scores, and profits.
- **Plan:** generator params live in `config.yaml` (swap for a real dump),
  **recalibrate** on an anonymized extract (PRD v1.0 rollout), publish
  distributions in the model card, and let **PSI monitoring (>0.2) trigger an
  automatic retrain signoff** so drift is caught before it hurts.

## 3. A required signal that never fired
- **Challenge:** salary delay feature = `max(0, days_since−31)` against a fixed
  monthly cycle → **0% prevalence** in the synthetic population; the "income"
  stress group was always empty.
- **Solved:** dashboard now mirrors the policy engine's truth (single source),
  so the UI never lies.
- **Plan:** fix the *generator* (inject +3..10d salary shifts across cycles) and
  compute delay **vs the 3-month median** instead of a constant 31; re-run and
  show a living income-signal bar.

## 4. Alert fatigue — suppression almost over-suppressed
- **Challenge:** the batch pipeline silently suppressed **every** flagged
  customer (129/131) because `run_all.py` skipped the feature-build step →
  single-source collapse.
- **Solved:** features step added to `run_all.py`; multi-signal check (≥2
  groups) + contact-7d hold + hardship + Red-cap now produce a realistic
  queue (131 alerts: 113 Red / 18 Amber / 128 suppressed).
- **Plan:** track suppression & snooze rates weekly, tune group thresholds on
  cohort data, add an A/B test of nudge vs no-contact to prove lift
  (PRD "Amber→Green cure vs baseline").

## 5. Template/build hardening
- **Challenge:** a Jinja conditional inside a tag attribute swallowed the
  `<main>` quote — pages rendered with 0-width content and text behind cards;
  the pyproject declared a nonexistent setuptools backend, killing Docker
  builds; Python 3.9 locals vs 3.11 deploy (PEP 604) crashed at import.
- **Solved:** layout repaired and **verified with headless-Chromium
  screenshots**; standard `setuptools.build_meta` + `requirements.txt`
  install; `from __future__ import annotations` for 3.9.
- **Plan:** add template-parse and Dockerfile build checks to CI, Playwright
  visual regression for the 6 key pages, `.python-version` + `make venv`
  pinning one interpreter everywhere.

## 6. SSO that never actually worked
- **Challenge:** Google doesn't populate `token["userinfo"]` without a `nonce`
  → callback looped forever.
- **Solved:** explicit userinfo fetch with the access token + `OAUTH_REDIRECT_URI`
  override + `ProxyFix` for https behind Render; `/ssostatus` diagnostics.
- **Plan:** CI test with a mocked OAuth provider, then move to the **nonce-
  based** flow for anti-replay; add per-bank domain lists from a config source.

## 7. Scale (2k demo → 100k+ production)
- **Challenge:** feature builder loops per-customer (Python); API targets
  p95 <200 ms; batch must do 100k in <30 min on a laptop.
- **Plan:** vectorize the remaining per-customer loops (groupby + shift
  windows, DuckDB/polars), precompute SHAP top-3 in batch (already), Redis/
  Valkey feature cache + FastAPI async for online scoring (Phase 6), stream
  ingestion behind a feature flag per PRD.

## 8. Free-tier hosting reality
- **Challenge:** Render free web services **sleep** (~50s cold start) and have
  no persistent disk.
- **Plan:** state moves to the free Postgres (already built: `DATABASE_URL`
  auto-creates + seeds tables), `/.well-known`-style health check + scheduled
  ping so judges don't hit a cold start, and a paid/alternate host (Railway/
  Fly) upgrade path for demo day.

## 9. Audit integrity beyond CSV
- **Challenge:** append-only logs are CSVs today — fine for demo, not a real
  control.
- **Plan:** Postgres-backed intervention/action tables (already switchable),
  then enforce append-only via DB triggers/permissions, hash-chain the log
  (tamper-evident), and export a signed **SR 11-7 pack** for model risk.

## 10. Two accounts / repo hygiene
- **Challenge:** work was split across `adhintra28/Credence` and a stale
  `rootbrites/Credence-1.0` upload → confusion (and a 92MB Playwright folder
  almost committed).
- **Solved:** full history on both repos' `main`, `.dockerignore`/`.gitignore`
  QA artifacts, `legacy-upload` preserved.
- **Plan:** pick one canonical repo for the pitch, delete stale branches,
  branch-protect `main` (CI must pass before merge).

---

## Pitch phrasing (one line per challenge)
> "We hit real problems — broken ML runtimes, a signal that never fired,
> SSO that looped, deploy builds that died. Every one is either **fixed and
> screenshot-verified** or has a **dated, testable plan** — because a
> pre-delinquency engine that can't explain itself is exactly the kind of
> model the regulator is afraid of."
