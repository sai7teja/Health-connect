-- RESTING HR ANOMALY DETECTION
-- Tracks baseline resting HR and flags abnormal elevations
-- Alert triggers: +5 BPM above 7-day baseline
-- Indicates: Overtraining, illness, stress, dehydration

SELECT
  TIMESTAMP_ADD(TIMESTAMP_MILLIS(time), INTERVAL 19800 SECOND) AS time,
  beats_per_minute AS resting_hr,
  
  -- 7-day rolling average baseline
  ROUND(AVG(beats_per_minute) OVER (
    ORDER BY time
    ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
  ), 1) AS baseline_7d,
  
  -- Deviation from baseline
  ROUND(
    beats_per_minute - AVG(beats_per_minute) OVER (
      ORDER BY time
      ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    ),
    1
  ) AS deviation_bpm,
  
  -- Alert flag
  CASE 
    WHEN beats_per_minute - AVG(beats_per_minute) OVER (
      ORDER BY time
      ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    ) >= 5 THEN 'ALERT'
    WHEN beats_per_minute - AVG(beats_per_minute) OVER (
      ORDER BY time
      ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
    ) >= 3 THEN 'WARNING'
    ELSE 'NORMAL'
  END AS status

FROM `lazybot7.health_analytics.resting_heart_rate_record_table`
WHERE time BETWEEN $__from AND $__to
ORDER BY time
