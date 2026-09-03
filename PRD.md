# PRD — Pre-Delinquency Early Warning Engine

> Companion to `IMPLEMENTATION_PLAN.md` (build phases, schemas, commands).
> This PRD defines **what** we build and **why**; the implementation plan defines **how** and **when**.
> Status: Draft v1.0 | Owner: preDeliquency team | Audience: builders, reviewers, bank stakeholders

---

## 1. Background & Problem

Banks intervene only after a missed EMI/credit-card payment, when recovery probability has already collapsed. Post-delinquency collections cost 15–20% of recovered amounts, damage relationships, and come too late.

Financial stress is visible weeks earlier — delayed salary credits, savings drawdown, late utility payments, reduced discretionary spend, ATM cash hoarding, lending-app borrowing, failed auto-debits — but signals are scattered across product silos and channels with no unified predictive view. Outreach is generic, resource-heavy, and often ignored. Regulators expect explainable, fair, consistent pre-delinquency treatment.

Opportunity: a platform-agnostic engine that unifies cash-flow + behavioral signals, predicts `P(default in 14/28d)`, and triggers timely, empathetic, channel-agnostic outreach (nudge, payment-holiday, restructuring) before the miss.

## 2. Goals & Non-Goals

### Goals (MVP)
1. Score every currently-clean customer daily for 28-day (primary) and 14-day (secondary) default risk.
2. Detect all 7 required signals: salary delay, savings WoW decline, UPI-to-lending-app spike, utility lateness, discretionary drop, ATM hoarding, auto-debit fails.
3. Tier into Green/Amber/Red with suppression so flagged rate <= 15% and collections team is not spammed.
4. Attach top-3 plain-language reasons + audit log to every Red alert.
5. Demonstrate payment-holiday / split / restructure offer flow with accept/decline tracking.
6. Provide Dash dashboard: portfolio view, customer 360, alerts queue, model health.

### Non-Goals (MVP explicitly out)
* Real-time <1s scoring, Kafka/Kinesis streaming, Flink/Spark Streaming.
* Airflow production cluster, Feast/SageMaker Feature Store, SageMaker training/hosting, Redshift, DynamoDB, SNS, QuickSight.
* Deep sequence models (LSTM/Transformer) unless LightGBM PR-AUC < 0.40.
* Automated GenAI decisions; GenAI used only for message wording with templates + guardrails.
* Direct CBS/core-banking integration; MVP runs on purpose-built synthetic data with documented assumptions for later recalibration.

## 3. Users & Stakeholders

| User | Needs | PRD implication |
|---|---|---|
| Risk / collections analyst | Prioritized queue, reasons, expected loss, snooze/approve | Alerts queue tab, cap top-K/day, suppression rules |
| Risk manager / model risk | Performance, drift, fairness, SR 11-7 pack | Model health tab, model card, cohort audits |
| Customer (borrower) | Empathetic, relevant, non-threatening help before miss | Amber=nudge, Red=choice of offers, plain language |
| Compliance / legal | Explainable, fair, consistent, auditable | Reason codes, 80% rule audit, intervention log |
| Engineering | One-command reproduce, seeded, tested | `run_all.py`, point-in-time features, pytest gates |

## 4. Scope

### In scope (MVP batch)
* Synthetic generator (20k customers x 12mo default; 5k fast mode for hackathon), flat Parquet/CSV per schemas in implementation plan Section 2.3.
* Feature builder: ~30 features across 7d/14d/28d + WoW, point-in-time correct.
* Model: LightGBM champion + XGBoost challenger, isotonic calibration, MLflow tracking, SHAP explanations.
* Scoring + policy engine: tiers, suppression, escalation, daily cap, intervention templates + log.
* Dashboard: 4 tabs + demo script (3 stressed customers T-28d -> Amber -> Red -> offer -> cure).
* Tests + docs: leakage test, policy test, schema test, model card, README.

### Out of scope (Phase 6+)
Streaming ingestion, online feature store, API serving with SLA, multi-product cross-sell, bureau integration, multilingual NLP, mobile app.

## 5. Functional Requirements

### FR-1 Data (synthetic, but production-shaped)
* FR-1.1 Tables: `customers, transactions, emi_schedule, labels` with columns/types per implementation plan Phase 0.
* FR-1.2 History: 12 months default; scoring date configurable; all feature inputs `timestamp <= scoring_date`.
* FR-1.3 Archetypes: `salaried_stable 50%, salaried_stressed 20%, gig 12%, SME 8%, pensioner 10%` (configurable).
* FR-1.4 Stress injection T-28d..T-7d before first miss: salary +3..10d late, savings -15% WoW x2wks, lending-app >=2/wk, utility 12->25th, discretionary -40%, ATM 2x, 1-2 autodebit fails.
* FR-1.5 Positive rate 8-12%; seeded reproducibility (same seed -> same hashes); EDA notebook validates coverage.
* FR-1.6 PII: hashed IDs only; no names/phones in data files (templates inject mock names at render only).

### FR-2 Features
* FR-2.1 Single entry `build_snapshot(transactions, emi, scoring_date)`; no per-customer Python loops for scale.
* FR-2.2 Groups: income (4), liquidity (5), discipline (4), borrowing (3), behavioral (4), cash (3), context (7) ≈ 30 features.
* FR-2.3 Imputation stats fit on train only; persisted as `imputer.pkl`.
* FR-2.4 Null rate <5% per feature; correlation review in notebook.

### FR-3 Modeling
* FR-3.1 Time splits: train 1-8mo, valid 9-10mo, test 11-12mo; never random split.
* FR-3.2 Optimize PR-AUC; report ROC-AUC, Recall@10%/15%, Precision@Red, KS, Brier, Expected Loss Saved.
* FR-3.3 Gate: `Recall@15% >= 0.70` on test, calibration slope 0.9-1.1, flagged <=15%.
* FR-3.4 Thresholds tuned on valid, frozen in `thresholds.json` (`<0.30 Green, 0.30-0.60 Amber, >0.60 Red` defaults).
* FR-3.5 Artifacts: `production.pkl, imputer.pkl, thresholds.json, shap_background.parquet`, MLflow IDs in model card.

### FR-4 Explainability & Fairness
* FR-4.1 Every score carries `shap_top3_json` with feature, value, contribution.
* FR-4.2 Mapping to plain language (e.g., "Salary 7 days late vs usual", "Savings down 22% WoW", "2 short-term borrowing txns this week").
* FR-4.3 Global SHAP bar + cohort SHAP (archetype/geography/product); 5 individual force plots in notebook.
* FR-4.4 Fairness: flagged-rate by geography/archetype with 80% rule; investigate gaps >20%; no protected attribute as raw feature.
* FR-4.5 Audit: `risk_scores` + `intervention_log` append-only with model version, thresholds, timestamp.

### FR-5 Scoring & Alert Policy
* FR-5.1 Daily batch `score.py --scoring-date` writes `risk_scores(customer_id, scoring_date, score, tier, shap_top3_json, model_version)`.
* FR-5.2 Suppression: skip if `contacted_last_7d OR in_hardship OR emi_due_in_2d_and_balance_ok`; single-source flags suppressed (require >=2 signal groups).
* FR-5.3 Escalation: Amber x7d -> Red; Red queue capped top-K/day by `expected_loss = score * emi_amount`.
* FR-5.4 Cross-environment correlation: features/alerts must join >=3 sources (e.g., NEFT salary + UPI lending + billpay); single-channel spikes do not trigger Red alone.

### FR-6 Interventions (empathetic, channel-agnostic)
* FR-6.1 Amber template (auto, no human): nudge + reminder/split option.
  > "Hi {name}, we noticed {reason_1}. Your EMI of Rs.{amt} is due {date}. Want a reminder or to split it? [Remind / Split]"
* FR-6.2 Red offers (human-approved queue): `payment-holiday (1 EMI pause, no late fee) / EMI split x2 / tenure +3mo`. Customer picks; log choice.
* FR-6.3 GenAI only for phrasing variants within approved templates; decision, tier, and offer eligibility are rules + model only.
* FR-6.4 Log: `intervention_log(customer_id, date, tier, reasons, offer, channel, accept/decline, model_version)`.

### FR-7 Dashboard (Dash MVP)
* FR-7.1 Portfolio: donut, tier migration, flagged-vs-DPD lift, PR curve; annotate n, dates, thresholds.
* FR-7.2 Customer 360: search by ID; balance curve + salary markers, utility strip, discretionary trend, SHAP waterfall, EMI table + mock offer buttons.
* FR-7.3 Queue: sortable/filterable `score, tier, top_reason, emi, expected_loss, Approve/Snooze`, CSV export.
* FR-7.4 Model health: PR-AUC trend, PSI per feature, score drift, fairness gaps.
* FR-7.5 Loads locally via `python src/dashboard/app.py`; demo path works without internet.

## 6. Non-Functional Requirements

| Category | Requirement | Rationale |
|---|---|---|
| Performance | 100k customers batch <30 min laptop; dashboard search <2s; future API p95 <200ms | Operational efficiency, no manual toil |
| Reproducibility | `run_all.py --scoring-date` end-to-end; fixed seeds; MLflow lineage | Audit + SR 11-7 |
| Reliability | Idempotent reruns; failed run leaves prior outputs intact; all outputs timestamped + versioned | Safe nightly ops |
| Data quality | Leakage test + schema test in CI/pytest; null/drift alerts | Prevent silent corruption |
| Security/privacy | No real PII; hashed IDs; templates render names ephemerally; logs exclude full account numbers | Compliance |
| Explainability latency | SHAP top-3 precomputed in batch; single-row LIME/FastSHAP <1s for ad-hoc | Usable queue |
| Maintainability | pandas + sklearn stack only in MVP; new feature = 1 function + 1 test + notebook cell | Avoid MLOps sprawl |
| Portability | All bank-specific thresholds in `config.yaml`; generator params swappable for real CBS dump | Platform-agnostic |

Scale-out NFRs (Phase 6): online p95 <100ms via Valkey/Redis, Feast parity diff <1e-6, PSI>0.2 auto-retrain trigger — not gated for MVP.

## 7. UX Principles

* Calm, supportive tone; never accusatory ("we noticed pressure" not "you are risky").
* Every risk number shows reasons; no bare scores.
* Fewer, better alerts: suppression + cap over exhaustive flagging.
* Context-aware: same score reads differently for gig vs salaried (show archetype + channel mix).
* One-click next action from every view (Remind / Offer / Snooze / Export).

## 8. Metrics & Acceptance

### Product metrics
* `Recall@15% >=0.70`, `Precision@Red >=0.35`, `PR-AUC >0.45` (test, out-of-time).
* Flagged <=15%/day; Red queue <=200/day default; suppression rate tracked.
* Intervention log completeness 100%; offer accept rate + simulated cure rate reported.

### Business proxies (synthetic)
* Expected Loss Saved per 10k customers; collections-cost-avoided estimate (15-20% of saved recoveries).
* Amber->Green cure rate vs no-contact baseline (simulated A/B in log).

### Acceptance checklist
* [ ] Generator hash reproducible; EDA shows >=90% of positives have >=2 stress signals pre-miss.
* [ ] Leakage test passes; thresholds frozen; calibration in range.
* [ ] 3 demo customers traceable T-28d -> Amber -> Red -> offer.
* [ ] Dashboard runs offline; queue exports CSV; model card + fairness table present.
* [ ] `run_all.py` reproduces outputs from clean `data/` in one command.

## 9. Risks, Assumptions, Open Questions

| Risk/Assumption | Mitigation / Decision needed |
|---|---|
| Synthetic-to-real gap | Document all distributions in model card; keep `config.yaml` tunable; plan recalibration on real dump |
| Alert fatigue | Suppression + cap + Amber auto-only; track snooze rate |
| Proxy bias (geography -> income) | Cohort audit; drop/constrain; 80% rule gate |
| Overbuilding streaming early | Hard gate in implementation plan; MVP batch only |
| GenAI hallucinations | Template-locked wording; no GenAI in scoring/policy |
| Small positives | Enforce 8-12% in generator; PR-AUC focus; stratified eval |

Open questions for stakeholders: real CBS field mapping (salary code? UPI MCC? bounce code?), EMI-holiday business rules, contact channel priority (SMS/app/call), Hindi/regional template needs, model-risk documentation depth for pilot.

## 10. Rollout Plan

* v0.1 (MVP, 10-12d): batch + Dash + docs; demo on synthetic; internal review vs acceptance checklist.
* v0.2: Airflow nightly, Feast+Redis parity, BentoML `/score`, drift monitors.
* v0.3: AWS port (Kinesis, SageMaker FS/training/endpoint, DynamoDB, SNS, QuickSight) behind feature flag; A/B vs batch.
* v1.0 pilot: recalibrate on anonymized real extract; SR 11-7 pack export; limited live cohort with control group.

## 11. Traceability to Brief

* Data Analytics, Predictive Analytics, Cross-Environment Correlation -> FR-1..FR-5.
* Alerting (smart, no noise) -> FR-5 suppression/cap/escalation.
* Automation -> one-command batch; Phase 6 orchestration.
* Visualization -> FR-7 four tabs.
* Scalability -> NFRs + scale-out table in implementation plan.
* Environment-Aware + fairness -> FR-4.3/FR-4.4 + cohort slices everywhere.

---

*End of PRD. Build order per `IMPLEMENTATION_PLAN.md` Phases 0-5; do not start Phase 6 until Section 8 acceptance passes.*
