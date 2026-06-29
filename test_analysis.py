import duckdb

DB_PATH = "/home/ztejksa/Downloads/Health/health_analytics.duckdb"
con = duckdb.connect(DB_PATH)

def print_table(title, headers, rows):
    print("="*65)
    print(title.upper())
    print("="*65)
    header_line = " | ".join(f"{h:<25}" for h in headers)
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print(" | ".join(f"{str(val):<25}" for val in row))
    print("="*65 + "\n")

# Analysis 1: Weekly Step Patterns
weekly_steps_query = """
SELECT 
    dayname(date) AS day_of_week,
    ROUND(AVG(total_steps))::INT AS avg_steps,
    COUNT(*) AS days_measured
FROM v_steps_daily
GROUP BY day_of_week, dayofweek(date)
ORDER BY dayofweek(date)
"""
rows1 = con.execute(weekly_steps_query).fetchall()
print_table("Analysis 1: Weekly Step Patterns (Day of Week)", ["Day of Week", "Avg Steps", "Days Measured"], rows1)

# Analysis 2: Resting Heart Rate Trend
monthly_hr_query = """
SELECT 
    strftime(recorded_at, '%Y-%m') AS month,
    ROUND(AVG(resting_bpm), 1) AS avg_resting_hr,
    MIN(resting_bpm) AS min_resting_hr,
    MAX(resting_bpm) AS max_resting_hr,
    COUNT(*) AS measurements
FROM v_resting_hr
GROUP BY month
ORDER BY month
"""
rows2 = con.execute(monthly_hr_query).fetchall()
print_table("Analysis 2: Resting Heart Rate (Monthly Trend)", ["Month", "Avg Resting HR", "Min HR", "Max HR", "Measurements"], rows2)

# Analysis 3: Daily Steps vs Sleep Duration
correlation_query = """
SELECT 
    CASE 
        WHEN s.total_steps < 5000 THEN '1. Sedentary (<5k)'
        WHEN s.total_steps BETWEEN 5000 AND 10000 THEN '2. Moderate (5k-10k)'
        WHEN s.total_steps BETWEEN 10000 AND 15000 THEN '3. Active (10k-15k)'
        ELSE '4. Highly Active (>15k)'
    END AS activity_level,
    ROUND(AVG(total_steps))::INT AS avg_steps,
    ROUND(AVG(sl.duration_hours), 2) AS avg_sleep_hours,
    COUNT(*) AS sample_days
FROM v_steps_daily s
JOIN v_sleep sl ON s.date = CAST(sl.sleep_start AS DATE)
GROUP BY 1
ORDER BY 1
"""
rows3 = con.execute(correlation_query).fetchall()
print_table("Analysis 3: Daily Steps vs. Sleep Duration", ["Activity Level", "Avg Steps", "Avg Sleep Hours", "Sample Days"], rows3)

# Analysis 4: Sleep Stage Proportions
stages_query = """
SELECT 
    stage_type,
    COUNT(*) AS occurrences,
    ROUND(AVG(duration_min), 1) AS avg_duration_min,
    ROUND(SUM(duration_min) * 100.0 / (SELECT SUM(duration_min) FROM v_sleep_stages), 1) AS percentage
FROM v_sleep_stages
GROUP BY stage_type
ORDER BY stage_type
"""
rows4 = con.execute(stages_query).fetchall()
print_table("Analysis 4: Sleep Stage Proportions", ["Stage Type", "Occurrences", "Avg Duration (Min)", "Percentage (%)"], rows4)

con.close()
