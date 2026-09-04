# Credence — Pre-Delinquency Risk Intelligence
### Presentation Guide: UI, Tech Stack & Page Walkthrough

> Everything below is true of the running system at `http://127.0.0.1:5000`
> (demo logins: `bank@bank.com/bank123`, `risk@bank.com/risk123`,
> `customer@customer.com/cust123`).

---

## 1. The One-Line Story

**"We predict the EMI miss before it happens."** A bank's pre-delinquency
engine that scores 2,000 currently-clean customers daily for 14/28-day default
risk, explains every alert with its top-3 reasons, suppress what's not urgent,
and offers borrowers a payment holiday, EMI split, or restructure *before*
their first late payment — all in a single dark, operationally-obsessed portal.

---

## 2. Architecture (what we built)

```
┌──────────────────────────────────────────────────────────────────┐
│  BATCH PIPELINE (daily)                                          │
│  generator → features (29 cols) → train (LightGBM/XGBoost/HGB,   │
│  isotonic calibration, SHAP) → score → policy engine             │
│  (suppression, multi-signal check, escalation, Red cap/day)      │
└───────────────┬──────────────────────────────────────────────────┘
                │ CSV / Parquet artifacts (also auto-seeded into Postgres / SQLite)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  STORE LAYER  src/services/store.py + db.py (file-first,         │
│  DATABASE_URL switches reads/writes to SQLAlchemy/Postgres)      │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────┬───────────────────────────────────┐
│ FLASK PORTAL  :5000 (UI)     │ FASTAPI  :8000 (/docs, JSON API)  │
│ gunicorn in prod             │ same services underneath          │
│ Jinja2 + hand-written CSS    │                                   │
└──────────────────────────────┴───────────────────────────────────┘
```

**Honest note for judges we can say out loud:** LightGBM/XGBoost wheels
couldn't load OpenMP on this machine, so the champion is
`scikit-learn` **HistGradientBoosting** (automatic fallback in `train.py`).
Result: **test PR-AUC 0.74, ROC-AUC 0.88, isotonic-calibrated**, thresholds
frozen in `models/thresholds.json` (`amber ≥ 0.30`, `red ≥ 0.60`).

---

## 3. Tech Stack (what we used)

| Layer | Technology | Why |
|---|---|---|
| UI | **Flask + Jinja2 templates** (server-rendered) | One-command local run; no SPA build; auditable server-side data |
| UI styling | **Hand-written CSS design system** — Obsidian tokens (`#09090b` zinc surfaces, violet `#a78bfa` primary, emerald/red/amber for function) | Developer-grade dark UI, "Precision in Darkness"; source: `stitch_ui_reference/DESIGN.md` |
| Typography | **Geist** (Google Fonts) + system fallback; `ui-monospace` for every metric | Tight tracking, high contrast, developer feel |
| JS | **Vanilla JS only** — one 15-line live-reload script (`fetch /__live` every 2s, reload on change) | No framework weight; template edits appear without refreshing |
| Auth | **Flask session cookies** + **Google OAuth 2.0 via authlib** (bank domain validation, customer open login) | Bank-grade SSO with strict email-domain check per institution |
| Data | **pandas / numpy / pyarrow** — CSV + Parquet artifacts; optional **SQLAlchemy → Postgres** via `DATABASE_URL` (auto-create + seed tables) | Reproducible batch; DB story optional and switchable |
| ML | **scikit-learn HistGradientBoosting**, isotonic calibration, **SHAP TreeExplainer**, MLflow logging | Explainable, calibrated, on-curriculum explainability |
| Policy | Hand-written engine: suppression (contacted-7d, hardship, single-source), Amber→Red escalation, Red cap 200/day, cross-environment group check (≥2 signal groups) | "Smart alerting, no noise" — the brief's core ask |
| Serving | **gunicorn** for the portal; **FastAPI + uvicorn** (`/docs`) for JSON API | Production-shaped serving |
| Deploy | **render.yaml blueprint** (free tier), Dockerfile (gunicorn on `$PORT`), docker-compose (portal+API+Postgres+MailHog) | One-click reproducible hosting |
| Quality | pytest suite (13 tests: pipeline, policy rules, API, portal routes), live-reload, `/healthz`, `/ssostatus` | CI-grade sanity |

**Design language rules we held (from `DESIGN.md`):** never a light background;
borders over shadows; accent color only for function; all metrics in mono font;
square corners (4–8px); focus rings violet; text `#fafafa`/`#a1a1aa`.

---

## 4. Page-by-Page Walkthrough (what each page does)

### 🔐 Sign-in (`/`) — the entry gate
- Password logins for two staff roles (analyst/manager) + a customer demo login.
- **Or continue with Google SSO** → bank employees pick their institution
  first (`/login/bank`); the callback validates their email ends with that
  bank's corporate domain (`frontend/banks.yaml`) — a Gmail at HDFC gets the
  red *Unauthorized* page. Customers link any account.
- Centered card, mono hints box with demo credentials.

### 📊 Portfolio Overview (`/bank`) — the executive view
- **Hero**: decision context — "Screening non-delinquent accounts (DPD=0) for
  forward distress signals across 14/28-day horizons."
- **6 KPI cards** (one glance story):
  1. Population Scored (2,000 · 0 DPD) — the clean cohort we screen
  2. Active Red Queue (113, 5.7%) — immediate-intervention candidates
  3. Amber Watchlist (18, 0.9%) — monitor/persistent-streak
  4. Silenced Today — suppression working (capacity guard)
  5. Offer Accept Rate (33.3%) — interventions are being accepted
  6. Expected Loss Exposure (₹2.87M) — why this matters in rupees
- **Horizon/filter bar**: 14D vs 28D, cycle window chip, tier chips
  (All / Red >0.60 / Amber 0.30–0.60) that deep-link into the queue.
- **Priority Risk Queue**: ranked by expected loss (score × EMI) — customer
  ref, score with bar, tier badge, top SHAP reason, stress-indicator chips
  (salary, liquidity, discipline, borrowing, behavioral, cash), policy
  decision (approved/human offer vs monitored/nudge), ₹ loss, Inspect.
- **Early Stress Signal Distribution** — prevalence of each of the 7 required
  signals (salary delay, savings drawdown, lending-app uptick, utility
  lateness, discretionary contraction, ATM hoarding, auto-debit failures) —
  thresholds mirror the policy engine exactly (single source of truth).
- **Policy & Suppression Guardrails** — multi-signal confirmation pass,
  contact-suppression holds, daily cap remaining, tonight's escalations.
- **Model governance footer**: champion model, PR-AUC/ROC/Recall@15%/
  Precision@Red/PSI, batch/API parity + quick actions.

### 🚨 Risk Queue (`/bank/queue`) — the analyst's workbench
- Filters (search customer/reason, tier, open/approved/snoozed) + sort
  Red-first by expected loss; frozen thresholds noted in the header.
- Full 10-column table: customer ref, score with bar, tier, top SHAP reason,
  stress-chips, policy decision, EMI, expected loss, analyst status, and
  **one-click Approve / Snooze** (POSTed to the policy engine, mirrored to the
  audit log). Inspect jumps to the customer 360.
- Pagination bar; empty-state copy tells you exactly which command to run.

### 👤 Customer Deep Dive & Streams (`/bank/customer/<id>`) — the evidence board
- **Risk Assessment**: score in tier color, probability bar, model + thresholds
  caption, profile chips (archetype, geography, product, EMI, income).
- **Top SHAP explanations** — the 3 plain-language reasons every alert carries.
- **Stress Signal Strip**: the 7 signals with *raw feature values*
  (salary delay days, savings WoW %, lending txns, utility delay, auto-debit
  fails, discretionary drop, ATM withdrawals).
- **Cash-Flow Timeline (120d)**: SVG sparkline from the real transaction
  stream (min/max annotated) — the "we see the pressure forming" visual.
- **Make an Offer / Send a Nudge**: empathetic template-locked offers
  (payment holiday, EMI split x2, tenure+3mo) + channel choice (call/sms/app/
  email/branch) — every log is append-only.
- **EMI Schedule** (last 12, DPD + bounce flags) and **Interventions &
  Analyst Actions** audit table.

### 🧪 Model Health & Drift (`/bank/model`) — the model-risk corner
- 8 metric cards: PR-AUC, ROC-AUC, Recall@15% (gate ≥0.70), Precision@Red,
  PSI (STABLE/DRIFT), flagged rate (≤15% target), base rate, Brier.
- **Global SHAP importance** — top-10 ranked violet bars.
- **Drift & Data Health**: score mean shift, PSI halves, retrain signal,
  null-rate violations (>5% → red chips).
- **Fairness Audit (80% rule)** per cohort — geography/archetype/product mix
  with PASS/INVESTIGATE chips — the SR 11-7 story.

### 📋 Interventions & Outcomes (`/bank/interventions`) — the audit trail
- Filterable append-only log (offered/accepted/declined/approved/snoozed),
  with accept-rate and cure-lift stats; each row links back to its customer.

### 🔎 Customer Self-Service (`/customer`) — the empathy side
- Calm, supportive tone ("we noticed some pressure before your EMI is missed —
  supportive, never a penalty"), score with bar, plain-language factors.
- **Available Support Options**: choose payment-holiday / split / restructure
  → request → "our team will confirm before your EMI date, no late fee".
- **Review Latest Bank Offer** → Accept/Decline. EMI schedule + full history.

### 🛠 Platform extras (finishing touches)
- `/ssostatus` — SSO diagnostics (fingerprinted client id, redirect URI).
- `/healthz` — liveness (n_scores + scoring_date).
- `/__live` + live-reload script — edit a template, the open page refreshes.
- FastAPI `/docs` at `:8000` — interactive API for integrations.

---

## 5. Data & Explainability Story (what's real)

- **Synthetic 2,000 customers × 12 months** (5 archetypes: salaried stable/
  stressed, gig, SME, pensioner) with point-in-time features, 8–12% positive
  rate, hashed IDs, no PII in files.
- **29 feature columns** across income/liquidity/discipline/borrowing/
  behavioral/cash/context groups; **7 required signals** detected.
- Pipeline: `run_all.py` (generate → features → train → score → policy) —
  one command reproduction, fixed seeds, MLflow lineage.
- **Explainability:** `shap_top3_json` on every score → plain language;
  global SHAP bars; fairness audit table. No bare scores — every number has a
  reason, per the PRD's UX principles.

---

## 6. Demo Script (60 seconds)

1. **Portfolio** — "2,000 clean customers; 113 red-tier. We predict stress
   weeks before a miss, not after."
2. **Deep dive** — click a red customer; show the 120-day balance sparkline,
   the 7-signal strip, and the 3 SHAP reasons in plain words.
3. **Intervention** — send the EMI-split offer; switch to the **customer**
   login (same cohort, other side of the table) and accept it; back to the
   queue: the offer is audited and the accept-rate card moved.
4. **Model Health** — PR-AUC 0.74, PSI stable, 80%-rule PASS — "model risk
   is not an afterthought."
5. **Both UIs** — same data through the Flask portal and the FastAPI `/docs`.

---

*Generated alongside the codebase; keep in sync with `frontend/templates/*`
and `src/services/*`.*
