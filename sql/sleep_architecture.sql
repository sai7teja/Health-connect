-- SLEEP ARCHITECTURE ANALYSIS
-- Compares actual sleep stage percentages vs ideal ranges
-- Ideal: REM 20-25%, Deep 15-20%, Light 50-60%

WITH sleep_totals AS (
  SELECT
    DATE(TIMESTAMP_ADD(TIMESTAMP_MILLIS(stage_start_time), INTERVAL 19800 SECOND)) AS sleep_date,
    
    -- Total time in each stage (minutes)
    SUM(CASE WHEN stage_type = 6 THEN (stage_end_time - stage_start_time) / 60000.0 ELSE 0 END) AS rem_mins,
    SUM(CASE WHEN stage_type = 5 THEN (stage_end_time - stage_start_time) / 60000.0 ELSE 0 END) AS deep_mins,
    SUM(CASE WHEN stage_type = 4 THEN (stage_end_time - stage_start_time) / 60000.0 ELSE 0 END) AS light_mins,
    SUM(CASE WHEN stage_type = 1 THEN (stage_end_time - stage_start_time) / 60000.0 ELSE 0 END) AS awake_mins,
    
    -- Total sleep time
    SUM((stage_end_time - stage_start_time) / 60000.0) AS total_mins
    
  FROM `lazybot7.health_analytics.sleep_stages_table`
  WHERE stage_start_time BETWEEN $__from AND $__to
  GROUP BY sleep_date
)
SELECT
  TIMESTAMP(sleep_date) AS time,
  
  -- Actual percentages
  ROUND(100.0 * rem_mins / NULLIF(total_mins, 0), 1) AS rem_pct,
  ROUND(100.0 * deep_mins / NULLIF(total_mins, 0), 1) AS deep_pct,
  ROUND(100.0 * light_mins / NULLIF(total_mins, 0), 1) AS light_pct,
  ROUND(100.0 * awake_mins / NULLIF(total_mins, 0), 1) AS awake_pct,
  
  -- Ideal ranges (for reference)
  22.5 AS rem_ideal,
  17.5 AS deep_ideal,
  55.0 AS light_ideal,
  
  -- Quality score (closer to ideal = better)
  ROUND(
    100 - (
      ABS(100.0 * rem_mins / NULLIF(total_mins, 0) - 22.5) +
      ABS(100.0 * deep_mins / NULLIF(total_mins, 0) - 17.5) +
      ABS(100.0 * light_mins / NULLIF(total_mins, 0) - 55.0)
    ) / 3,
    0
  ) AS architecture_score

FROM sleep_totals
WHERE total_mins > 60  -- Filter out naps
ORDER BY time
