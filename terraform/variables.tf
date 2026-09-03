variable "aws_region" {
  description = "AWS region for all infrastructure."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Lowercase prefix for provisioned resources."
  type        = string
  default     = "predelinquency"
}

variable "app_image" {
  description = "Immutable ECR image URI (for example, <account>.dkr.ecr.ap-south-1.amazonaws.com/predelinquency:sha-123). Leave empty for the bootstrap apply that creates only the ECR repository."
  type        = string
  default     = ""
}

variable "app_count" {
  description = "Number of Fargate API tasks after an image has been supplied."
  type        = number
  default     = 1
}

variable "db_instance_class" {
  description = "RDS instance size. db.t3.micro is appropriate only for a demo."
  type        = string
  default     = "db.t3.micro"
}

variable "allowed_cidr" {
  description = "CIDR permitted to reach the public ALB; replace 0.0.0.0/0 with an office/VPN CIDR for a real deployment."
  type        = string
  default     = "0.0.0.0/0"
}
