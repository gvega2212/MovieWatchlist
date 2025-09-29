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
from werkzeug.exceptions import HTTPException, BadRequest, UnsupportedMediaType
from typing import Any, Dict, Tuple
import movie_api as mapi
from werkzeug.exceptions import Unauthorized, Forbidden
from functools import wraps
from flask import current_app  # ADDED

# Json error handlers 
def install_json_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http(e: HTTPException):
        return {
            "error": {
                "status": e.code,
                "code": e.name.replace(" ", "_").upper(),  # for example "NOT_FOUND"
                "message": e.description
            }
        }, e.code

    @app.errorhandler(Exception)
    def handle_generic(e: Exception):
        # for debugging
        return {
            "error": {
                "status": 500,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal Server Error"
            }
        }, 500


ALLOWED_ORDERS = {"-created_at", "title", "rating", "-rating"}  # allowed order parameters

def expect_json():
    if request.method in {"POST", "PUT", "PATCH"}:
        ctype = request.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            raise UnsupportedMediaType("Use Content-Type: application/json")

def read_json() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        raise BadRequest("Invalid or missing JSON body")
    if not isinstance(data, dict):
        raise BadRequest("JSON body must be an object")
    return data

def validate_title(v: Any) -> str:
    title = (v or "").strip()
    if not title:
        raise BadRequest("title is required")
    if len(title) > 255:
        raise BadRequest("title must be ≤ 255 chars")
    return title

def validate_year(v: Any) -> str | None:
    year = (v or "").strip()
    if not year:
        return None
    if not (len(year) == 4 and year.isdigit()):
        raise BadRequest("year must be a 4-digit string, e.g. '1999'")
    return year

def parse_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "1", "yes"}:
            return True
        if s in {"false", "0", "no"}:
            return False
    raise BadRequest("watched must be boolean")

def parse_rating(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        r = int(v)
    except Exception:
        raise BadRequest("personal_rating must be an integer 0–10")
    if not (0 <= r <= 10):
        raise BadRequest("personal_rating must be between 0 and 10")
    return r

def validate_pagination() -> Tuple[int, int]:
    try:
        page = max(int(request.args.get("page", 1)), 1)
        size = int(request.args.get("page_size", 10))
    except Exception:
        raise BadRequest("page and page_size must be integers")
    page_size = max(min(size, 100), 1)
    return page, page_size

def validate_order_param() -> str:
    order = request.args.get("order", "-created_at")
    if order not in ALLOWED_ORDERS:
        raise BadRequest(f"order must be one of {sorted(ALLOWED_ORDERS)}")
    return order

# simple bearer auth decorator 
def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = current_app.config.get("API_TOKEN")
        if not token:
            # Auth disabled when API_TOKEN is not set
            return fn(*args, **kwargs)
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise Unauthorized("Missing Bearer token")
        supplied = header.split(" ", 1)[1]
        if supplied != token:
            raise Forbidden("Invalid token")
        return fn(*args, **kwargs)
    return wrapper

def create_app():
    app = Flask(__name__)
    install_json_error_handlers(app)
    CORS(app)  # will allow requests from a browser client eventually
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///moviewatchlist.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["API_TOKEN"] = os.getenv("API_TOKEN")  # simple authentication token

    db.init_app(app)
    with app.app_context():
        db.create_all()
        
        from sqlalchemy import text
        db.session.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_movie_source_external
        ON movie (source, external_id)
        """))
        db.session.commit()

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
        q = (request.args.get("q") or "").strip()
        watched = request.args.get("watched")  # "true"/"false"/None
        order = validate_order_param()
        page, page_size = validate_pagination()

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

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [movie_to_dict(m) for m in items],
        }

    @app.post("/api/movies")
    @require_auth
    def create_movie():
        expect_json()
        data = read_json()

        title   = validate_title(data.get("title"))
        year    = validate_year(data.get("year"))
        rating  = parse_rating(data.get("personal_rating"))
        watched = parse_bool(data.get("watched")) if "watched" in data else False

        # check for existing (title+year)
        maybe = Movie.query.filter(
            Movie.title.ilike(title),
            Movie.year == year
        ).first()
        if maybe:
            return movie_to_dict(maybe) | {"created": False}, 200

        m = Movie(
            title=title,
            year=year,
            personal_rating=rating,
            watched=watched,
        )
        db.session.add(m)
        db.session.commit()
        return movie_to_dict(m), 201

    @app.get("/api/movies/<int:movie_id>")  # logic to get a specific movie by its ID
    def get_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        return movie_to_dict(m)

    @app.put("/api/movies/<int:movie_id>")
    @app.patch("/api/movies/<int:movie_id>")
    @require_auth
    def update_movie(movie_id):
        expect_json()
        data = read_json()
        m = Movie.query.get_or_404(movie_id)
        
        if "title" in data:
            m.title = validate_title(data.get("title"))
        if "year" in data:
            m.year = validate_year(data.get("year"))
        if "personal_rating" in data:
            m.personal_rating = parse_rating(data.get("personal_rating"))
        if "watched" in data:
            m.watched = parse_bool(data.get("watched"))
        if "external_id" in data:
            m.external_id = (data.get("external_id") or None)
        if "source" in data:
            m.source = (data.get("source") or None)
        
        db.session.commit()
        return movie_to_dict(m)

    @app.delete("/api/movies/<int:movie_id>")  # logic to delete a specific movie by its ID
    @require_auth
    def delete_movie(movie_id):
        m = Movie.query.get_or_404(movie_id)
        db.session.delete(m)
        db.session.commit()
        return {"deleted": movie_id}

    # tmbd search endpoint
    @app.get("/api/search/tmdb")
    def api_search_tmdb():
        q = (request.args.get("q") or "").strip()
        if not q:
            return {"results": []}
        return {"results": search_tmdb(q)}

    @app.post("/api/movies/from-tmdb")
    @require_auth
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
        try:
            min_rating = int(request.args.get("min_rating", 8))
            k = int(request.args.get("k", 3))
        except Exception:
            raise BadRequest("min_rating and k must be integers")
        if not (0 <= min_rating <= 10):
            raise BadRequest("min_rating must be between 0 and 10")
        if not (1 <= k <= 10):
            raise BadRequest("k must be between 1 and 10")

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
        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        top_tmdb_ids = [tmdb_id for tmdb_id, _ in top]

        if not top_tmdb_ids:
            return {"results": [], "reason": "No watched movies with high ratings yet."}

        # use discover endpoint to get movies by genre
        results = discover_by_genres(top_tmdb_ids)
        # remove ones we already have by external_id
        have = {m.external_id for m in Movie.query.filter_by(source="tmdb").all()}
        filtered = [r for r in results if str(r["tmdb_id"]) not in have]

        return {"top_genres": top_tmdb_ids, "results": filtered[:20]}

    @app.get("/")
    def home():
        return "<h1>Movie Watchlist API</h1><p>Use /api/movies or /api/health</p>"

    @app.post("/api/movies/<int:movie_id>/toggle-watched")  # watched status of a movie
    @require_auth
    def toggle_watched(movie_id):
        m = Movie.query.get_or_404(movie_id)  # get movie or result in 404
        m.watched = not m.watched
        db.session.commit()
        return {"id": m.id, "watched": m.watched}
    
    @app.post("/api/movies/bulk/from-tmdb")
    @require_auth
    def api_bulk_from_tmdb():
        """
        Body:
        {
          "tmdb_ids": [603, 78, 335984],
          "watched": false,              # optional default applied to all
          "personal_rating": 8           # optional default applied to all (0-10)
        }
        Returns per-item result with created flag or error.
        """
        expect_json()
        data = read_json()

        tmdb_ids = data.get("tmdb_ids")
        if not isinstance(tmdb_ids, list) or not tmdb_ids:
            raise BadRequest("tmdb_ids must be a non-empty array of integers")

        default_rating = parse_rating(data.get("personal_rating"))
        default_watched = parse_bool(data.get("watched")) if "watched" in data else False

        results = []
        created_count = 0

        # process items one-by-one
        for raw_id in tmdb_ids:
            try:
                tmdb_id = int(raw_id)
            except Exception:
                results.append({"tmdb_id": raw_id, "ok": False, "error": "tmdb_id must be an integer"})
                continue

            # incase its there 
            existing = Movie.query.filter_by(source="tmdb", external_id=str(tmdb_id)).first()
            if existing:
                results.append({"tmdb_id": tmdb_id, "ok": True, "created": False, "id": existing.id})
                continue

            # fetching details from tmdb
            try:
                info = mapi.get_tmdb_movie(int(tmdb_id))
            except Exception as e:
                results.append({"tmdb_id": tmdb_id, "ok": False, "error": "TMDB fetch failed"})
                continue

            title = (info.get("title") or info.get("name") or "").strip()
            year = (info.get("release_date") or "")[:4] or None
            poster_path = info.get("poster_path")
            overview = info.get("overview")
            genres = info.get("genres", [])  

            # upsert genres locally
            existing_map = {g.tmdb_id: g for g in Genre.query.filter(Genre.tmdb_id.in_([g["id"] for g in genres])).all()}
            genre_models = []
            for g in genres:
                if g["id"] in existing_map:
                    genre_models.append(existing_map[g["id"]])
                else:
                    gm = Genre(tmdb_id=g["id"], name=g["name"])
                    db.session.add(gm)
                    genre_models.append(gm)

            m = Movie(
                title=title or str(tmdb_id),
                year=year,
                external_id=str(tmdb_id),
                source="tmdb",
                watched=default_watched,
                personal_rating=default_rating,
            )
            # optional fields 
            if hasattr(m, "poster_path"):
                m.poster_path = poster_path
            if hasattr(m, "overview"):
                m.overview = overview

            m.genres = genre_models
            try:
                db.session.add(m)
                db.session.commit()
            except Exception:
                db.session.rollback()
                # Unique index or other DB failure
                results.append({"tmdb_id": tmdb_id, "ok": False, "error": "DB insert failed (maybe duplicate?)"})
                continue

            created_count += 1
            results.append({"tmdb_id": tmdb_id, "ok": True, "created": True, "id": m.id})

        return {
            "summary": {"requested": len(tmdb_ids), "created": created_count, "skipped_or_failed": len(tmdb_ids) - created_count},
            "results": results
        }, 200

    @app.post("/api/movies/<int:movie_id>/rate")  #rate a movie
    @require_auth
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

    # read-only export endpoint (no auth)
    @app.get("/api/export")
    def api_export():
        # Export genres and movies in one payload
        genres = Genre.query.order_by(Genre.name.asc()).all()
        movies = Movie.query.order_by(Movie.created_at.asc()).all()

        def genre_row(g):
            return {"id": g.id, "tmdb_id": g.tmdb_id, "name": g.name}

        def movie_row(m):
            return {
                **movie_to_dict(m),
                "genre_names": [g.name for g in m.genres],  # friendly for re-import
            }

        return {
            "meta": {"version": 1},
            "genres": [genre_row(g) for g in genres],
            "movies": [movie_row(m) for m in movies],
        }

    # import endpoint (auth protected)
    @app.post("/api/import")
    @require_auth
    def api_import():
        """
        Accepts a JSON backup in the shape returned by /api/export.
        Only fields used to restore: title, year, source, external_id, watched, personal_rating, genre_names.
        If source+external_id exists, we skip (idempotent).
        If not, we insert and attach genres (create missing ones by name).
        """
        expect_json()
        payload = read_json()

        if not isinstance(payload, dict): 
            raise BadRequest("Body must be an object")
        if "movies" not in payload or not isinstance(payload["movies"], list):
            raise BadRequest("Body must contain 'movies' as an array")

        movies = payload["movies"]
        created = 0
        skipped = 0
        errors = []

        # preload existing genres by name
        all_names = set()
        for m in movies:
            for name in m.get("genre_names", []):
                if isinstance(name, str) and name.strip():
                    all_names.add(name.strip())
        existing_by_name = {g.name: g for g in Genre.query.filter(Genre.name.in_(list(all_names))).all()}

        for idx, m in enumerate(movies):
            try:
                title = validate_title(m.get("title"))
                year = validate_year(m.get("year"))
                watched = bool(m.get("watched", False))
                rating = parse_rating(m.get("personal_rating"))
                source = (m.get("source") or None)
                external_id = (m.get("external_id") or None)

                # if we have source+external_id, skip existing
                if source and external_id:
                    existing = Movie.query.filter_by(source=source, external_id=external_id).first()
                    if existing:
                        skipped += 1
                        continue

                # build genre associations (create missing by name)
                genre_models = []
                for name in m.get("genre_names", []):
                    name = (name or "").strip()
                    if not name:
                        continue
                    g = existing_by_name.get(name)
                    if not g:
                        g = Genre(name=name)  # tmdb_id unknown
                        db.session.add(g)
                        existing_by_name[name] = g
                    genre_models.append(g)

                new = Movie(
                    title=title,
                    year=year,
                    watched=watched,
                    personal_rating=rating,
                    source=source,
                    external_id=external_id,
                )
                #  if present in export
                if hasattr(new, "poster_path") and m.get("poster_url"):
                    # not restoring poster_path from full url
                    pass
                if hasattr(new, "overview") and m.get("overview"):
                    new.overview = m.get("overview")

                new.genres = genre_models
                db.session.add(new)
                db.session.commit()
                created += 1
            except HTTPException as e:
                db.session.rollback()
                errors.append({"index": idx, "message": e.description})
            except Exception:
                db.session.rollback()
                errors.append({"index": idx, "message": "Unexpected error"})

        return {
            "summary": {"received": len(movies), "created": created, "skipped": skipped, "errors": len(errors)},
            "errors": errors,
        }, 200

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
