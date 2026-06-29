#!/usr/bin/env bash
# =============================================================================
#  setup.sh — One-shot deployment script for Health Connect GCP Pipeline
#  Author : kanikesaiteja@gmail.com
#  Repo   : https://github.com/YOUR_USERNAME/health-connect-pipeline
#
#  This script automates every step needed to deploy a fully serverless,
#  event-driven health data pipeline on Google Cloud Platform (GCP) using
#  only free-tier resources.
#
#  Run once:  chmod +x setup.sh && ./setup.sh
#  Re-run safely — each step is idempotent (checks before creating).
# =============================================================================

set -euo pipefail   # Exit on error, unset variable, or pipe failure
IFS=$'\n\t'         # Safer word-splitting

# ─────────────────────────────────────────────────────────────────────────────
#  ████  CONFIG — Edit these variables before running  ████
# ─────────────────────────────────────────────────────────────────────────────

# Your GCP Project ID (find it at console.cloud.google.com)
PROJECT_ID="lazybot7"

# The Google Drive FILE ID of your health_connect_export.zip
# From the file URL: drive.google.com/file/d/THIS_PART/view
DRIVE_FILE_ID="1gLWNAhBW5OLgLaNzTXKJHJXfCJZlFKnF"

# GCP region (us-central1 has the broadest free-tier coverage)
REGION="us-central1"

# BigQuery dataset name (will be created automatically)
BQ_DATASET="health_analytics"

# Service account that will run the pipeline
SA_NAME="health-pipeline-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Secret Manager secret name (stores Drive API credentials securely)
SECRET_NAME="drive-sa-credentials"

# GCS bucket names (must be globally unique — project prefix helps)
RAW_BUCKET="${PROJECT_ID}-health-raw-zip"
PROCESSED_BUCKET="${PROJECT_ID}-health-processed-parquet"

# Container Registry image names
RECEIVER_IMAGE="gcr.io/${PROJECT_ID}/drive-receiver:latest"
MIGRATOR_IMAGE="gcr.io/${PROJECT_ID}/parquet-migrator:latest"

# ─────────────────────────────────────────────────────────────────────────────
#  ANSI colour codes for pretty output
# ─────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'   # No Colour (reset)

# ─────────────────────────────────────────────────────────────────────────────
#  Helper functions
# ─────────────────────────────────────────────────────────────────────────────

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[✓]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[✗]${NC}    $*" >&2; }
step()    { echo -e "\n${BLUE}${BOLD}━━━  $*  ━━━${NC}\n"; }
pause()   { echo -e "${YELLOW}Press ENTER to continue...${NC}"; read -r; }

# Print a banner when any command fails
trap 'error "Command failed at line $LINENO. Check the error above and re-run."; exit 1' ERR

# ─────────────────────────────────────────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────────────────────────────────────────
clear
echo -e "${BLUE}${BOLD}"
cat << 'EOF'
  ╔══════════════════════════════════════════════════════════════╗
  ║     Health Connect → GCP Serverless Pipeline Setup          ║
  ║     Automated deployment using 100% free-tier resources     ║
  ╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"
echo -e "  ${CYAN}Project ID  :${NC} ${PROJECT_ID}"
echo -e "  ${CYAN}Drive File  :${NC} ${DRIVE_FILE_ID}"
echo -e "  ${CYAN}Region      :${NC} ${REGION}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 0 — Preflight checks
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 0: Preflight Checks"

# Check for required CLI tools
REQUIRED_TOOLS=("gcloud" "terraform" "python3" "curl")
for tool in "${REQUIRED_TOOLS[@]}"; do
  if command -v "$tool" &>/dev/null; then
    success "$tool is installed ($(command -v "$tool"))"
  else
    error "$tool is NOT installed. Please install it before running this script."
    echo ""
    case "$tool" in
      gcloud)    echo "  Install: https://cloud.google.com/sdk/docs/install" ;;
      terraform) echo "  Install: https://developer.hashicorp.com/terraform/install" ;;
      python3)   echo "  Install: sudo apt install python3  (Ubuntu/WSL)" ;;
      curl)      echo "  Install: sudo apt install curl" ;;
    esac
    exit 1
  fi
done

# Check gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q "@"; then
  error "gcloud is not authenticated. Please run: gcloud auth login"
  exit 1
fi
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
success "Authenticated as: ${ACTIVE_ACCOUNT}"

# Verify the project exists
if ! gcloud projects describe "${PROJECT_ID}" &>/dev/null; then
  error "Project '${PROJECT_ID}' not found or you don't have access."
  exit 1
fi
success "GCP Project '${PROJECT_ID}' verified"

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 1 — GCP Project Setup
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 1: GCP Project & API Setup"

info "Setting active project to '${PROJECT_ID}'..."
gcloud config set project "${PROJECT_ID}" --quiet
success "Active project set"

info "Enabling all required GCP APIs (this may take ~60 seconds)..."
# Each API serves a specific purpose:
#   run.googleapis.com           — Cloud Run (our serverless containers)
#   pubsub.googleapis.com        — Pub/Sub (event routing between services)
#   storage.googleapis.com       — Google Cloud Storage (file storage)
#   bigquery.googleapis.com      — BigQuery (data warehouse / analytics)
#   drive.googleapis.com         — Google Drive API (file watching)
#   cloudscheduler.googleapis.com— Cloud Scheduler (cron for watch renewal)
#   iam.googleapis.com           — Identity & Access Management
#   secretmanager.googleapis.com — Secret Manager (secure credential storage)
#   containerregistry.googleapis.com — Container Registry (Docker images)
gcloud services enable \
  run.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  drive.googleapis.com \
  cloudscheduler.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project="${PROJECT_ID}" --quiet
success "All APIs enabled"

info "Setting up Application Default Credentials (ADC) for Terraform..."
info "This will open your browser for authentication."
warn "If running in WSL/Linux without a browser, run on Windows PowerShell:"
warn "  gcloud auth application-default login"
pause
gcloud auth application-default login --quiet 2>/dev/null || \
  warn "ADC login may have already been done — continuing..."
success "ADC credentials configured"

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 2 — Service Account & Secret Manager
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 2: Service Account & Secure Credentials"

# Create SA only if it doesn't already exist
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  warn "Service account '${SA_EMAIL}' already exists — skipping creation"
else
  info "Creating service account '${SA_NAME}'..."
  gcloud iam service-accounts create "${SA_NAME}" \
    --project="${PROJECT_ID}" \
    --display-name="Health Pipeline Service Account" \
    --description="Runs the Cloud Run services for the health data pipeline"
  success "Service account created: ${SA_EMAIL}"
fi

info "Granting required IAM roles to the service account..."
# These roles let the SA:
#   storage.objectAdmin     — Read/write GCS buckets
#   bigquery.admin          — Create datasets and load data into BigQuery
#   run.invoker             — Invoke Cloud Run services (used by Pub/Sub)
#   pubsub.publisher        — Publish messages to Pub/Sub topics
#   pubsub.subscriber       — Subscribe to Pub/Sub topics
#   secretmanager.secretAccessor — Read secrets from Secret Manager
for ROLE in \
  "roles/storage.objectAdmin" \
  "roles/bigquery.admin" \
  "roles/run.invoker" \
  "roles/pubsub.publisher" \
  "roles/pubsub.subscriber" \
  "roles/secretmanager.secretAccessor"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet 2>&1 | tail -1
  success "Granted ${ROLE}"
done

# Store SA key in Secret Manager (more secure than env vars)
# We create a temporary key file, push it to Secret Manager, then delete it.
if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
  warn "Secret '${SECRET_NAME}' already exists — skipping creation"
else
  info "Creating SA key and storing it securely in Secret Manager..."
  TEMP_KEY="/tmp/health-sa-key-setup-temp.json"

  # Step 1: Create the key (needed so service account can call Drive API)
  gcloud iam service-accounts keys create "${TEMP_KEY}" \
    --iam-account="${SA_EMAIL}" \
    --project="${PROJECT_ID}"

  # Step 2: Upload the key to Secret Manager (encrypted at rest)
  gcloud secrets create "${SECRET_NAME}" \
    --project="${PROJECT_ID}" \
    --replication-policy=automatic \
    --data-file="${TEMP_KEY}"

  # Step 3: Immediately delete the local copy — no JSON file left on disk
  rm -f "${TEMP_KEY}"
  success "SA key stored in Secret Manager and local copy deleted"
fi

info "Granting pipeline SA read access to the secret..."
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" --quiet
success "Secret access granted"

echo ""
echo -e "${YELLOW}${BOLD}⚠️  MANUAL STEP REQUIRED — Share your Drive file${NC}"
echo ""
echo "  The service account needs read access to your health_connect_export.zip file."
echo ""
echo "  1. Open your Drive file:"
echo "     https://drive.google.com/file/d/${DRIVE_FILE_ID}/view"
echo ""
echo "  2. Click Share → Add this email as Viewer:"
echo -e "     ${CYAN}${SA_EMAIL}${NC}"
echo ""
echo "  3. Uncheck 'Notify people' → Click Share"
echo ""
pause

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 3 — CI/CD Setup & Initial Build (Serverless)
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 3: CI/CD Setup & Initial Build"

info "Granting Cloud Build permissions to deploy to Cloud Run..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# Allow Cloud Build to deploy to Cloud Run
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin" --quiet >/dev/null

# Allow Cloud Build to attach the pipeline Service Account to Cloud Run
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser" --quiet >/dev/null
success "Cloud Build IAM configured for autonomous CI/CD"

info "Submitting initial build for drive-receiver (runs in Cloud Build, no local Docker needed)..."
gcloud builds submit services/drive-receiver/ \
  --tag "${RECEIVER_IMAGE}" \
  --project="${PROJECT_ID}" \
  --quiet
success "drive-receiver image built & pushed to GCR"

info "Submitting initial build for parquet-migrator..."
gcloud builds submit services/parquet-migrator/ \
  --tag "${MIGRATOR_IMAGE}" \
  --project="${PROJECT_ID}" \
  --quiet
success "parquet-migrator image built & pushed to GCR"

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 4 — Terraform Infrastructure
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 4: Provisioning Infrastructure with Terraform"

info "Updating terraform.tfvars with your project details..."
# Replace placeholders in tfvars with actual values
cat > terraform/terraform.tfvars << EOF
# Auto-generated by setup.sh — do not edit manually
project_id    = "${PROJECT_ID}"
drive_file_id = "${DRIVE_FILE_ID}"
region        = "${REGION}"
EOF
success "terraform.tfvars updated"

info "Initialising Terraform (downloads Google provider plugin)..."
cd terraform
terraform init -upgrade
success "Terraform initialised"

info "Importing pre-existing resources into Terraform state..."
# The SA and Secret were created manually above; we must import them
# so Terraform doesn't try to create them again and throw a 409 error.
if ! terraform state list | grep -q "google_service_account.pipeline_sa"; then
  terraform import \
    google_service_account.pipeline_sa \
    "projects/${PROJECT_ID}/serviceAccounts/${SA_EMAIL}" 2>&1 | tail -3
  success "Service account imported into Terraform state"
else
  warn "Service account already in Terraform state — skipping import"
fi

if ! terraform state list | grep -q "google_secret_manager_secret.drive_sa_credentials"; then
  terraform import \
    google_secret_manager_secret.drive_sa_credentials \
    "projects/${PROJECT_ID}/secrets/${SECRET_NAME}" 2>&1 | tail -3
  success "Secret imported into Terraform state"
else
  warn "Secret already in Terraform state — skipping import"
fi

info "Running terraform apply (creates GCS, Pub/Sub, Cloud Run, Scheduler)..."
info "This will take approximately 2-5 minutes..."
terraform apply -auto-approve
success "All infrastructure provisioned!"
cd ..

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 5 — Post-Deploy Wiring
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 5: Wiring Services Together"

info "Getting live Cloud Run URL for drive-receiver..."
WEBHOOK_URL=$(gcloud run services describe drive-receiver \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)" 2>/dev/null)
success "Cloud Run URL: ${WEBHOOK_URL}"

info "Patching WEBHOOK_URL environment variable on drive-receiver..."
# The webhook URL wasn't known during Terraform apply (chicken-and-egg),
# so we patch it now that the service is deployed.
gcloud run services update drive-receiver \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="WEBHOOK_URL=${WEBHOOK_URL}" \
  --quiet
success "WEBHOOK_URL patched to: ${WEBHOOK_URL}"

info "Verifying drive-receiver health endpoint..."
HEALTH_RESP=$(curl -sf "${WEBHOOK_URL}/health" 2>/dev/null || echo '{"status":"error"}')
if echo "${HEALTH_RESP}" | grep -q "healthy"; then
  success "drive-receiver is healthy: ${HEALTH_RESP}"
else
  warn "Health check returned: ${HEALTH_RESP} — service may still be starting up"
fi

info "Registering the first Google Drive watch channel..."
# This tells Google Drive to send HTTP notifications to our webhook
# whenever the specified file is updated. It expires in 6 days.
# Cloud Scheduler will call /renew every 6 days automatically.
WATCH_RESP=$(curl -sf -X POST "${WEBHOOK_URL}/renew" \
  -H "Content-Type: application/json" 2>/dev/null || echo '{"error":"failed"}')
if echo "${WATCH_RESP}" | grep -q "expiration"; then
  CHANNEL_ID=$(echo "${WATCH_RESP}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','unknown'))")
  EXPIRY=$(echo "${WATCH_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expiration',''))")
  success "Drive watch channel registered!"
  info "  Channel ID : ${CHANNEL_ID}"
  info "  Expires    : ${EXPIRY} (auto-renewed by Cloud Scheduler)"
else
  warn "Watch registration returned: ${WATCH_RESP}"
  warn "If the Drive file isn't shared with the SA yet, share it and run:"
  warn "  curl -X POST ${WEBHOOK_URL}/renew"
fi

# ─────────────────────────────────────────────────────────────────────────────
#  PHASE 6 — End-to-End Test
# ─────────────────────────────────────────────────────────────────────────────
step "PHASE 6: End-to-End Pipeline Test"

# Check if there's a local DB to test with
if [ -f "health_connect_export.db" ]; then
  info "Found local health_connect_export.db — using it for E2E test..."

  info "Zipping database file..."
  python3 -c "
import zipfile, os
with zipfile.ZipFile('/tmp/health_test.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    z.write('health_connect_export.db', 'health_connect_export.db')
size = os.path.getsize('/tmp/health_test.zip') / (1024*1024)
print(f'  Created /tmp/health_test.zip ({size:.1f} MB)')
"
  success "Zip created"

  info "Uploading test zip to GCS raw bucket (this triggers the full pipeline)..."
  gcloud storage cp /tmp/health_test.zip \
    "gs://${RAW_BUCKET}/health_connect_export.zip"
  success "Uploaded to gs://${RAW_BUCKET}/health_connect_export.zip"

  info "Waiting 30 seconds for Pub/Sub → parquet-migrator to process..."
  for i in $(seq 30 -1 1); do
    printf "\r  Processing... %2ds remaining" "$i"
    sleep 1
  done
  echo ""

  info "Checking parquet-migrator logs..."
  gcloud logging read \
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"parquet-migrator\"" \
    --project="${PROJECT_ID}" \
    --limit=10 \
    --format="value(textPayload)" \
    --freshness=5m 2>/dev/null | head -10 || warn "No logs yet — processing may still be running"

  info "Checking BigQuery for loaded tables..."
  sleep 10
  BQ_TABLES=$(bq ls --project_id="${PROJECT_ID}" "${BQ_DATASET}" 2>/dev/null | grep TABLE | wc -l || echo 0)
  if [ "${BQ_TABLES}" -gt 0 ]; then
    success "BigQuery dataset '${BQ_DATASET}' has ${BQ_TABLES} tables loaded!"
  else
    warn "BigQuery tables not yet visible — processing may still be running."
    warn "Check: bq ls ${PROJECT_ID}:${BQ_DATASET}"
  fi

  rm -f /tmp/health_test.zip
else
  warn "No local health_connect_export.db found — skipping automated E2E test."
  warn "To test manually, export a backup from your phone to Drive and watch the pipeline run."
fi

# ─────────────────────────────────────────────────────────────────────────────
#  FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
step "Deployment Complete!"

echo -e "${GREEN}${BOLD}"
cat << 'EOF'
  ╔══════════════════════════════════════════════════════════════╗
  ║                  🎉  All Done!  🎉                          ║
  ╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "  ${BOLD}GCP Resources Created:${NC}"
echo -e "  ├── ${CYAN}Cloud Run${NC}       drive-receiver    → Webhook receiver"
echo -e "  ├── ${CYAN}Cloud Run${NC}       parquet-migrator  → DB processor"
echo -e "  ├── ${CYAN}GCS Bucket${NC}      gs://${RAW_BUCKET}"
echo -e "  ├── ${CYAN}GCS Bucket${NC}      gs://${PROCESSED_BUCKET}"
echo -e "  ├── ${CYAN}Pub/Sub${NC}         health-raw-zip-events"
echo -e "  ├── ${CYAN}BigQuery${NC}        ${PROJECT_ID}.${BQ_DATASET}"
echo -e "  ├── ${CYAN}Secret Manager${NC}  ${SECRET_NAME}"
echo -e "  └── ${CYAN}Cloud Scheduler${NC} gdrive-watch-renewal (every 6 days)"
echo ""
echo -e "  ${BOLD}Service URLs:${NC}"
echo -e "  ├── Webhook   : ${WEBHOOK_URL}/webhook"
echo -e "  ├── Renew     : ${WEBHOOK_URL}/renew"
echo -e "  └── Health    : ${WEBHOOK_URL}/health"
echo ""
echo -e "  ${BOLD}Next Steps:${NC}"
echo -e "  1. Connect ${CYAN}Grafana Cloud${NC} to BigQuery (see README.md)"
echo -e "  2. Export a backup from your phone to trigger the pipeline"
echo -e "  3. Monitor logs: ${CYAN}gcloud run services logs read parquet-migrator --project=${PROJECT_ID}${NC}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "  # Check BigQuery tables"
echo -e "  ${CYAN}bq ls ${PROJECT_ID}:${BQ_DATASET}${NC}"
echo -e "  # View pipeline logs"
echo -e "  ${CYAN}gcloud run services logs read parquet-migrator --region=${REGION}${NC}"
echo -e "  # Manually renew Drive watch"
echo -e "  ${CYAN}curl -X POST ${WEBHOOK_URL}/renew${NC}"
echo ""
success "Setup complete. Happy tracking! 🚀"
