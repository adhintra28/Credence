# PreDeliquency

Welcome to the **PreDeliquency** repository. This document serves as the primary understanding, architecture, and implementation overview for the project.

---

## Project Overview

PreDeliquency is an intelligent **early-warning risk prediction and intervention platform** designed to identify customers who may experience financial stress **before their first EMI default**.

Unlike traditional delinquency systems that react after a missed payment has already occurred, PreDeliquency focuses on detecting behavioural and financial stress signals in advance. The system evaluates an eligible population of customers, generates time-aware features from financial activity, predicts short-term repayment risk, and routes high-risk customers through a structured intervention and policy engine.

The platform supports a complete risk workflow—from synthetic data generation and feature engineering to machine learning prediction, alert prioritisation, suppression rules, intervention tracking, and outcome measurement.

The objective is to help financial institutions move from:

> **Reactive Collections → Proactive Prevention**

---

## Core Features

- **Pre-Delinquency Risk Prediction:** Identifies customers showing financial stress before their first missed EMI using configurable 14-day and 28-day prediction horizons.
- **Eligible Population Filtering:** Ensures customers who are already delinquent or have recently experienced repayment failure are excluded from the pre-delinquency scoring population.
- **Financial Stress Signal Detection:** Analyses behavioural indicators such as salary disruption, balance pressure, transaction changes, lender activity, spending behaviour, and repayment affordability.
- **Machine Learning Risk Scoring:** Uses gradient-boosting models to generate calibrated probabilities representing the likelihood of a future repayment miss.
- **Risk Tiering:** Categorises customers into **Green, Amber, and Red** risk tiers based on calibrated scores and configurable policy thresholds.
- **Policy & Alert Engine:** Applies multi-signal validation, suppression rules, escalation logic, and daily alert caps before generating actionable analyst queues.
- **Explainable Predictions:** Provides feature-level explanations and top contributing risk factors for each customer score.
- **Daily Risk Monitoring:** Supports continuous scoring across date ranges, enabling historical risk tracking and Amber-to-Red escalation.
- **Intervention Management:** Tracks customer outreach, financial assistance offers, analyst actions, and intervention outcomes.
- **Outcome Measurement:** Supports control-group comparisons and cure-rate analysis to measure whether interventions improve repayment outcomes.
- **Role-Based Access Control:** Separates analyst, risk manager, customer, and service access with authenticated and authorised APIs.
- **Model Governance & Monitoring:** Tracks model versions, drift, calibration, fairness metrics, promotion, rollback, and production acceptance gates.

---

##  The Process: Architectural Flow

### 1. Data Generation & Ingestion

Customer profiles, transactions, balances, EMI schedules, and repayment events are generated or ingested into the system.

The data layer captures financial activity required to identify early signs of repayment stress.

### 2. Eligible Population Selection

Before scoring, the system filters customers to ensure the prediction problem remains genuinely **pre-delinquency**.

Customers with existing delinquency or recent repayment failures are excluded from the scoring population.

This ensures the model is not simply learning to recognise customers who have already defaulted.

### 3. Feature Engineering

The system builds time-aware feature snapshots using historical financial activity available up to the scoring date.

Features may include:

- Balance pressure
- EMI-to-income affordability
- Salary timing behaviour
- Transaction pattern changes
- New lender activity
- Channel usage diversity
- Cash-flow buffer estimates
- Spending behaviour
- Financial stress indicators
- Customer and product characteristics

All features are governed through a structured feature contract defining their data type, calculation window, range, and missing-value policy.

### 4. Risk Prediction

Eligible customer feature snapshots are passed through the trained machine learning model.

The model estimates:

- **14-Day Risk Probability**
- **28-Day Risk Probability**

Model predictions are calibrated to produce reliable probability estimates and evaluated using risk-focused metrics such as PR-AUC, Recall@Risk, Precision, KS, and Brier Score.

### 5. Risk Tier Classification

Customer scores are mapped into actionable tiers:

- 🟢 **Green** — Low repayment risk
- 🟠 **Amber** — Emerging financial stress
- 🔴 **Red** — High probability of repayment failure

Thresholds are centrally versioned so that batch scoring and API scoring produce identical results.

### 6. Policy & Suppression Engine

Not every high model score should immediately create an intervention.

The policy engine evaluates additional business rules including:

- Multi-signal confirmation
- Recent customer contact suppression
- Daily Red alert limits
- Amber risk streak escalation
- Duplicate prevention
- Audit logging

Customers who are suppressed or capped are still recorded with an explicit reason to maintain transparency.

### 7. Intervention & Outreach

Approved alerts can trigger interventions such as:

- Customer assistance offers
- Payment restructuring discussions
- Repayment reminders
- Financial support workflows
- Analyst review

The system tracks each intervention using a unique identifier and maintains an auditable action history.

### 8. Outcome Measurement

The final stage measures whether intervention strategies improve customer outcomes.

The platform compares treated and control groups to calculate metrics such as:

- Cure rate
- Repayment success
- Intervention acceptance
- Offer effectiveness
- Expected loss reduction

This allows the business impact of the pre-delinquency system to be measured rather than assumed.

---

##  Risk Intelligence Architecture

PreDeliquency combines three major intelligence layers:

### Predictive Intelligence

Machine learning models analyse historical customer behaviour and identify patterns associated with future repayment stress.

### Behavioural Intelligence

Financial signals are aggregated across time windows to identify changes in customer behaviour rather than relying on a single transaction or balance value.

### Policy Intelligence

Business rules ensure model predictions are operationally safe and actionable by applying suppression, escalation, prioritisation, and alert-cap logic.

Together, these layers transform raw financial activity into actionable early-warning signals.

---

##  Coordination & Measurements

The platform evaluates model and business performance using multiple layers of metrics.

### Model Performance

- PR-AUC
- ROC-AUC
- Recall@10%
- Recall@15%
- Precision@Red
- KS Statistic
- Brier Score
- Calibration Slope

### Operational Performance

- Percentage of customers flagged
- Daily alert volume
- Suppression rate
- Red queue utilisation
- Amber-to-Red escalation

### Business Performance

- Cure rate
- Treated vs Control performance
- Intervention acceptance rate
- Expected loss saved
- Repayment improvement after intervention

### Model Monitoring

- Feature distribution drift
- Score distribution drift
- Population Stability Index (PSI)
- Cohort fairness metrics
- Model version comparison

---

##  Routing, State & Decision Management

To manage risk decisions across the platform:

- **Risk Scores:** Stored as time-aware scoring records rather than overwritten values.
- **Alerts:** Generated from risk scores after policy evaluation.
- **Suppressions:** Record why potentially risky customers were not alerted.
- **Interventions:** Track customer outreach and financial assistance actions.
- **Audit Logs:** Capture actor, action, target, timestamp, and state transitions.
- **Model Runs:** Maintain data lineage, model artifacts, and pipeline execution history.
- **Outcomes:** Connect interventions with future repayment results.

This architecture ensures that predictions remain reproducible, explainable, and auditable.

---

##  Security & Access Control

PreDeliquency is designed around role-based access control.

### Supported Roles

- **Analyst** — Reviews customer alerts and risk information.
- **Risk Manager** — Manages policies, thresholds, models, and operational decisions.
- **Customer** — Can access only their own offers and repayment-related information.
- **Service** — Used for authenticated internal system communication.

Security capabilities include:

- JWT-based authentication
- Role-based authorisation
- Customer identity scoping
- Restricted CORS configuration
- Rate limiting
- Password hashing
- CSRF protection
- Immutable audit logs
- Request tracing
- Secure secrets management

---

##  Model Lifecycle

```text
Raw Financial Data
        │
        ▼
Eligible Population
        │
        ▼
Feature Engineering
        │
        ▼
Train / Calibration / Test Split
        │
        ▼
Model Training
        │
        ▼
Probability Calibration
        │
        ▼
Threshold Optimisation
        │
        ▼
Acceptance Gates
        │
        ▼
Champion Model
        │
        ▼
Daily Scoring
        │
        ▼
Policy Engine
        │
        ▼
Alerts & Interventions
        │
        ▼
Outcome Measurement
```

Models are promoted only when predefined performance and calibration requirements are satisfied.

---

##  Project Structure

```text
preDeliquency/
├── src/
│   ├── config.py                 # Central typed configuration loader
│   ├── logging.py                # Structured application logging
│   │
│   ├── generator/                # Synthetic data generation
│   ├── labels/
│   │   └── build.py              # Eligible population & prediction labels
│   ├── features/
│   │   ├── build.py              # Feature engineering pipeline
│   │   └── contract.py           # Feature contract definitions
│   ├── models/
│   │   ├── train.py              # Model training
│   │   ├── evaluate.py           # Performance evaluation
│   │   ├── calibrate.py          # Probability calibration
│   │   └── registry.py           # Model version management
│   ├── scoring/
│   │   └── score.py              # Daily batch and customer scoring
│   ├── policy/
│   │   └── engine.py             # Alert, suppression & escalation rules
│   ├── services/
│   │   ├── store.py
│   │   ├── risk_service.py
│   │   ├── intervention_service.py
│   │   ├── model_service.py
│   │   ├── auth_service.py
│   │   ├── audit_service.py
│   │   ├── notification_service.py
│   │   ├── feature_service.py
│   │   ├── explain_service.py
│   │   ├── outcome_service.py
│   │   └── run_service.py
│   └── serving/
│       └── api.py                # Authenticated API service
│
├── frontend/
│   ├── bank/                     # Analyst & risk dashboards
│   └── customer/                 # Customer portal
├── tests/                        # Unit, integration & regression tests
├── migrations/                   # Database migrations
├── models/                       # Local model artifacts
├── data/
│   ├── raw/
│   ├── processed/
│   └── outputs/
├── terraform/                    # Production infrastructure
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── config.yaml
└── README.md
```

---

##  Technology Stack

### Backend & APIs

- Python 3.11
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic

### Machine Learning

- LightGBM
- XGBoost
- Scikit-learn
- SHAP
- MLflow

### Data Processing

- Pandas
- NumPy
- PyArrow
- PostgreSQL

### Infrastructure

- Docker
- Docker Compose
- GitHub Actions
- Terraform

### Production Deployment

- AWS ECS Fargate
- Amazon RDS PostgreSQL
- Amazon S3
- AWS Secrets Manager
- Application Load Balancer
- CloudWatch

---

##  Testing & Reliability

PreDeliquency follows a **test-first correctness approach**.

Key validation areas include:

- Deterministic data generation
- Pre-delinquency population validation
- Positive-rate bounds
- Label consistency
- Feature leakage prevention
- Constant-feature detection
- Train/test customer isolation
- Time-based data splitting
- Probability calibration
- Model acceptance gates
- Batch/API prediction parity
- Suppression logic
- Risk escalation
- Alert caps
- Authentication and authorisation
- Customer data isolation
- Intervention correctness
- Database concurrency
- Drift detection
- Production rollback

The goal is to ensure that every major risk, feature, and policy decision can be reproduced and tested.

---

##  Onboarding & Local Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL
- Make

### 1. Clone the Repository

```bash
git clone https://github.com/adhintra28/PreDeliquency.git
cd PreDeliquency
```

### 2. Install Dependencies

```bash
make install
```

### 3. Configure Environment Variables

Create a `.env` file:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/predelinquency

PREDELINQ_SECRET=your_secure_secret

MODEL_ARTIFACT_PATH=models/

ENVIRONMENT=development
```

### 4. Start Local Services

```bash
docker compose up --build
```

### 5. Run Database Migrations

```bash
alembic upgrade head
```

### 6. Generate Data

```bash
make data
```

### 7. Train the Model

```bash
make train
```

The training pipeline performs:

- Dataset preparation
- Feature engineering
- Time-aware splitting
- Model training
- Calibration
- Threshold optimisation
- Acceptance testing
- Model card generation

### 8. Run Risk Scoring

```bash
make score
```

For date-range scoring:

```bash
python -m src.scoring.score \
  --from 2026-01-01 \
  --to 2026-01-31
```

### 9. Run the Complete Pipeline

```bash
make all
```

This reproduces the complete workflow from data generation to scoring and alert generation.

---

##  Dashboard Capabilities

### Risk & Analyst Portal

- Portfolio overview
- Active Red and Amber queues
- Customer risk profiles
- Score history
- Risk explanations
- Suppressed customer visibility
- Cohort analysis
- Intervention tracking
- Model health
- Drift monitoring
- Model registry
- Pipeline run history
- Audit logs

###  Customer Portal

- Personal offers
- Intervention history
- Offer responses
- Contact preferences
- Consent management

---

##  Monitoring & Governance

The system continuously tracks:

- Feature drift
- Score drift
- Population Stability Index
- Calibration performance
- Fairness across cohorts
- Model acceptance metrics
- Champion vs Challenger performance

A challenger model can be evaluated through shadow scoring before being promoted.

If a production issue occurs, the previous champion model can be restored through a controlled rollback workflow.

---

##  Design Principles

### **Predict Before Default**

The system should identify stress before the repayment failure occurs.

### **Correctness Before Complexity**

A simple, correctly evaluated batch model is more valuable than a complex architecture built on incorrect labels or leaked features.

### **Explain Every Decision**

Risk predictions should provide understandable reasons for analysts and customers.

### **Policy Complements ML**

Machine learning identifies risk patterns, while policy logic ensures decisions remain operationally appropriate.

### **Measure Outcomes**

An intervention system is only valuable if its impact can be measured against a meaningful baseline.

### **Security by Default**

Financial risk scores and behavioural data require strict authentication, authorisation, auditing, and access control.

---


---

<p align="center">
  <b>PreDeliquency</b><br>
  Predicting financial stress before it becomes delinquency.
</p>
