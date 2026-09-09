# Admin Web deployment (owner decision, 2026-09-03: "Use AWS Amplify
# as the Admin Web deployment target... Keep the Admin Web separate
# from the EKS backend infrastructure.") — a deliberately separate
# Terraform module/state from ../aws/, same reasoning as
# ../aws-state-backend/ being separate: Admin Web's own lifecycle
# (deploy a new frontend build) has nothing to do with the backend's
# EKS/RDS/ElastiCache/Kafka apply cycle, and coupling them into one
# state would mean every Admin Web deploy risks touching backend
# infrastructure state, or vice versa.
#
# platform = "WEB_COMPUTE", not the default "WEB" — verified directly
# against the AWS SDK's own Platform enum
# (aws-sdk-go-v2/service/amplify/types), not assumed: "WEB" is
# static-only, "WEB_COMPUTE" is Amplify's SSR/server-compute mode.
# Confirmed apps/admin-web genuinely needs this, not just Amplify's
# default: it has 18 dynamic route segments (`app/drivers/[driverId]`
# and similar) with no `generateStaticParams`, each an async Server
# Component reading `params` at request time (Next.js 16's `params`-as-
# Promise pattern) — inspected directly, not assumed from the
# framework's reputation. A static export (`output: "export"`) would
# fail to build these routes at all, since a fully static export has
# no server to resolve an arbitrary `driverId`/`customerId`/etc. at
# request time — exactly the owner's own caution: "Do not force a
# static export merely to use S3/CloudFront."

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_amplify_app" "admin_web" {
  name      = "${var.project_name}-admin-web-${var.environment}"
  platform  = "WEB_COMPUTE"

  # Monorepo: the Next.js app lives at apps/admin-web, not the repo
  # root — Amplify needs to know to cd there before building.
  build_spec = <<-YAML
    version: 1
    applications:
      - appRoot: apps/admin-web
        frontend:
          phases:
            preBuild:
              commands:
                - npm ci
            build:
              commands:
                - npm run build
          artifacts:
            baseDirectory: .next
            files:
              - '**/*'
          cache:
            paths:
              - node_modules/**/*
  YAML

  environment_variables = {
    NEXT_PUBLIC_API_BASE_URL = var.backend_api_base_url
  }

  # No `repository`/`access_token` here — deliberately. AWS's current
  # recommended flow connects a GitHub repository to Amplify via a
  # GitHub App installation done once in the Amplify Console (OAuth-
  # less, no long-lived token), not a classic personal-access-token
  # passed to this resource's own `access_token` argument (a real,
  # if optional, alternative Terraform supports — but it would end up
  # stored in this module's tfstate, the same class of concern that
  # keeps kafka.tf/rds.tf's own sensitive values out of any default
  # here). Connect the repository once, by hand, in the Amplify
  # Console after this app is created — see this module's own README.

  tags = {
    Environment = var.environment
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.admin_web.id
  branch_name = var.git_branch
  # Auto-build on every push to this branch, once the repository is
  # connected (see main.tf's own comment above) — the standard Amplify
  # Hosting CI/CD behavior, no separate pipeline needed.
  enable_auto_build = true

  # "Next.js - SSR" matches Amplify Console's own display string for
  # this framework — this field is free-form (confirmed against the
  # AWS SDK's own struct definition: no enum, no validation), purely
  # informational/cosmetic for the Console UI, not something a wrong
  # value here could break a build over.
  framework = "Next.js - SSR"
  stage     = "PRODUCTION"
}
