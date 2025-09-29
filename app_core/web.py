from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Movie
import movie_api as mapi

web_bp = Blueprint("web", __name__) # blueprint for HTML pages

def movie_row(m: Movie): #helper to convert movie model to dict for templates
    return {
        "id": m.id,
        "title": m.title,
        "year": m.year,
        "personal_rating": m.personal_rating,
        "watched": m.watched,
        "overview": getattr(m, "overview", None),
        "poster_url": mapi.tmdb_poster_url(getattr(m, "poster_path", None)) if m.source == "tmdb" else None,
    }

@web_bp.get("/") # main index page with search and filter options
def html_index():
    q = (request.args.get("q") or "").strip()
    watched = request.args.get("watched")  # "true" / "false" / None
    order = request.args.get("order", "-created_at")

    qry = Movie.query # base query
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

    items = qry.all() # execute query
    movies = [movie_row(m) for m in items]
    return render_template("index.html", movies=movies, q=q, watched=watched, order=order)

@web_bp.get("/search")
def html_search():
    return render_template("search.html")

@web_bp.get("/add")
def html_add_get():
    return redirect(url_for("web.html_search"))

@web_bp.get("/edit/<int:movie_id>")
def html_edit_get(movie_id):
    m = Movie.query.get_or_404(movie_id)
    return render_template("edit_movie.html", movie=movie_row(m))

@web_bp.post("/edit/<int:movie_id>")
def html_edit_post(movie_id):
    m = Movie.query.get_or_404(movie_id)

    m.title = (request.form.get("title") or m.title).strip()
    year = (request.form.get("year") or "").strip()
    m.year = year if year else None

    pr = request.form.get("personal_rating")
    if pr is None or pr == "":
        m.personal_rating = None
    else:
        try:
            r = int(pr)
            if 0 <= r <= 10:
                m.personal_rating = r
        except Exception:
            pass

    m.watched = bool(request.form.get("watched"))
    db.session.commit()
    flash("Movie updated.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.post("/delete/<int:movie_id>") 
def html_delete(movie_id):
    m = Movie.query.get_or_404(movie_id)
    db.session.delete(m)
    db.session.commit()
    flash("Movie deleted.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.post("/edit/<int:movie_id>/attach-tmdb")
def html_attach_tmdb(movie_id):
    m = Movie.query.get_or_404(movie_id)
    tmdb_id = (request.form.get("tmdb_id") or "").strip()
    if not tmdb_id.isdigit():
        flash("Invalid TMDB id.", "error")
        return redirect(url_for("web.html_edit_get", movie_id=movie_id))

    try:
        info = mapi.get_tmdb_movie(int(tmdb_id)) # fetch movie details from TMDB
    except Exception:
        flash("TMDB lookup failed.", "error")
        return redirect(url_for("web.html_edit_get", movie_id=movie_id))

    m.source = "tmdb"
    m.external_id = str(tmdb_id)
    m.poster_path = info.get("poster_path") or info.get("backdrop_path")
    if not m.year:
        m.year = (info.get("release_date") or "")[:4] or None
    if hasattr(m, "overview") and not m.overview:
        m.overview = info.get("overview")
    db.session.commit()
    flash("Attached TMDB data.", "success")
    return redirect(url_for("web.html_edit_get", movie_id=movie_id))
