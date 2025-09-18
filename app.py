import os
from flask import Flask, request, jsonify, abort
from models import db, Movie

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///moviewatchlist.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    with app.app_context():
        db.create_all()

    # our variables / functions
    def movie_to_dict(m: Movie):
        return {
            "id": m.id,
            "title": m.title,
            "year": m.year,
            "external_id": m.external_id,
            "source": m.source,
            "personal_rating": m.personal_rating,
            "watched": m.watched,
            "created_at": m.created_at.isoformat(),
            "updated_at": m.updated_at.isoformat(),
        }

    # routers for API
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/movies")
    def list_movies():
        q = request.args.get("q", "").strip()
        watched = request.args.get("watched")
        order = request.args.get("order", "-created_at")  # defaulting to newest first
        qry = Movie.query
        if q:
            qry = qry.filter(Movie.title.ilike(f"%{q}%")) # filtering by different dbs
        if watched in {"true", "false"}:
            qry = qry.filter(Movie.watched == (watched == "true"))
        if order == "title":
            qry = qry.order_by(Movie.title.asc())
        elif order == "rating":
            qry = qry.order_by(Movie.personal_rating.asc().nulls_last())
        elif order == "-rating":
            qry = qry.order_by(Movie.personal_rating.desc().nulls_last())
        else:
            qry = qry.order_by(Movie.created_at.desc())
        return jsonify([movie_to_dict(m) for m in qry.all()])

    @app.post("/api/movies") # logic to add a new movie
    def create_movie():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            abort(400, "title is required")
        m = Movie(
            title=title,
            year=(data.get("year") or None),
            external_id=(data.get("external_id") or None),
            source=(data.get("source") or None),
            personal_rating=(int(data["personal_rating"]) if data.get("personal_rating") not in (None, "") else None),
            watched=bool(data.get("watched", False)),
        )
        db.session.add(m)
        db.session.commit()
        return movie_to_dict(m), 201

    @app.get("/api/movies/<int:movie_id>") # logic to get a specific movie by its ID
    def get_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        return movie_to_dict(m)

    @app.put("/api/movies/<int:movie_id>") # logic to update a specific movie by its ID
    @app.patch("/api/movies/<int:movie_id>") # allowing partial updates
    def update_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        data = request.get_json(silent=True) or {}
        if "title" in data:
            title = (data.get("title") or "").strip() 
            if not title:
                abort(400, "title cannot be empty")
            m.title = title
        if "year" in data:
            m.year = data.get("year") or None
        if "personal_rating" in data:
            v = data.get("personal_rating")
            m.personal_rating = (int(v) if v not in (None, "") else None)
        if "watched" in data:
            m.watched = bool(data.get("watched")) 
        if "external_id" in data:
            m.external_id = data.get("external_id") or None
        if "source" in data:
            m.source = data.get("source") or None
        db.session.commit()
        return movie_to_dict(m)

    @app.delete("/api/movies/<int:movie_id>") # logic to delete a specific movie by its ID
    def delete_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        db.session.delete(m)
        db.session.commit()
        return {"deleted": movie_id}

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
