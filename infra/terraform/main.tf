# CivicProof GCP Infrastructure
# Constraint: $300 credits, near-zero idle cost
# All Cloud Run services: min_instances=0

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "civicproof-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Cloud SQL (PostgreSQL) ─────────────────────────────────────

resource "google_sql_database_instance" "main" {
  name             = "civicproof-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      require_ssl     = true
    }

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    database_flags {
      name  = "max_connections"
      value = "50"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "civicproof" {
  name     = "civicproof"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = "civicproof"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# ── VPC Network ────────────────────────────────────────────────

resource "google_compute_network" "vpc" {
  name                    = "civicproof-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "civicproof-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

resource "google_compute_global_address" "private_ip" {
  name          = "civicproof-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# ── Cloud Storage (Artifact Lake) ──────────────────────────────

resource "google_storage_bucket" "artifacts" {
  name          = "${var.project_id}-artifacts"
  location      = var.region
  force_destroy = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
    condition {
      age = 90
    }
  }

  uniform_bucket_level_access = true
}

# ── Pub/Sub Topics ─────────────────────────────────────────────

resource "google_pubsub_topic" "artifact_fetched" {
  name = "artifact-fetched"
}

resource "google_pubsub_topic" "doc_parsed" {
  name = "doc-parsed"
}

resource "google_pubsub_topic" "entity_resolved" {
  name = "entity-resolved"
}

resource "google_pubsub_topic" "dead_letter" {
  name = "dead-letter"
}

resource "google_pubsub_subscription" "worker_artifact" {
  name  = "worker-artifact-sub"
  topic = google_pubsub_topic.artifact_fetched.id

  ack_deadline_seconds = 60

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.worker.uri}/internal/pubsub/artifact-fetched"
  }
}

resource "google_pubsub_subscription" "worker_parsed" {
  name  = "worker-parsed-sub"
  topic = google_pubsub_topic.doc_parsed.id

  ack_deadline_seconds = 60

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.worker.uri}/internal/pubsub/doc-parsed"
  }
}

# ── Secret Manager ─────────────────────────────────────────────

resource "google_secret_manager_secret" "db_password" {
  secret_id = "db-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "postgresql+asyncpg://civicproof:${random_password.db_password.result}@/${google_sql_database.civicproof.name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
}

resource "google_secret_manager_secret" "api_secret_key" {
  secret_id = "api-secret-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "openrouter-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "sam_gov_api_key" {
  secret_id = "sam-gov-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "openfec_api_key" {
  secret_id = "openfec-api-key"
  replication {
    auto {}
  }
}

# ── IAM Service Accounts ──────────────────────────────────────

resource "google_service_account" "api" {
  account_id   = "civicproof-api"
  display_name = "CivicProof API Service"
}

resource "google_service_account" "worker" {
  account_id   = "civicproof-worker"
  display_name = "CivicProof Worker Service"
}

resource "google_service_account" "gateway" {
  account_id   = "civicproof-gateway"
  display_name = "CivicProof Gateway Service"
}

# API SA: Cloud SQL Client + Storage Object Admin (own bucket) + Pub/Sub Publisher
resource "google_project_iam_member" "api_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "api_storage" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Worker SA: Pub/Sub Subscriber + Storage + SQL Client
resource "google_project_iam_member" "worker_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_storage_bucket_iam_member" "worker_storage" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker.email}"
}

# Gateway SA: Secret Manager accessor (LLM keys only)
resource "google_secret_manager_secret_iam_member" "gateway_openrouter" {
  secret_id = google_secret_manager_secret.openrouter_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gateway.email}"
}

# ── Cloud Run Services ─────────────────────────────────────────

resource "google_cloud_run_v2_service" "api" {
  name     = "civicproof-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/civicproof/api:latest"

      ports {
        container_port = 8080
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    service_account = google_service_account.api.email

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "civicproof-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/civicproof/worker:latest"

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    service_account = google_service_account.worker.email

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }
}

resource "google_cloud_run_v2_service" "gateway" {
  name     = "civicproof-gateway"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/civicproof/gateway:latest"

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    service_account = google_service_account.gateway.email
  }
}

# Public access for API only
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Cloud Scheduler (Ingestion Cron) ───────────────────────────

resource "google_cloud_scheduler_job" "usaspending_daily" {
  name     = "ingest-usaspending-daily"
  schedule = "0 3 * * *"
  time_zone = "UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/ingest/runs"
    http_method = "POST"
    body        = base64encode(jsonencode({ source_id = "usaspending", mode = "incremental" }))
    headers     = { "Content-Type" = "application/json" }
  }
}

resource "google_cloud_scheduler_job" "doj_6h" {
  name     = "ingest-doj-6h"
  schedule = "0 */6 * * *"
  time_zone = "UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/ingest/runs"
    http_method = "POST"
    body        = base64encode(jsonencode({ source_id = "doj", mode = "incremental" }))
    headers     = { "Content-Type" = "application/json" }
  }
}

resource "google_cloud_scheduler_job" "sec_edgar_6h" {
  name     = "ingest-sec-edgar-6h"
  schedule = "0 */6 * * *"
  time_zone = "UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/ingest/runs"
    http_method = "POST"
    body        = base64encode(jsonencode({ source_id = "sec_edgar", mode = "incremental" }))
    headers     = { "Content-Type" = "application/json" }
  }
}

resource "google_cloud_scheduler_job" "oversight_weekly" {
  name     = "ingest-oversight-weekly"
  schedule = "0 6 * * 0"
  time_zone = "UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/ingest/runs"
    http_method = "POST"
    body        = base64encode(jsonencode({ source_id = "oversight", mode = "incremental" }))
    headers     = { "Content-Type" = "application/json" }
  }
}

resource "google_cloud_scheduler_job" "sam_gov_daily" {
  name     = "ingest-sam-gov-daily"
  schedule = "0 4 * * *"
  time_zone = "UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/ingest/runs"
    http_method = "POST"
    body        = base64encode(jsonencode({ source_id = "sam_gov", mode = "incremental" }))
    headers     = { "Content-Type" = "application/json" }
  }
}

resource "google_cloud_scheduler_job" "openfec_daily" {
  name     = "ingest-openfec-daily"
  schedule = "0 5 * * *"
  time_zone = "UTC"

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/v1/ingest/runs"
    http_method = "POST"
    body        = base64encode(jsonencode({ source_id = "openfec", mode = "incremental" }))
    headers     = { "Content-Type" = "application/json" }
  }
}

# ── Artifact Registry ─────────────────────────────────────────

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "civicproof"
  format        = "DOCKER"
}
