import os
import logging
from pathlib import Path
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text, event
from flask import has_request_context, session as _flask_session

from models import db, Movie
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp
from app_core.web import web_bp
from app_core.metrics import metrics_bp  

load_dotenv()

def _resolve_db_uri() -> str:
   
    direct_uri = os.getenv("SQLALCHEMY_DATABASE_URI")
    if direct_uri:
        return direct_uri

    db_path = os.getenv("DB_PATH")
    if not db_path:
        # Default persistent location outside the project tree (survives git clean, rebuilds)
        persistent_dir = Path.home() / ".moviewatchlist_data"
        persistent_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(persistent_dir / "moviewatchlist.db")
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"[MovieWatchlist] DB file -> {Path(db_path).resolve()}")
    return f"sqlite:///{db_path}"

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app)

    class RequestFormatter(logging.Formatter):
        def format(self, record):
            if has_request_context():
                u = (_flask_session.get("u") or "").strip().lower() or None
                record.user = u or "-"
            else:
                record.user = "-"
            return super().format(record)

    handler = logging.StreamHandler()
    handler.setFormatter(RequestFormatter('%(asctime)s %(levelname)s user="%(user)s" msg="%(message)s"'))
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")
    # robust, persistent DB location
    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_db_uri()

    # extensions
    install_json_error_handlers(app)
    db.init_app(app)

    # attach owner automatically on new Movie rows (based on session 'u')
    @event.listens_for(db.session, "before_flush")
    def _attach_owner_before_flush(session, flush_context, instances):
        if not has_request_context():
            return
        u = (_flask_session.get("u") or "").strip().lower() or None
        for obj in session.new:
            if isinstance(obj, Movie) and obj.owner is None:
                obj.owner = u

    with app.app_context():
        db.create_all()
        # make (owner, source, external_id) unique (drop older generic index)
        db.session.execute(text("DROP INDEX IF EXISTS ix_movie_source_external"))
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_owner_source_external
            ON movie (owner, source, external_id)
        """))
        db.session.commit()

    # blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(metrics_bp)  # /metrics

    return app

app = create_app()

if __name__ == "__main__":
    # allow PORT override for Docker/Compose
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=True)
