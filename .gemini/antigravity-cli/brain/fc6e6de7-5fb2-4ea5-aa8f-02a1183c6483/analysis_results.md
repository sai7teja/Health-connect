# Health Connect Data Analysis Results

This document presents the insights retrieved from your SQLite database after running the custom analytical script [test_analysis.py](file:///home/ztejksa/.gemini/antigravity-cli/brain/fc6e6de7-5fb2-4ea5-aa8f-02a1183c6483/scratch/test_analysis.py) on [health_analytics.duckdb](file:///home/ztejksa/Downloads/Health/health_analytics.duckdb).

---

## 📅 1. Weekly Step Patterns (Day of Week)
Analyzing your average daily steps by day of the week shows that you are highly active on weekdays (especially mid-week) and slightly more sedentary on weekends.

| Day of Week | Average Steps | Days Measured |
| :--- | :--- | :--- |
| **Wednesday** | **15,004** 🏆 | 40 |
| **Thursday** | 14,276 | 39 |
| **Monday** | 13,310 | 38 |
| **Tuesday** | 13,272 | 41 |
| **Friday** | 11,709 | 38 |
| **Sunday** | 10,395 | 36 |
| **Saturday** | **9,918** 💤 | 41 |

> [!NOTE]
> Saturday is your least active day on average, falling below the 10,000-step mark, whereas Wednesday represents your peak activity.

---

## 🫀 2. Resting Heart Rate Fitness Trend
Tracking resting heart rate (RHR) monthly shows a **significant improvement in cardiovascular fitness** from February to June 2026.

| Month | Avg Resting HR (BPM) | Min HR | Max HR | Measurements |
| :--- | :---: | :---: | :---: | :---: |
| **Feb 2026** | 61.5 | 58 | 69 | 22 |
| **Mar 2026** | 58.1 | 55 | 66 | 27 |
| **Apr 2026** | 56.5 | 53 | 60 | 27 |
| **May 2026** | 58.0 | 56 | 67 | 31 |
| **Jun 2026** | **56.5** 📉 | 54 | 59 | 24 |

> [!TIP]
> A reduction of **5.0 BPM** in average resting heart rate over 5 months indicates a substantial increase in cardiorespiratory efficiency and physical conditioning.

---

## 💤 3. Daily Steps vs. Sleep Duration
We analyzed the correlation between how active you were during the day and how long you slept that night.

| Activity Level | Step Range | Avg Sleep Duration | Sample Days |
| :--- | :--- | :---: | :---: |
| **Highly Active** | >15,000 steps | **6.06 hours** 🛌 | 126 |
| **Moderate** | 5,000–10,000 steps | 5.63 hours | 27 |
| **Active** | 10,000–15,000 steps | 5.51 hours | 37 |
| **Sedentary** | <5,000 steps | **4.91 hours** ⏳ | 19 |

> [!IMPORTANT]
> There is a clear positive trend: highly active days (>15k steps) correspond to your longest average sleep duration (6.06 hours), whereas sedentary days (<5k steps) correlate with your shortest sleep duration (4.91 hours).

---

## 🧠 4. Sleep Stage Proportions
Based on Android Health Connect specifications, the tracked sleep stages break down as follows:
* **Stage 1 (Awake)**: Intermittent awakenings.
* **Stage 4 (Light Sleep)**: Crucial for cognitive rest.
* **Stage 5 (Deep Sleep)**: Vital for physical recovery and tissue repair.
* **Stage 6 (REM Sleep)**: Vital for memory consolidation and dreaming.

| Sleep Stage | Occurrences | Avg Segment Duration | Percentage of Tracked Sleep |
| :--- | :---: | :---: | :---: |
| **Stage 4 (Light Sleep)** | 2,199 | 23.3 mins | **70.4%** |
| **Stage 5 (Deep Sleep)** | 602 | 16.7 mins | **13.9%** |
| **Stage 6 (REM Sleep)** | 1,248 | 7.8 mins | **13.3%** |
| **Stage 1 (Awake)** | 156 | 11.3 mins | **2.4%** |
