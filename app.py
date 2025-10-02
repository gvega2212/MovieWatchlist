import os
from pathlib import Path
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text

from models import db
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp
from app_core.web import web_bp  # added html blueprint

from sqlalchemy import event
from models import Movie
from flask import has_request_context, session as _flask_session

load_dotenv()

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app)

    # config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")

    # using a persistent, absolute SQLite path under instance
    instance_db = Path(app.instance_path) / "moviewatchlist.db"
    instance_db.parent.mkdir(parents=True, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{instance_db}"

    # initialize extensions
    install_json_error_handlers(app)
    db.init_app(app)

    # making sure the owner is set on new Movie objects
    @event.listens_for(db.session, "before_flush")
    def _attach_owner_before_flush(session, flush_context, instances):
        # only if within a request context (otherwise skip)
        if not has_request_context():
            return
        # normalize username (lowercase) or None
        u = (_flask_session.get("u") or "").strip().lower() or None
        if u is None:
            # allow anonymous to remain None (your UI shows those only when logged-out)
            pass
        for obj in session.new:
            if isinstance(obj, Movie) and obj.owner is None:
                obj.owner = u

    with app.app_context():
        db.create_all()
        # making uniqueness per-user by including the owner column.
        db.session.execute(text("DROP INDEX IF EXISTS ix_movie_source_external"))
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_owner_source_external
            ON movie (owner, source, external_id)
        """))
        db.session.commit()

    # blueprints
    app.register_blueprint(api_bp)   
    app.register_blueprint(web_bp)   # /

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
