from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, Movie
import movie_api as mapi

web_bp = Blueprint("web", __name__) # blueprint for HTML pages

def _user():
    u = (session.get("u") or "").strip().lower()
    return u or None

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
    user = _user()
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

@web_bp.get("/recs") #  link to recommendations page
@web_bp.get("/recommendations")
def html_recommendations():
    return render_template("recommendations.html")

# login
@web_bp.get("/login")
def html_login_get():
    return render_template("login.html")

@web_bp.post("/login")
def html_login_post():
    name = (request.form.get("username") or "").strip().lower()
    if not name:
        flash("Please enter a name.", "error")
        return redirect(url_for("web.html_login_get"))
    session["u"] = name
    flash(f"Signed in as {name}.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.get("/logout")
def html_logout():
    session.pop("u", None)
    flash("Signed out.", "success")
    return redirect(url_for("web.html_index"))
