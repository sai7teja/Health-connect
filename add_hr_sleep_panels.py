#!/usr/bin/env python3
"""
Add HR/Sleep/Recovery panels to Grafana dashboard
"""
import json
import sys
from pathlib import Path

def load_sql_query(sql_file):
    """Load SQL query from file"""
    return Path(sql_file).read_text()

def create_hr_recovery_panel():
    """Create HR Recovery Rate panel"""
    sql = load_sql_query('sql/hr_recovery_rate.sql')
    
    return {
        "title": "💓 HR Recovery Rate (1-min drop)",
        "type": "timeseries",
        "description": "Heart rate drop in first minute after exercise. Good: >20 BPM, Excellent: >30 BPM. Higher = better fitness.",
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 100},
        "targets": [{
            "rawSql": sql,
            "refId": "A",
            "format": 0,
            "datasource": {"type": "grafana-bigquery-datasource", "uid": "cfqmoixji27eoc"}
        }],
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "custom": {
                    "axisLabel": "BPM Drop",
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "pointSize": 8,
                    "showPoints": "always",
                    "fillOpacity": 10
                },
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "red", "value": 0},
                        {"color": "yellow", "value": 12},
                        {"color": "green", "value": 20},
                        {"color": "blue", "value": 30}
                    ]
                },
                "unit": "short"
            }
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "single"}
        }
    }

def create_resting_hr_anomaly_panel():
    """Create Resting HR Anomaly Detection panel"""
    sql = load_sql_query('sql/resting_hr_anomaly.sql')
    
    return {
        "title": "🚨 Resting HR Anomaly Detection",
        "type": "timeseries",
        "description": "Tracks resting HR vs 7-day baseline. Alert: +5 BPM (overtraining/illness). Warning: +3 BPM.",
        "gridPos": {"h": 8, "w": 8, "x": 8, "y": 100},
        "targets": [{
            "rawSql": sql,
            "refId": "A",
            "format": 0,
            "datasource": {"type": "grafana-bigquery-datasource", "uid": "cfqmoixji27eoc"}
        }],
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisLabel": "BPM",
                    "drawStyle": "line",
                    "lineWidth": 1,
                    "fillOpacity": 0
                },
                "unit": "short"
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "resting_hr"},
                    "properties": [
                        {"id": "displayName", "value": "Resting HR"},
                        {"id": "color", "value": {"fixedColor": "blue", "mode": "fixed"}},
                        {"id": "custom.lineWidth", "value": 2}
                    ]
                },
                {
                    "matcher": {"id": "byName", "options": "baseline_7d"},
                    "properties": [
                        {"id": "displayName", "value": "7-Day Baseline"},
                        {"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}},
                        {"id": "custom.lineStyle", "value": {"fill": "dash"}}
                    ]
                }
            ]
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"}
        }
    }

def create_sleep_architecture_panel():
    """Create Sleep Architecture panel"""
    sql = load_sql_query('sql/sleep_architecture.sql')
    
    return {
        "title": "😴 Sleep Architecture (Stage Distribution)",
        "type": "timeseries",
        "description": "Sleep stage percentages. Ideal: REM 20-25%, Deep 15-20%, Light 50-60%",
        "gridPos": {"h": 8, "w": 8, "x": 16, "y": 100},
        "targets": [{
            "rawSql": sql,
            "refId": "A",
            "format": 0,
            "datasource": {"type": "grafana-bigquery-datasource", "uid": "cfqmoixji27eoc"}
        }],
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisLabel": "Percentage",
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": 30,
                    "stacking": {"mode": "percent"}
                },
                "unit": "percent"
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "rem_pct"},
                    "properties": [
                        {"id": "displayName", "value": "REM"},
                        {"id": "color", "value": {"fixedColor": "purple", "mode": "fixed"}}
                    ]
                },
                {
                    "matcher": {"id": "byName", "options": "deep_pct"},
                    "properties": [
                        {"id": "displayName", "value": "Deep"},
                        {"id": "color", "value": {"fixedColor": "dark-blue", "mode": "fixed"}}
                    ]
                },
                {
                    "matcher": {"id": "byName", "options": "light_pct"},
                    "properties": [
                        {"id": "displayName", "value": "Light"},
                        {"id": "color", "value": {"fixedColor": "light-blue", "mode": "fixed"}}
                    ]
                }
            ]
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"}
        }
    }

def main():
    print("Loading existing dashboard...")
    with open('/tmp/fixed_dashboard.json', 'r') as f:
        dashboard = json.load(f)
    
    print("\nAdding new panels:")
    
    # Add new row for HR/Sleep/Recovery
    new_row = {
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 100},
        "id": 50,
        "title": "❤️ HR Analysis & Recovery",
        "type": "row"
    }
    dashboard['dashboard']['panels'].append(new_row)
    print("  ✓ Added row: HR Analysis & Recovery")
    
    # Add panels
    panels = [
        ("HR Recovery Rate", create_hr_recovery_panel()),
        ("Resting HR Anomaly", create_resting_hr_anomaly_panel()),
        ("Sleep Architecture", create_sleep_architecture_panel())
    ]
    
    for name, panel in panels:
        panel['id'] = 50 + len(dashboard['dashboard']['panels'])
        dashboard['dashboard']['panels'].append(panel)
        print(f"  ✓ Added panel: {name}")
    
    # Save updated dashboard
    with open('/tmp/updated_dashboard.json', 'w') as f:
        json.dump(dashboard, f, indent=2)
    
    print(f"\n✅ Dashboard updated with {len(panels)} new panels")
    print("📁 Saved to: /tmp/updated_dashboard.json")
    print("\nNext: Upload to Grafana Cloud")

if __name__ == '__main__':
    main()
