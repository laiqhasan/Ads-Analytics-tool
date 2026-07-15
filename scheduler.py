import time
import logging
import sys
from main import main as run_sync

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("scheduler_daemon")

def run_loop():
    logger.info("Starting Ads Analytics Sync Scheduler Daemon...")
    while True:
        logger.info("Triggering scheduled sync job...")
        try:
            # Mock CLI arguments to run a full sync across all providers with a 30-day lookback window
            sys.argv = ["main.py", "--provider", "all", "--lookback-days", "30"]
            run_sync()
            logger.info("Scheduled sync job completed successfully.")
        except Exception as e:
            logger.error(f"Sync job failed in scheduler loop: {e}", exc_info=True)
        
        # Sleep for 24 hours (86400 seconds)
        logger.info("Sleeping for 24 hours until the next daily sync run...")
        time.sleep(86400)

if __name__ == "__main__":
    run_loop()
