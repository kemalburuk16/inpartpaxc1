# /var/www/instavido/adminpanel/analytics_data.py

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest
from google.oauth2 import service_account
import os

SERVICE_ACCOUNT_FILE = "/var/www/instavido/anly/webb1-466620-5d22f4311e8f.json"
PROPERTY_ID = "499908879"  # <-- BURAYA GA4 mülk ID'ni yaz (sadece rakam!)

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
client = BetaAnalyticsDataClient(credentials=credentials)

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
