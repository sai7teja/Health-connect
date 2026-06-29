variable "project_id" {
  description = "The GCP project ID to deploy to."
  type        = string
}

variable "region" {
  description = "The GCP region to deploy resources in."
  type        = string
  default     = "us-central1"
}

variable "drive_file_id" {
  description = "The Google Drive File ID of your health_connect_export.zip file."
  type        = string
}
