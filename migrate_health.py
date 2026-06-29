"""
Migrate health_connect_export.db → DuckDB + Parquet
Exports the high-value tables with human-readable timestamps.
"""
import sqlite3
import duckdb
import os

SRC = "/home/ztejksa/Downloads/Health/health_connect_export.db"
DST_DB = "/home/ztejksa/Downloads/Health/health_analytics.duckdb"
DST_PARQUET = "/home/ztejksa/Downloads/Health/health_parquet"

os.makedirs(DST_PARQUET, exist_ok=True)

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

src = sqlite3.connect(SRC)
duck = duckdb.connect(DST_DB)

# Get actual columns per table to avoid missing-column errors
def actual_cols(table, wanted):
    cur = src.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    return [c for c in wanted if c in existing]

migrated = []
for table, cols in TABLES.items():
    cols = actual_cols(table, cols)
    if not cols:
        continue
    df = src.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    if not df:
        print(f"  skip {table} (empty)")
        continue

    # Register in DuckDB and export Parquet
    duck.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM sqlite_scan('{SRC}', '{table}')")
    
    # Project only wanted columns
    duck.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT {', '.join(cols)} FROM {table}
    """)
    
    parquet_path = f"{DST_PARQUET}/{table}.parquet"
    duck.execute(f"COPY (SELECT * FROM {table}) TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    count = duck.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    size = os.path.getsize(parquet_path) // 1024
    print(f"  ✓ {table}: {count:,} rows → {size} KB parquet")
    migrated.append(table)

src.close()

# Create analytical views with human-readable timestamps
duck.execute("""
CREATE OR REPLACE VIEW v_heart_rate AS
SELECT
    epoch_ms(epoch_millis) AS ts,
    beats_per_minute AS bpm,
    parent_key AS session_id
FROM heart_rate_record_series_table
ORDER BY epoch_millis
""")

duck.execute("""
CREATE OR REPLACE VIEW v_steps_daily AS
SELECT
    DATE(epoch_ms(start_time)) AS date,
    SUM(count) AS total_steps
FROM steps_record_table
GROUP BY 1 ORDER BY 1
""")

duck.execute("""
CREATE OR REPLACE VIEW v_sleep AS
SELECT
    epoch_ms(start_time) AS sleep_start,
    epoch_ms(end_time)   AS sleep_end,
    (end_time - start_time) / 3600000.0 AS duration_hours
FROM sleep_session_record_table
ORDER BY start_time
""")

duck.execute("""
CREATE OR REPLACE VIEW v_weight AS
SELECT
    epoch_ms(time) AS recorded_at,
    weight / 1000.0 AS weight_kg
FROM weight_record_table
ORDER BY time
""")

duck.execute("""
CREATE OR REPLACE VIEW v_resting_hr AS
SELECT
    epoch_ms(time) AS recorded_at,
    beats_per_minute AS resting_bpm
FROM resting_heart_rate_record_table
ORDER BY time
""")

duck.execute("""
CREATE OR REPLACE VIEW v_sleep_stages AS
SELECT
    parent_key AS session_id,
    stage_type,
    epoch_ms(stage_start_time) AS stage_start,
    epoch_ms(stage_end_time)   AS stage_end,
    (stage_end_time - stage_start_time) / 60000.0 AS duration_min
FROM sleep_stages_table
ORDER BY stage_start_time
""")

duck.execute("""
CREATE OR REPLACE VIEW v_steps_cadence AS
SELECT
    parent_key AS session_id,
    epoch_ms(epoch_millis) AS ts,
    rate AS steps_per_minute
FROM steps_cadence_record_table
ORDER BY session_id, epoch_millis
""")

duck.execute("""
CREATE OR REPLACE VIEW v_speed AS
SELECT
    parent_key AS session_id,
    epoch_ms(epoch_millis) AS ts,
    speed AS speed_mps,
    speed * 3.6 AS speed_kmh
FROM speed_record_table
ORDER BY session_id, epoch_millis
""")

duck.execute("""
CREATE OR REPLACE VIEW v_calories_daily AS
SELECT
    DATE(epoch_ms(start_time)) AS date,
    SUM(energy) / 4184.0 AS total_calories_kcal
FROM total_calories_burned_record_table
GROUP BY 1 ORDER BY 1
""")

duck.execute("""
CREATE OR REPLACE VIEW v_exercise_routes AS
SELECT
    parent_key AS session_id,
    epoch_ms(timestamp_millis) AS ts,
    latitude,
    longitude,
    altitude
FROM exercise_route_table
ORDER BY session_id, timestamp_millis
""")

duck.close()

print(f"\nDone. DuckDB: {DST_DB}")
print(f"Parquet dir: {DST_PARQUET}/")
print(f"\nQuick-start:\n  duckdb {DST_DB}\n  SELECT * FROM v_steps_daily LIMIT 10;")
