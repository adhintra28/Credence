# AWS architecture

The repository deploys through the Terraform configuration in
[`../terraform`](../terraform). The supported production flow is:

```text
ALB -> ECS Fargate / FastAPI -> RDS PostgreSQL
                  |-> S3 artifacts
                  |-> Secrets Manager
                  |-> CloudWatch Logs
```

There is deliberately no Lambda, DynamoDB, Kinesis, SageMaker, Redshift, or SNS
implementation in this repository. See [terraform/README.md](../terraform/README.md)
for deployment steps.
