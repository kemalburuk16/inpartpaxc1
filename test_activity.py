#!/usr/bin/env python3
"""
Test script to check activity views without authentication
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from flask import Flask
from adminpanel.activity_views import activity_bp

app = Flask(__name__)
app.secret_key = 'test-secret-key'

# Register blueprint
app.register_blueprint(activity_bp)

if __name__ == '__main__':
    print("Activity routes:")
    for rule in app.url_map.iter_rules():
        if 'activity' in rule.rule:
            print(f"  {rule.rule} -> {rule.endpoint}")
    
    print("\nStarting test server on port 5001...")
    app.run(debug=True, port=5001)