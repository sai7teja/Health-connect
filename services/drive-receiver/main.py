import os
import io
import json
import uuid
import logging
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from google.cloud import storage, secretmanager
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Environment config ──────────────────────────────────────────────────────
PROJECT_ID   = os.environ.get("GCP_PROJECT", "lazybot7")
RAW_BUCKET   = os.environ.get("RAW_BUCKET_NAME")
FILE_ID      = os.environ.get("DRIVE_FILE_ID")          # Drive file ID
WEBHOOK_URL  = os.environ.get("WEBHOOK_URL")
SECRET_NAME  = os.environ.get("DRIVE_SECRET_NAME", "drive-sa-credentials")
FILE_NAME    = "health_connect_export.zip"

# Cache the Drive service to avoid re-fetching the secret on every request
_drive_service = None


def get_secret(secret_id: str) -> str:
    """Fetch the latest version of a secret from Secret Manager.
    Cloud Run uses ADC automatically — no explicit credentials needed here.
    """
    client = secretmanager.SecretManagerServiceClient()
    name   = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    resp   = client.access_secret_version(request={"name": name})
    return resp.payload.data.decode("utf-8")


def get_drive_service():
    """Build a Drive v3 client from credentials stored in Secret Manager.
    Result is module-level cached so the secret is only fetched once per container instance.
    """
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    logger.info("Fetching Drive credentials from Secret Manager...")
    creds_json = get_secret(SECRET_NAME)
    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    _drive_service = build("drive", "v3", credentials=creds)
    logger.info("Drive service client initialised.")
    return _drive_service


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Receives Google Drive push notifications for the watched file.
    Drive sends a 'sync' on watch registration; we ignore non-update events.
    """
    resource_state = request.headers.get("X-Goog-Resource-State", "")
    channel_id     = request.headers.get("X-Goog-Channel-ID", "")
    logger.info(f"Webhook: state={resource_state!r}  channel={channel_id!r}")

    # Drive always sends a 'sync' ping right after watch registration — safe to ignore
    if resource_state in ("sync", ""):
        return jsonify({"status": "ignored", "reason": "sync event"}), 200

    if resource_state != "update":
        return jsonify({"status": "ignored", "reason": f"state={resource_state}"}), 200

    try:
        drive = get_drive_service()

        # Verify metadata before downloading
        meta = drive.files().get(
            fileId=FILE_ID,
            fields="id,name,modifiedTime,size"
        ).execute()
        logger.info(f"File: {meta['name']}  modified={meta['modifiedTime']}  size={meta.get('size')} B")

        # Stream-download in 8 MB chunks → avoids OOM on large files
        req    = drive.files().get_media(fileId=FILE_ID)
        buf    = io.BytesIO()
        dl     = MediaIoBaseDownload(buf, req, chunksize=8 * 1024 * 1024)
        done   = False
        while not done:
            _, done = dl.next_chunk()
        buf.seek(0)

        # Upload to GCS — Cloud Run ADC handles auth automatically (no key needed)
        gcs    = storage.Client()
        bucket = gcs.bucket(RAW_BUCKET)
        blob   = bucket.blob(FILE_NAME)
        blob.upload_from_file(buf, content_type="application/zip")

        logger.info(f"Uploaded → gs://{RAW_BUCKET}/{FILE_NAME}")
        return jsonify({
            "status":   "success",
            "file":     meta["name"],
            "modified": meta["modifiedTime"],
        }), 200

    except Exception as exc:
        logger.exception("Webhook processing failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/renew", methods=["POST"])
def renew_watch():
    """
    Called by Cloud Scheduler every 6 days to refresh the Drive push-notification channel.
    Drive webhooks expire after at most 7 days (604 800 s for the 'files' resource type).
    A fresh UUID is used each time — Drive requires a unique channel id per watch call.
    """
    try:
        drive = get_drive_service()
        body  = {
            "id":      f"health-watch-{uuid.uuid4()}",
            "type":    "web_hook",
            "address": f"{WEBHOOK_URL}/webhook",
            "ttl":     518400,   # 6 days in seconds
        }
        resp = drive.files().watch(fileId=FILE_ID, body=body).execute()
        logger.info(f"Watch channel renewed: {resp}")
        return jsonify(resp), 200

    except Exception as exc:
        logger.exception("Watch renewal failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
