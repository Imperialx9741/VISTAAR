# VISTAAR Environment Configuration Guide

This document describes how to configure environment variables for VISTAAR applications and services.

## Usage

1. **Copy the Template**: Copy `.env.example` at the project root to `.env` in the same directory:
   ```bash
   cp .env.example .env
   ```
2. **Configure Locally**: Edit the values in your local `.env` file to match your development environment.

## Safety & Security Constraints

- **Never Commit `.env` Files**: The `.env` file contains your local connection details and credentials. It is listed in `.gitignore` and must **never** be committed to Git.
- **No Production Secrets in Git**: Real production credentials, API keys, private keys, or webhook secrets must never be placed in the codebase or in `.env.example`. Real secrets must be managed using local environment vaults, CI/CD secrets, or cloud key-management services.
- **Phasing Note**: Infrastructure connections and their corresponding code logic (PostgreSQL, Redis, Kafka, MinIO, payment gateways) will be integrated in later project phases. Currently, these environment values serve only as structural placeholders.

## Configuration Categories

1. **Application**: Core application metadata (`APP_ENV`, `APP_NAME`, `APP_VERSION`).
2. **Backend**: Host and port configurations for VISTAAR API services (`BACKEND_HOST`, `BACKEND_PORT`).
3. **Database**: Connection string to the primary PostgreSQL data store (`DATABASE_URL`).
4. **Redis**: Connection details for cached sessions and lock managers (`REDIS_URL`).
5. **Kafka**: Endpoint targets for event-driven message brokers (`KAFKA_BOOTSTRAP_SERVERS`).
6. **Object Storage**: S3-compatible cloud storage settings for hosting uploaded documents (`STORAGE_ENDPOINT`, `STORAGE_BUCKET`, etc.).
7. **Authentication**: Parameters governing signature validation and expiration of JWT tokens (`JWT_SECRET`, `JWT_ALGORITHM`, etc.).
8. **Payments**: Integrations for handling rides transactions (`PAYMENT_PROVIDER`, `PAYMENT_API_KEY`, etc.).
