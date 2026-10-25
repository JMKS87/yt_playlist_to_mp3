import logging
import os
from collections import Counter
from datetime import datetime

from flask import Flask

from . import config, db, worker


def _localtime(value):
    """UTC ISO z bazy → czas lokalny (wg TZ procesu) ze strefą."""
    if not value:
        return ""
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _status_counts(items):
    return Counter(item["status"] for item in items if item["kind"] == "video")


def create_app():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = Flask(__name__)
    app.config.from_object(config)

    os.makedirs(app.config["OUTPUT_ROOT"], exist_ok=True)
    db.init_db(app.config["DB_PATH"])
    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)
    app.add_template_filter(_localtime, "localtime")
    app.add_template_filter(_status_counts, "status_counts")

    # Reloader w trybie debug ładuje aplikację dwa razy; worker ma żyć tylko w procesie, który obsługuje ruch.
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        worker.start(app.config["DB_PATH"], app.config["OUTPUT_ROOT"], app.config["TEMP_DIR"],
                     app.config["WORKER_POLL_SECONDS"])

    return app
