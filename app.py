import os
from pathlib import Path
from flask import Flask, has_request_context, session as _flask_session
# from flask_cors import CORS
from sqlalchemy import text, event
from models import db, Movie
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp
from app_core.web import web_bp


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Load env config (Azure injects environment variables automatically)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")

    # Database configuration
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        try:
            safe_dest = database_url.split("@", 1)[-1]
        except Exception:
            safe_dest = "<hidden>"
        print(f"[MovieWatchlist] Using DATABASE_URL -> {safe_dest}")
    else:
        instance_db = Path(app.instance_path) / "moviewatchlist.db"
        instance_db.parent.mkdir(parents=True, exist_ok=True)
        print(f"[MovieWatchlist] DB file -> {instance_db.resolve()}")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{instance_db}"

    # Install JSON error handlers & SQLAlchemy
    install_json_error_handlers(app)
    db.init_app(app)

    # Automatically attach owner before flush
    @event.listens_for(db.session, "before_flush")
    def _attach_owner_before_flush(session, flush_context, instances):
        if not has_request_context():
            return
        u = (_flask_session.get("u") or "").strip().lower() or None
        for obj in session.new:
            if isinstance(obj, Movie) and obj.owner is None:
                obj.owner = u

    # Initialize database safely
    with app.app_context():
        try:
            db.create_all()
            db.session.execute(text("DROP INDEX IF EXISTS ix_movie_source_external"))
            db.session.execute(
                text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_owner_source_external
                    ON movie (owner, source, external_id)
                """)
            )
            db.session.commit()
        except Exception as e:
            print(f"[Warning] Database initialization skipped due to error: {e}")

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    return app


app = create_app()

# Development only — Azure ignores this block
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
