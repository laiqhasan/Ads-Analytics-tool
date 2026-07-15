import argparse
import sys
import logging
from db.session import SessionLocal
from connectors.mock import MockConnector
from connectors.meta import MetaConnector
from sync.orchestrator import SyncOrchestrator

def main():
    parser = argparse.ArgumentParser(description="Ads Analytics Tool - Sync Layer CLI")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Number of historical days to re-sync (default: 30)"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="all",
        choices=["google", "meta", "all"],
        help="Platform provider to sync (default: all)"
    )
    args = parser.parse_args()

    # Configure logging to stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger("ads_sync_main")
    logger.info("Starting Ads Analytics Sync Job...")

    # For Phase 1 validation, we run the MockConnector simulating Google and/or Meta platforms
    connectors = []
    if args.provider in ("google", "all"):
        logger.info("Registering Google Mock Connector")
        connectors.append(MockConnector(provider_name="google"))
    if args.provider in ("meta", "all"):
        logger.info("Registering Meta Connector")
        connectors.append(MetaConnector())

    # Initialize sync orchestrator
    orchestrator = SyncOrchestrator(
        session_factory=SessionLocal,
        connectors=connectors
    )

    # Execute sync
    try:
        orchestrator.sync(lookback_days=args.lookback_days)
        logger.info("Daily sync job completed successfully.")
    except Exception as e:
        logger.critical(f"Daily sync job failed with critical error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
