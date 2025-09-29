from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Movie
import movie_api as mapi

web_bp = Blueprint("web", __name__) # blueprint for HTML routes

def movie_row(m: Movie): # serialize movie for templates
    """Serialize a Movie for templates (adds full poster_url when TMDB)."""
    poster_url = None
    try:
        if m.source == "tmdb": # only TMDB movies have posters
            poster_url = mapi.tmdb_poster_url(getattr(m, "poster_path", None))
    except Exception:
        pass
    return {
        "id": m.id,
        "title": m.title,
        "year": m.year,
        "personal_rating": m.personal_rating,
        "watched": m.watched,
        "overview": getattr(m, "overview", None),
        "poster_url": poster_url,
    }

@web_bp.get("/") # main index route
def html_index():
    q = (request.args.get("q") or "").strip()
    watched = request.args.get("watched")
    order = request.args.get("order", "-created_at")
    page = max(int(request.args.get("page", 1)), 1)
    page_size = max(min(int(request.args.get("page_size", 12)), 100), 1)

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

    total = qry.count() # total matching items
    items = qry.offset((page - 1) * page_size).limit(page_size).all()
    page_count = (total + page_size - 1) // page_size if total else 1

    return render_template(
        "index.html",
        movies=[movie_row(m) for m in items],
        q=q, watched=watched, order=order,
        page=page, page_size=page_size, page_count=page_count, total=total
    )

@web_bp.get("/add") # add movie form
def html_add_get():
    return render_template("add_movie.html")

@web_bp.post("/add") # handle add movie 
def html_add_post():
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Title is required.", "error")
        return redirect(url_for("web.html_add_get"))
    year = (request.form.get("year") or "").strip() or None
    pr = request.form.get("personal_rating")
    rating = int(pr) if pr not in (None, "") else None
    watched = request.form.get("watched") == "on"

    m = Movie(title=title, year=year, personal_rating=rating, watched=watched)
    db.session.add(m); db.session.commit()
    flash("Movie added!", "success")
    return redirect(url_for("web.html_index"))

@web_bp.get("/edit/<int:movie_id>") # edit movie form
def html_edit_get(movie_id):
    m = Movie.query.get_or_404(movie_id)
    return render_template("edit_movie.html", movie=m)

@web_bp.post("/edit/<int:movie_id>") # handle edit movie
def html_edit_post(movie_id):
    m = Movie.query.get_or_404(movie_id)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Title cannot be empty.", "error")
        return redirect(url_for("web.html_edit_get", movie_id=movie_id))
    year = (request.form.get("year") or "").strip() or None
    pr = request.form.get("personal_rating")
    rating = int(pr) if pr not in (None, "") else None
    watched = request.form.get("watched") == "on"

    m.title = title; m.year = year; m.personal_rating = rating; m.watched = watched
    db.session.commit()
    flash("Movie updated.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.post("/delete/<int:movie_id>") # handle delete movie
def html_delete(movie_id):
    m = Movie.query.get_or_404(movie_id)
    db.session.delete(m); db.session.commit()
    flash("Movie deleted.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.get("/_ping") # health check route
def ping():
    return "pong", 200

@web_bp.get("/search")
def html_search():
    return render_template("search.html")

