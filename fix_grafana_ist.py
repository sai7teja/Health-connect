#!/usr/bin/env python3
"""
Fix Grafana dashboard queries to use IST timezone (Asia/Kolkata)
Converts all timestamp operations to IST before grouping/display
"""
import json
import re
import sys

IST_OFFSET_SECONDS = 19800  # 5.5 hours = 19800 seconds

def add_ist_conversion(sql_query):
    """
    Convert BigQuery timestamp operations to use IST timezone
    """
    
    # Pattern 1: TIMESTAMP_TRUNC(TIMESTAMP_MILLIS(field), DAY)
    # Replace with: TIMESTAMP_TRUNC(TIMESTAMP_ADD(TIMESTAMP_MILLIS(field), INTERVAL 19800 SECOND), DAY)
    pattern1 = r'TIMESTAMP_TRUNC\(TIMESTAMP_MILLIS\((\w+)\),\s*DAY\)'
    replacement1 = f'TIMESTAMP_TRUNC(TIMESTAMP_ADD(TIMESTAMP_MILLIS(\\1), INTERVAL {IST_OFFSET_SECONDS} SECOND), DAY)'
    sql_query = re.sub(pattern1, replacement1, sql_query)
    
    # Pattern 2: TIMESTAMP_MILLIS(field) AS time (simple conversion without grouping)
    # Replace with: TIMESTAMP_ADD(TIMESTAMP_MILLIS(field), INTERVAL 19800 SECOND) AS time
    pattern2 = r'TIMESTAMP_MILLIS\((\w+)\)\s+AS\s+time'
    replacement2 = f'TIMESTAMP_ADD(TIMESTAMP_MILLIS(\\1), INTERVAL {IST_OFFSET_SECONDS} SECOND) AS time'
    sql_query = re.sub(pattern2, replacement2, sql_query)
    
    # Pattern 3: DATE(TIMESTAMP_TRUNC(TIMESTAMP_MILLIS(field), DAY))
    # This should already be caught by pattern1, but let's handle nested DATE()
    pattern3 = r'DATE\(TIMESTAMP_TRUNC\(TIMESTAMP_MILLIS\((\w+)\),\s*DAY\)\)'
    replacement3 = f'DATE(TIMESTAMP_TRUNC(TIMESTAMP_ADD(TIMESTAMP_MILLIS(\\1), INTERVAL {IST_OFFSET_SECONDS} SECOND), DAY))'
    sql_query = re.sub(pattern3, replacement3, sql_query)
    
    # Pattern 4: DATE(TIMESTAMP_MILLIS(field))
    # Replace with: DATE(TIMESTAMP_ADD(TIMESTAMP_MILLIS(field), INTERVAL 19800 SECOND))
    pattern4 = r'DATE\(TIMESTAMP_MILLIS\((\w+)\)\)'
    replacement4 = f'DATE(TIMESTAMP_ADD(TIMESTAMP_MILLIS(\\1), INTERVAL {IST_OFFSET_SECONDS} SECOND))'
    sql_query = re.sub(pattern4, replacement4, sql_query)
    
    # Pattern 5: EXTRACT(... FROM TIMESTAMP_MILLIS(field))
    # Replace with: EXTRACT(... FROM TIMESTAMP_ADD(TIMESTAMP_MILLIS(field), INTERVAL 19800 SECOND))
    pattern5 = r'EXTRACT\((HOUR|MINUTE|DAYOFWEEK)\s+FROM\s+TIMESTAMP_MILLIS\((\w+)\)\)'
    replacement5 = f'EXTRACT(\\1 FROM TIMESTAMP_ADD(TIMESTAMP_MILLIS(\\2), INTERVAL {IST_OFFSET_SECONDS} SECOND))'
    sql_query = re.sub(pattern5, replacement5, sql_query)
    
    # Pattern 6: FORMAT_DATE(..., DATE(TIMESTAMP_MILLIS(field)))
    # Already handled by pattern4
    
    return sql_query

def fix_dashboard_queries(dashboard_json):
    """
    Fix all queries in the dashboard to use IST
    """
    panels = dashboard_json.get('dashboard', {}).get('panels', [])
    
    fixed_count = 0
    for panel in panels:
        if 'targets' in panel:
            for target in panel['targets']:
                if 'rawSql' in target:
                    original_sql = target['rawSql']
                    fixed_sql = add_ist_conversion(original_sql)
                    
                    if original_sql != fixed_sql:
                        target['rawSql'] = fixed_sql
                        fixed_count += 1
                        print(f"✓ Fixed panel: {panel.get('title', 'Unknown')} (ID: {panel.get('id')})")
    
    return dashboard_json, fixed_count

def main():
    # Load dashboard JSON
    with open('/tmp/existing_dashboard.json', 'r') as f:
        dashboard_data = json.load(f)
    
    print("=" * 60)
    print("Fixing Grafana Dashboard Queries for IST Timezone")
    print("=" * 60)
    print()
    
    # Fix queries
    fixed_dashboard, count = fix_dashboard_queries(dashboard_data)
    
    print()
    print(f"✅ Fixed {count} queries with IST timezone conversion")
    print()
    
    # Save fixed dashboard
    with open('/tmp/fixed_dashboard.json', 'w') as f:
        json.dump(fixed_dashboard, f, indent=2)
    
    print("📁 Fixed dashboard saved to: /tmp/fixed_dashboard.json")
    print()
    print("Next step: Upload to Grafana Cloud")
    
    return fixed_dashboard

if __name__ == '__main__':
    main()
