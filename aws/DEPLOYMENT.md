# Legacy AWS batch integration

This optional Lambda/DynamoDB/SNS path is preserved for the existing hackathon
demo. It receives already-scored `outputs/risk_scores_*.csv` and
policy-approved `outputs/alerts_*.csv` from S3; it does not score raw
transactions.

Configure these Lambda environment variables:

```text
DYNAMODB_RISK_SCORES_TABLE=CustomerRiskScores
SNS_ALERT_TOPIC_ARN=arn:aws:sns:ap-south-1:ACCOUNT_ID:FinancialStressAlerts
```

Do not add `AWS_REGION`: Lambda provides it automatically. The newer Terraform
deployment in `terraform/` is separate and does not use this optional path.
