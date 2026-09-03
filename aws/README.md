# AWS MVP integration

This repository uses a batch-first AWS flow:

```text
local batch scoring -> S3 outputs/risk_scores_*.csv -> Lambda -> DynamoDB
local policy engine -> S3 outputs/alerts_*.csv -> Lambda -> SNS
```

The Lambda never sends a customer message directly from raw transactions or a
bare model score. The policy engine produces the approved alert message first.
See [DEPLOYMENT.md](DEPLOYMENT.md) for the required S3 prefixes, DynamoDB key
schema, Lambda environment variables, and least-privilege IAM permissions.

For frontend integration, run the FastAPI service and request:

```text
GET /api/customers/{customer_id}/risk-payload
```

It returns `customer_id`, `risk_score`, `risk_level`, `stress_velocity`,
`top_reason`, and `recommended_action`.

`sagemaker_train_deploy.py` remains a placeholder. The local model artifact is
`models/production.pkl` and stays out of Git; do not claim a SageMaker endpoint
exists until one is actually deployed.
