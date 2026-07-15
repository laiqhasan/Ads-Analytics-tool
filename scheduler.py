import time
import logging
import sys
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "Ads Analytics Sync Scheduler"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress logging request noise to keep console logs clean
        pass

def start_health_check_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Starting health check HTTP server on port {port}...")
    server.serve_forever()

def run_loop():
    logger.info("Starting Ads Analytics Sync Scheduler Daemon...")
    
    # Start health check server in a background thread
    health_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_thread.start()
    
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

