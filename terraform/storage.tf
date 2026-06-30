# GCS Bucket for Raw Zip Archive
resource "google_storage_bucket" "raw_bucket" {
  name          = "${var.project_id}-health-raw-zip"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 90 # Auto-delete raw zip backups after 90 days to keep GCS free-tier clean
    }
    action {
      type = "Delete"
    }
  }
  
  depends_on = [google_project_service.apis]
}

# GCS Bucket for Processed Parquet
resource "google_storage_bucket" "processed_bucket" {
  name          = "${var.project_id}-health-processed-parquet"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30 # Auto-delete old Parquet files after 30 days (BigQuery already has the data)
    }
    action {
      type = "Delete"
    }
  }
  
  depends_on = [google_project_service.apis]
}
