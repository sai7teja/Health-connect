import sqlite3
import duckdb
import os
import logging
from google.cloud import bigquery

logger = logging.getLogger(__name__)

# Tables to migrate with their value columns
TABLES = {
    "heart_rate_record_series_table": ["parent_key", "beats_per_minute", "epoch_millis"],
    "heart_rate_record_table":        ["row_id", "start_time", "end_time", "start_zone_offset"],
    "steps_record_table":             ["row_id", "start_time", "end_time", "count"],
    "distance_record_table":          ["row_id", "start_time", "end_time", "distance"],
    "active_calories_burned_record_table": ["row_id", "start_time", "end_time", "active_calories_burned"],
    "exercise_session_record_table":  ["row_id", "start_time", "end_time", "exercise_type"],
    "sleep_session_record_table":     ["row_id", "start_time", "end_time"],
    "sleep_stages_table":             ["parent_key", "stage_type", "stage_start_time", "stage_end_time"],
    "weight_record_table":            ["row_id", "time", "weight"],
    "resting_heart_rate_record_table":["row_id", "time", "beats_per_minute"],
    "vo2_max_record_table":           ["row_id", "start_time", "vo2_max_milliliters_per_minute_per_kilogram"],
    "application_info_table":         ["row_id", "package_name", "app_name"],
    "device_info_table":              ["row_id", "manufacturer", "model", "type"],
    "steps_cadence_record_table":     ["parent_key", "rate", "epoch_millis"],
    "speed_record_table":             ["parent_key", "speed", "epoch_millis"],
    "total_calories_burned_record_table": ["row_id", "start_time", "end_time", "energy"],
    "exercise_route_table":           ["parent_key", "timestamp_millis", "longitude", "latitude", "altitude"],
    "elevation_gained_record_table":  ["row_id", "start_time", "end_time", "elevation"],
    "exercise_segments_table":        ["parent_key", "segment_start_time", "segment_end_time", "segment_type", "repetitions_count", "weight_grams", "set_index"],
}

# Helper to verify column existence in source SQLite
def actual_cols(src_conn, table, wanted):
    cur = src_conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    return [c for c in wanted if c in existing]

def run_migration(src_sqlite, dst_duckdb, dst_parquet_dir):
    os.makedirs(dst_parquet_dir, exist_ok=True)
    
    src_conn = sqlite3.connect(src_sqlite)
    duck = duckdb.connect(dst_duckdb)
    
    migrated = []
    for table, cols in TABLES.items():
        cols = actual_cols(src_conn, table, cols)
        if not cols:
            continue
        
        # Verify if table is populated in SQLite
        row = src_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if not row or row[0] == 0:
            logger.info(f"Skipping {table} (empty)")
            continue
            
        # Migrate into DuckDB using sqlite_scan extension
        duck.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM sqlite_scan('{src_sqlite}', '{table}')")
        
        # Project only specified columns
        duck.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT {', '.join(cols)} FROM {table}")
        
        # Export to Parquet
        parquet_path = os.path.join(dst_parquet_dir, f"{table}.parquet")
        duck.execute(f"COPY (SELECT * FROM {table}) TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        
        migrated.append(table)
        
    src_conn.close()
    duck.close()
    return migrated

def load_to_bigquery(parquet_dir, tables, dataset_id):
    client = bigquery.Client()
    
    # Ensure BigQuery Dataset exists
    dataset_ref = client.dataset(dataset_id)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = os.environ.get("GCP_REGION", "us-central1")
    try:
        client.create_dataset(dataset, exists_ok=True)
        logger.info(f"Dataset {dataset_id} created/verified")
    except Exception as e:
        logger.warning(f"Error checking/creating dataset: {str(e)}")

    processed_bucket_name = os.environ.get("PROCESSED_BUCKET_NAME")

    for table in tables:
        parquet_uri = f"gs://{processed_bucket_name}/parquet/{table}/{table}.parquet"
        table_ref = dataset_ref.table(table)
        
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )
        
        logger.info(f"Loading {parquet_uri} into BigQuery table {dataset_id}.{table}...")
        load_job = client.load_table_from_uri(
            parquet_uri, 
            table_ref, 
            job_config=job_config
        )
        load_job.result()  # Wait for the load job to complete
        logger.info(f"Completed loading {table}")
