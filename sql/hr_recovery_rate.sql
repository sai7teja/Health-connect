-- HR RECOVERY RATE
-- Measures how fast heart rate drops after exercise ends
-- Good fitness: >20 BPM drop in first minute
-- Excellent fitness: >30 BPM drop in first minute

WITH workout_end_times AS (
  SELECT
    row_id,
    exercise_type,
    TIMESTAMP_ADD(TIMESTAMP_MILLIS(end_time), INTERVAL 19800 SECOND) AS workout_end_ist,
    end_time as end_millis
  FROM `lazybot7.health_analytics.exercise_session_record_table`
  WHERE end_time BETWEEN $__from AND $__to
),
hr_at_end AS (
  SELECT
    w.row_id,
    w.exercise_type,
    w.workout_end_ist,
    MAX(h.beats_per_minute) AS peak_hr
  FROM workout_end_times w
  JOIN `lazybot7.health_analytics.heart_rate_record_series_table` h
    ON h.epoch_millis BETWEEN (w.end_millis - 60000) AND w.end_millis
  GROUP BY 1, 2, 3
),
hr_after_1min AS (
  SELECT
    w.row_id,
    MIN(h.beats_per_minute) AS hr_1min_later
  FROM workout_end_times w
  JOIN `lazybot7.health_analytics.heart_rate_record_series_table` h
    ON h.epoch_millis BETWEEN w.end_millis AND (w.end_millis + 60000)
  GROUP BY 1
)
SELECT
  e.workout_end_ist AS time,
  e.peak_hr,
  a.hr_1min_later,
  (e.peak_hr - a.hr_1min_later) AS recovery_bpm,
  CASE 
    WHEN (e.peak_hr - a.hr_1min_later) >= 30 THEN 'Excellent'
    WHEN (e.peak_hr - a.hr_1min_later) >= 20 THEN 'Good'
    WHEN (e.peak_hr - a.hr_1min_later) >= 12 THEN 'Fair'
    ELSE 'Poor'
  END AS fitness_level
FROM hr_at_end e
JOIN hr_after_1min a ON e.row_id = a.row_id
ORDER BY time
