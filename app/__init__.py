"""Flask application factory."""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


def create_app() -> Flask:
    # Load .env from project root
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

    # Initialize Firestore eagerly so init errors surface at boot, not first request
    from .firebase_client import get_db
    get_db()

    from .routes import bp
    app.register_blueprint(bp)

    return app


# For `flask --app app run`
app = create_app()
