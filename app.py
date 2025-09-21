import os
from flask import Flask, request, jsonify, abort
from models import db, Movie

from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy


from dotenv import load_dotenv
load_dotenv()

from movie_api import search_tmdb, get_tmdb_movie, get_tmdb_genres, discover_by_genres
from models import db, Movie, Genre

from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    CORS(app)  # will allows requests from a browser client eventually
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
        order = request.args.get("order", "-created_at")  # -created_at, rating, -rating, title
        page = max(int(request.args.get("page", 1)), 1)
        page_size = max(min(int(request.args.get("page_size", 10)), 100), 1)

        qry = Movie.query
        if q:
            qry = qry.filter(Movie.title.ilike(f"%{q}%"))
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

        total = qry.count()
        items = qry.offset((page - 1) * page_size).limit(page_size).all()

        def movie_to_dict(m: Movie):
            return {
                "id": m.id, "title": m.title, "year": m.year,
                "external_id": m.external_id, "source": m.source,
                "personal_rating": m.personal_rating, "watched": m.watched,
                "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
            }

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [movie_to_dict(m) for m in items],
        }

    @app.post("/api/movies")  # logic to add a new movie
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

    @app.get("/api/movies/<int:movie_id>")  # logic to get a specific movie by its ID
    def get_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        return movie_to_dict(m)

    @app.put("/api/movies/<int:movie_id>")  # logic to update a specific movie by its ID
    @app.patch("/api/movies/<int:movie_id>")  # allowing partial updates
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

    @app.delete("/api/movies/<int:movie_id>")  # logic to delete a specific movie by its ID
    def delete_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        db.session.delete(m)
        db.session.commit()
        return {"deleted": movie_id}

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)

# tmbd search endpoint
@app.get("/api/search/tmdb")
def api_search_tmdb():
    q = (request.args.get("q") or "").strip()
    if not q:
        return {"results": []}
    return {"results": search_tmdb(q)}

# tmbd genres endpoint
@app.post("/api/movies/from-tmdb")
def api_add_from_tmdb():
    data = request.get_json(silent=True) or {}
    tmdb_id = data.get("tmdb_id")
    if not tmdb_id:
        abort(400, "tmdb_id is required")

    # fetching details
    info = get_tmdb_movie(int(tmdb_id))
    title = info.get("title") or info.get("name")
    year = (info.get("release_date") or "")[:4]
    genres = info.get("genres", [])

    # upsert genres locally
    existing = {g.tmdb_id: g for g in Genre.query.filter(Genre.tmdb_id.in_([g["id"] for g in genres])).all()}
    genre_models = []
    for g in genres:
        if g["id"] in existing:
            genre_models.append(existing[g["id"]])
        else:
            gm = Genre(tmdb_id=g["id"], name=g["name"])
            db.session.add(gm)
            genre_models.append(gm)

    # creating movie entry
    m = Movie(
        title=title,
        year=year or None,
        external_id=str(tmdb_id),
        source="tmdb",
        watched=bool(data.get("watched", False)),
        personal_rating=(int(data["personal_rating"]) if data.get("personal_rating") not in (None, "") else None),
    )
    m.genres = genre_models
    db.session.add(m)
    db.session.commit()

    # reusing existing serializer
    return {
        "id": m.id, "title": m.title, "year": m.year,
        "external_id": m.external_id, "source": m.source,
        "personal_rating": m.personal_rating, "watched": m.watched,
        "genres": [g.name for g in m.genres],
        "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
    }, 201

#reccomendations endpoint based on the watched movies with the highest ratings
@app.get("/api/recommendations")
def api_recommendations():
    min_rating = int(request.args.get("min_rating", 8))  #  >= 8
    limit_genres = int(request.args.get("k", 3))         # top genres
    # collect genre counts weighted by rating
    scores = {}
    watched_good = (
        Movie.query.filter(Movie.watched.is_(True))
                   .filter(Movie.personal_rating >= min_rating)
                   .all()
    )
    for m in watched_good:
        for g in m.genres:
            scores[g.tmdb_id] = scores.get(g.tmdb_id, 0) + (m.personal_rating or min_rating)

    # pick top tmdb genre ids
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit_genres]
    top_tmdb_ids = [tmdb_id for tmdb_id, _ in top]

    if not top_tmdb_ids:
        return {"results": [], "reason": "No watched movies with high ratings yet."}

    # use discover endpoint to get movies by genre
    results = discover_by_genres(top_tmdb_ids)
    # remove ones we already have by external_id
    have = {m.external_id for m in Movie.query.filter_by(source="tmdb").all()}
    filtered = [r for r in results if str(r["tmdb_id"]) not in have]

    return {"top_genres": top_tmdb_ids, "results": filtered[:20]}

@app.post("/api/movies/<int:movie_id>/toggle-watched")  # watched status of a movie
def toggle_watched(movie_id):
    m = Movie.query.get_or_404(movie_id)  # get movie or result in 404
    m.watched = not m.watched
    db.session.commit()
    return {"id": m.id, "watched": m.watched}

@app.post("/api/movies/<int:movie_id>/rate")  #rate a movie
def rate_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    data = request.get_json(silent=True) or {}  #get the json data
    if "personal_rating" not in data:  # checking if the personal_rating is present
        return {"error": "personal_rating required"}, 400  #400 bad request
    try:
        r = int(data["personal_rating"])
    except Exception:
        return {"error": "personal_rating must be an integer 0–10"}, 400
    if not (0 <= r <= 10):
        return {"error": "personal_rating must be 0–10"}, 400
    m.personal_rating = r
    db.session.commit()
    return {  #returning the updated movie info
        "id": m.id,
        "title": m.title,
        "personal_rating": m.personal_rating
    }
