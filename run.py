"""
Starts both the Telegram bot and the Flask dashboard in parallel.

  python run.py

Dashboard → http://localhost:5000
"""
import threading
import logging
import sys
import os

# Make sure the package root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dashboard.app import app
from config import DASHBOARD_PORT

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)


def start_dashboard():
    logging.info("Dashboard starting at http://localhost:%s", DASHBOARD_PORT)
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, use_reloader=False)


def start_bot():
    from bot import main
    logging.info("Telegram bot starting…")
    main()


if __name__ == "__main__":
    t = threading.Thread(target=start_dashboard, daemon=True, name="dashboard")
    t.start()

    # Bot runs in main thread (owns the asyncio event loop)
    start_bot()
