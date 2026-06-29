# 🏃 Health Connect → GCP Serverless Analytics Pipeline

> **A fully automated, event-driven, always-free data pipeline that syncs your Android Health Connect data to Google BigQuery and visualizes it in Grafana — triggered automatically every time you export a backup from your phone.**

[![GCP Free Tier](https://img.shields.io/badge/GCP-Free%20Tier-blue?logo=google-cloud)](https://cloud.google.com/free)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-Serverless-green?logo=google-cloud)](https://cloud.google.com/run)
[![BigQuery](https://img.shields.io/badge/BigQuery-Analytics-orange?logo=google-cloud)](https://cloud.google.com/bigquery)
[![Terraform](https://img.shields.io/badge/Terraform-IaC-purple?logo=terraform)](https://terraform.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 Table of Contents

1. [What This Project Does](#-what-this-project-does)
2. [Architecture Overview](#-architecture-overview)
3. [Data Available](#-data-available)
4. [Tech Stack & Free Tier Usage](#-tech-stack--free-tier-usage)
5. [Prerequisites](#-prerequisites)
6. [Quick Start](#-quick-start)
7. [Step-by-Step Manual Setup](#-step-by-step-manual-setup)
8. [Directory Structure](#-directory-structure)
9. [Services Deep Dive](#-services-deep-dive)
10. [Grafana Dashboard Setup](#-grafana-dashboard-setup)
11. [Security Architecture](#-security-architecture)
12. [Known Limitations](#-known-limitations)
13. [Troubleshooting](#-troubleshooting)
14. [Contributing](#-contributing)
15. [License](#-license)

---

## 🎯 What This Project Does

Android's **Health Connect** app lets you export all your health data (steps, heart rate, sleep, workouts, GPS routes, calories) into a single SQLite database ZIP file. This project takes that ZIP file and builds a fully automated cloud pipeline around it:

1. **You export** a backup from your phone to Google Drive (one tap)
2. **Google Drive detects** the file changed and fires a webhook
3. **Cloud Run** downloads the ZIP, extracts the SQLite database, converts every table to compressed Parquet format using DuckDB
4. **BigQuery** receives all 18 health tables, ready for SQL analytics
5. **Grafana** connects to BigQuery and visualizes your health trends in beautiful dashboards

**The entire pipeline runs on GCP's Always Free tier — $0/month.**

### What You Get

| Metric | Coverage | Rows |
|---|---|---|
| Steps | 273/290 days (94%) | 57,024 |
| Distance | 268/290 days (92%) | 29,872 |
| Heart Rate | 130,988 samples, 189 days | 130,988 |
| Sleep Sessions | 144 days (50%) | 209 |
| Sleep Stages | 4,205 segments | 4,205 |
| Calories (Total) | 25,049 records | 25,049 |
| Exercise Sessions | 199 workouts | 199 |
| Resting Heart Rate | 133 days | 133 |
| GPS Routes | 1,723 GPS points | 1,723 |
| + 9 more tables | — | — |

---

## 🗺️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        YOUR ANDROID PHONE                               │
│  Health Connect App → Export → health_connect_export.zip → Google Drive │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ File updated
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         GOOGLE DRIVE API                                │
│  files.watch() channel → HTTP POST notification (every file change)     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ Webhook POST /webhook
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│           CLOUD RUN: drive-receiver  (Python/Flask)                     │
│  • Validates Drive webhook headers                                      │
│  • Downloads updated ZIP from Drive (streaming, 8MB chunks)             │
│  • Uploads ZIP to GCS Raw Bucket                                        │
│  • Credentials fetched from Secret Manager (no JSON files)              │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ gs://PROJECT-health-raw-zip/
                                    │ OBJECT_FINALIZE event
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CLOUD PUB/SUB TOPIC                                  │
│  GCS notification → Pub/Sub → Push subscription to parquet-migrator     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ OIDC-authenticated POST
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│          CLOUD RUN: parquet-migrator  (Python/Flask/DuckDB)             │
│  • Downloads ZIP from GCS                                               │
│  • Extracts health_connect_export.db (SQLite)                           │
│  • Converts 18 tables → Parquet (ZSTD compressed) via DuckDB           │
│  • Uploads Parquet files to GCS Processed Bucket                        │
│  • Loads all tables into BigQuery (WRITE_TRUNCATE)                      │
└──────────────────────┬────────────────────────────┬────────────────────┘
                       │                            │
                       ▼                            ▼
        gs://PROJECT-health-              BigQuery Dataset:
        processed-parquet/                health_analytics
        parquet/TABLE/TABLE.parquet       (18 tables)
                                                    │
                                                    ▼
                                       ┌────────────────────┐
                                       │   GRAFANA CLOUD    │
                                       │  BigQuery Plugin   │
                                       │  Dashboards 📊     │
                                       └────────────────────┘

── AUTOMATED WATCH RENEWAL ──────────────────────────────────────────────
  Cloud Scheduler (every 6 days) → POST /renew → drive-receiver
  → files.watch() with new UUID → new 6-day watch channel
  (Drive webhooks expire after max 7 days — this keeps them alive forever)
```

---

## 📊 Data Available

All 18 tables land in BigQuery under the `health_analytics` dataset:

| Table | Description | Key Columns |
|---|---|---|
| `steps_record_table` | Step counts per interval | `start_time`, `end_time`, `count` |
| `heart_rate_record_series_table` | Continuous HR readings | `epoch_millis`, `beats_per_minute` |
| `heart_rate_record_table` | HR session boundaries | `start_time`, `end_time` |
| `sleep_session_record_table` | Sleep sessions | `start_time`, `end_time` |
| `sleep_stages_table` | Deep/REM/Light/Awake stages | `stage_type`, `stage_start_time`, `stage_end_time` |
| `distance_record_table` | Distance per interval | `start_time`, `end_time`, `distance` (meters) |
| `active_calories_burned_record_table` | Active calorie burn | `start_time`, `end_time`, `active_calories_burned` |
| `total_calories_burned_record_table` | Total calorie burn | `start_time`, `end_time`, `energy` (Joules → kCal = /4184) |
| `exercise_session_record_table` | Workout sessions | `start_time`, `end_time`, `exercise_type` |
| `exercise_route_table` | GPS coordinates | `timestamp_millis`, `latitude`, `longitude`, `altitude` |
| `exercise_segments_table` | Workout splits/sets | `segment_type`, `repetitions_count`, `weight_grams` |
| `resting_heart_rate_record_table` | Resting HR per day | `time`, `beats_per_minute` |
| `weight_record_table` | Body weight entries | `time`, `weight` (grams → kg = /1000) |
| `steps_cadence_record_table` | Cadence time series | `epoch_millis`, `rate` (steps/min) |
| `speed_record_table` | Speed time series | `epoch_millis`, `speed` (m/s) |
| `elevation_gained_record_table` | Elevation climbed | `start_time`, `end_time`, `elevation` (meters) |
| `application_info_table` | Source apps | `package_name`, `app_name` |
| `device_info_table` | Recording devices | `manufacturer`, `model` |

### Sleep Stage Type Reference

| `stage_type` value | Meaning |
|---|---|
| 1 | Awake |
| 4 | Light Sleep |
| 5 | Deep Sleep |
| 6 | REM Sleep |

---

## 🛠️ Tech Stack & Free Tier Usage

| GCP Service | Role | Free Tier Limit | Our Usage |
|---|---|---|---|
| **Cloud Run** | Serverless containers | 2M requests/mo, 360K vCPU-sec/mo | ~30 invocations/mo |
| **Cloud Storage** | File storage | 5 GB Standard | ~200 MB |
| **Cloud Pub/Sub** | Event routing | 10 GB/mo | ~30 MB/mo |
| **BigQuery** | Data warehouse | 10 GB storage, 1 TB query/mo | ~200 MB storage |
| **Secret Manager** | Secure credentials | 6 active secrets free | 1 secret |
| **Cloud Scheduler** | Cron jobs | 3 jobs/mo free | 1 job |
| **Container Registry** | Docker images | Part of GCS (5 GB) | ~1 GB |
| **Google Drive API** | File watching | Free | push notifications |

**Estimated monthly cost: $0.00** ✅

---

## 📋 Prerequisites

### Required Tools

| Tool | Version | Install |
|---|---|---|
| `gcloud` CLI | Latest | [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) |
| `docker` | 20.x+ | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| `terraform` | 1.3.0+ | [developer.hashicorp.com/terraform/install](https://developer.hashicorp.com/terraform/install) |
| `python3` | 3.9+ | Pre-installed on most systems |
| `curl` | Any | `sudo apt install curl` |

### Required Accounts

- **Google Account** with a GCP project (billing enabled — but we stay within free limits)
- **Grafana Cloud** free account → [grafana.com/auth/sign-up](https://grafana.com/auth/sign-up)
- **Android phone** with Health Connect installed and exporting data

### Verify Installation

```bash
gcloud --version
docker --version
terraform --version
python3 --version
```

---

## ⚡ Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/health-connect-pipeline.git
cd health-connect-pipeline

# 2. Edit the config section at the top of setup.sh
nano setup.sh   # Set PROJECT_ID and DRIVE_FILE_ID

# 3. Run the automated setup (takes ~10 minutes)
chmod +x setup.sh
./setup.sh
```

That's it! The script handles everything automatically.

---

## 📚 Step-by-Step Manual Setup

If you prefer to understand and run each step manually, follow this guide.

### Step 1 — Prepare Your Google Drive File

1. Install **Health Connect** on your Android phone
2. Open Health Connect → Settings → **Export health data**
3. Export to Google Drive (creates `health_connect_export.zip`)
4. Note the **file ID** from the Drive URL:
   ```
   https://drive.google.com/file/d/THIS_IS_YOUR_FILE_ID/view
   ```

### Step 2 — Clone & Configure

```bash
git clone https://github.com/YOUR_USERNAME/health-connect-pipeline.git
cd health-connect-pipeline
```

Edit `terraform/terraform.tfvars`:
```hcl
project_id    = "your-gcp-project-id"
drive_file_id = "your-drive-file-id"
region        = "us-central1"
```

### Step 3 — Authenticate gcloud

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login   # Needed for Terraform
```

### Step 4 — Enable APIs

```bash
gcloud services enable \
  run.googleapis.com pubsub.googleapis.com storage.googleapis.com \
  bigquery.googleapis.com drive.googleapis.com \
  cloudscheduler.googleapis.com iam.googleapis.com \
  secretmanager.googleapis.com containerregistry.googleapis.com
```

### Step 5 — Create Service Account & Store Credentials

```bash
# Create the service account
gcloud iam service-accounts create health-pipeline-sa \
  --display-name="Health Pipeline Service Account"

SA_EMAIL="health-pipeline-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# Grant required roles
for ROLE in roles/storage.objectAdmin roles/bigquery.admin \
            roles/run.invoker roles/pubsub.publisher \
            roles/pubsub.subscriber roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" --role="${ROLE}" --quiet
done

# Create key → store in Secret Manager → delete local file
gcloud iam service-accounts keys create /tmp/sa-key.json \
  --iam-account="${SA_EMAIL}"

gcloud secrets create drive-sa-credentials \
  --replication-policy=automatic \
  --data-file=/tmp/sa-key.json

rm /tmp/sa-key.json   # Delete immediately — no JSON files left!

# Grant pipeline SA access to read its own secret
gcloud secrets add-iam-policy-binding drive-sa-credentials \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 6 — Share Drive File With Service Account

Open your Drive file → Share → Add `health-pipeline-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com` as **Viewer**.

### Step 7 — Initial Cloud Build (CI/CD)

```bash
# Grant Cloud Build permissions to deploy to Cloud Run
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT --format="value(projectNumber)")
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:${CLOUDBUILD_SA}" --role="roles/run.admin"

gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" --role="roles/iam.serviceAccountUser"

# Submit initial builds to Cloud Build (serverless, no local Docker needed)
gcloud builds submit services/drive-receiver/ --tag gcr.io/YOUR_PROJECT/drive-receiver:latest
gcloud builds submit services/parquet-migrator/ --tag gcr.io/YOUR_PROJECT/parquet-migrator:latest
```

> **Automating CI/CD with GitHub:** To make this completely autonomous, go to **GCP Console > Cloud Build > Triggers**, connect your GitHub repo, and create two triggers pointing to the `cloudbuild.yaml` files in each service directory. Set the "Included files" filter to `services/drive-receiver/**` and `services/parquet-migrator/**` respectively. This guarantees that a change to one service won't rebuild the other!

### Step 8 — Deploy Infrastructure with Terraform

```bash
cd terraform

terraform init

# Import pre-existing resources (created manually in steps 5)
terraform import google_service_account.pipeline_sa \
  "projects/YOUR_PROJECT/serviceAccounts/${SA_EMAIL}"
terraform import google_secret_manager_secret.drive_sa_credentials \
  "projects/YOUR_PROJECT/secrets/drive-sa-credentials"

terraform apply -auto-approve
cd ..
```

### Step 9 — Wire the Webhook URL

```bash
# Get the deployed Cloud Run URL
URL=$(gcloud run services describe drive-receiver \
  --region=us-central1 --format="value(status.url)")

# Patch the WEBHOOK_URL env var (needed for watch renewal)
gcloud run services update drive-receiver \
  --region=us-central1 \
  --update-env-vars="WEBHOOK_URL=${URL}"

# Register the first Drive watch channel
curl -X POST "${URL}/renew"
```

### Step 10 — Test End-to-End

```bash
# Zip your local DB file
python3 -c "
import zipfile
with zipfile.ZipFile('/tmp/test.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    z.write('health_connect_export.db', 'health_connect_export.db')
"

# Upload to GCS raw bucket (triggers the full pipeline!)
gcloud storage cp /tmp/test.zip gs://YOUR_PROJECT-health-raw-zip/health_connect_export.zip

# Wait ~60 seconds, then check BigQuery
bq ls YOUR_PROJECT:health_analytics
```

---

## 📁 Directory Structure

```
health-connect-pipeline/
│
├── 📄 README.md                    ← You are here
├── 🔧 setup.sh                     ← One-command automated setup
│
├── terraform/                      ← Infrastructure as Code (IaC)
│   ├── main.tf                     ← GCP provider + APIs + Secret Manager
│   ├── storage.tf                  ← GCS buckets (raw + processed)
│   ├── pubsub.tf                   ← Pub/Sub topic + GCS notifications
│   ├── compute.tf                  ← Cloud Run services + IAM + Scheduler
│   ├── variables.tf                ← Input variable declarations
│   └── terraform.tfvars            ← Your actual values (gitignored!)
│
├── services/
│   │
│   ├── drive-receiver/             ← Ingestion Microservice
│   │   ├── main.py                 ← Flask app (webhook + renew endpoints)
│   │   ├── requirements.txt        ← Python dependencies
│   │   └── Dockerfile              ← Container definition
│   │
│   └── parquet-migrator/           ← Processing Microservice
│       ├── main.py                 ← Flask app (Pub/Sub event handler)
│       ├── migrate_health.py       ← Core migration logic (SQLite→Parquet→BQ)
│       ├── requirements.txt        ← Python dependencies
│       └── Dockerfile              ← Container definition
│
├── health_parquet/                 ← Local Parquet exports (gitignored)
├── health_connect_export.db        ← Local SQLite DB (gitignored)
└── health_analytics.duckdb         ← Local DuckDB file (gitignored)
```

> ⚠️ **Add to `.gitignore`**:
> ```
> *.db
> *.duckdb
> health_parquet/
> terraform/terraform.tfvars
> terraform/.terraform/
> terraform/*.tfstate*
> *.json
> ```

---

## 🔍 Services Deep Dive

### drive-receiver

**Purpose**: Receives Google Drive push notifications when your health ZIP file is updated.

**Endpoints**:
| Endpoint | Method | Description |
|---|---|---|
| `/webhook` | POST | Receives Drive change notifications |
| `/renew` | POST | Registers/renews the Drive watch channel |
| `/health` | GET | Health check (returns `{"status":"healthy"}`) |

**How the webhook flow works**:
1. Google Drive calls `POST /webhook` with special headers:
   - `X-Goog-Resource-State: update` → file was modified
   - `X-Goog-Resource-State: sync` → channel just registered (safe to ignore)
2. Service downloads the ZIP from Drive using streaming (8 MB chunks)
3. Uploads ZIP to `gs://PROJECT-health-raw-zip/`
4. Returns 200 OK within Drive's timeout window

**Security**: Drive SA credentials are fetched from Secret Manager at startup and cached in memory. GCS upload uses ADC (no credentials needed — Cloud Run's attached SA is used automatically).

### parquet-migrator

**Purpose**: Converts the raw SQLite database to columnar Parquet format and loads it into BigQuery.

**Trigger**: Pub/Sub push subscription fires on every `OBJECT_FINALIZE` event from the GCS raw bucket.

**Processing steps**:
1. Decodes base64 Pub/Sub message → extracts GCS bucket + object name
2. Downloads ZIP from GCS to `/tmp/health_processing/`
3. Extracts `health_connect_export.db` from ZIP
4. For each of 18 tables:
   - Reads via DuckDB's `sqlite_scan()` extension
   - Projects only meaningful columns (strips internal metadata)
   - Exports to `TABLE.parquet` with ZSTD compression
5. Uploads all Parquet files to `gs://PROJECT-health-processed-parquet/parquet/TABLE/`
6. Calls BigQuery load jobs (WRITE_TRUNCATE → full refresh each time)
7. Cleans up `/tmp/` directory

**Why DuckDB?** DuckDB can query SQLite databases directly via its `sqlite_scan` extension — no SQLite3 Python calls needed. It also handles Parquet export and ZSTD compression natively.

---

## 📊 Grafana Dashboard Setup

### Connect BigQuery as a Data Source

1. Log in to [grafana.com](https://grafana.com) (free account)
2. Go to **Connections** → **Add new connection** → search **BigQuery**
3. Install the **Google BigQuery** plugin
4. Create a new data source:
   - **Authentication**: Use GCP service account JSON (Upload `grafana-key.json` generated by `setup.sh`)
   - **Project**: `your-gcp-project-id`
   - **Default Dataset**: `health_analytics`

> **Note**: The `setup.sh` script automatically creates a `grafana-reader` service account with `roles/bigquery.dataViewer` and `roles/bigquery.jobUser` and exports the key to `grafana-key.json` for you.

### 🌐 GCP Observability (Monitor your Cloud Resources)

Because the `setup.sh` script also grants the `grafana-reader` service account `roles/monitoring.viewer` and `roles/compute.viewer`, you can use the exact same JSON key to monitor your entire GCP project in Grafana!

1. Go to **Connections** → **Add new connection** → search **Google Cloud Monitoring**.
2. Under Authentication, select **JWT File** and upload the exact same `grafana-key.json`.
3. Set Default Project to your GCP project ID and click **Save & Test**.
4. Click on the **Dashboards** tab inside the connection settings and click **Import** to instantly get pre-built observability dashboards for:
   - **Google Cloud / Cloud Run**
   - **Google Cloud / Cloud Storage**
   - **Google Cloud / BigQuery**
   - **Google Cloud / PubSub**

### Example BigQuery Queries for Panels

**Daily Steps (Time Series)**:
```sql
SELECT
  DATE(TIMESTAMP_MILLIS(start_time)) AS date,
  SUM(count) AS total_steps
FROM `PROJECT.health_analytics.steps_record_table`
GROUP BY date
ORDER BY date
```

**Sleep Stage Distribution (Pie Chart)**:
```sql
SELECT
  CASE stage_type
    WHEN 1 THEN 'Awake'
    WHEN 4 THEN 'Light Sleep'
    WHEN 5 THEN 'Deep Sleep'
    WHEN 6 THEN 'REM Sleep'
  END AS stage,
  SUM((stage_end_time - stage_start_time) / 60000.0) AS duration_minutes
FROM `PROJECT.health_analytics.sleep_stages_table`
GROUP BY stage_type
```

**Resting Heart Rate Trend (Time Series)**:
```sql
SELECT
  TIMESTAMP_MILLIS(time) AS recorded_at,
  beats_per_minute AS resting_bpm
FROM `PROJECT.health_analytics.resting_heart_rate_record_table`
ORDER BY time
```

**Heart Rate Zones During Exercise**:
```sql
SELECT
  CASE
    WHEN beats_per_minute < 111 THEN '1. Warm Up'
    WHEN beats_per_minute < 130 THEN '2. Fat Burn'
    WHEN beats_per_minute < 148 THEN '3. Aerobic'
    WHEN beats_per_minute < 166 THEN '4. Anaerobic'
    ELSE '5. Peak'
  END AS zone,
  COUNT(*) AS samples
FROM `PROJECT.health_analytics.heart_rate_record_series_table`
GROUP BY zone
ORDER BY zone
```

**Sleep Duration by Day of Week**:
```sql
SELECT
  FORMAT_DATE('%A', DATE(TIMESTAMP_MILLIS(start_time))) AS day_of_week,
  AVG((end_time - start_time) / 3600000.0) AS avg_sleep_hours
FROM `PROJECT.health_analytics.sleep_session_record_table`
GROUP BY EXTRACT(DAYOFWEEK FROM TIMESTAMP_MILLIS(start_time)), day_of_week
ORDER BY EXTRACT(DAYOFWEEK FROM TIMESTAMP_MILLIS(start_time))
```

---

## 🔐 Security Architecture

This project was built with **zero-trust principles** for handling personal health data:

| Security Control | Implementation |
|---|---|
| **No JSON keys on disk** | SA key created → immediately stored in Secret Manager → local file deleted |
| **No secrets in env vars** | `DRIVE_SECRET_NAME` env var holds only the *name* of the secret, not the value |
| **Runtime secret fetch** | drive-receiver fetches SA credentials from Secret Manager at startup |
| **ADC for GCP services** | Cloud Run's attached SA provides automatic credentials for GCS/BigQuery/Pub/Sub — no keys needed |
| **Private parquet-migrator** | Only accepts requests authenticated with OIDC tokens from Pub/Sub (returns 403 to everyone else) |
| **Public drive-receiver** | Must be public to receive Google Drive webhooks (Drive cannot authenticate to private endpoints) |
| **Least-privilege IAM** | Each role granted is the minimum required for the specific operation |
| **Drive file sharing** | File shared only with pipeline SA (Viewer access), not made public |
| **TLS everywhere** | All Cloud Run endpoints are HTTPS-only by default |

---

## ⚠️ Known Limitations

### Google Drive Webhook Expiration
- **Limitation**: Drive push notification channels expire after **maximum 7 days**
- **Solution**: Cloud Scheduler runs every 6 days to renew the channel automatically
- **Risk**: If the scheduler fails and the channel expires, you'll miss updates until manually renewed
- **Manual fix**: `curl -X POST YOUR_WEBHOOK_URL/renew`

### Samsung Health Sleep Score
- **Limitation**: Samsung's sleep score (0-100) and "Fair/Good" rating is a proprietary algorithm and is **not exported** by Health Connect
- **Workaround**: We can approximate it using sleep duration + stage percentages + regularity metrics

### Sleep Regularity Score
- **Limitation**: Health Connect doesn't export a sleep regularity percentage directly
- **Workaround**: Compute it in BigQuery using standard deviation of bedtime times over 30-day windows

### Sparse Weight Data
- **Limitation**: Weight entries are only recorded when you manually log them (15% coverage over 9 months)
- **No workaround** — this is a data collection limitation

### vo2_max_record_table Empty
- **Limitation**: VO2 Max data requires a VO2 Max-capable wearable. The table exists but has no rows
- **Note**: Added to migration script for forward compatibility

### NAP Detection
- **Limitation**: Health Connect doesn't have a separate "nap" table
- **Workaround**: Short sleep sessions (<2 hours) during daytime hours (10:00–18:00) can be classified as naps in BigQuery

### BigQuery WRITE_TRUNCATE on Every Run
- **Limitation**: Each pipeline run completely overwrites all BigQuery tables (no incremental append)
- **Reason**: Health Connect re-exports the entire history every time, so deduplication on append would be complex
- **Impact**: BigQuery load jobs count against the free 1TB query quota. At current data sizes (~200MB), this is well within limits
- **Future improvement**: Implement incremental loads using `start_time` watermarks

### Cloud Run Cold Starts
- **Limitation**: parquet-migrator has a 60-second timeout on DuckDB processing. Very large databases (>500 MB) may timeout
- **Current DB size**: ~46 MB — well within limits
- **Future improvement**: Increase Cloud Run timeout or switch to Cloud Run Jobs

---

## 🔧 Troubleshooting

### Drive watch channel not receiving updates

```bash
# Check the current watch channel
curl -X POST YOUR_WEBHOOK_URL/renew | python3 -m json.tool

# Check drive-receiver logs for webhook events
gcloud run services logs read drive-receiver --region=us-central1 --limit=50
```

### parquet-migrator not triggered after GCS upload

```bash
# Check if Pub/Sub subscription is delivering
gcloud pubsub subscriptions describe parquet-migrator-gcs-trigger

# Check migrator logs
gcloud run services logs read parquet-migrator --region=us-central1 --limit=50

# Check Pub/Sub dead-letter / undelivered messages
gcloud pubsub subscriptions pull parquet-migrator-gcs-trigger --limit=5
```

### BigQuery tables not loading

```bash
# Check BigQuery recent load jobs
bq ls -j --project_id=YOUR_PROJECT --max_results=10

# Query a table directly
bq query --use_legacy_sql=false \
  'SELECT COUNT(*) FROM `YOUR_PROJECT.health_analytics.steps_record_table`'
```

### Terraform state conflicts

```bash
# List what's in state
terraform state list

# If a resource was created outside Terraform, import it
terraform import RESOURCE_TYPE.NAME RESOURCE_ID

# If state is corrupt, view and remove specific resources
terraform state rm RESOURCE_TYPE.NAME
```

### Docker push authentication fails

```bash
# Re-authenticate Docker with GCR
gcloud auth configure-docker gcr.io --quiet

# Verify Docker credentials
docker pull gcr.io/YOUR_PROJECT/drive-receiver:latest
```

---

## 🚀 Future Improvements

- [ ] **Incremental BigQuery loads** — append only new records using watermarks
- [ ] **LLM Health Insights** — scheduled Cloud Run job exports weekly summaries to Gemini for personalized health recommendations
- [ ] **Grafana dashboard export** — share pre-built dashboard JSON
- [ ] **Sleep score computation** — BigQuery view that approximates Samsung's sleep score algorithm
- [ ] **Alert policies** — Cloud Monitoring alerts when RHR spikes >5 BPM above 7-day baseline
- [ ] **Multi-user support** — parameterize by Drive file ID for family health tracking
- [ ] **Terraform Cloud backend** — remote state storage for team environments

---

## 🤝 Contributing

Pull requests welcome! For major changes, open an issue first to discuss.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit with conventional commits: `git commit -m 'feat: add sleep score approximation'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file.

---

## 🙏 Acknowledgements

- [DuckDB](https://duckdb.org/) — for making SQLite → Parquet conversion trivially easy
- [Google Health Connect](https://developer.android.com/health-and-fitness/guides/health-connect) — for open health data export
- [Grafana](https://grafana.com) — for the beautiful free cloud dashboards
- [Terraform Google Provider](https://registry.terraform.io/providers/hashicorp/google) — for clean GCP IaC

---

<div align="center">
  Made with ❤️ for personal health analytics · <a href="https://github.com/YOUR_USERNAME/health-connect-pipeline">GitHub</a>
</div>
