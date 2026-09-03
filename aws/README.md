# AWS architecture

The repository deploys through the Terraform configuration in
[`../terraform`](../terraform). The supported production flow is:

```text
ALB -> ECS Fargate / FastAPI -> RDS PostgreSQL
                  |-> S3 artifacts
                  |-> Secrets Manager
                  |-> CloudWatch Logs
```

The earlier hackathon Lambda/DynamoDB/SNS files remain in this folder as an
optional, separate demo path; see [DEPLOYMENT.md](DEPLOYMENT.md). They are not
part of the ECS production deployment. See [terraform/README.md](../terraform/README.md)
for deployment steps.
