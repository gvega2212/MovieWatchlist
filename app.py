import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text

from models import db
from app_core.errors import install_json_error_handlers
from app_core.api import api_bp
from app_core.web import web_bp  # added html blueprint

load_dotenv()

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app)

    # config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///moviewatchlist.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")  

    # initialize extensions
    install_json_error_handlers(app)
    db.init_app(app)

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
