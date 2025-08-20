# /var/www/instavido/adminpanel/analytics_data.py

import os
import json
# Minimal mock implementations
def get_summary_7days():
    """Mock analytics data for 7 days"""
    return {
        "total_pageviews": 12500,
        "unique_visitors": 8300,
        "bounce_rate": 0.35,
        "avg_session_duration": "2:45"
    }

def get_realtime_users():
    """Mock realtime users data"""
    return {
        "active_users": 156,
        "current_hour": 89,
        "peak_hour": 234
    }

def get_summary_7days():
    """Son 7 günün temel analytics verileri"""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[{"name": "date"}],
        metrics=[
            {"name": "activeUsers"},
            {"name": "newUsers"},
            {"name": "screenPageViews"}
        ],
        date_ranges=[{"start_date": "7daysAgo", "end_date": "today"}]
    )
    response = client.run_report(request)
    rows = []
    for row in response.rows:
        rows.append({
            "date": row.dimension_values[0].value,
            "active_users": int(row.metric_values[0].value),
            "new_users": int(row.metric_values[1].value),
            "pageviews": int(row.metric_values[2].value)
        })
    return rows

def get_realtime_users():
    """Anlık aktif kullanıcı sayısı"""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        metrics=[{"name": "activeUsers"}],
        date_ranges=[{"start_date": "today", "end_date": "today"}]
    )
    response = client.run_report(request)
    if response.rows:
        return int(response.rows[0].metric_values[0].value)
    return 0
