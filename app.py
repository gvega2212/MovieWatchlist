import os
import time
from pathlib import Path

from flask import (
    Flask,
    has_request_context,
    session as _flask_session,
    jsonify,
    g,
    request,
)
from sqlalchemy import text, event
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from models import db, Movie
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp
from app_core.web import web_bp


# PROMETHEUS METRICS
REQUEST_COUNT = Counter(
    "moviewatchlist_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)

REQUEST_LATENCY = Histogram(
    "moviewatchlist_request_latency_seconds",
    "Latency of HTTP requests in seconds",
    ["endpoint"],
)

ERROR_COUNT = Counter(
    "moviewatchlist_errors_total",
    "Total HTTP 5xx responses",
    ["endpoint"],
)


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Load env config
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

    # Installing JSON error handlers & SQLAlchemy
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

    # Initializing database safely
    with app.app_context():
        try:
            db.create_all()
            db.session.execute(text("DROP INDEX IF EXISTS ix_movie_source_external"))
            db.session.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_owner_source_external
                    ON movie (owner, source, external_id)
                """
                )
            )
            db.session.commit()
        except Exception as e:
            print(f"[Warning] Database initialization skipped due to error: {e}")

    # MONITORING MIDDLEWARE
    @app.before_request
    def _start_timer():
        g._start_time = time.perf_counter()

    @app.after_request
    def _record_metrics(response):
        try:
            endpoint = (request.endpoint or "unknown").lower()
            status_code = response.status_code

            # Count requests
            REQUEST_COUNT.labels(
                request.method,
                endpoint,
                status_code,
            ).inc()

            # Latency
            start_time = getattr(g, "_start_time", None)
            if start_time is not None:
                elapsed = time.perf_counter() - start_time
                REQUEST_LATENCY.labels(endpoint).observe(elapsed)

            # Errors (5xx)
            if status_code >= 500:
                ERROR_COUNT.labels(endpoint).inc()
        except Exception as e:
            # Metrics must never break the app
            print(f"[Metrics] Failed to record metrics: {e}")

        return response

    # HEALTH CHECK ENDPOINT
    @app.route("/health")
    def health():
        """
        Basic health endpoint for monitoring.
        Returns 200 if DB is reachable, 500 otherwise.
        """
        db_ok = True
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            db_ok = False

        status_code = 200 if db_ok else 500

        return jsonify({"status": "ok" if db_ok else "error", "database": db_ok}), status_code

    # PROMETHEUS METRICS ENDPOINT
    @app.route("/metrics")
    def metrics():
        """
        Expose Prometheus metrics in text format.
        Prometheus will scrape this endpoint.
        """
        data = generate_latest()
        return data, 200, {"Content-Type": CONTENT_TYPE_LATEST}

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    return app


app = create_app()

# Development only 
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
