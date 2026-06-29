# Project: Serverless Health Connect Data Pipeline

This document summarizes the goals, context, and current status of the project as reconstructed from [kiro.chat.log](file:///home/ztejksa/Downloads/Health/kiro.chat.log).

---

## 🎯 Main Goal

Establish an automated, event-driven, **always-free** data ingestion and analysis pipeline on Google Cloud Platform (GCP) to sync and process personal health records from Android Health Connect.

### End-to-End Workflow Design
1. **Source Backup**: Mobile device exports health records into a zipped SQLite archive (`health_connect_export.zip`) to a designated Google Drive folder.
2. **Change Watcher**: Google Drive API sends push notifications (webhooks) to a GCP HTTPS endpoint on file updates.
3. **Queue / Event Router**: Notifications trigger Google Cloud Pub/Sub.
4. **Extraction Service**: A Cloud Run service downloads the ZIP file from Drive, extracts the database (`health_connect_export.db`), and stores it in Google Cloud Storage (GCS).
5. **Data Processor**: A GCS event notification triggers a second Cloud Run service (or job) executing the migration script. The script projects clean columns, converts tables to Parquet files (compressed with ZSTD), and uploads them back to GCS.
6. **Data Warehouse**: The Parquet files are loaded into Google BigQuery (within the 10 GB free tier).
7. **Visualization**: A Grafana instance (via Grafana Cloud Free or hosted on Cloud Run) connects directly to BigQuery for visualization.
8. **AI Assistant Integration**: A scheduled job exports key summaries from BigQuery to an LLM for personalized health suggestions.

---

## 📂 Current Local Context

### 1. Existing Workspace Files
* **[health_connect_export.db](file:///home/ztejksa/Downloads/Health/health_connect_export.db)**: Original SQLite database (~46 MB) containing raw records from Health Connect.
* **[migrate_health.py](file:///home/ztejksa/Downloads/Health/migrate_health.py)**: Python script implementing SQLite-to-DuckDB & Parquet migration.
* **[health_analytics.duckdb](file:///home/ztejksa/Downloads/Health/health_analytics.duckdb)**: Transformed DuckDB file (~5 MB).
* **[health_parquet](file:///home/ztejksa/Downloads/Health/health_parquet)**: Directory containing columnar Parquet exports.

### 2. Migration Status
The script successfully exports 12 high-value tables to Parquet format and configures these local DuckDB views:
* `v_heart_rate`: Epoch milliseconds mapped to datetime, heart rates (BPM), and session IDs.
* `v_steps_daily`: Aggregated daily step count.
* `v_sleep`: Sleep sessions including start/end times and durations in hours.
* `v_weight`: Weight trend in kg (originally tracked as `time` instead of `start_time` and divided by 1000).
* `v_resting_hr`: Resting heart rate recordings over time.
* `v_sleep_stages`: Fine-grained sleep stage segments (Deep, REM, Light, etc.) with durations in minutes.

### 3. Data Audit Results
A local audit indicates the following coverage from September 12, 2025 to June 28, 2026 (~9.5 months):
* **Steps**: 273/290 days (94% coverage) — *Excellent for daily trends.*
* **Distance**: 268/290 days (92% coverage) — *Excellent.*
* **Heart Rate**: 130,988 samples across 189 days (65% coverage) — *Good (avg 693 samples/day).*
* **Sleep sessions**: 144 days (50% coverage) — *Moderate.*
* **Sleep stages**: 4,205 segments (51% coverage) — *Moderate.*
* **Exercise sessions**: 199 sessions — *Good.*
* **Resting HR**: 133 days (48% coverage) — *Moderate.*
* **Weight**: 44 entries (15% coverage) — *Sparse.*

---

## 🛠️ Next Steps

To proceed with Phase 1 of the GCP implementation:
1. Initialize a Terraform configuration or GCP deployment scripts.
2. Configure the Google Drive API Push Notification channel.
3. Scaffold the extractor service code (extracting `health_connect_export.db` from the zipped file and uploading it to GCS).
