# Grafana Dashboard IST Timezone Fix

## Summary
Fixed **26 BigQuery queries** in the "Android Health Connect Analytics" dashboard to properly handle IST (Indian Standard Time, Asia/Kolkata) timezone.

## Problem
- **Before**: All timestamps were converted to UTC, causing data to be grouped by UTC days
- **Impact**: Sleep sessions and activities after 6:30 PM IST were counted in the wrong day
- **Example**: A sleep session at 11:30 PM IST on Sept 12 would be grouped as Sept 12 UTC (actually 6:00 PM UTC Sept 12), but should be grouped as Sept 12 IST

## Solution
Added IST timezone conversion (+5.5 hours = 19800 seconds) to all timestamp operations BEFORE grouping/aggregation.

### Query Transformation Example

**BEFORE (Incorrect - UTC grouping):**
```sql
SELECT
  TIMESTAMP_TRUNC(TIMESTAMP_MILLIS(start_time), DAY) AS time,
  SUM(count) AS steps
FROM `YOUR_PROJECT.health_analytics.steps_record_table`
GROUP BY 1
```

**AFTER (Correct - IST grouping):**
```sql
SELECT
  TIMESTAMP_TRUNC(
    TIMESTAMP_ADD(TIMESTAMP_MILLIS(start_time), INTERVAL 19800 SECOND),
    DAY
  ) AS time,
  SUM(count) AS steps
FROM `YOUR_PROJECT.health_analytics.steps_record_table`
GROUP BY 1
```

## Patterns Fixed

1. **Daily aggregations**: `TIMESTAMP_TRUNC(..., DAY)` → Added IST offset before truncation
2. **Timestamp display**: `TIMESTAMP_MILLIS(field) AS time` → Added IST offset
3. **Date extraction**: `DATE(TIMESTAMP_MILLIS(field))` → Added IST offset
4. **Hour/Minute extraction**: `EXTRACT(HOUR FROM TIMESTAMP_MILLIS(field))` → Added IST offset
5. **Nested operations**: All combinations of the above

## Panels Fixed (26 total)

### Activity Panels
- Daily Steps
- Daily Calories Burned
- Distance Traveled
- Average Steps by Day of Week
- Daily Step Goal Achievement
- Steps vs. Distance Correlation

### Sleep Panels
- Total Sleep Duration
- Sleep Efficiency %
- Sleep Start Time Consistency
- Workout vs Rest Day Sleep
- Deep & REM Sleep: Workout vs Rest
- Sleep Duration → Next Day RHR
- Sleep Score
- Avg Sleep Duration
- Sleep Regularity
- Awake Time
- Sleep Window (Start vs Wake)
- Sleep Stages by Night

### Health Metrics Panels
- Resting Heart Rate Trend
- Body Weight Trend
- RHR Anomaly Detection
- Weight vs Rolling 7d Calories

## Dashboard Details
- **Dashboard UID**: `health-analytics-main`
- **Dashboard Name**: Android Health Connect Analytics
- **Grafana URL**: https://YOUR_ORG.grafana.net/d/health-analytics-main
- **Version**: 8 (updated on 2026-08-15)
- **Status**: ✅ Successfully deployed

## Verification

To verify the fix is working:
1. Open the dashboard: https://YOUR_ORG.grafana.net/d/health-analytics-main
2. Check any daily aggregation panel (e.g., "Daily Steps")
3. Compare data points - they should now align with IST dates
4. A sleep session starting at 11:30 PM IST should now count toward that IST day, not the next day

## Notes

- Grafana dashboard timezone is set to `"browser"`, so it will display in your browser's timezone
- The fix ensures data is **grouped by IST** before display
- IST offset is hardcoded as 19800 seconds (IST doesn't have DST, so this is constant)
- If you need to support multiple timezones, consider adding `zone_offset` column support

## Script Location
- Fix script: `fix_grafana_ist.py`
- Original dashboard backup: `/tmp/existing_dashboard.json`
- Fixed dashboard: `/tmp/fixed_dashboard.json`
