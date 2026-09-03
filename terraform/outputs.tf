output "ecr_repository_url" { value = aws_ecr_repository.app.repository_url }
output "artifact_bucket" { value = aws_s3_bucket.artifacts.id }
output "database_secret_arn" { value = aws_secretsmanager_secret.app.arn }
output "api_url" {
  value = local.deploy_app ? "http://${aws_lb.main[0].dns_name}" : null
}
