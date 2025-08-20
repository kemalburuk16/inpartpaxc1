#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instagram Automation System - Main Application Entry Point

This system provides automatic liking and following functionality for Instagram
while respecting rate limits and using the existing session infrastructure.
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime
from typing import Dict, Any

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils import (
    load_config, setup_logging, get_summary_stats, clean_old_logs,
    validate_config, create_default_config, save_config
)
from src.instagram_client import InstagramClient
from src.like_manager import LikeManager
from src.follow_manager import FollowManager
from src.session_manager import SessionManager

logger = logging.getLogger(__name__)


def create_default_config_file():
    """Create a default configuration file if it doesn't exist"""
    config_path = "config/settings.json"
    
    if os.path.exists(config_path):
        print(f"Configuration file already exists: {config_path}")
        return
    
    print(f"Creating default configuration file: {config_path}")
    
    default_config = create_default_config()
    
    if save_config(default_config, config_path):
        print(f"✅ Default configuration created: {config_path}")
        print("Please review and customize the settings before running the automation.")
    else:
        print(f"❌ Failed to create configuration file")


def check_session_health(session_manager: SessionManager) -> bool:
    """
    Check if sessions are healthy enough to proceed
    Returns True if sessions are OK
    """
    print("🔍 Checking session health...")
    
    health_results = session_manager.perform_health_check()
    
    if 'error' in health_results:
        print(f"❌ Session health check failed: {health_results['error']}")
        return False
    
    status = session_manager.get_session_status()
    
    print(f"📊 Session Status:")
    print(f"   Total: {status['total']}")
    print(f"   Active: {status['active']}")
    print(f"   Pending: {status['pending']}")
    print(f"   Invalid: {status['invalid']}")
    print(f"   Blocked: {status['blocked']}")
    
    # Check if we have enough active sessions
    if status['active'] < 1:
        print("❌ No active sessions available. Cannot proceed with automation.")
        print("Please check your session configuration and add valid Instagram sessions.")
        return False
    
    if status['active'] < 2:
        print("⚠️  Warning: Only 1 active session. Automation will be limited.")
    
    # Get recommendations
    recommendations = session_manager.get_session_recommendations()
    
    if recommendations.get('critical'):
        print("🚨 Critical Issues:")
        for issue in recommendations['critical']:
            print(f"   - {issue}")
    
    if recommendations.get('warnings'):
        print("⚠️  Warnings:")
        for warning in recommendations['warnings']:
            print(f"   - {warning}")
    
    return status['active'] > 0


def run_like_automation(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the hashtag-based liking automation
    Returns session results
    """
    print("🎯 Starting hashtag-based liking automation...")
    
    try:
        # Initialize components
        client = InstagramClient(config)
        like_manager = LikeManager(client, config)
        
        # Show current rate limit status
        rate_status = client.get_rate_limit_status()
        print(f"📈 Rate Limit Status:")
        print(f"   Likes used: {rate_status['hourly_likes']}/{rate_status['likes_limit']}")
        print(f"   Hour remaining: {rate_status['hour_remaining']/60:.1f} minutes")
        
        # Check if we can proceed
        if rate_status['hourly_likes'] >= rate_status['likes_limit']:
            print("⏰ Hourly like limit already reached. Skipping like automation.")
            return {'skipped': True, 'reason': 'rate_limit_reached'}
        
        # Run the automation
        results = like_manager.run_hashtag_liking_session()
        
        # Show results
        print(f"✅ Liking session completed:")
        print(f"   Total likes: {results['total_likes']}")
        print(f"   Hashtags processed: {len(results['hashtags_processed'])}")
        print(f"   Errors: {results['total_errors']}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error in like automation: {e}")
        print(f"❌ Like automation failed: {e}")
        return {'error': str(e)}


def run_follow_automation(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the user-based following automation
    Returns session results
    """
    print("👥 Starting user-based following automation...")
    
    try:
        # Initialize components
        client = InstagramClient(config)
        follow_manager = FollowManager(client, config)
        
        # Show current rate limit status
        rate_status = client.get_rate_limit_status()
        print(f"📈 Rate Limit Status:")
        print(f"   Follows used: {rate_status['hourly_follows']}/{rate_status['follows_limit']}")
        print(f"   Hour remaining: {rate_status['hour_remaining']/60:.1f} minutes")
        
        # Check if we can proceed
        if rate_status['hourly_follows'] >= rate_status['follows_limit']:
            print("⏰ Hourly follow limit already reached. Skipping follow automation.")
            return {'skipped': True, 'reason': 'rate_limit_reached'}
        
        # Run the automation
        results = follow_manager.run_following_session()
        
        # Show results
        print(f"✅ Following session completed:")
        print(f"   Total follows: {results['total_follows']}")
        print(f"   Strategies used: {len(results['strategies_used'])}")
        print(f"   Errors: {results['total_errors']}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error in follow automation: {e}")
        print(f"❌ Follow automation failed: {e}")
        return {'error': str(e)}


def show_statistics():
    """Show automation statistics"""
    print("📊 Automation Statistics:")
    
    try:
        stats = get_summary_stats({})  # Pass empty config since it's not used
        
        print(f"   Likes - Total: {stats['likes']['total']}, Today: {stats['likes']['today']}, Success: {stats['likes']['successful']}")
        print(f"   Follows - Total: {stats['follows']['total']}, Today: {stats['follows']['today']}, Success: {stats['follows']['successful']}")
        
        if stats['last_activity']:
            print(f"   Last Activity: {stats['last_activity']}")
        else:
            print(f"   Last Activity: No activity recorded")
            
    except Exception as e:
        print(f"❌ Could not load statistics: {e}")


def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(
        description="Instagram Automation System - Automatic liking and following"
    )
    
    parser.add_argument(
        '--config', '-c', 
        default='config/settings.json',
        help='Configuration file path (default: config/settings.json)'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['like', 'follow', 'both', 'status', 'init'],
        default='both',
        help='Automation mode (default: both)'
    )
    
    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--clean-logs',
        action='store_true',
        help='Clean old log entries (older than 30 days)'
    )
    
    args = parser.parse_args()
    
    # Handle special modes
    if args.mode == 'init':
        create_default_config_file()
        return
    
    if args.clean_logs:
        print("🧹 Cleaning old log entries...")
        clean_old_logs()
        print("✅ Log cleanup completed")
        return
    
    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        print("Run with --mode init to create a default configuration file.")
        return
    
    # Validate configuration
    is_valid, errors = validate_config(config)
    if not is_valid:
        print("❌ Configuration validation failed:")
        for error in errors:
            print(f"   - {error}")
        return
    
    # Override log level if verbose
    if args.verbose:
        config['logging']['level'] = 'DEBUG'
    
    # Set up logging
    setup_logging(config)
    
    # Print header
    print("=" * 60)
    print("🤖 Instagram Automation System")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Config: {args.config}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No actual actions will be performed")
    
    print()
    
    # Initialize session manager
    session_manager = SessionManager()
    
    # Handle status mode
    if args.mode == 'status':
        check_session_health(session_manager)
        show_statistics()
        return
    
    # Check session health
    if not check_session_health(session_manager):
        print("❌ Cannot proceed due to session health issues.")
        return
    
    if args.dry_run:
        print("✅ Dry run completed - sessions are healthy and configuration is valid.")
        return
    
    # Run automation based on mode
    results = {}
    
    try:
        if args.mode in ['like', 'both']:
            results['like'] = run_like_automation(config)
            print()
        
        if args.mode in ['follow', 'both']:
            results['follow'] = run_follow_automation(config)
            print()
        
        # Show final statistics
        show_statistics()
        
        print("\n✅ Automation session completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Automation interrupted by user")
        logger.info("Automation interrupted by user")
        
    except Exception as e:
        print(f"\n❌ Automation failed: {e}")
        logger.error(f"Automation failed: {e}")
    
    finally:
        # Clean up
        logger.info("Automation session ended")


if __name__ == "__main__":
    main()
