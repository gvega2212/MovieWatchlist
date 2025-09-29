import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

from models import db
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp  # our /api/* blueprint

load_dotenv()

def create_app():
    app = Flask(__name__)
    CORS(app)

    # configuration
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///moviewatchlist.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")  # optional bearer token

    # init extensions
    install_json_error_handlers(app)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        # unique index on (source, external_id) to prevent duplicates
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_source_external
            ON movie (source, external_id)
        """))
        db.session.commit()

    # register blueprints
    app.register_blueprint(api_bp)

    # simple root page
    @app.get("/")
    def home():
        return "<h1>Movie Watchlist API</h1><p>Use /api/health and /api/movies</p>"

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
