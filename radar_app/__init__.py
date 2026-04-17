"""Application bootstrap helpers for the refactor branch."""

import os
import sys

from dotenv import load_dotenv
from flask import Flask

from radar_app.legacy.search_backend import warm_search_backend
from radar_app.context import register_context_processors
from radar_app.extensions import init_extensions
from radar_app.routes import register_routes
from radar_app.settings import load_settings


def _prepare_runtime():
    root = os.path.dirname(os.path.dirname(__file__))
    scripts_dir = os.path.join(root, "scripts")
    if root not in sys.path:
        sys.path.insert(0, root)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    load_dotenv(os.path.join(root, ".env"))
    warm_search_backend()


def create_app():
    """Build the Flask app directly from the refactored module tree."""
    _prepare_runtime()
    import db

    db.init_db()
    db._migrate()
    db.expire_stale_jobs()
    settings = load_settings()
    root = os.path.dirname(os.path.dirname(__file__))

    app = Flask(
        __name__,
        template_folder=os.path.join(root, "templates"),
        static_folder=os.path.join(root, "static"),
    )
    app.secret_key = settings.secret_key
    bcrypt, oauth = init_extensions(app)
    register_context_processors(app)
    register_routes(app, bcrypt, oauth)
    return app


def run_dev_server(flask_app):
    """Preserve the current local startup behaviour behind the new entrypoint."""
    import db

    db.init_db()
    db.expire_stale_jobs()
    settings = load_settings()
    print(f"🚀 Personal Buffett → http://127.0.0.1:{settings.port} (debug={'on' if settings.debug else 'off'})")
    flask_app.run(debug=settings.debug, use_reloader=settings.debug, host="0.0.0.0", port=settings.port)
