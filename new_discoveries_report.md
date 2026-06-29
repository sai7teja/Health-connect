# Discovery of Additional Health Connect Metrics

We audited the SQLite database [health_connect_export.db](file:///home/ztejksa/Downloads/Health/health_connect_export.db) and discovered several highly populated tables that were not included in the original local migration. 

Here is the breakdown of these new tables, their schemas, and the type of analysis we can perform with them.

---

## 📈 1. Detailed Activity & Energy Metrics

### `total_calories_burned_record_table` (25,049 rows)
* **Columns**: `start_time`, `end_time`, `energy` (stored in Joules)
* **What it is**: Your total daily and hourly energy expenditure (Basal Metabolic Rate + Active Energy).
* **Formula**: $\text{kCal} = \text{Joules} / 4184.0$
* **Potential Analysis**: 
  * Hourly energy expenditure profile (circadian metabolic curve).
  * Day-by-day caloric burn trends over the 9.5-month span.

### `steps_cadence_record_table` (43,794 rows)
* **Columns**: `parent_key`, `rate` (steps per minute), `epoch_millis`
* **What it is**: A high-resolution time-series of your cadence while walking or running.
* **Potential Analysis**:
  * Identify running form efficiency (e.g., target cadence is typically 170–180 steps/min).
  * Identify walking pace intensity (slow walk vs. power walk vs. jog).

---

## 🏃‍♂️ 2. Performance & Workout Tracking

### `speed_record_table` (43,661 rows)
* **Columns**: `parent_key`, `speed` (meters per second), `epoch_millis`
* **What it is**: High-resolution velocity readings during active sessions.
* **Potential Analysis**:
  * Convert to pace curves (e.g., minutes per kilometer or mile).
  * Speed consistency/intervals analysis during running sessions.

### `elevation_gained_record_table` (199 rows)
* **Columns**: `start_time`, `end_time`, `elevation` (meters)
* **What it is**: Vertical climb volume during walks, runs, or stair climbing.
* **Potential Analysis**:
  * Track total vertical ascent per week or per month.
  * Correlate elevation gain with heart rate spikes to measure cardiovascular resistance.

### `exercise_segments_table` (199 rows)
* **Columns**: `segment_start_time`, `segment_end_time`, `segment_type`, `repetitions_count`, `weight_grams`, `set_index`
* **What it is**: Splits, workout intervals, or weightlifting sets/reps.
* **Potential Analysis**:
  * Track strength-training progress (reps and weights lifted over time, if recorded).
  * Segment workouts into active intervals vs. rest periods.

---

## 🗺️ 3. Geolocation & Routes

### `exercise_route_table` (1,723 rows)
* **Columns**: `parent_key`, `timestamp_millis`, `longitude`, `latitude`, `altitude`
* **What it is**: GPS tracks associated with your exercise sessions.
* **Potential Analysis**:
  * Extract GPX coordinates for visualization on maps (e.g., plotting your running or biking routes).
  * Correlate altitude/slope changes with speed and heart rate to measure effort efficiency.
