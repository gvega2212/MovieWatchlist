import os
import time
from pathlib import Path
from flask import Flask, Response, g, request
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text, event
from flask import has_request_context, session as _flask_session

from models import db, Movie
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp
from app_core.web import web_bp

# Prometheus metrics
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

load_dotenv()

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency (seconds)",
    ["endpoint"]
)

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app)

    # config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")

    # persistent SQLite under instance/
    instance_db = Path(app.instance_path) / "moviewatchlist.db"
    instance_db.parent.mkdir(parents=True, exist_ok=True)
    print(f"[MovieWatchlist] DB file -> {instance_db.resolve()}")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{instance_db}"

    # error handlers + db
    install_json_error_handlers(app)
    db.init_app(app)

    # Attach owner (per-session username) to new Movie rows created during requests
    @event.listens_for(db.session, "before_flush")
    def _attach_owner_before_flush(session, flush_context, instances):
        if not has_request_context():
            return
        u = (_flask_session.get("u") or "").strip().lower() or None
        for obj in session.new:
            if isinstance(obj, Movie) and obj.owner is None:
                obj.owner = u

    # DB bootstrap (indexes)
    with app.app_context():
        db.create_all()
        db.session.execute(text("DROP INDEX IF EXISTS ix_movie_source_external"))
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_owner_source_external
            ON movie (owner, source, external_id)
        """))
        db.session.commit()

    # Metrics: before/after request
    @app.before_request
    def _metrics_start():
        g._start_time = time.perf_counter()

    @app.after_request
    def _metrics_stop(resp):
        try:
            endpoint = (request.endpoint or "unknown")
            dur = time.perf_counter() - getattr(g, "_start_time", time.perf_counter())
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(dur)
            REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=str(resp.status_code)).inc()
        except Exception:
            pass
        return resp

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    # blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    return app

app = create_app()

if __name__ == "__main__":
    # Default to 5050 to avoid conflicts and to match docs.yaml
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=True)
