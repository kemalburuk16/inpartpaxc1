#!/usr/bin/env python3
"""
Instagram Otomatik Beğenme ve Takip Etme Sistemi
Instagram session verilerini kullanarak otomatik beğenme ve takip etme işlemleri yapan Python uygulaması.

Bu sistem eğitim ve araştırma amaçlıdır. Kullanım sorumluluğu kullanıcıya aittir.
Instagram Terms of Service'e uygun kullanım zorunludır.
"""

import argparse
import json
import logging
import os
import schedule
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.instagram_client import InstagramClient
from src.like_manager import LikeManager
from src.follow_manager import FollowManager
from src.session_manager import InstagramSessionManager
from src.utils import load_config, setup_logging, clean_old_logs


class InstagramBot:
    """
    Main Instagram automation bot class that coordinates all activities.
    """
    
    def __init__(self, config_path: str = "config/settings.json"):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.logger = setup_logging()
        self.running = False
        
        # Initialize components
        self.client = None
        self.like_manager = None
        self.follow_manager = None
        self.session_manager = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("Instagram Bot initialized")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def initialize_components(self) -> bool:
        """Initialize all bot components."""
        try:
            # Initialize Instagram client
            self.client = InstagramClient(self.config)
            
            # Initialize managers
            self.like_manager = LikeManager(self.client, self.config)
            self.follow_manager = FollowManager(self.client, self.config)
            self.session_manager = InstagramSessionManager()
            
            self.logger.info("All components initialized successfully")
            
            # Test session validity (optional, don't fail if this fails)
            try:
                valid = self.client.is_session_valid()
                if valid:
                    self.logger.info("Session validation successful")
                else:
                    self.logger.warning("Session validation failed - some features may not work")
            except Exception as e:
                self.logger.warning(f"Session validation error (continuing anyway): {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            return False
    
    def run_like_cycle(self) -> Dict[str, Any]:
        """Run a complete like cycle."""
        self.logger.info("Starting like cycle")
        
        if not self.like_manager.can_like_more():
            self.logger.info("Like limit reached, skipping like cycle")
            return {'status': 'skipped', 'reason': 'limit_reached'}
        
        try:
            # Get target hashtags from config
            target_hashtags = self.config.get('target_hashtags', [])
            if not target_hashtags:
                self.logger.warning("No target hashtags configured")
                return {'status': 'error', 'reason': 'no_hashtags'}
            
            # Run auto-like from hashtags
            result = self.like_manager.auto_like_from_hashtags(
                hashtags=target_hashtags,
                posts_per_hashtag=3
            )
            
            self.logger.info(f"Like cycle completed: {result['total_posts_liked']} posts liked")
            return {'status': 'success', 'result': result}
            
        except Exception as e:
            self.logger.error(f"Error during like cycle: {e}")
            return {'status': 'error', 'reason': str(e)}
    
    def run_follow_cycle(self) -> Dict[str, Any]:
        """Run a complete follow cycle."""
        self.logger.info("Starting follow cycle")
        
        if not self.follow_manager.can_follow_more():
            self.logger.info("Follow limit reached, skipping follow cycle")
            return {'status': 'skipped', 'reason': 'limit_reached'}
        
        try:
            # Run auto-follow strategy
            result = self.follow_manager.auto_follow_strategy(max_follows=10)
            
            self.logger.info(f"Follow cycle completed: {result['total_followed']} users followed")
            return {'status': 'success', 'result': result}
            
        except Exception as e:
            self.logger.error(f"Error during follow cycle: {e}")
            return {'status': 'error', 'reason': str(e)}
    
    def run_unfollow_cycle(self) -> Dict[str, Any]:
        """Run unfollow cycle to clean up old follows."""
        self.logger.info("Starting unfollow cycle")
        
        if not self.follow_manager.can_unfollow_more():
            self.logger.info("Unfollow limit reached, skipping unfollow cycle")
            return {'status': 'skipped', 'reason': 'limit_reached'}
        
        try:
            result = self.follow_manager.auto_unfollow_old()
            
            self.logger.info(f"Unfollow cycle completed: {result['users_unfollowed']} users unfollowed")
            return {'status': 'success', 'result': result}
            
        except Exception as e:
            self.logger.error(f"Error during unfollow cycle: {e}")
            return {'status': 'error', 'reason': str(e)}
    
    def run_maintenance(self) -> None:
        """Run maintenance tasks."""
        self.logger.info("Running maintenance tasks")
        
        try:
            # Clean old logs
            clean_old_logs()
            
            # Refresh session status
            if self.session_manager:
                self.session_manager.refresh_session_status()
                self.session_manager.cleanup_expired_blocks()
            
            # Clean up follow manager data
            if self.follow_manager:
                self.follow_manager.cleanup_following_data()
            
            # Clean up like manager data
            if self.like_manager:
                self.like_manager.cleanup_old_liked_posts()
            
            self.logger.info("Maintenance tasks completed")
            
        except Exception as e:
            self.logger.error(f"Error during maintenance: {e}")
    
    def get_bot_stats(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics."""
        stats = {
            'timestamp': datetime.now().isoformat(),
            'client_stats': {},
            'like_stats': {},
            'follow_stats': {},
            'session_stats': {}
        }
        
        try:
            if self.client:
                stats['client_stats'] = self.client.get_request_stats()
            
            if self.like_manager:
                stats['like_stats'] = self.like_manager.get_like_stats()
            
            if self.follow_manager:
                stats['follow_stats'] = self.follow_manager.get_follow_stats()
            
            if self.session_manager:
                stats['session_stats'] = self.session_manager.get_session_stats()
                
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
        
        return stats
    
    def run_interactive_mode(self) -> None:
        """Run bot in interactive mode."""
        self.logger.info("Starting interactive mode")
        
        while True:
            print("\n=== Instagram Bot Interactive Mode ===")
            print("1. Run like cycle")
            print("2. Run follow cycle")
            print("3. Run unfollow cycle")
            print("4. Show statistics")
            print("5. Run maintenance")
            print("6. Exit")
            
            try:
                choice = input("\nSelect option (1-6): ").strip()
                
                if choice == '1':
                    result = self.run_like_cycle()
                    print(f"Like cycle result: {result}")
                
                elif choice == '2':
                    result = self.run_follow_cycle()
                    print(f"Follow cycle result: {result}")
                
                elif choice == '3':
                    result = self.run_unfollow_cycle()
                    print(f"Unfollow cycle result: {result}")
                
                elif choice == '4':
                    stats = self.get_bot_stats()
                    print(json.dumps(stats, indent=2))
                
                elif choice == '5':
                    self.run_maintenance()
                    print("Maintenance completed")
                
                elif choice == '6':
                    break
                
                else:
                    print("Invalid option")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
        
        self.logger.info("Interactive mode ended")
    
    def run_scheduled_mode(self) -> None:
        """Run bot in scheduled mode."""
        self.logger.info("Starting scheduled mode")
        self.running = True
        
        # Schedule tasks
        schedule.every(30).minutes.do(self.run_like_cycle)
        schedule.every(2).hours.do(self.run_follow_cycle)
        schedule.every(6).hours.do(self.run_unfollow_cycle)
        schedule.every().day.at("03:00").do(self.run_maintenance)
        
        self.logger.info("Scheduled tasks configured")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(f"Error in scheduled mode: {e}")
                time.sleep(300)  # Sleep 5 minutes on error
        
        self.logger.info("Scheduled mode ended")
    
    def run_single_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """Run a single action."""
        self.logger.info(f"Running single action: {action}")
        
        if action == 'like':
            hashtag = kwargs.get('hashtag')
            if hashtag:
                return {'result': self.like_manager.like_posts_by_hashtag(hashtag)}
            else:
                return self.run_like_cycle()
        
        elif action == 'follow':
            username = kwargs.get('username')
            if username:
                success = self.follow_manager.follow_user(username)
                return {'result': {'success': success}}
            else:
                return self.run_follow_cycle()
        
        elif action == 'unfollow':
            username = kwargs.get('username')
            if username:
                success = self.follow_manager.unfollow_user(username)
                return {'result': {'success': success}}
            else:
                return self.run_unfollow_cycle()
        
        elif action == 'stats':
            return self.get_bot_stats()
        
        elif action == 'maintenance':
            self.run_maintenance()
            return {'result': 'maintenance completed'}
        
        else:
            return {'error': f'Unknown action: {action}'}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Instagram Automation Bot')
    parser.add_argument('--config', '-c', default='config/settings.json',
                       help='Configuration file path')
    parser.add_argument('--mode', '-m', choices=['interactive', 'scheduled', 'single'],
                       default='interactive', help='Run mode')
    parser.add_argument('--action', '-a', help='Single action to run (like, follow, unfollow, stats, maintenance)')
    parser.add_argument('--hashtag', help='Hashtag for like action')
    parser.add_argument('--username', help='Username for follow/unfollow action')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create bot instance
    bot = InstagramBot(args.config)
    
    # Initialize components
    if not bot.initialize_components():
        print("Failed to initialize bot components")
        sys.exit(1)
    
    try:
        if args.mode == 'interactive':
            bot.run_interactive_mode()
        
        elif args.mode == 'scheduled':
            bot.run_scheduled_mode()
        
        elif args.mode == 'single':
            if not args.action:
                print("Action required for single mode")
                sys.exit(1)
            
            result = bot.run_single_action(
                args.action,
                hashtag=args.hashtag,
                username=args.username
            )
            print(json.dumps(result, indent=2))
        
    except Exception as e:
        bot.logger.error(f"Fatal error: {e}")
        sys.exit(1)
    
    bot.logger.info("Bot execution completed")


if __name__ == "__main__":
    main()