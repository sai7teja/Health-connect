import duckdb

DB_PATH = "/home/ztejksa/Downloads/Health/health_analytics.duckdb"
con = duckdb.connect(DB_PATH)

def print_table(title, headers, rows):
    print("="*80)
    print(title.upper())
    print("="*80)
    header_line = " | ".join(f"{h:<20}" for h in headers)
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print(" | ".join(f"{str(val):<20}" for val in row))
    print("="*80 + "\n")

# Mapping exercise types based on Android Health Connect constants
# 5: Biking (Stationary), 34: Treadmill Running, 58: Running (Outdoor/Generic in older spec or treadmill depending on SDK)
# Let's label them clearly in the output
EXERCISE_LABELS = {
    5: "Stationary Biking (5)",
    34: "Treadmill Running (34)",
    58: "Running (58)",
    53: "Rowing (53)"
}

# 1. Exercise Stats Summary
exercise_query = """
SELECT 
    e.exercise_type,
    COUNT(*) AS sessions_count,
    ROUND(AVG((e.end_time - e.start_time) / 60000.0), 1) AS avg_duration_min,
    ROUND(SUM((e.end_time - e.start_time) / 3600000.0), 1) AS total_hours,
    ROUND(AVG(h.avg_bpm))::INT AS avg_bpm,
    ROUND(AVG(h.max_bpm))::INT AS avg_max_bpm
FROM exercise_session_record_table e
LEFT JOIN (
    SELECT 
        parent_key,
        AVG(beats_per_minute) as avg_bpm,
        MAX(beats_per_minute) as max_bpm
    FROM heart_rate_record_series_table
    GROUP BY parent_key
) h ON h.parent_key = e.row_id
GROUP BY e.exercise_type
ORDER BY sessions_count DESC
"""
rows1 = con.execute(exercise_query).fetchall()
labeled_rows1 = []
for r in rows1:
    label = EXERCISE_LABELS.get(r[0], f"Unknown ({r[0]})")
    labeled_rows1.append((label, r[1], r[2], r[3], r[4], r[5]))

print_table(
    "Analysis 1: Workout Summary & Heart Rate Intensities", 
    ["Workout Type", "Sessions", "Avg Duration (Min)", "Total Hours", "Avg BPM", "Avg Max BPM"], 
    labeled_rows1
)

# 2. Heart Rate Zones Distribution
# Using a standard Max HR = 185 bpm
# Zones: Warmup (<111), Fat Burn (111-130), Aerobic (130-148), Anaerobic (148-166), Peak (>166)
zones_query = """
WITH hr_samples AS (
    SELECT 
        e.exercise_type,
        h.beats_per_minute AS bpm
    FROM exercise_session_record_table e
    JOIN heart_rate_record_series_table h ON h.epoch_millis BETWEEN e.start_time AND e.end_time
),
classified AS (
    SELECT 
        exercise_type,
        CASE 
            WHEN bpm < 111 THEN '1. Warm Up (<111)'
            WHEN bpm BETWEEN 111 AND 130 THEN '2. Fat Burn (111-130)'
            WHEN bpm BETWEEN 130 AND 148 THEN '3. Aerobic (130-148)'
            WHEN bpm BETWEEN 148 AND 166 THEN '4. Anaerobic (148-166)'
            ELSE '5. Peak (>166)'
        END AS hr_zone
    FROM hr_samples
)
SELECT 
    exercise_type,
    hr_zone,
    COUNT(*) AS samples,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(PARTITION BY exercise_type), 1) AS pct
FROM classified
GROUP BY exercise_type, hr_zone
ORDER BY exercise_type, hr_zone
"""
rows2 = con.execute(zones_query).fetchall()
labeled_rows2 = []
for r in rows2:
    label = EXERCISE_LABELS.get(r[0], f"Unknown ({r[0]})")
    labeled_rows2.append((label, r[1], r[2], f"{r[3]}%"))

print_table(
    "Analysis 2: Heart Rate Zone Distribution during Workouts",
    ["Workout Type", "Heart Rate Zone", "Samples", "Time spent %"],
    labeled_rows2
)

# 3. Workout Day vs. Rest Day Sleep Comparison
# Compare sleep duration and stages on days with workouts vs days without workouts
sleep_comparison_query = """
WITH daily_workouts AS (
    SELECT 
        epoch_ms(start_time)::DATE AS workout_date,
        COUNT(*) AS workout_count
    FROM exercise_session_record_table
    GROUP BY 1
),
sleep_with_workout_flag AS (
    SELECT 
        s.sleep_start::DATE AS sleep_date,
        s.duration_hours,
        CASE WHEN w.workout_count IS NOT NULL THEN 'Workout Day' ELSE 'Rest Day' END AS day_type
    FROM v_sleep s
    LEFT JOIN daily_workouts w ON s.sleep_start::DATE = w.workout_date
)
SELECT 
    day_type,
    ROUND(AVG(duration_hours), 2) AS avg_sleep_duration,
    COUNT(*) AS sleep_sessions_measured
FROM sleep_with_workout_flag
GROUP BY day_type
"""
rows3 = con.execute(sleep_comparison_query).fetchall()
print_table(
    "Analysis 3: Sleep Duration on Workout Days vs. Rest Days",
    ["Day Type", "Avg Sleep Duration (Hrs)", "Sleep Sessions Measured"],
    rows3
)

# 4. Deep & REM Sleep Stage Ratios on Workout vs. Rest Days
sleep_stages_comparison_query = """
WITH daily_workouts AS (
    SELECT 
        epoch_ms(start_time)::DATE AS workout_date,
        COUNT(*) AS workout_count
    FROM exercise_session_record_table
    GROUP BY 1
),
session_day_types AS (
    SELECT 
        s.row_id AS session_id,
        CASE WHEN w.workout_count IS NOT NULL THEN 'Workout Day' ELSE 'Rest Day' END AS day_type
    FROM sleep_session_record_table s
    LEFT JOIN daily_workouts w ON epoch_ms(s.start_time)::DATE = w.workout_date
),
stage_durations AS (
    SELECT 
        sdt.day_type,
        st.stage_type,
        SUM(st.stage_end_time - st.stage_start_time) / 60000.0 AS total_min
    FROM sleep_stages_table st
    JOIN session_day_types sdt ON st.parent_key = sdt.session_id
    GROUP BY 1, 2
)
SELECT 
    day_type,
    CASE 
        WHEN stage_type = 1 THEN 'Awake (1)'
        WHEN stage_type = 4 THEN 'Light Sleep (4)'
        WHEN stage_type = 5 THEN 'Deep Sleep (5)'
        WHEN stage_type = 6 THEN 'REM Sleep (6)'
        ELSE 'Other (' || stage_type || ')'
    END AS stage_label,
    ROUND(total_min) AS total_minutes,
    ROUND(total_min * 100.0 / SUM(total_min) OVER (PARTITION BY day_type), 1) AS percentage
FROM stage_durations
ORDER BY day_type, stage_type
"""
rows4 = con.execute(sleep_stages_comparison_query).fetchall()
print_table(
    "Analysis 4: Sleep Stages Breakdown on Workout Days vs. Rest Days",
    ["Day Type", "Sleep Stage", "Total Minutes", "Percentage %"],
    rows4
)

con.close()
