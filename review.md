# preDeliquency — Code Review + Single Build Plan

**Repo:** `github.com/adhintra28/preDeliquency` @ `a1d061f` ("Mvp prototype phase 1")
**Reviewed:** 2026-09-03 · every file read · pipeline executed locally
**Verdict:** The plan documents are good. The code that exists does **not** solve the stated problem — it detects customers who have *already* missed an EMI. Treat the repo as a scaffold, keep ~30% of it, rebuild the data/label/feature core.

This file is the complete build specification. An agent can execute Stages 0–9 in order without reading anything else.

---

## Part A — What I actually ran

Cloned the repo, created a venv with `pandas, numpy, pyarrow, scikit-learn, pyyaml, python-dateutil`, set `n_customers: 300` for speed, and ran the pipeline end to end. `lightgbm`, `xgboost`, `shap`, and `mlflow` were not installed, so the code's `HistGradientBoostingClassifier` fallback was the champion. Every number in Part B is from that run, not from reading.

---

## Part B — Blocking defects (verified)

### B1. `run_all.py` produces zero alerts. The whole product is dead on a clean run.

`run_all.py` runs four steps: `generate → train → score → policy`. It never runs `src/features/build.py`. But `src/policy/engine.py` reads `data/processed/features_<date>.parquet` to count signal groups, and `src/scoring/score.py` builds features in memory and never writes them. So the file does not exist, `count_signal_groups(None)` returns `0`, and every single alert is suppressed.

```
$ python run_all.py            # generate, train, score, policy
tier
Green    261
Red       31
Amber      8
alerts=0 red=0 amber=0 suppressed=39
$ cut -d, -f3 data/outputs/suppressed_2024-11-01.csv | sort | uniq -c
  39 single_source_only:none
```

Adding the missing step by hand fixes it (`alerts=17 red=14 amber=3`). Nobody has ever run this pipeline start to finish.

### B2. It is a post-delinquency detector, not a pre-delinquency one.

`IMPLEMENTATION_PLAN.md` §1.1 says: *"Exclude customers already 30+ DPD at scoring time."* No code anywhere does this. The result:

```
population: 300 | already missed an EMI before scoring date: 56
P(label_28d=1 | prior miss) = 0.661
P(label_28d=1 | clean)      = 0.033
Red-tier customers who had already missed an EMI: 96.8%
```

A one-line rule — "has bounced before" — reaches 66% precision against a 3.3% base rate. The model adds nothing on top of it, and the product's entire premise (catch stress 2–4 weeks *before* the first miss) is untested. This is the most important finding in this document.

### B3. The generator injects a permanent stress regime, not a pre-miss window.

`gen_for_customer` sets `stress_start = start + (months - 4)` and then every subsequent month is stressed. The PRD (FR-1.4) asks for stress from `T-28d` to `T-7d` before the *first* miss. What is generated is a step-change at month 8 that never ends, so a stressed customer misses EMIs repeatedly for the last four months.

The consequence lands in the splits. Training snapshots are months 2, 5, 7 — all pre-stress, so positives there have no signal at all. Validation and test are months 8–11 — all in-stress:

```
train pos=0.066 | valid pos=0.118 | test pos=0.138
```

The model is trained on near-noise and evaluated on a different regime. Reported PR-AUC is meaningless.

### B4. Six of twenty-five features are constant. Including the flagship signal.

```
CONSTANT: salary_delay_vs_median, missing_salary_flag, utility_partial_ratio,
          gambling_flag, night_txn_ratio, tenure_months
```

- `salary_delay_vs_median = max(0, days_since_salary - 31)` — fires only if salary is >31 days late, which the generator never produces. **"Salary delay", the headline signal in the PRD, is not in the model.**
- `night_txn_ratio` is 1.0 for everyone: the generator writes date-only timestamps, so `.dt.hour` is always 0 and `(hour >= 22) | (hour <= 4)` is always true.
- `gambling_flag` and `utility_partial_ratio`: `gambling` and `savings_transfer` are declared in the schema and never generated; `utility_partial_ratio` is hardcoded `0.0` in `build.py`.
- `tenure_months` is `(year-2024)*12 + month - 1` — a raw calendar index, identical for every customer at a given snapshot and out-of-range at test time. Worse than useless: it leaks the snapshot date into the trees.

The committed `models/global_shap.csv` confirms what the model actually learned: `emi_to_income (1.78)`, `avg_balance_28d (1.51)`, `min_balance_14d (0.61)`. Static affordability and balance level. Not one of the seven stress signals appears in the top ten — because the generator's own miss rule is `can_pay = balance > emi * 1.05`, so the model correctly reverse-engineered the simulator.

### B5. Scoring ignores the tuned threshold.

`train.py` tunes a threshold and writes `"tuned_red": 0.1415` to `thresholds.json`. `score.py` reads `cfg["tiers"]["red_min"]` — `0.60` — and ignores the file. `risk_service.score_single_customer` reads `thresholds.json` but falls back to `red_min: 0.6`, which is also what is in the file. So there are two tiering paths that can disagree, and the tuned value is dead. The README quotes both numbers as if the system uses them.

### B6. Isotonic calibration saturates to 1.0.

Fitted on validation and applied to test, the calibrator emits exact `1.0` scores. Verified in the alerts output: `C000110, Red, 1.0`. A 28-day default probability of 1.0 is not a probability, and it corrupts `expected_loss = score * emi_amount`, which is the field the Red queue is ranked by. `IsotonicRegression` needs clipping to `[0.001, 0.999]` or a Platt/beta calibrator.

### B7. Explanations exist for the first 500 customers only.

`score.py` computes SHAP on `.iloc[:500]`. Beyond row 500, `reasons` is `[]`, the policy engine substitutes the literal string `"pressure on cash-flow"`, and that string is what the analyst and the customer see. PRD FR-4.1 ("every score carries `shap_top3_json`") is not met at any realistic portfolio size.

### B8. Validation data is used three times.

Champion selection, isotonic calibration, and threshold tuning are all fitted on the same validation split. Every reported gate number is optimistically biased. Separately, the same customers appear in train, validation, and test — only the snapshot date changes — so a customer's stressed identity is memorised in training and re-scored at test.

### B9. Amber→Red escalation is unreachable.

`amber_streak_days` walks back day by day looking for `risk_scores_<YYYY-MM-DD>.csv`. The pipeline only ever produces one file per run at monthly-ish snapshot dates, so `os.path.exists` fails on the first iteration and the function `break`s and returns 0. The escalation rule in FR-5.3 has never fired.

### B10. Security: the portal and the API are open.

| Issue | Location | Risk |
|---|---|---|
| No authentication on any API route | `src/serving/api.py` | Full portfolio, per-customer risk scores and EMI history readable by anyone who can reach port 8000 |
| `allow_origins=["*"]` | `api.py` L18 | Any web page can read the API from a logged-in browser |
| Customer can view any customer | `frontend/app.py` L82 — `customer_id` from the login form overrides the session identity | IDOR. Log in as the demo customer, type `C000123`, see their salary, balances, EMI history |
| Hardcoded credentials | `frontend/app.py` L28–34 | `bank123` / `risk123` / `cust123` in source, and prefilled in `login.html` |
| Default secret key | `PREDELINQ_SECRET` defaults to `"predelinq-prod-change-me"` | Session cookie forgery |
| `debug=True` | `frontend/app.py` L177 | Werkzeug console = remote code execution |
| No CSRF tokens | all POST forms | Approve, snooze, and offer actions are forgeable |

### B11. Data layer is CSV append with no keys and no locking.

`store.append_intervention` opens the log in `"a"` mode. The Flask portal, the FastAPI service, and the batch job all write to it concurrently with no lock — interleaved writes will corrupt rows. There is no `intervention_id`: `respond_to_offer` picks the customer's *last* row and assumes that is the open offer, so an accept can attach to the wrong offer. The header-migration branch rewrites the file mid-append and can duplicate or drop a header.

### B12. Tests do not test, and they mutate production data.

- `tests/test_pipeline.py::test_no_leakage` asserts `max(txn.timestamp) <= 2024-12-31`. That is a statement about the generator's date range, not about leakage. There is no leakage test in this repository.
- Every test requires generated data that is `.gitignore`d, so `pytest` fails on a fresh clone.
- `test_intervention_flow` writes real rows into `data/outputs/intervention_log.csv`. Running the suite pollutes the dataset the dashboard reads.
- No test covers: generator determinism, positive-rate bounds, suppression, the Red cap, calibration, or fairness.

### B13. Smaller but real

| # | Issue | Location |
|---|---|---|
| B13.1 | `upi_lending_app` is debited from balance. Borrowing should credit it. The `balance += 0` line and its comment acknowledge the shortcut and do nothing. | `generate.py` L60 |
| B13.2 | Generated positive rate is **15.0%**, outside the PRD's 8–12% band, and nothing checks it. | verified run |
| B13.3 | `emi_day` is hardcoded to `5` in `gen_customers`; `config.yaml: emi_day` is never read. | `generate.py` L32 |
| B13.4 | `labels.csv` is written for one scoring date only. `model_service` joins it to *any* scoring date and silently reports wrong metrics. | `model_service.py` L30 |
| B13.5 | `label_14d` is specified in the PRD and the plan and implemented nowhere. | — |
| B13.6 | `score_psi_halves` splits the score array by row order, not by time, so the "drift" metric and the `retrain_signal` derived from it are noise. | `model_service.py` L60 |
| B13.7 | `precision_at_red` runs `scores.iterrows()` inside a list comprehension over `scores` — O(n²). | `model_service.py` L52 |
| B13.8 | `policy/engine.py` filters `emis[emis.customer_id == cid]` inside the per-alert loop — O(alerts × emi_rows). | `engine.py` L138 |
| B13.9 | `imputer.pkl` and `shap_background.parquet` are required by FR-3.5 and never written. `fillna(0)` is used instead, which encodes "missing" as a real zero balance. | `train.py` |
| B13.10 | `model_card.md` is required by the PRD acceptance checklist and does not exist. | — |
| B13.11 | The `Recall@15% >= 0.70` gate is never enforced in code. The README reports 0.67 — a failing number — as a shipped result. | `train.py` |
| B13.12 | `StandardScaler` is fitted, never used, and its mean is pickled into the model bundle. | `train.py` L74 |
| B13.13 | `feature_repo/features.py` contains `"scoring_date" if False else "scoring_date"`, and points at a parquet that has no `scoring_date` column. `feast apply` will fail. | `features.py` L9 |
| B13.14 | `bento_service.py` uses `@svc.api` with no signature spec (not valid in BentoML 1.2+) and opens `models/production.pkl` at import time inside a `try/except ImportError` that will not catch the `FileNotFoundError`. | — |
| B13.15 | The Airflow DAG runs `score → policy` only. No generate, no features, no train. Wrapping a DAG file in `try/except ImportError` also hides real import errors from the scheduler. | `dags/nightly_score.py` |
| B13.16 | `models/thresholds.json` and `global_shap.csv` are committed while `models/*.pkl` is gitignored — the artifacts in git can never match the model in use. | `.gitignore` |
| B13.17 | `IMPLEMENTATION_PLAN.md` §7 contains a hardcoded Windows path with a personal name in it, and PowerShell commands in a cross-platform repo. | plan §7 |
| B13.18 | Per-customer Python loops in `build_snapshot` and `generate` directly contradict FR-2.1 ("no per-customer Python loops for scale"). Measured at 1.9 ms/customer — acceptable on time, but the whole transaction parquet is held in memory, which is the real limit at 100k × 12 months (~17M rows). | `build.py` L27 |
| B13.19 | The Amber SMS template renders `"Hi C000110, ..."`. Correct on privacy, unusable as customer copy. `due` is hardcoded to `"5th"`. | `engine.py` L23 |
| B13.20 | Red-queue cap silently drops alerts above top-K with no audit row, so a capped customer is indistinguishable from a never-flagged one. | `engine.py` L188 |

---

## Part C — Review of the three tracks in `IMPLEMENTATION_PLAN.md`

### C1. Local OSS track — sound, but under-specified in three places

What is right: batch-first, the hard gate against adopting Kafka/Feast/Airflow before the batch targets are met, time-based splits, PR-AUC over accuracy, suppression before more alerting.

| Gap | Fix |
|---|---|
| The plan never says to **exclude already-delinquent customers** in the *code*, only in §1.1 prose. This is exactly the requirement the implementation dropped. | Make it a schema-level filter with its own test (Stage 2, T2.3). |
| No **daily** scoring cadence, only monthly snapshots — yet suppression (`contacted_last_7d`) and escalation (`Amber × 7d`) both need daily history. The plan's own policy rules are incompatible with its own scoring frequency. | Generate a daily scoring calendar; the run loop is a date range, not a single date (Stage 6). |
| The scale-out table names swaps but no **parity test** between them. "Feast parity diff < 1e-6" appears in Phase 6 with no method. | Define parity as a golden-vector test (Stage 9). |
| Feature count is quoted as "~30" and delivered as 25, with no list reconciling the two. | Freeze an explicit feature contract (Stage 4). |

### C2. AWS track — currently decoration, not a plan

Every file under `aws/` is fully commented out. `sagemaker_feature_store.py`, `redshift.py`, `dynamodb_scores.py`, and `sns_notify.py` are referenced in `aws/README.md` and **do not exist**. What is there has deeper problems than being unfinished:

| Issue | Consequence |
|---|---|
| `SKLearn(entry_point="src/models/train.py")` | `train.py` reads local paths from `config.yaml` and writes local pickles. It cannot run as a SageMaker entry point without an S3 I/O rewrite. |
| Nine AWS services proposed for a batch job that scores a few thousand rows a day | Kinesis + Managed Flink + Feature Store + Redshift + DynamoDB + SNS + QuickSight is roughly $2–4k/month to replicate what one nightly container and Postgres already do. |
| No IaC, no VPC, no KMS, no IAM least-privilege, no data-residency note | This is retail lending data. In India that means RBI localisation; the config's `ap-south-1` is the only nod to it. |
| No cost, no SLA, no rollback, no DR | "Port to AWS" is not a plan without these. |

**Recommendation:** delete the streaming/Feature-Store/Redshift branch entirely. The signals are daily-cadence — a salary lands once a month, a utility bill once a month. Sub-second streaming buys nothing a nightly batch does not already deliver. The AWS target should be: **ECS Fargate scheduled task + RDS Postgres + S3 for artifacts + SES/SNS for outbound + the existing dashboard behind an ALB.** One page of Terraform. Keep SageMaker only if the bank's model-risk function requires a managed registry.

### C3. "Final production output" — this is the real hole

Neither document defines what *production* means. Missing entirely:

- **Deployment target.** Container? VM? Who runs it? Nothing is dockerised; there is no `Dockerfile` and no `docker-compose.yml`.
- **The bank data contract.** Everything runs on synthetic data with "documented assumptions for later recalibration". No field mapping to a core banking system, no ingestion path, no reconciliation rules. This is the single largest unknown between the demo and a pilot, and it has one line in the PRD's open questions.
- **How outreach is actually sent.** `alerts.csv` is described as "SNS-ready". There is no channel adapter, no delivery confirmation, no consent or DNC check, no rate limit, no quiet hours. In India, unsolicited financial messaging is regulated (TRAI DLT registration for SMS templates). Not mentioned anywhere.
- **Human-in-the-loop.** The Red queue has Approve/Snooze buttons. No maker-checker, no four-eyes on a restructure, no reason-for-override capture, no SLA on an unactioned alert.
- **Outcome measurement.** The PRD promises "Amber→Green cure rate vs no-contact baseline". Nothing holds out a control group or joins an intervention to a subsequent payment. Without this the business case is unfalsifiable.
- **Model governance runtime.** Model card, challenger promotion, drift-triggered retrain, and champion rollback are named in Phase 6 with no mechanism.
- **Retention and DSAR.** No retention policy, no deletion path, no PII inventory — on a system that stores per-customer financial behaviour and risk scores.

---

## Part D — The build plan

Ten stages. Each has a definition of done and exact tests. Do not start a stage until the previous stage's tests pass in CI.

**Global rules for the implementing agent**
1. One config, `config.yaml`, loaded through a single `src/config.py`. No literal thresholds, dates, or paths anywhere else.
2. Every stage adds tests to `tests/` and they run in CI on every commit.
3. `make all` reproduces everything from an empty `data/`. Same seed, same output hashes.
4. Deterministic seeds. `numpy.random.default_rng(seed)` per component, never a shared global.
5. Never `fillna(0)` a financial quantity. Missing is its own signal — impute with a persisted train-fit statistic and emit a `*_was_missing` indicator.
6. Anything that cannot be tested does not get built.

---

### Stage 0 — Foundation

**Build**
- `pyproject.toml` (replaces `requirements.txt`), `ruff` + `black`, Python 3.11 pinned.
- `src/config.py`: typed config loader with Pydantic `Settings`. Fails loudly on an unknown or missing key.
- `Makefile`: `install`, `lint`, `test`, `data`, `train`, `score`, `serve`, `all`.
- `Dockerfile` + `docker-compose.yml` (app + Postgres + MailHog).
- `.github/workflows/ci.yml`: lint → test → build image.
- `src/logging.py`: structured JSON logging with a `run_id` on every record.

**Tests**
| ID | Test |
|---|---|
| T0.1 | `make install && make lint && make test` passes on a clean clone with no data present. |
| T0.2 | Loading a config with an unknown key raises; loading with a missing required key raises. |
| T0.3 | `docker compose up` starts the app and Postgres; `/health` returns 200. |

---

### Stage 1 — Storage

Replace CSV-as-a-database. This must happen before anything writes state, or every later stage inherits B11.

**Build**
- Postgres via SQLAlchemy + Alembic. Tables: `customers`, `transactions`, `emi_schedule`, `features`, `risk_scores`, `alerts`, `suppressions`, `interventions`, `alert_actions`, `model_runs`, `outcomes`.
- Every operational table gets a surrogate primary key. `interventions.intervention_id` is **mandatory** — B11 exists because it is missing.
- `risk_scores`, `alerts`, `interventions` are append-only with `(entity_id, valid_from, valid_to)`; nothing is ever updated in place.
- Rewrite `src/services/store.py` against the ORM, keeping its function signatures so callers do not change.
- Parquet stays for the immutable raw generator output and for feature snapshots only.

**Tests**
| ID | Test |
|---|---|
| T1.1 | Alembic migrates up and down cleanly on an empty database. |
| T1.2 | 50 concurrent `append_intervention` calls from 10 threads produce exactly 50 rows with 50 distinct ids. (Fails today.) |
| T1.3 | Updating an append-only table raises. |
| T1.4 | `respond_to_offer(intervention_id=X)` attaches the response to X, never to the customer's latest row. |
| T1.5 | Every `store` function returns an empty typed frame, not an exception, when the table is empty. |

---

### Stage 2 — Generator rebuild

Fixes B2, B3, B13.1–B13.3.

**Build** — `src/generator/`
- **Stress is a window, not a regime.** For each customer that will default, pick a `first_miss_date`, then inject stress only over `[first_miss - 28d, first_miss - 7d]` per FR-1.4. Recovery ("cure") paths for a configurable share of stressed customers, so the model sees stress that does not end in a miss.
- **Hourly timestamps.** Sample a plausible hour per transaction type. Fixes `night_txn_ratio`.
- **Emit every declared type.** Add `savings_transfer` and `gambling`, or delete them from the schema. Do not keep dead enum members.
- **Correct signs.** `upi_lending_app` credits the balance; the downstream spend debits it.
- **Weaken the deterministic miss rule.** Today `can_pay = balance > emi * 1.05` makes balance the only real cause. Replace with a probabilistic hazard driven by the seven stress signals plus noise, so no single feature is a giveaway.
- Read `emi_day` from config. Enforce the 8–12% positive rate in code and fail the build outside it.
- Emit `labels` for **both** 14d and 28d horizons, for **every** scoring date, not one.

**Tests**
| ID | Test |
|---|---|
| T2.1 | Same seed → identical SHA-256 of every output file. Different seed → different. |
| T2.2 | Positive rate is within 8–12% at every scoring date, asserted, not printed. |
| T2.3 | **No customer with a missed EMI on or before the scoring date appears in that date's scoring population.** (The B2 regression guard.) |
| T2.4 | ≥90% of positives show ≥2 distinct stress signals in the 28 days before the first miss (PRD acceptance). |
| T2.5 | ≥95% of negatives show ≤1 stress signal in any 28-day window. |
| T2.6 | Transaction hours span ≥8 distinct values. |
| T2.7 | Every `txn_type` in the schema enum appears at least once. |
| T2.8 | A `upi_lending_app` transaction raises `balance_after`. |
| T2.9 | The running `balance_after` equals the cumulative signed sum of successful transactions, per customer. |
| T2.10 | Failed transactions never move the balance. |
| T2.11 | A customer with a cure path shows stress and then no miss. |

---

### Stage 3 — Label + population contract

Split out of Stage 2 because it is where the product definition lives.

**Build** — `src/labels/build.py`
- `eligible_population(scoring_date)` → customers with `0 DPD` and no bounce in the trailing 90 days. Everything downstream consumes this, never the raw customer table.
- `label_14d` and `label_28d` from the forward window, with an explicit `observation_end` so the last 28 days of history are censored, not silently labelled 0.
- Persist an eligibility audit row per customer per date with the exclusion reason.

**Tests**
| ID | Test |
|---|---|
| T3.1 | An excluded customer never appears in features, scores, or alerts for that date. |
| T3.2 | Customers within 28 days of the data horizon are censored, not labelled negative. |
| T3.3 | `label_14d = 1` implies `label_28d = 1`, always. |
| T3.4 | A naive "prior miss" baseline scores **≤ 0.15 PR-AUC** on the eligible population. This is the test that proves B2 is dead; it currently reaches 0.66. |
| T3.5 | Eligible population size and positive rate are stable (±2%) across scoring dates. |

---

### Stage 4 — Features

Fixes B4, B8, B13.9.

**Build** — `src/features/`
- A frozen `FEATURE_CONTRACT`: name, dtype, window, group, allowed range, null policy. Tests read this, not a bare list.
- Rewrite `build_snapshot` as vectorised groupby-rolling over the whole frame. No per-customer Python loop.
- Fix the broken definitions: `salary_delay_vs_median` compares to the customer's own trailing 6-month median pay date, not to a fixed 31; drop or genuinely compute `utility_partial_ratio`; drop `tenure_months` (calendar leakage) and replace with `months_on_book` from an origination date.
- Add what the plan promised and the code lacks: `new_lender_cnt`, `channel_mix_entropy`, `salary_to_emi_buffer_days`.
- Encode `archetype`, `geography`, `product_type` as model inputs. Right now they are merged in and never used, so the "environment-aware" requirement is unmet.
- `Imputer` fitted on train only, persisted to `imputer.pkl`, with a `*_was_missing` indicator per imputed column.

**Tests**
| ID | Test |
|---|---|
| T4.1 | **Leakage.** For a snapshot at `t`, append synthetic transactions dated `t+1..t+30`, rebuild, and assert every feature value is byte-identical. (A real leakage test; today's is a date-range assertion.) |
| T4.2 | **No constant features.** Every feature in the contract has `nunique() > 1` across the population. (Six fail today.) |
| T4.3 | Null rate < 5% per feature (FR-2.4). |
| T4.4 | Vectorised output matches a slow reference loop implementation to 1e-9 on 100 customers. |
| T4.5 | Fitting the imputer on train and applying to test never reads a test statistic — asserted by fitting on a shifted dataset and comparing. |
| T4.6 | Rebuilding the same snapshot twice is identical. |
| T4.7 | Every feature value is within its contract range. |
| T4.8 | 10k customers × 12 months builds in under 60 seconds and under 2 GB RSS. |

---

### Stage 5 — Model

Fixes B6, B8, B11, B13.11.

**Build** — `src/models/`
- **Split by customer *and* by time.** Disjoint customer sets across train/valid/test, and disjoint date ranges. Fixes the memorisation half of B8.
- Three splits, three jobs: **train** fits the model; **calibration** fits the calibrator *only*; **test** is touched once, at the end, for the gate. Threshold tuning happens on calibration, never on test. Fixes the rest of B8.
- Clip calibrated output to `[0.001, 0.999]`. Fixes B6.
- LightGBM champion with real early stopping (`callbacks=[lgb.early_stopping(50)]`, `eval_metric="average_precision"`), XGBoost challenger.
- Report every metric FR-3.2 asks for: PR-AUC, ROC-AUC, Recall@10%/15%, Precision@Red, KS, Brier, Expected Loss Saved. Sliced by archetype, geography, and product.
- **A failing gate exits non-zero.** `Recall@15% >= 0.70`, calibration slope in `[0.9, 1.1]`, flagged ≤ 15%. The current code prints a failing 0.67 and saves the model anyway.
- Generate `model_card.md` from the run: data lineage, metrics, cohort slices, fairness table, known limitations, MLflow run id.
- Artifacts to S3/disk under a run id: `model.pkl`, `imputer.pkl`, `calibrator.pkl`, `thresholds.json`, `shap_background.parquet`, `feature_contract.json`, `model_card.md`.

**Tests**
| ID | Test |
|---|---|
| T5.1 | Customer id sets across train/valid/test are pairwise disjoint. |
| T5.2 | Date ranges across splits do not overlap. |
| T5.3 | A model trained on shuffled labels scores PR-AUC ≈ base rate. (Catches leakage that T4.1 misses.) |
| T5.4 | Calibrated scores are strictly inside `(0, 1)`. (Fails today: 1.0 is emitted.) |
| T5.5 | Calibration slope on the held-out test split is within `[0.9, 1.1]`. |
| T5.6 | A gate failure exits non-zero and writes no `production.pkl`. |
| T5.7 | The bundle's feature list equals `FEATURE_CONTRACT`, in order. |
| T5.8 | Retraining on the same seed and data reproduces test PR-AUC to 1e-6. |
| T5.9 | At least 4 of the 7 required stress signals appear in the top 10 by global SHAP. (Today: zero.) |
| T5.10 | `model_card.md` is generated and contains every required section. |

---

### Stage 6 — Scoring + policy

Fixes B1, B5, B7, B9, B13.20.

**Build**
- `src/scoring/score.py` **persists the feature snapshot** it builds. Fixes B1 at the source rather than patching `run_all.py`.
- Thresholds come from `thresholds.json` — one source of truth, used identically by batch scoring and the single-customer API path. Fixes B5.
- SHAP for **all** rows via `TreeExplainer` on the full matrix (vectorised, not a 500-row slice). Fixes B7.
- **Daily scoring calendar.** `score --from <date> --to <date>` writes one row set per day, which is what suppression and escalation need. Fixes B9.
- Policy engine rewritten as pure functions over a features frame — no per-row DataFrame filtering. Fixes B13.8.
- Every suppressed *and* every capped customer gets an audit row with a reason. Fixes B13.20.
- Idempotency: re-running a date replaces that date's rows in one transaction, or fails and leaves the prior output intact (NFR "Reliability").

**Tests**
| ID | Test |
|---|---|
| T6.1 | **`make all` from an empty `data/` produces a non-empty `alerts` table.** The direct B1 regression guard. |
| T6.2 | Every scored customer has exactly 3 non-empty reasons. (Fails beyond row 500 today.) |
| T6.3 | Batch tier for customer X equals `POST /api/scores/single` tier for X, on the same date. |
| T6.4 | Suppression: a customer contacted 3 days ago is suppressed; 8 days ago is not. |
| T6.5 | Escalation: 7 consecutive Amber days promotes to Red on day 8; a Green day in between resets the streak. (Unreachable today.) |
| T6.6 | Red cap: with `red_cap_per_day=10` and 50 Reds, exactly 10 alert and 40 carry a `capped` audit row. |
| T6.7 | Multi-signal gate: a single-group customer is suppressed; a two-group customer is not. |
| T6.8 | Flagged rate ≤ 15% of the eligible population. |
| T6.9 | Re-running a scoring date twice leaves identical output and no duplicate rows. |
| T6.10 | A mid-run failure leaves the previous day's outputs untouched. |
| T6.11 | 100k customers × 1 scoring date completes in under 30 minutes (NFR). |
| T6.12 | No rendered message contains a name, phone number, or account number. |

---

### Stage 7 — API + auth

Fixes B10.

**Build**
- OAuth2 password flow with JWT. Roles: `analyst`, `risk_manager`, `customer`, `service`.
- **Every** route authenticated. `customer` role is scoped to its own `customer_id`, derived from the token and never from a request parameter. Fixes the IDOR directly.
- CORS restricted to the portal origin from config.
- Rate limiting (SlowAPI), request id propagation, `/metrics` for Prometheus.
- Users move to the database with bcrypt hashes. Delete the hardcoded dictionary and the prefilled login form.
- Audit log: every state-changing call records actor, action, target, timestamp, before/after.

**Tests**
| ID | Test |
|---|---|
| T7.1 | Every route returns 401 without a token. Enumerate the route table so a new route cannot skip this. |
| T7.2 | A `customer` token requesting another customer's id returns 403. (Currently 200 with full data.) |
| T7.3 | An `analyst` token cannot promote a model or edit thresholds. |
| T7.4 | An expired token returns 401; a tampered signature returns 401. |
| T7.5 | A cross-origin request from a non-allowlisted origin is rejected. |
| T7.6 | Exceeding the rate limit returns 429. |
| T7.7 | Every mutating endpoint writes exactly one audit row. |
| T7.8 | No 5xx contains a stack trace or a file path. |
| T7.9 | POST without a CSRF token on the portal returns 400. |

---

### Stage 8 — Portal, dashboard, outcomes

**Build**
- Rebuild the Flask portal against the API (it currently imports services directly, so authorisation would be bypassable).
- Add the missing pages in Part E.
- **Outcome tracking** — the gap that makes the business case unfalsifiable today. A holdout control group at assignment time, an `outcomes` table joining intervention → next EMI result, and a cure-rate report of treated vs control.
- Notification adapters behind one `notification_service` interface: console, email, SMS. Consent check, DNC list, quiet hours, per-customer rate limit.

**Tests**
| ID | Test |
|---|---|
| T8.1 | Every page renders with an empty database (no exception, an empty state). |
| T8.2 | Every page renders with data, for each of the three roles. |
| T8.3 | A customer-role session cannot reach any `/bank/*` route. |
| T8.4 | An offer created in the portal appears via `GET /api/interventions` with a matching `intervention_id`. |
| T8.5 | The control group receives no outreach and still accrues outcome rows. |
| T8.6 | Cure rate is computed only over customers with a matured 28-day window. |
| T8.7 | A customer on the DNC list is never sent to. |
| T8.8 | Outreach outside quiet hours only; a queued message sends at the next allowed slot. |
| T8.9 | Queue CSV export column set matches the on-screen table. |

---

### Stage 9 — Production hardening

**Build**
- Terraform: ECS Fargate scheduled task, RDS Postgres, S3 artifacts, Secrets Manager, ALB, CloudWatch alarms. **Not** Kinesis, Flink, Feature Store, Redshift, or DynamoDB — see C2.
- Drift monitoring: per-feature PSI against the training distribution, score-distribution PSI over time, alert at PSI > 0.2. (The current halves-of-an-array metric is meaningless.)
- MLflow registry with Champion/Challenger, a shadow-scoring window before promotion, and one-command rollback.
- Retention policy, PII inventory, DSAR deletion path.
- Runbook: what to do when a run fails, when drift fires, when the gate fails on retrain.

**Tests**
| ID | Test |
|---|---|
| T9.1 | `terraform plan` is clean; `apply` into a sandbox account produces a working scheduled run. |
| T9.2 | Injecting a synthetic distribution shift raises PSI above 0.2 and fires the alert. |
| T9.3 | Promoting a challenger and then rolling back restores byte-identical scores. |
| T9.4 | A shadow-scored challenger writes scores but drives no alerts. |
| T9.5 | A DSAR deletion removes the customer from every table and leaves aggregate metrics computable. |
| T9.6 | A killed run leaves no partial state; the next run succeeds. |
| T9.7 | No secret appears in any image layer, log line, or environment dump. |

---

## Part E — Complete inventory to build

### E1. Services

| Service | Status | Responsibility |
|---|---|---|
| `store` | rewrite | ORM data access. Currently CSV with no keys or locking (B11). |
| `risk_service` | keep, fix | Portfolio, search, 360, single-score. Remove the direct model load; call `model_service`. |
| `intervention_service` | rewrite | Offers keyed by `intervention_id`. Currently guesses the open offer from the last row. |
| `model_service` | rewrite | Metrics against the correct per-date labels (B13.4); real per-feature PSI (B13.6); fairness. |
| `auth_service` | **new** | JWT issue/verify, roles, scoping. |
| `audit_service` | **new** | Immutable actor/action/target log for SR 11-7. |
| `notification_service` | **new** | Channel adapters, consent, DNC, quiet hours, rate limit. |
| `feature_service` | **new** | One entry point for feature building, shared by batch and online. Prevents batch/online skew. |
| `explain_service` | **new** | SHAP on demand for a single customer; today explanations exist only for the first 500 rows. |
| `outcome_service` | **new** | Control assignment, cure-rate measurement, uplift. |
| `run_service` | **new** | Pipeline run registry: run id, status, lineage, artifact pointers. |
| `config_service` | **new** | Threshold and policy changes as versioned, audited records instead of a hand-edited YAML. |
| `eligibility_service` | **new** | The `0-DPD` population filter from Stage 3. The missing piece behind B2. |

### E2. Endpoints

Existing (all need auth added):
`GET /health` · `GET /api/portfolio/summary` · `GET /api/customers/search` · `GET /api/customers/{id}` · `GET /api/scores` · `POST /api/scores/single` · `GET /api/alerts` · `POST /api/alerts/{id}/action` · `GET /api/interventions` · `POST /api/interventions` · `POST /api/interventions/respond` · `GET /api/model/health` · `GET /api/model/fairness` · `GET /api/model/thresholds` · `GET /api/model/acceptance`

To add:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/token` | Issue JWT |
| `POST` | `/api/auth/refresh` | Refresh |
| `GET` | `/api/auth/me` | Current identity and role |
| `POST` | `/api/scores/batch` | Score a list of customers |
| `GET` | `/api/customers/{id}/features` | Feature row with contract metadata |
| `GET` | `/api/customers/{id}/explain` | On-demand SHAP, replaces the 500-row cap |
| `GET` | `/api/customers/{id}/timeline` | Split out of the heavy 360 payload |
| `GET` | `/api/customers/{id}/outcomes` | Interventions joined to subsequent EMI results |
| `GET` | `/api/alerts/{id}` | Single alert with full audit trail |
| `POST` | `/api/alerts/{id}/escalate` | Manual escalation with a reason |
| `GET` | `/api/alerts/export` | Server-side CSV/XLSX |
| `GET` | `/api/suppressions` | Suppressed and capped customers with reasons — built, never exposed |
| `GET` | `/api/interventions/{id}` | By id. No id exists today. |
| `PATCH` | `/api/interventions/{id}` | Status transition with audit |
| `POST` | `/api/interventions/{id}/approve` | Maker-checker second approval |
| `GET` | `/api/runs` · `/api/runs/{id}` | Pipeline run history, status, lineage |
| `POST` | `/api/runs/trigger` | Manual run (risk_manager only) |
| `GET` | `/api/model/card` | Rendered model card |
| `GET` | `/api/model/versions` | Registry listing |
| `POST` | `/api/model/promote` | Challenger → champion |
| `POST` | `/api/model/rollback` | Restore prior champion |
| `GET` | `/api/model/drift` | Per-feature PSI series |
| `GET` | `/api/config/thresholds` · `PUT` | Versioned, audited threshold changes |
| `GET` | `/api/outcomes/cure-rate` | Treated vs control |
| `GET` | `/api/audit` | Audit log query |
| `GET` | `/metrics` | Prometheus |
| `POST` | `/api/customers/{id}/consent` | Contact consent |
| `DELETE` | `/api/customers/{id}/data` | DSAR deletion |

### E3. Pages

Existing: `/` login · `/bank` portfolio · `/bank/queue` · `/bank/customer/<id>` · `/bank/model` · `/bank/interventions` · `/customer`

To add:

| Route | Role | Purpose |
|---|---|---|
| `/bank/suppressed` | analyst | Why customers were *not* alerted — the trust surface for a suppression-heavy design, currently invisible |
| `/bank/cohorts` | risk | Slice metrics by archetype, geography, product |
| `/bank/outcomes` | risk | Cure rate, treated vs control, acceptance by offer type |
| `/bank/runs` | risk | Run history, status, lineage, manual trigger |
| `/bank/model/card` | risk | Rendered model card |
| `/bank/model/drift` | risk | PSI charts, retrain recommendation |
| `/bank/model/versions` | risk | Registry, promote, rollback |
| `/bank/config` | risk | Threshold and policy editor with an audit trail |
| `/bank/audit` | risk | Searchable audit log |
| `/bank/customer/<id>/history` | analyst | Score trajectory over time — the 2–4 week ramp is the whole product story and there is no view of it |
| `/customer/offers` | customer | Offer detail with terms before accepting |
| `/customer/history` | customer | Past requests and outcomes |
| `/customer/consent` | customer | Contact preferences, opt-out |
| `/403`, `/404`, `/500` | all | Error pages that leak nothing |

### E4. Data contracts to freeze in Stage 0

`feature_contract.json` (name, dtype, window, group, range, null policy) · `event_schema.json` (transaction envelope for future ingestion) · `alert_payload.json` (what a channel adapter receives) · `model_bundle.json` (artifact manifest with hashes).

---

## Part F — Delete, do not port

| Delete | Why |
|---|---|
| `src/streaming/kafka_io.py` | Two functions that both `raise NotImplementedError`. Signals are daily-cadence; streaming buys nothing. |
| `aws/kinesis_ingest.py` | Same, in AWS form. |
| `feature_repo/` (Feast) | 28 lines with a dead `if False` expression, pointed at a parquet lacking the timestamp column it names. A Postgres feature table serves batch and online at this scale. |
| `src/models/sequence_model.py` | An untrained LSTM class. The plan's own gate says skip unless the GBM lands under 0.40 PR-AUC. |
| `src/serving/bento_service.py` | The FastAPI app already serves the model; two serving stacks is one too many. |
| `aws/data_notify_store.py`, `aws/sagemaker_train_deploy.py` | Fully commented, and the entry point they name cannot run under SageMaker. Replace with the Terraform in Stage 9. |
| `models/thresholds.json`, `models/global_shap.csv` | Committed artifacts that can never match a gitignored model. Generate into an artifact store keyed by run id. |
| `StandardScaler` in `train.py` | Fitted, unused, pickled. |

Roughly 400 lines of the 2,890 exist to make a technology checklist look complete. Cutting them makes the remaining system easier to defend in a model-risk review, not weaker.

---

## Part G — Order of work

**Correctness before features.** Stages 2 and 3 are the whole review: until the population excludes already-delinquent customers and the generator injects stress as a pre-miss *window*, every metric produced downstream is measuring the wrong thing, and a better dashboard on top of it is worse than none.

| Priority | Stages | Rationale |
|---|---|---|
| P0 | 2, 3 | B2 and B3. Without these the product does not exist. |
| P0 | 1 | Storage before anything writes state. |
| P1 | 4, 5 | B4, B6, B8. Real features, honest evaluation. |
| P1 | 6 | B1, B5, B7, B9. Make the pipeline actually produce alerts. |
| P2 | 7 | B10. Required before any real data touches the system. |
| P2 | 8 | Outcome measurement — otherwise the business case is unfalsifiable. |
| P3 | 9 | Deployment and governance. |

Stage 0 runs first regardless.

---

*One check that summarises this review: T3.4. A "has this customer missed before" baseline must score at or below 0.15 PR-AUC on the eligible population. Today it scores 0.66, and the trained model is not meaningfully beating it.*
