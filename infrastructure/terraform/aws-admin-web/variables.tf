variable "project_name" {
  type    = string
  default = "vistaar"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "git_branch" {
  description = "The branch Amplify builds from on every push, once the repository is connected (see this module's own README)."
  type        = string
  default     = "main"
}

variable "backend_api_base_url" {
  description = "The real backend API's public URL (e.g. https://api.vistaar.example) — becomes NEXT_PUBLIC_API_BASE_URL, the one env var apps/admin-web actually reads (confirmed by inspecting its source — see main.tf's own comment). No default: the real domain doesn't exist yet (infrastructure/kubernetes/backend-ingress.yaml's own REPLACE_ME_DOMAIN)."
  type        = string
}
