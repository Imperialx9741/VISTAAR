# EKS — the AWS equivalent of the superseded DOKS module
# (digitalocean_kubernetes_cluster). Real IAM plumbing is required here
# that DOKS didn't need (DigitalOcean manages the equivalent
# permissions implicitly) — this is the biggest structural difference
# between the two modules, not extra scope added for its own sake.

resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-${var.environment}-eks-cluster"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "vistaar" {
  name     = "${var.project_name}-${var.environment}"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
    endpoint_private_access = true
    # Public endpoint left enabled (default) so `kubectl`/CI can reach
    # the API server without a VPN/bastion — restrict
    # `endpoint_public_access_cidrs` to known-good ranges before a real
    # production apply; left open (0.0.0.0/0, the aws provider's own
    # default) here deliberately, not silently narrowed to a guess.
    endpoint_public_access = true
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]

  tags = {
    Environment = var.environment
  }
}

# --- AWS Load Balancer Controller (owner decision, 2026-09-03: "Use
# AWS Application Load Balancer with the AWS Load Balancer Controller
# for VISTAAR HTTP/HTTPS ingress... Do not use community Ingress-NGINX
# for the new production deployment.") ---
#
# This cluster is standard EKS (aws_eks_node_group above, a classic
# managed node group) — verified directly, not assumed, per the
# owner's own instruction to check first. EKS Auto Mode is a distinct
# cluster mode (a `compute_config { enabled = true }` block on
# aws_eks_cluster, with no separate aws_eks_node_group resource at
# all) that bundles its own load-balancing management; this module
# uses neither that block nor that pattern, so there is no built-in
# controller here to duplicate — installing the AWS Load Balancer
# Controller is required, not redundant.
#
# IRSA (IAM Roles for Service Accounts) is the mechanism: an OIDC
# identity provider for this cluster's own issuer, then an IAM role
# only the controller's Kubernetes ServiceAccount (kube-system/
# aws-load-balancer-controller) can assume — no static AWS credentials
# stored in the cluster for this. The controller software itself is
# NOT installed by this Terraform (same "Helm chart, run once the
# cluster exists" treatment this module's own README already gives
# cert-manager) — see infrastructure/kubernetes/README.md for the
# exact `helm install` step and the ServiceAccount annotation that
# wires it to the role this file creates.

data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.vistaar.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.vistaar.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
}

data "aws_caller_identity" "current" {}

locals {
  eks_oidc_issuer_host = replace(
    aws_eks_cluster.vistaar.identity[0].oidc[0].issuer, "https://", ""
  )
}

resource "aws_iam_role" "aws_load_balancer_controller" {
  name = "${var.project_name}-${var.environment}-aws-lb-controller"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.eks_oidc_issuer_host}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
          "${local.eks_oidc_issuer_host}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_policy" "aws_load_balancer_controller" {
  name = "${var.project_name}-${var.environment}-aws-lb-controller"
  # The exact, official policy published by kubernetes-sigs/
  # aws-load-balancer-controller (fetched directly from that project's
  # own docs/install/iam_policy.json, not reconstructed from memory —
  # a large, security-sensitive document worth getting byte-for-byte
  # right). Re-check that upstream file for updates before every major
  # controller version upgrade.
  policy = file("${path.module}/iam-policy-aws-load-balancer-controller.json")
}

resource "aws_iam_role_policy_attachment" "aws_load_balancer_controller" {
  role       = aws_iam_role.aws_load_balancer_controller.name
  policy_arn = aws_iam_policy.aws_load_balancer_controller.arn
}

resource "aws_iam_role" "eks_node_group" {
  name = "${var.project_name}-${var.environment}-eks-node-group"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_ecr_read_only" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.vistaar.name
  node_group_name = "${var.project_name}-default-pool"
  node_role_arn   = aws_iam_role.eks_node_group.arn
  # Worker nodes in the private subnets only — matches the superseded
  # DOKS module's own node pool, which never exposed nodes directly to
  # the public internet either.
  subnet_ids = aws_subnet.private[*].id

  instance_types = [var.node_instance_type]

  scaling_config {
    min_size     = var.node_count_min
    max_size     = var.node_count_max
    desired_size = var.node_count_min
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_ecr_read_only,
  ]

  tags = {
    Environment = var.environment
  }
}
