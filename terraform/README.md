# AWS production deployment

This Terraform configuration provisions only the agreed architecture:

```text
Internet -> ALB -> ECS Fargate (FastAPI) -> RDS PostgreSQL
                         |-> S3 model/artifact bucket
                         |-> Secrets Manager (DATABASE_URL)
                         |-> CloudWatch Logs
```

It intentionally creates no Lambda, DynamoDB, Kinesis, SageMaker, Redshift, or
SNS resources.

## Deploy in two safe applies

From `terraform/`, authenticate with an IAM principal allowed to provision the
listed resources, then:

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

The first apply creates the ECR repository, VPC, RDS, S3 bucket, secret, ECS
cluster, and CloudWatch log group. It does not create an API service until an
image is available. Copy the `ecr_repository_url` output, build and push the
Docker image, then set `app_image` in `terraform.tfvars` to that immutable URI.
Run `terraform plan` and `terraform apply` again; it creates the ALB, Fargate
service, and health check.

The default RDS configuration is demo-oriented (`db.t3.micro`, one-day backup,
no deletion protection). Review and harden it before any non-demo use.
