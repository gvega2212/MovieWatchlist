from flask import Blueprint, request, abort
from werkzeug.exceptions import BadRequest
from models import db, Movie, Genre
import movie_api as mapi
from .errors import (
    expect_json, read_json, validate_title, validate_year,
    parse_bool, parse_rating, validate_pagination, validate_order_param, require_auth
)

api_bp = Blueprint("api", __name__, url_prefix="/api")

# serializer
def movie_to_dict(m: Movie):
    return {
        "id": m.id,
        "title": m.title,
        "year": m.year,
        "external_id": m.external_id,
        "source": m.source,
        "personal_rating": m.personal_rating,
        "watched": m.watched,
        "poster_url": mapi.tmdb_poster_url(getattr(m, "poster_path", None)) if m.source == "tmdb" else None,
        "overview": getattr(m, "overview", None),
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
    }

# health check
@api_bp.get("/health")
def health():
    return {"ok": True}

# list movies
@api_bp.get("/movies")
def list_movies():
    q = (request.args.get("q") or "").strip()
    watched = request.args.get("watched")
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

# create movie
@api_bp.post("/movies")
@require_auth
def create_movie():
    expect_json()
    data = read_json()

    title   = validate_title(data.get("title"))
    year    = validate_year(data.get("year"))
    rating  = parse_rating(data.get("personal_rating"))
    watched = parse_bool(data.get("watched")) if "watched" in data else False

    maybe = Movie.query.filter(Movie.title.ilike(title), Movie.year == year).first()
    if maybe:
        return movie_to_dict(maybe) | {"created": False}, 200

    m = Movie(title=title, year=year, personal_rating=rating, watched=watched)
    db.session.add(m); db.session.commit()
    return movie_to_dict(m), 201

# get movie details
@api_bp.get("/movies/<int:movie_id>")
def get_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    return movie_to_dict(m)

# update movie (full or partial)
@api_bp.put("/movies/<int:movie_id>")
@api_bp.patch("/movies/<int:movie_id>")
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

# deleting movie
@api_bp.delete("/movies/<int:movie_id>")
@require_auth
def delete_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    db.session.delete(m); db.session.commit()
    return {"deleted": movie_id}

@api_bp.get("/search/tmdb")
def api_search_tmdb():
    q = (request.args.get("q") or "").strip()
    default = (request.args.get("default") or "trending").lower()

    if q:
        raw = mapi.search_tmdb(q)
    else:
        if default == "top_rated":
            raw = mapi.top_rated_movies()
        elif default == "popular":
            raw = mapi.popular_movies()
        elif default == "now_playing":
            raw = mapi.now_playing_movies()
        else:
            raw = mapi.trending_movies()

    results = [{
        **r,
        "poster_url": mapi.tmdb_poster_url(r.get("poster_path"))
    } for r in raw]
    return {"results": results}



# adding movie from tmdb
@api_bp.post("/movies/from-tmdb")
@require_auth
def api_add_from_tmdb():
    data = request.get_json(silent=True) or {}
    tmdb_id = data.get("tmdb_id")
    if not tmdb_id:
        abort(400, "tmdb_id is required")

    info = mapi.get_tmdb_movie(int(tmdb_id))
    title = info.get("title") or info.get("name")
    year = (info.get("release_date") or "")[:4]
    genres = info.get("genres", [])
    poster_path = info.get("poster_path") or info.get("backdrop_path")
    overview = info.get("overview")

    existing = {g.tmdb_id: g for g in Genre.query.filter(Genre.tmdb_id.in_([g["id"] for g in genres])).all()}
    genre_models = []
    for g in genres:
        if g["id"] in existing:
            genre_models.append(existing[g["id"]])
        else:
            gm = Genre(tmdb_id=g["id"], name=g["name"])
            db.session.add(gm)
            genre_models.append(gm)

    m = Movie(
        title=title,
        year=year or None,
        external_id=str(tmdb_id),
        source="tmdb",
        watched=bool(data.get("watched", False)),
        personal_rating=(int(data["personal_rating"]) if data.get("personal_rating") not in (None, "") else None),
        poster_path=poster_path,
        overview=overview,
    )
    m.genres = genre_models
    db.session.add(m); db.session.commit()

    return {
        "id": m.id, "title": m.title, "year": m.year,
        "external_id": m.external_id, "source": m.source,
        "personal_rating": m.personal_rating, "watched": m.watched,
        "genres": [g.name for g in m.genres],
        "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
    }, 201

# reccomendations based on watched movies with high ratings
@api_bp.get("/recommendations")
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

    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    top_tmdb_ids = [tmdb_id for tmdb_id, _ in top]

    if not top_tmdb_ids:
        return {"results": [], "reason": "No watched movies with high ratings yet."}

    results = mapi.discover_by_genres(top_tmdb_ids)
    have = {m.external_id for m in Movie.query.filter_by(source="tmdb").all()}
    filtered = [r for r in results if str(r["tmdb_id"]) not in have]

    return {"top_genres": top_tmdb_ids, "results": filtered[:20]}

# toggle watched
@api_bp.post("/movies/<int:movie_id>/toggle-watched")
@require_auth
def toggle_watched(movie_id):
    m = Movie.query.get_or_404(movie_id)
    m.watched = not m.watched
    db.session.commit()
    return {"id": m.id, "watched": m.watched}

# bulk add from tmdb
@api_bp.post("/movies/bulk/from-tmdb")
@require_auth
def api_bulk_from_tmdb():
    expect_json()
    data = read_json()

    tmdb_ids = data.get("tmdb_ids")
    if not isinstance(tmdb_ids, list) or not tmdb_ids:
        raise BadRequest("tmdb_ids must be a non-empty array of integers")

    default_rating = parse_rating(data.get("personal_rating"))
    default_watched = parse_bool(data.get("watched")) if "watched" in data else False

    results = []
    created_count = 0

    for raw_id in tmdb_ids:
        try:
            tmdb_id = int(raw_id)
        except Exception:
            results.append({"tmdb_id": raw_id, "ok": False, "error": "tmdb_id must be an integer"})
            continue

        existing = Movie.query.filter_by(source="tmdb", external_id=str(tmdb_id)).first()
        if existing:
            results.append({"tmdb_id": tmdb_id, "ok": True, "created": False, "id": existing.id})
            continue

        try:
            info = mapi.get_tmdb_movie(int(tmdb_id))
        except Exception:
            results.append({"tmdb_id": tmdb_id, "ok": False, "error": "TMDB fetch failed"})
            continue

        title = (info.get("title") or info.get("name") or "").strip()
        year = (info.get("release_date") or "")[:4] or None
        poster_path = info.get("poster_path") or info.get("backdrop_path")
        overview = info.get("overview")
        genres = info.get("genres", [])

        existing_map = {g.tmdb_id: g for g in Genre.query.filter(Genre.tmdb_id.in_([g["id"] for g in genres])).all()}
        genre_models = []
        for g in genres:
            if g["id"] in existing_map:
                genre_models.append(existing_map[g["id"]])
            else:
                gm = Genre(tmdb_id=g["id"], name=g["name"])
                db.session.add(gm)
                genre_models.append(gm)

        m = Movie(  # create movie
            title=title or str(tmdb_id),
            year=year,
            external_id=str(tmdb_id),
            source="tmdb",
            watched=default_watched,
            personal_rating=default_rating,
        )
        if hasattr(m, "poster_path"):  # new field in model
            m.poster_path = poster_path
        if hasattr(m, "overview"):
            m.overview = overview

        m.genres = genre_models
        try:
            db.session.add(m); db.session.commit()
        except Exception:
            db.session.rollback()
            results.append({"tmdb_id": tmdb_id, "ok": False, "error": "DB insert failed (maybe duplicate?)"})
            continue

        created_count += 1
        results.append({"tmdb_id": tmdb_id, "ok": True, "created": True, "id": m.id})

    return {
        "summary": {"requested": len(tmdb_ids), "created": created_count, "skipped_or_failed": len(tmdb_ids) - created_count},
        "results": results
    }, 200

# rating movie
@api_bp.post("/movies/<int:movie_id>/rate")
@require_auth
def rate_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    data = request.get_json(silent=True) or {}
    if "personal_rating" not in data:
        return {"error": "personal_rating required"}, 400
    try:
        r = int(data["personal_rating"])
    except Exception:
        return {"error": "personal_rating must be an integer 0–10"}, 400
    if not (0 <= r <= 10):
        return {"error": "personal_rating must be 0–10"}, 400
    m.personal_rating = r
    db.session.commit()
    return {"id": m.id, "title": m.title, "personal_rating": m.personal_rating}

# exporting
@api_bp.get("/export")
def api_export():
    genres = Genre.query.order_by(Genre.name.asc()).all()
    movies = Movie.query.order_by(Movie.created_at.asc()).all()

    def genre_row(g): return {"id": g.id, "tmdb_id": g.tmdb_id, "name": g.name}
    def movie_row(m):
        return { **movie_to_dict(m), "genre_names": [g.name for g in m.genres] }

    return {
        "meta": {"version": 1},
        "genres": [genre_row(g) for g in genres],
        "movies": [movie_row(m) for m in movies],
    }

@api_bp.post("/maintenance/fix-missing-posters")
def fix_missing_posters():
    qry = Movie.query.filter_by(source="tmdb")
    missing = qry.filter((Movie.poster_path.is_(None)) | (Movie.poster_path == "")).all()

    fixed = 0; failed = 0
    for m in missing:
        try:
            info = mapi.get_tmdb_movie(int(m.external_id))
            m.poster_path = info.get("poster_path") or info.get("backdrop_path")
            if hasattr(m, "overview") and not m.overview:
                m.overview = info.get("overview")
            db.session.add(m); db.session.commit()
            fixed += 1
        except Exception:
            db.session.rollback()
            failed += 1

    return {"fixed": fixed, "failed": failed, "checked": len(missing)}

# importing
@api_bp.post("/import")
@require_auth
def api_import():
    expect_json()
    payload = read_json()

    if not isinstance(payload, dict):
        raise BadRequest("Body must be an object")
    if "movies" not in payload or not isinstance(payload["movies"], list):
        raise BadRequest("Body must contain 'movies' as an array")

    movies = payload["movies"]
    created = 0; skipped = 0; errors = []

    # preload genres by name
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

            if source and external_id:
                existing = Movie.query.filter_by(source=source, external_id=external_id).first()
                if existing:
                    skipped += 1
                    continue

            genre_models = []
            for name in m.get("genre_names", []):
                name = (name or "").strip()
                if not name: continue
                g = existing_by_name.get(name)
                if not g:
                    g = Genre(name=name)
                    db.session.add(g)
                    existing_by_name[name] = g
                genre_models.append(g)

            new = Movie(title=title, year=year, watched=watched, personal_rating=rating, source=source, external_id=external_id)
            if hasattr(new, "overview") and m.get("overview"):
                new.overview = m.get("overview")
            new.genres = genre_models
            db.session.add(new); db.session.commit()
            created += 1
        except Exception as e:
            db.session.rollback()
            from werkzeug.exceptions import HTTPException
            if isinstance(e, HTTPException):
                errors.append({"index": idx, "message": e.description})
            else:
                errors.append({"index": idx, "message": "Unexpected error"})

    return { "summary": {"received": len(movies), "created": created, "skipped": skipped, "errors": len(errors)}, "errors": errors }, 200
