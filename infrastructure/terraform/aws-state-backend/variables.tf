variable "region" {
  description = "AWS region for the state bucket/lock table. Should typically match ../aws/'s var.region (ap-south-1 default), though the state backend itself can technically live in a different region — not required to match, just simpler operationally if it does."
  type        = string
  default     = "ap-south-1"
}

variable "lock_table_name" {
  type    = string
  default = "vistaar-terraform-locks"
}
