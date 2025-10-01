from flask import Blueprint, request, abort, session
from werkzeug.exceptions import BadRequest
from models import db, Movie, Genre
import movie_api as mapi
from .errors import (
    expect_json, read_json, validate_title, validate_year,
    parse_bool, parse_rating, validate_pagination, validate_order_param, require_auth
)

api_bp = Blueprint("api", __name__, url_prefix="/api") # blueprint for API routes

def _current_user() -> str | None:
    u = (session.get("u") or "").strip()
    return u or None

def movie_to_dict(m: Movie):   # helper to convert movie for JSON responses
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

@api_bp.get("/health")
def health():
    return {"ok": True}

@api_bp.get("/movies") # list movies with filtering, sorting, pagination
def list_movies():
    q = (request.args.get("q") or "").strip()
    watched = request.args.get("watched")
    order = validate_order_param()
    page, page_size = validate_pagination()

    qry = Movie.query
    user = _current_user()
    if user:
        qry = qry.filter(Movie.owner == user)
    else:
        qry = qry.filter(Movie.owner.is_(None))

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

@api_bp.post("/movies") # create a new movie
@require_auth
def create_movie():
    expect_json()
    data = read_json()

    title   = validate_title(data.get("title"))
    year    = validate_year(data.get("year"))
    rating  = parse_rating(data.get("personal_rating"))
    watched = parse_bool(data.get("watched")) if "watched" in data else False

    user = _current_user()
    maybe = Movie.query.filter(Movie.title.ilike(title), Movie.year == year, Movie.owner == user).first()
    if maybe:
        return movie_to_dict(maybe) | {"created": False}, 200

    m = Movie(title=title, year=year, personal_rating=rating, watched=watched, owner=user)
    db.session.add(m); db.session.commit()
    return movie_to_dict(m), 201

@api_bp.get("/movies/<int:movie_id>") # get movie details
def get_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    return movie_to_dict(m)

@api_bp.put("/movies/<int:movie_id>")
@api_bp.patch("/movies/<int:movie_id>")
@require_auth
def update_movie(movie_id): # update movie details
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

@api_bp.delete("/movies/<int:movie_id>") # delete a movie
@require_auth
def delete_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    db.session.delete(m); db.session.commit()
    return {"deleted": movie_id}

@api_bp.get("/search/tmdb") # search TMDB for movies
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

    have_tmdb = {m.external_id for m in Movie.query.filter_by(source="tmdb").filter(Movie.owner == (_current_user())).all()}
    results = [{
        **r,
        "poster_url": mapi.tmdb_poster_url(r.get("poster_path"))
    } for r in raw if str(r.get("tmdb_id")) not in have_tmdb]
    return {"results": results}

@api_bp.post("/movies/from-tmdb") # add a movie from TMDB 
@require_auth
def api_add_from_tmdb():
    data = request.get_json(silent=True) or {}
    tmdb_id = data.get("tmdb_id")
    if not tmdb_id:
        abort(400, "tmdb_id is required")

    user = _current_user()
    # --- duplicate guard per user to avoid 500 on unique constraint ---
    existing = Movie.query.filter_by(source="tmdb", external_id=str(tmdb_id), owner=user).first()
    if existing:
        return movie_to_dict(existing) | {"created": False}, 200

    info = mapi.get_tmdb_movie(int(tmdb_id))
    title = info.get("title") or info.get("name")
    year = (info.get("release_date") or "")[:4]
    genres = info.get("genres", [])
    poster_path = info.get("poster_path") or info.get("backdrop_path")
    overview = info.get("overview")

    existing_genres = [g["id"] for g in genres]
    if existing_genres:
        found = Genre.query.filter(Genre.tmdb_id.in_(existing_genres)).all()
        existing_map = {g.tmdb_id: g for g in found}
    else:
        existing_map = {}

    genre_models = []
    for g in genres:
        if g["id"] in existing_map:
            genre_models.append(existing_map[g["id"]])
        else:
            gm = Genre(tmdb_id=g["id"], name=g["name"])
            db.session.add(gm)
            genre_models.append(gm)

    # validate and clamp rating to 0–10 using parse_rating
    rating = None
    if "personal_rating" in data and data.get("personal_rating") not in (None, ""):
        rating = parse_rating(data.get("personal_rating"))

    m = Movie( # creating new movie record
        title=title,
        year=year or None,
        external_id=str(tmdb_id),
        source="tmdb",
        watched=bool(data.get("watched", False)),
        personal_rating=rating,
        poster_path=poster_path,
        overview=overview,
        owner=user,
    )
    m.genres = genre_models
    try:
        db.session.add(m); db.session.commit()
    except Exception:
        db.session.rollback()
        # if anything slips through (race), respond gracefully
        existing = Movie.query.filter_by(source="tmdb", external_id=str(tmdb_id), owner=user).first()
        if existing:
            return movie_to_dict(existing) | {"created": False}, 200
        raise

    return {
        "id": m.id, "title": m.title, "year": m.year,
        "external_id": m.external_id, "source": m.source,
        "personal_rating": m.personal_rating, "watched": m.watched,
        "genres": [g.name for g in m.genres],
        "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
    }, 201

@api_bp.get("/recommendations") # get movie recommendations based on watched movies
def api_recommendations():
    try:
        rmin = int(request.args.get("rmin", request.args.get("min_rating", 7)))
        ywin = int(request.args.get("ywin", 10))
        vmin = float(request.args.get("vmin", 7.0))
        cmin = int(request.args.get("cmin", 200))
        pages = max(1, min(int(request.args.get("pages", 2)), 3))
    except Exception:
        raise BadRequest("Invalid parameters")

    seeds = (
        Movie.query.filter(Movie.watched.is_(True))
                   .filter(Movie.personal_rating >= rmin)
                   .filter(Movie.owner == (_current_user()))
                   .all()
    )
    if not seeds:
        return {"results": [], "reason": f"No watched movies with rating ≥ {rmin} yet."} 

    have_tmdb = {m.external_id for m in Movie.query.filter_by(source="tmdb").filter(Movie.owner == (_current_user())).all()}

    pool = {} # candidate pool keyed by tmdb_id
    for m in seeds:
        seed_genres = [g.tmdb_id for g in m.genres]
        if not seed_genres:
            continue
        seed_year = None
        if m.year and isinstance(m.year, str) and m.year.isdigit():
            seed_year = int(m.year)

        y_from = seed_year - ywin if seed_year else None
        y_to   = seed_year + ywin if seed_year else None

        for p in range(1, pages + 1): # fetch multiple pages of results
            try:
                cand = mapi.discover_by_genres_window(
                    seed_genres,
                    year_from=y_from,
                    year_to=y_to,
                    min_vote_average=vmin,
                    min_vote_count=cmin,
                    page=p,
                    sort_by="vote_average.desc", # giving preference to higher-rated movies
                )
            except Exception:
                cand = [] # if TMDB fetch fails, skip
            for it in cand:
                tid = str(it.get("tmdb_id")) # skip if its already in DB
                if not tid or tid in have_tmdb:
                    continue
                pool[tid] = it

    if not pool:
        return {"results": [], "reason": "No suitable candidates found. Try lowering thresholds."}

    import math # for logarithmic popularity scoring
    max_votes = max((c.get("vote_count") or 0) for c in pool.values()) or 1 # avoid div by zero

    def genre_overlap(seed_ids, cand_ids): 
        if not seed_ids: 
            return 0.0
        inter = len(set(seed_ids) & set(cand_ids))
        return inter / float(len(seed_ids))

    def time_score(seed_year, cand_year):
        if not seed_year or not cand_year:
            return 0.0
        dy = abs(seed_year - cand_year)
        return max(0.0, 1.0 - (dy / float(ywin)))

    def rating_score(v):
        try:
            v = float(v or 0)
        except Exception:
            v = 0.0
        return max(0.0, min(1.0, (v - 6.0) / 4.0))

    def pop_score(vc): #scaling of vote count
        try:
            vc = float(vc or 0)
        except Exception:
            vc = 0.0
        return max(0.0, min(1.0, (math.log1p(vc) / math.log1p(max_votes))))

    scores = {} # final scores for candidates
    for tid, c in pool.items():
        cyear = int(c["year"]) if (c.get("year") and str(c["year"]).isdigit()) else None
        cgenres = c.get("genre_ids") or []
        cr = float(c.get("vote_average") or 0.0)
        cv = int(c.get("vote_count") or 0) #

        total = 0.0
        for s in seeds:
            seed_year = int(s.year) if (s.year and s.year.isdigit()) else None
            sgenres = [g.tmdb_id for g in s.genres]
            sw = (float(s.personal_rating) - rmin) / float(max(1, 10 - rmin))
            sw = max(0.0, min(1.0, sw))

            go = genre_overlap(sgenres, cgenres)
            ts = time_score(seed_year, cyear)
            rs = rating_score(cr)
            ps = pop_score(cv)

            total += sw * (0.55*go + 0.20*ts + 0.20*rs + 0.05*ps)
            # weights are calculates using the  genre overlap most important, then time proximity and rating, then popularity
            # multiplied by seed weight based on personal rating
            # this way, multiple seeds contribute to the score

        if total > 0:
            scores[tid] = total

    if not scores:
        return {"results": [], "reason": "No high-scoring candidates. Try widening the window or lowering vmin."}

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    kept = [] # final selection ensuring genre diversity
    last_top2 = set()
    for tid, _ in ranked:
        c = pool[tid]
        g = list(sorted((c.get("genre_ids") or [])))[:2]
        gset = set(g)
        if kept and gset == last_top2:
            continue
        kept.append(c)
        last_top2 = gset
        if len(kept) >= 20:
            break

    enriched = [{ # adding poster URLs
        **c,
        "poster_url": mapi.tmdb_poster_url(c.get("poster_path")), 
    } for c in kept]

    return {
        "params": {"rmin": rmin, "ywin": ywin, "vmin": vmin, "cmin": cmin}, 
        "based_on": [m.title for m in seeds],
        "results": enriched,
    }

@api_bp.post("/movies/<int:movie_id>/toggle-watched") #watched status toggle
@require_auth
def toggle_watched(movie_id):
    m = Movie.query.get_or_404(movie_id)
    m.watched = not m.watched
    db.session.commit()
    return {"id": m.id, "watched": m.watched}

@api_bp.post("/movies/bulk/from-tmdb") # bulk add movies from TMDB
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

        existing = Movie.query.filter_by(source="tmdb", external_id=str(tmdb_id), owner=_current_user()).first()
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

        existing_map = {g.tmdb_id: g for g in Genre.query.filter(Genre.tmdb_id.in_([g["id"] for g in genres])).all()} if genres else {}
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
            owner=_current_user(),
        )
        if hasattr(m, "poster_path"):
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

@api_bp.post("/movies/<int:movie_id>/rate")
@require_auth
def rate_movie(movie_id):
    m = Movie.query.get_or_404(movie_id)
    data = request.get_json(silent=True) or {}
    if "personal_rating" not in data:
        return {"error": "personal rating required"}, 400 #ensuring user inputs 1-10
    try:
        r = int(data["personal rating"])
    except Exception:
        return {"error": "personal rating must be an integer 0–10"}, 400
    if not (0 <= r <= 10):
        return {"error": "personal rating must be 0–10"}, 400
    m.personal_rating = r
    db.session.commit()
    return {"id": m.id, "title": m.title, "personal rating": m.personal_rating}

@api_bp.get("/export")
def api_export():
    genres = Genre.query.order_by(Genre.name.asc()).all()
    movies = Movie.query.filter(Movie.owner == (_current_user())).order_by(Movie.created_at.asc()).all()

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
                existing = Movie.query.filter_by(source=source, external_id=external_id, owner=_current_user()).first()
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

            new = Movie(title=title, year=year, watched=watched, personal_rating=rating, source=source, external_id=external_id, owner=_current_user())
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
