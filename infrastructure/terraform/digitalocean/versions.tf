terraform {
  required_version = ">= 1.7.0"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.40"
    }
    # Used only to run `CREATE EXTENSION postgis;` against the Managed
    # PostgreSQL cluster once it exists — the digitalocean provider
    # itself has no resource for enabling a database extension.
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.21"
    }
  }
}

provider "digitalocean" {
  # Reads DIGITALOCEAN_TOKEN from the environment — never hardcode a
  # token in this repo. See README.md in this directory.
}

provider "postgresql" {
  host            = digitalocean_database_cluster.postgres.host
  port            = digitalocean_database_cluster.postgres.port
  username        = digitalocean_database_cluster.postgres.user
  password        = digitalocean_database_cluster.postgres.password
  database        = digitalocean_database_cluster.postgres.database
  sslmode         = "require"
  superuser       = false
  connect_timeout = 15
}
