#!/usr/bin/env python3
"""
Simple test version of Instagram Bot for demonstration.
"""

import json
import os
import sys

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils import load_config, setup_logging


def main():
    """Simple main function for testing."""
    print("Instagram Bot - Demo Version")
    print("============================")
    
    # Load configuration
    try:
        config = load_config("config/settings.json")
        print(f"✓ Configuration loaded successfully")
        print(f"  - Target hashtags: {config.get('target_hashtags', [])}")
        print(f"  - Daily like limit: {config.get('daily_limits', {}).get('likes', 0)}")
        print(f"  - Hourly like limit: {config.get('hourly_limits', {}).get('likes', 0)}")
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return
    
    # Setup logging
    try:
        logger = setup_logging()
        print("✓ Logging setup completed")
    except Exception as e:
        print(f"✗ Failed to setup logging: {e}")
    
    # Try to load session data
    try:
        from src.session_manager import InstagramSessionManager
        session_manager = InstagramSessionManager()
        stats = session_manager.get_session_stats()
        print(f"✓ Session manager initialized")
        print(f"  - Total sessions: {stats.get('total', 0)}")
        print(f"  - Active sessions: {stats.get('active', 0)}")
        print(f"  - Invalid sessions: {stats.get('invalid', 0)}")
    except Exception as e:
        print(f"✗ Failed to initialize session manager: {e}")
    
    # Show available actions
    print("\nAvailable Actions:")
    print("- Like posts from hashtags")
    print("- Follow users")
    print("- Unfollow old follows")
    print("- Get statistics")
    print("- Run maintenance")
    
    print("\nBot is ready! Use main.py with proper arguments to run automation.")


if __name__ == "__main__":
    main()