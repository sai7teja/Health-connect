# Pub/Sub Topic for GCS upload events
resource "google_pubsub_topic" "gcs_topic" {
  name = "health-raw-zip-events"
  
  depends_on = [google_project_service.apis]
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

# Setup GCS Bucket notification to publish to Pub/Sub topic on uploads
resource "google_storage_notification" "gcs_notification" {
  bucket         = google_storage_bucket.raw_bucket.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.gcs_topic.id
  event_types    = ["OBJECT_FINALIZE"]

  depends_on = [google_pubsub_topic_iam_binding.gcs_pub_binding]
}
