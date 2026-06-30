import os
import json
import base64
import logging
import zipfile
import shutil
from flask import Flask, request, jsonify
from google.cloud import storage
import migrate_health

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/", methods=["POST"])
def index():
    envelope = request.get_json()
    if not envelope:
        logger.error("No JSON payload received")
        return "Bad Request: no JSON payload", 400

    if not isinstance(envelope, dict) or "message" not in envelope:
        logger.error("Invalid Pub/Sub message format")
        return "Bad Request: invalid Pub/Sub message format", 400

    pubsub_message = envelope["message"]
    if "data" not in pubsub_message:
        logger.error("Pub/Sub message missing 'data' field")
        return "Bad Request: missing data field", 400

    try:
        # Decode GCS notification payload
        gcs_event_data = base64.b64decode(pubsub_message["data"]).decode("utf-8")
        event = json.loads(gcs_event_data)
        
        bucket_name = event["bucket"]
        object_name = event["name"]
        
        logger.info(f"Processing upload event: bucket={bucket_name}, file={object_name}")

        if not object_name.endswith(".zip"):
            logger.info("Ignored non-zip file upload")
            return jsonify({"status": "ignored", "reason": "not a zip file"}), 200

        # Define temporary local working directory
        tmp_dir = "/tmp/health_processing"
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        zip_local_path = os.path.join(tmp_dir, "downloaded.zip")
        db_local_path = os.path.join(tmp_dir, "health_connect_export.db")
        parquet_local_dir = os.path.join(tmp_dir, "health_parquet")

        # 1. Download zip from GCS
        gcs_client = storage.Client()
        raw_bucket = gcs_client.bucket(bucket_name)
        blob = raw_bucket.blob(object_name)
        blob.download_to_filename(zip_local_path)
        logger.info("Successfully downloaded ZIP file from GCS")

        # 2. Extract SQLite database
        with zipfile.ZipFile(zip_local_path, 'r') as zip_ref:
            # Locate health_connect_export.db inside zip
            db_name = None
            for name in zip_ref.namelist():
                if name.endswith("health_connect_export.db"):
                    db_name = name
                    break
            
            if not db_name:
                raise ValueError("health_connect_export.db not found in ZIP file")
                
            with open(db_local_path, "wb") as f_out:
                f_out.write(zip_ref.read(db_name))
        logger.info("Successfully extracted database")

        # 3. Execute Migration to Parquet and DuckDB
        duckdb_path = os.path.join(tmp_dir, "health_analytics.duckdb")
        
        # We invoke migrate_health as a module function passing custom local paths
        migrated_tables = migrate_health.run_migration(
            src_sqlite=db_local_path,
            dst_duckdb=duckdb_path,
            dst_parquet_dir=parquet_local_dir
        )
        logger.info(f"Successfully ran migration for {len(migrated_tables)} tables")

        # 4. Upload Parquet files to Processed GCS Bucket
        processed_bucket_name = os.environ.get("PROCESSED_BUCKET_NAME")
        processed_bucket = gcs_client.bucket(processed_bucket_name)
        
        for table in migrated_tables:
            parquet_file = f"{table}.parquet"
            local_parquet_path = os.path.join(parquet_local_dir, parquet_file)
            if os.path.exists(local_parquet_path):
                dest_blob = processed_bucket.blob(f"parquet/{table}/{parquet_file}")
                dest_blob.upload_from_filename(local_parquet_path)
                logger.info(f"Uploaded Parquet to GCS: {parquet_file}")

        # 5. Load Parquet into BigQuery
        dataset_id = os.environ.get("BQ_DATASET_ID", "health_analytics")
        migrate_health.load_to_bigquery(
            parquet_dir=parquet_local_dir,
            tables=migrated_tables,
            dataset_id=dataset_id
        )
        logger.info("Successfully loaded Parquet tables to BigQuery")

        # Cleanup
        shutil.rmtree(tmp_dir)
        logger.info("Temporary workspace cleaned up")
        return jsonify({"status": "success", "processed_tables": migrated_tables}), 200

    except Exception as e:
        logger.error(f"Error processing Parquet migration: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/status", methods=["GET"])
def status():
    """Returns pipeline health by checking the freshness of BigQuery data.
    If the most recent record is older than 72 hours, reports 'stale'.
    """
    try:
        from google.cloud import bigquery
        from datetime import datetime, timezone

        client = bigquery.Client()
        dataset_id = os.environ.get("BQ_DATASET_ID", "health_analytics")

        query = f"""
            SELECT TIMESTAMP_MILLIS(MAX(start_time)) AS latest_record
            FROM `{client.project}.{dataset_id}.steps_record_table`
        """
        result = list(client.query(query).result())

        if result and result[0].latest_record:
            latest = result[0].latest_record
            age_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
            freshness = "fresh" if age_hours < 72 else "stale"
            return jsonify({
                "status": freshness,
                "latest_record": latest.isoformat(),
                "age_hours": round(age_hours, 1),
                "threshold_hours": 72
            }), 200
        else:
            return jsonify({"status": "empty", "message": "No data in BigQuery yet"}), 200

    except Exception as e:
        logger.error(f"Status check failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
