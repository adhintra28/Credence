# AWS deployment checklist

The local engine remains the MVP source of truth. AWS receives the already-scored
`risk_scores_YYYY-MM-DD.csv` output and policy-approved `alerts_YYYY-MM-DD.csv`;
it must not score or notify from raw transactions.

The frontend/API payload is available locally at
`GET /api/customers/{customer_id}/risk-payload`. It includes `risk_score`,
`risk_level`, `stress_velocity`, `top_reason`, and `recommended_action`.

## Required resources

- S3 bucket: upload batch outputs at `outputs/risk_scores_YYYY-MM-DD.csv` and
  `outputs/alerts_YYYY-MM-DD.csv`.
- DynamoDB table: `customer_id` **partition key** (String) and `scoring_date`
  **sort key** (String). The sort key is required for the PRD's append-only
  daily audit history; a table with only `customer_id` overwrites old scores.
- SNS topic: subscribe internal risk/collections recipients only. Do not send
  customer-facing messages directly from raw model output; the policy engine
  determines intervention eligibility.
- Lambda: upload `aws/lambda_function.py` as `lambda_function.lambda_handler`,
  set an S3 notification filter of `outputs/` plus suffix `.csv`, and set the
  variables below. Risk-score files write audit records to DynamoDB; alert files
  publish only the policy engine's approved message to SNS.

## Lambda environment variables

```text
AWS_REGION=ap-south-1
DYNAMODB_RISK_SCORES_TABLE=CustomerRiskScores
SNS_ALERT_TOPIC_ARN=arn:aws:sns:ap-south-1:ACCOUNT_ID:FinancialStressAlerts
```

## Least-privilege IAM permissions

Grant the Lambda execution role only `s3:GetObject` for the output prefix,
`dynamodb:PutItem` for this table, and `sns:Publish` for this topic. Use an IAM
role or AWS profile locally; never store access keys in the repository.

## Local scripts

Set `S3_DATA_BUCKET` to list input objects with
`python aws/kinesis_ingest.py`, or download one with
`python aws/kinesis_ingest.py raw/transactions.csv`. Set
`DYNAMODB_RISK_SCORES_TABLE` to read one record with
`python aws/data_notify_store.py CUST001`.
