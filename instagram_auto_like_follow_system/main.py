import logging
import configparser
from instagram_client import InstagramClient
from managers import LikeManager, FollowManager

# Setup logging
logging.basicConfig(level=logging.INFO)

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Initialize Instagram client
instagram_client = InstagramClient(config['Instagram']['username'], config['Instagram']['password'])

# Initialize managers
like_manager = LikeManager(instagram_client)
follow_manager = FollowManager(instagram_client)

def main():
    try:
        while True:
            # Execute like and follow operations
            like_manager.perform_likes()
            follow_manager.perform_follows()
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()