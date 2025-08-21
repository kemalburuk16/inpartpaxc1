# /var/www/instavido/adminpanel/analytics_data.py

import os

# Try to import Google Analytics modules, fallback if not available
try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import RunReportRequest
    from google.oauth2 import service_account
    GOOGLE_ANALYTICS_AVAILABLE = True
except ImportError:
    GOOGLE_ANALYTICS_AVAILABLE = False
    BetaAnalyticsDataClient = None
    RunReportRequest = None
    service_account = None

SERVICE_ACCOUNT_FILE = "/var/www/instavido/anly/webb1-466620-5d22f4311e8f.json"
PROPERTY_ID = "499908879"  # <-- BURAYA GA4 mülk ID'ni yaz (sadece rakam!)

# Initialize client only if Google Analytics is available and credentials exist
client = None
if GOOGLE_ANALYTICS_AVAILABLE and os.path.exists(SERVICE_ACCOUNT_FILE):
    try:
        credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
        client = BetaAnalyticsDataClient(credentials=credentials)
    except Exception as e:
        print(f"Warning: Could not initialize Google Analytics client: {e}")
        client = None

def get_summary_7days():
    """Son 7 günün temel analytics verileri"""
    if not client or not GOOGLE_ANALYTICS_AVAILABLE:
        # Return mock data when Google Analytics is not available
        return [
            {
                "date": "2025-01-08",
                "active_users": 150,
                "new_users": 25,
                "pageviews": 500
            },
            {
                "date": "2025-01-09", 
                "active_users": 175,
                "new_users": 30,
                "pageviews": 620
            }
        ]
    
    try:
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
    except Exception as e:
        print(f"Error getting analytics data: {e}")
        return []

def get_realtime_users():
    """Anlık aktif kullanıcı sayısı"""
    if not client or not GOOGLE_ANALYTICS_AVAILABLE:
        # Return mock data when Google Analytics is not available
        return 42
    
    try:
        request = RunReportRequest(
            property=f"properties/{PROPERTY_ID}",
            metrics=[{"name": "activeUsers"}],
            date_ranges=[{"start_date": "today", "end_date": "today"}]
        )
        response = client.run_report(request)
        if response.rows:
            return int(response.rows[0].metric_values[0].value)
        return 0
    except Exception as e:
        print(f"Error getting realtime users: {e}")
        return 0
