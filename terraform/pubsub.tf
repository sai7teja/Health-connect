# Pub/Sub Topic for GCS upload events
resource "google_pubsub_topic" "gcs_topic" {
  name = "health-raw-zip-events"
  
  depends_on = [google_project_service.apis]
}

# ── Dead Letter Topic ───────────────────────────────────────────────────────
# Messages that fail processing after max retries land here instead of being
# silently dropped. This prevents data loss from transient failures.
resource "google_pubsub_topic" "dead_letter_topic" {
  name = "health-pipeline-dead-letter"

  depends_on = [google_project_service.apis]
}

# Dead letter subscription — retains failed messages for 7 days (free tier)
resource "google_pubsub_subscription" "dead_letter_sub" {
  name  = "health-pipeline-dead-letter-sub"
  topic = google_pubsub_topic.dead_letter_topic.name

  message_retention_duration = "604800s" # 7 days
  retain_acked_messages      = true

  expiration_policy {
    ttl = "" # Never expire
  }
}

# Service Account for GCS to publish events to Pub/Sub
data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

# Grant GCS service account permission to publish to Pub/Sub topic
resource "google_pubsub_topic_iam_binding" "gcs_pub_binding" {
  topic = google_pubsub_topic.gcs_topic.name
  role  = "roles/pubsub.publisher"
  members = [
    "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
  ]
}

# Grant Pub/Sub service account permission to publish to Dead Letter topic
# (required so Pub/Sub can forward failed messages)
resource "google_pubsub_topic_iam_binding" "dead_letter_pub_binding" {
  topic = google_pubsub_topic.dead_letter_topic.name
  role  = "roles/pubsub.publisher"
  members = [
    "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  ]
}

# Data source for project number (needed for Pub/Sub service agent email)
data "google_project" "project" {
  project_id = var.project_id
}

# Setup GCS Bucket notification to publish to Pub/Sub topic on uploads
resource "google_storage_notification" "gcs_notification" {
  bucket         = google_storage_bucket.raw_bucket.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.gcs_topic.id
  event_types    = ["OBJECT_FINALIZE"]

  depends_on = [google_pubsub_topic_iam_binding.gcs_pub_binding]
}
