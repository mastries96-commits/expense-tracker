"""
Local:  python run.py  → Flask dashboard + Telegram bot (polling)
Render: gunicorn run:flask_app  → Flask only (bot uses webhook)
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

from dashboard.app import app as flask_app  # noqa: E402  (used by gunicorn)

if __name__ == "__main__":
    from config import DASHBOARD_PORT

    if os.environ.get("RENDER"):
        # Cloud: Flask serves everything; Telegram uses webhook
        logging.info("Running on Render — webhook mode, port %s", DASHBOARD_PORT)
        flask_app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, use_reloader=False)
    else:
        # Local: run Flask in background thread + bot polling in main thread
        import threading
        t = threading.Thread(
            target=lambda: flask_app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, use_reloader=False),
            daemon=True, name="dashboard",
        )
        t.start()
        logging.info("Dashboard → http://localhost:%s", DASHBOARD_PORT)

        from bot import main as bot_main
        logging.info("Telegram bot starting (polling)…")
        bot_main()
