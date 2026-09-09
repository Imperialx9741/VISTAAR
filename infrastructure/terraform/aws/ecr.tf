# ECR — resolves deployment-runbook.md §5.1's previously-open
# "container registry choice" (that section was written against the
# superseded DigitalOcean plan, where DOCR was "the path of least
# friction, same provider as everything else" but never actually
# created). ECR is the same reasoning applied to AWS: same provider as
# everything else in this module, natively integrated with EKS node
# IAM roles (AmazonEC2ContainerRegistryReadOnly, already attached in
# eks.tf) with no separate registry credential to manage in the
# cluster at all — a real improvement over DOCR, which needed its own
# imagePullSecret.

resource "aws_ecr_repository" "backend" {
  name                 = var.backend_ecr_repository_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images, expire the rest — an engineering housekeeping default, not a compliance/retention decision."
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}
