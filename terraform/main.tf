terraform {
  backend "gcs" {
    bucket = "lazybot7-terraform-state"
    prefix = "terraform/state"
  }
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required GCP APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "bigquery.googleapis.com",
    "drive.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ── Secret Manager: Drive Service Account Credentials ──────────────────────
# The actual secret value is created via CLI (gcloud secrets create) before
# terraform apply, so we only import the existing secret here.
resource "google_secret_manager_secret" "drive_sa_credentials" {
  secret_id = "drive-sa-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# Data source to reference the latest version already loaded by gcloud CLI
data "google_secret_manager_secret_version" "drive_sa_credentials_version" {
  secret  = google_secret_manager_secret.drive_sa_credentials.secret_id
  version = "latest"
  project = var.project_id
}
