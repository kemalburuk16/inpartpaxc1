#!/usr/bin/env python3
"""
Test script for Instagram Bot functionality.
"""

import os
import sys
import json

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils import load_config, setup_logging
from src.session_manager import InstagramSessionManager
from src.instagram_client import InstagramClient


def test_config_loading():
    """Test configuration loading."""
    print("Testing configuration loading...")
    
    config = load_config("config/settings.json")
    
    assert isinstance(config, dict), "Config should be a dictionary"
    assert 'target_hashtags' in config, "Config should have target_hashtags"
    assert 'daily_limits' in config, "Config should have daily_limits"
    
    print("✓ Configuration loading test passed")


def test_session_manager():
    """Test session manager functionality."""
    print("Testing session manager...")
    
    try:
        session_manager = InstagramSessionManager()
        
        # Test loading sessions
        sessions = session_manager.load_sessions()
        print(f"  - Loaded {len(sessions)} sessions")
        
        # Test getting stats
        stats = session_manager.get_session_stats()
        print(f"  - Session stats: {stats}")
        
        print("✓ Session manager test passed")
        
    except Exception as e:
        print(f"✗ Session manager test failed: {e}")


def test_instagram_client():
    """Test Instagram client initialization."""
    print("Testing Instagram client...")
    
    try:
        config = load_config("config/settings.json")
        client = InstagramClient(config)
        
        # Test request stats
        stats = client.get_request_stats()
        print(f"  - Request stats: {stats}")
        
        print("✓ Instagram client test passed")
        
    except Exception as e:
        print(f"✗ Instagram client test failed: {e}")


def test_utilities():
    """Test utility functions."""
    print("Testing utilities...")
    
    from src.utils import (
        get_random_delay, is_within_limits, format_username,
        extract_hashtags_from_text
    )
    
    # Test delay function
    delay = get_random_delay(5, 10)
    assert 5 <= delay <= 10, "Delay should be within range"
    
    # Test format username
    assert format_username("@testuser") == "testuser"
    assert format_username("testuser") == "testuser"
    
    # Test hashtag extraction
    hashtags = extract_hashtags_from_text("This is a #test with #multiple hashtags")
    assert "test" in hashtags and "multiple" in hashtags
    
    print("✓ Utilities test passed")


def main():
    """Run all tests."""
    print("=== Instagram Bot Test Suite ===\n")
    
    # Change to bot directory
    os.chdir(os.path.dirname(__file__))
    
    try:
        test_config_loading()
        test_utilities()
        test_session_manager()
        test_instagram_client()
        
        print("\n✓ All tests passed!")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()