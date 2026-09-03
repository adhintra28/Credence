# Pre-Delinquency Early Warning Engine — Complete Implementation Plan

> Goal: Detect financial stress 2–4 weeks BEFORE a missed EMI / credit-card payment and trigger empathetic, channel-agnostic outreach (nudge, payment-holiday, restructuring).
> Workspace: `preDeliquency/` (currently empty, greenfield)
> Decision log: Real datasets evaluated and rejected — Berka (PKDD'99, 682 loans, 1990s Czech, no UPI/salary-delay labels) and StrideSec Kaggle synthetic (nested JSON, no DPD labels) do not cover the 7 required signals. **Build purpose-built synthetic data.**

---

## 1. Problem Framing

### 1.1 ML formulation
Do NOT predict `missed_payment_now`. Predict:

```
P(default in next 14d OR 28d | currently clean, 0 DPD today)
```

* Unit: one row per `customer_id x scoring_date` (daily batch in MVP).
* Exclude customers already 30+ DPD at scoring time.
* Label:
```
label_28d = 1 if (missed_EMI OR min_due_unpaid OR auto_debit_bounce) in (t+1 .. t+28) else 0
label_14d = same with 14-day window (secondary, higher precision)
```

### 1.2 Success criteria (tied to Benefits in brief)
| Business benefit | Measurable target |
|---|---|
| Reduced credit losses | Recall@flagged_15% >= 0.70 on out-of-time test, PR-AUC > 0.45 |
| Lower collections cost | Flagged rate <= 15% (avoid alert fatigue), Precision@Red > 0.35 |
| Improved recovery | Intervention acceptance rate tracked; uplift vs control (simulated) |
| Stronger relationships | Amber = nudge only, no human call; Red = offer, not threat |
| Risk visibility | Dash shows Green/Amber/Red migration + top-3 SHAP reasons per alert |
| Regulatory goodwill | Every Red alert ships with 3 plain-language reasons + audit log |
| Operational efficiency | Daily batch < 30 min for 100k customers on laptop; API p95 < 200ms |

### 1.3 Non-goals for MVP
No real-time (<1s) scoring, no Kafka/Flink, no Airflow cluster, no SageMaker, no GenAI auto-decisions. Those are Phase 4+.

---

## 2. Solution Architecture

### 2.1 Logical flow (MVP = batch)
```
synthetic_generator.py
  -> data/raw/transactions.parquet + customers.csv + emi_schedule.csv + labels.csv
  -> features/build_features.py (7d/14d/28d/WoW windows)
  -> data/processed/feature_store.parquet (point-in-time correct)
  -> models/train.py (LightGBM champion + XGBoost challenger, MLflow)
  -> models/scoring.py (daily batch -> risk_scores.csv)
  -> policy/engine.py (Green/Amber/Red + suppression rules -> alerts.csv)
  -> dashboard/app.py (Plotly Dash: portfolio, customer 360, queue, model health)
```

### 2.2 Scale-out path (post-MVP, no rewrite)
| Layer | MVP (local) | Scale (OSS) | Scale (AWS) |
|---|---|---|---|
| Ingest | Parquet files | Kafka topic `txns` + Python producer | Kinesis Data Streams + Firehose -> S3 |
| Processing | pandas batch | Kafka consumer / Spark | Lambda + Managed Flink (KDA) |
| Offline store | Parquet | Postgres / Parquet | S3 + Redshift + Athena + Iceberg |
| Feature store | Parquet + pickle medians | Feast + Redis online | SageMaker Feature Store (Valkey hot) |
| Orchestration | `run_all.py` script | Airflow DAG nightly | Airflow / SageMaker Pipelines |
| Training | sklearn/LightGBM + MLflow | Same + registry | SageMaker Training + Registry |
| Serving | Batch CSV | BentoML / FastAPI | SageMaker Endpoint + Lambda |
| State | CSV | Postgres/Redis | DynamoDB `risk_scores` |
| Notify | Console + CSV | Kafka `risk_alerts` | SNS per tier |
| Dashboard | Plotly Dash | Dash | QuickSight |

Rule: do not introduce Kafka/Feast/Airflow/SageMaker until batch MVP meets Section 1.2 targets.

### 2.3 Repo structure to create
```
preDeliquency/
  IMPLEMENTATION_PLAN.md (this file)
  requirements.txt
  README.md
  config.yaml (windows, dates, volumes, thresholds, seeds)
  data/
    raw/           # generator output, never hand-edited
    processed/     # features, train/valid/test splits
  src/
    generator/     # synthetic customers, txns, emi, labels
    features/      # window aggregations, point-in-time join
    models/        # train, calibrate, explain, evaluate
    scoring/       # daily batch scoring
    policy/        # tiering + suppression + intervention templates
    dashboard/     # Dash app
    utils/         # seeds, dates, metrics, io
  notebooks/
    01_eda.ipynb
    02_features.ipynb
    03_modeling.ipynb
  tests/
    test_generator.py
    test_features_no_leakage.py
    test_policy.py
  models/          # mlflow artifacts + production.pkl (gitignored large files)
```

---

## 3. Phase-by-Phase Implementation

### Phase 0 — Setup + Contracts (0.5 day)
**Objective:** reproducible skeleton, no ML yet.
- [ ] Create folders above, `requirements.txt`: `pandas, numpy, pyarrow, scikit-learn, lightgbm, xgboost, shap, mlflow, plotly, dash, pytest, pyyaml`
- [ ] `config.yaml`: `seed: 42, n_customers: 20000, start: 2024-01-01, months: 12, emi_day: 5, scoring_date: 2024-11-01, test_months: 2`
- [ ] Define flat schemas (enforced by generator):
  - `customers(customer_id, archetype, age_band, geography, product_type, emi_amount, emi_day, income_median, salary_day)`
  - `transactions(txn_id, customer_id, timestamp, txn_type, amount, balance_after, channel, merchant_category, status)`
    - `txn_type`: `salary_credit, upi_p2m, upi_lending_app, utility_bill, dining, entertainment, atm_withdrawal, savings_transfer, emi_debit, gambling`
    - `channel`: `UPI, NEFT, ATM, billpay, autodebit`
    - `status`: `success, fail`
  - `emi_schedule(customer_id, due_date, paid_date, amount_due, amount_paid, dpd_days, bounce_flag)`
- [ ] Exit: `pytest tests/test_generator.py::test_schemas` passes (stub).

### Phase 1 — Synthetic Data Generator (2 days) — HIGHEST PRIORITY
**Why:** replaces Berka/StrideSec; must exhibit all 7 signals with ground-truth stress trajectories.

Archetype mix (configurable):
- `salaried_stable 50%` — never defaults (negatives)
- `salaried_stressed 20%` — salary delay -> default
- `gig_worker 12%` — irregular income -> default
- `SME_owner 8%` — deposit frequency drop -> default
- `pensioner 10%` — stable, rare default

Generation logic per customer:
1. Base monthly salary on `salary_day +/- 1d jitter`, amount `N(income_median, 5%)`.
2. Daily spend: discretionary `dining+entertainment ~ 12% income`, utility on `due_day 10, paid_day ~12` normally.
3. Savings ledger: maintain `balance_after` running total; persist to txn rows.
4. Stress injection (only for future `label_28d=1`, starting `T-28d` to `T-7d` before first missed EMI):
   - salary `+3 to +10d late` and/or `-10% amount`, 1 month
   - `savings_balance WoW -15% for 2+ weeks`
   - `lending_app txn_count >= 2/week` (new)
   - `utility paid_day 12 -> 25`, or partial pay
   - `discretionary -40%` vs prior 28d mean
   - `atm count 2x`, amount stable (cash hoarding)
   - `1-2 auto_debit fail` events
5. EMI engine: on each `due_date`, if `balance_after < emi_amount + buffer` or stressed flag + random draw -> `missed (dpd>0, bounce_flag=1)`, else paid.
6. Target positive rate 8-12%. Seed all RNGs. Output `transactions.parquet (~3-6M rows for 20k x 12mo)`, `emi_schedule.csv`, `labels.csv(customer_id, scoring_date, label_14d, label_28d)`.

Validation (must pass before Phase 2):
- [ ] Positive rate in range, no customer with label=1 but zero stress signals in prior 28d > 90% have >=2 signals
- [ ] No future leakage: all txns used for label at `t` have `timestamp <= t`
- [ ] Reproducible: same seed -> same row counts + hash
- [ ] `notebooks/01_eda.ipynb`: default rate by archetype, balance curves clean vs stressed, signal coverage heatmap

### Phase 2 — Feature Engineering (2 days)
**Objective:** turn 7 narrative signals into ~30 point-in-time numeric features.

Windows: `7d, 14d, 28d` ending at scoring date `t`; plus `WoW deltas` and `vs 90d median`.

Feature groups:
1. Income: `days_since_salary, salary_delay_vs_median, salary_amount_cv_3m, missing_salary_flag`
2. Liquidity: `savings_wow_pct, avg_balance_28d, balance_slope_28d, drawdown_streak_weeks, min_balance_14d`
3. Discipline: `utility_pay_day, utility_delay_days, utility_partial_ratio, autodebit_fail_cnt_28d`
4. Borrowing: `lending_app_cnt_7d/28d, lending_app_amt_ratio, new_lender_cnt`
5. Behavioral: `discretionary_ratio_28d, discretionary_drop_pct, gambling_flag, night_txn_ratio`
6. Cash: `atm_cnt_7d, atm_amt_avg, cash_to_spend_ratio`
7. Context: `archetype, product_type, geography, channel_mix, emi_to_income, tenure_months, bureau_proxy_if_any`

Implementation:
- `src/features/build.py`: single function `build_snapshot(transactions, emi, scoring_date) -> features_df`, pandas only, no global aggregates leaking future.
- Persist medians/modes from train only for imputation.
- Output `data/processed/features_YYYY-MM-DD.parquet`.

Tests:
- [ ] `test_features_no_leakage.py`: max txn timestamp <= scoring date; WoW recomputes identically on rerun
- [ ] Null rate < 5% per feature; correlation matrix reviewed in `02_features.ipynb`

### Phase 3 — Modeling + Explainability (3 days)
**Objective:** calibrated 28-day risk score + human-readable reasons.

Splits (time-based, never random):
- train: months 1-8, valid: 9-10, test: 11-12 (out-of-time). Stratify by archetype in valid/test reporting.

Models:
1. Champion: `LightGBM` (`scale_pos_weight`, `min_child_samples 100`, early stopping on PR-AUC). Fast, handles nulls, SHAP-native.
2. Challenger: `XGBoost` same objective. Compare PR-AUC, Recall@10%.
3. V2 only (post-MVP): LSTM/Transformer on weekly sequences in PyTorch — skip unless champion PR-AUC < 0.40.

Training steps (`src/models/train.py` + MLflow):
- Class imbalance: `scale_pos_weight = neg/pos`, threshold tuned on valid for `Recall>=0.70 at flagged<=0.15`, isotonic calibration on valid.
- Metrics (report all, optimize PR-AUC): `PR-AUC, ROC-AUC, Recall@10%/15%, Precision@Red, KS, Brier, Expected Loss Saved = sum(emi * p_recovered_if_intervened)`.
- Explainability: `shap.TreeExplainer` -> global bar, cohort by archetype/geography, per-row top-3. Map to plain language templates:
  - `salary_delay_7d (+0.21)` -> "Salary 7 days late vs usual"
  - `savings_down_22% (+0.15)` -> "Savings down 22% WoW"
  - `lending_app_x2 (+0.12)` -> "2 short-term borrowing txns this week"
- Fairness audit: disparate impact (flagged rate by geography/archetype, 80% rule), SHAP by cohort, drop or constrain leaky proxies. Log in `model_card.md`.
- Artifacts: `models/production.pkl + imputer.pkl + thresholds.json + shap_background.parquet`, MLflow run IDs.

Exit: test `Recall@15% >=0.70`, calibration curve slope 0.9-1.1, 5 example force plots in `03_modeling.ipynb`.

### Phase 4 — Scoring + Alert Policy + Intervention (2 days)
**Objective:** daily batch that acts without overwhelming teams.

`src/scoring/score.py` (runs for each `scoring_date`):
- Load features -> `predict_proba` -> calibrate -> write `risk_scores(customer_id, scoring_date, score, tier, shap_top3_json)`.

Tiering (`config.yaml` thresholds from valid):
```
score < 0.30 -> Green (no action)
0.30-0.60   -> Amber (auto nudge, no human)
> 0.60      -> Red (human queue + offer)
```

Suppression (`src/policy/engine.py`) — critical for noise:
```
suppress if contacted_last_7d OR in_hardship_program OR emi_due_in_2d_and_balance_ok
Amber x 7 consecutive days -> escalate to Red
Cap Red queue to top-K per day (e.g., 200) sorted by expected_loss = score * emi_amount
```

Interventions (templates, GenAI personalization ONLY for wording, never for decision):
- Amber: `"Hi {name}, we noticed {reason_1}. Your EMI of Rs.{amt} is due {date}. Need a reminder or split? [Yes/Remind/Split]"`
- Red: offer choice: `1-week payment-holiday (1 EMI pause, no late fee) / EMI split x2 / tenure +3mo restructure`. Log `offer, accept/decline, channel`.
- Write `alerts.csv` + append to `intervention_log.csv` for uplift tracking.

Tests: `test_policy.py` — suppression, escalation, cap, template rendering with no PII leak.

### Phase 5 — Dashboard + Demo (2 days)
**Objective:** intuitive risk visibility per Design Considerations.

`src/dashboard/app.py` (Dash, no QuickSight in MVP):
1. Portfolio tab: risk donut, migration Green->Amber->Red, flagged vs DPD lift, PR curve
2. Customer 360 tab: search `customer_id` -> balance curve with salary markers, utility timing strip, discretionary trend, SHAP waterfall, EMI schedule + offer buttons (mock)
3. Alerts queue tab: sortable table `score, tier, top_reason, emi_amt, expected_loss, action[Approve/Snooze]`, export CSV
4. Model health tab: PR-AUC over time, PSI per feature, score drift, fairness gaps

Exit: `python src/dashboard/app.py` runs locally, demo script: pick 3 stressed customers, show T-28d signals -> Amber -> Red -> holiday offer -> simulated cure.

### Phase 6 — Hardening + Scale Prep (post-MVP, optional for hackathon)
- Airflow DAG `nightly_score`: `materialize -> build_features -> score -> policy -> dashboard refresh`
- Feast `feature_repo/features.py` + Redis; Kafka producer/consumer mirroring batch logic; parity test batch vs streaming < 1e-6 diff
- BentoML/FastAPI `/score` with SHAP payload; DynamoDB/SNS or Postgres/Kafka equivalents
- Drift monitors: PSI>0.2 or score_mean_shift>8% triggers retrain; MLflow registry Champion/Challenger promotion
- SR 11-7 pack: data lineage, conceptual soundness note, out-of-time validation, sensitivity analysis, 5 individual explanations, bias audit — one-click PDF/HTML export

---

## 4. Cross-Cutting Requirements

* **Environment-aware:** always slice metrics by `archetype, geography, product_type, channel_mix`. Never use protected attributes as raw features; audit proxies (e.g., geography -> income).
* **Cross-environment correlation:** join across `accounts x products x channels` by `customer_id`; features must combine at least 3 sources (e.g., salary NEFT + UPI lending + billpay timing) — single-source flags are suppressed.
* **Automation:** `python run_all.py --scoring-date YYYY-MM-DD` reproduces raw -> features -> scores -> alerts -> dashboard data with one command. All seeds fixed.
* **Visualization:** every chart needs `n, date range, threshold` annotation; no black-box scores without reasons.
* **Scalability:** pandas MVP must handle 100k customers in <30 min; vectorize windows, avoid per-customer Python loops; profile with 20k first.

---

## 5. Timeline (solo, 10-12 working days)
| Day | Phase | Output |
|---|---|---|
| 1 | 0 + start 1 | skeleton + generator v0 |
| 2-3 | 1 | validated synthetic data + EDA |
| 4-5 | 2 | feature table + leakage tests |
| 6-8 | 3 | calibrated model + SHAP + model card |
| 9-10 | 4 | scoring + policy + templates |
| 11-12 | 5 | Dash + demo script + README |

If hackathon 48h: cut to 5k customers, 15 features, LightGBM only, 2 dashboard tabs (Portfolio + Customer 360).

---

## 6. Risks + Mitigations
* Leakage (future txns in features) -> point-in-time builder + unit test on max timestamp.
* Tiny positives -> enforce 8-12% rate in generator; use PR-AUC not accuracy; stratify reporting.
* Alert fatigue -> suppression + cap + Amber-nudge-only.
* Bias/fairness -> cohort audit, 80% rule, reason-code logging.
* Synthetic-to-real gap -> document assumptions in `model_card.md`; keep generator params in `config.yaml` so bank can recalibrate on real CBS dump without code change.
* Over-engineering streaming too early -> hard gate: no Kafka/Feast until batch targets met.

---

## 7. What to Run First (after approving this plan)
```powershell
Test-Path -LiteralPath "C:\Users\Yasotha Anumanthan\Desktop\work\preDeliquency"
# then scaffold files per Section 2.3, then:
python -m src.generator.generate --config config.yaml
python -m src.features.build --scoring-date 2024-11-01
python -m src.models.train
python -m src.scoring.score --scoring-date 2024-11-01
python src/dashboard/app.py
```

---

*End of plan. Next action: approve to scaffold code, starting with Phase 0 + Phase 1 generator.*
