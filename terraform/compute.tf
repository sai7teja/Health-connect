# Service Account for Cloud Run Pipeline
resource "google_service_account" "pipeline_sa" {
  account_id   = "health-pipeline-sa"
  display_name = "Service Account for Health Pipeline Webhook and Migrator"
}

# Grant Service Account permissions to GCS buckets
resource "google_storage_bucket_iam_member" "raw_bucket_admin" {
  bucket = google_storage_bucket.raw_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_storage_bucket_iam_member" "proc_bucket_admin" {
  bucket = google_storage_bucket.processed_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# Grant BigQuery permissions to Service Account
resource "google_project_iam_member" "bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# Cloud Run Service: drive-receiver
resource "google_cloud_run_v2_service" "drive_receiver" {
  name     = "drive-receiver"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.pipeline_sa.email

    containers {
      image = "gcr.io/${var.project_id}/drive-receiver:latest"

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "RAW_BUCKET_NAME"
        value = google_storage_bucket.raw_bucket.name
      }
      env {
        name  = "DRIVE_FILE_ID"
        value = var.drive_file_id
      }
      # WEBHOOK_URL is patched after first deploy via gcloud run services update
      env {
        name  = "WEBHOOK_URL"
        value = "https://placeholder.run.app"
      }
      # ✅ DRIVE_SECRET_NAME tells the app which secret to fetch at runtime via Secret Manager API
      # The actual secret value lives encrypted in Secret Manager — never in env vars or code
      env {
        name  = "DRIVE_SECRET_NAME"
        value = google_secret_manager_secret.drive_sa_credentials.secret_id
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret.drive_sa_credentials,
  ]
}

# Allow public unauthenticated access to Drive Webhook receiver endpoint
resource "google_cloud_run_v2_service_iam_member" "webhook_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.drive_receiver.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Cloud Run Service: parquet-migrator
resource "google_cloud_run_v2_service" "parquet_migrator" {
  name     = "parquet-migrator"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.pipeline_sa.email
    containers {
      image = "gcr.io/${var.project_id}/parquet-migrator:latest" # Image will be built & pushed during deployment
      
      env {
        name  = "PROCESSED_BUCKET_NAME"
        value = google_storage_bucket.processed_bucket.name
      }
      env {
        name  = "BQ_DATASET_ID"
        value = "health_analytics"
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Pub/Sub Push Subscription to invoke parquet-migrator on file upload
resource "google_pubsub_subscription" "migrator_push_sub" {
  name  = "parquet-migrator-gcs-trigger"
  topic = google_pubsub_topic.gcs_topic.name

  push_config {
    push_endpoint = google_cloud_run_v2_service.parquet_migrator.uri
    oidc_token {
      service_account_email = google_service_account.pipeline_sa.email
    }
  }

  depends_on = [google_pubsub_topic.gcs_topic]
}

# Allow Pub/Sub to invoke the parquet-migrator service
resource "google_cloud_run_v2_service_iam_member" "migrator_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.parquet_migrator.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# Cloud Scheduler Watch Renewal Job (triggers every 6 days)
resource "google_cloud_scheduler_job" "watch_renewal" {
  name             = "gdrive-watch-renewal"
  description      = "Trigger drive-receiver to renew Google Drive files.watch channel"
  schedule         = "0 0 */6 * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.drive_receiver.uri}/renew"
    oidc_token {
      service_account_email = google_service_account.pipeline_sa.email
    }
  }

  depends_on = [google_cloud_run_v2_service.drive_receiver]
}
