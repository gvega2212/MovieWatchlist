from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Movie
import movie_api as mapi
from .session_utils import current_user

web_bp = Blueprint("web", __name__)

def movie_row(m: Movie):
    return {
        "id": m.id,
        "title": m.title,
        "year": m.year,
        "personal_rating": m.personal_rating,
        "watched": m.watched,
        "overview": getattr(m, "overview", None),
        "poster_url": mapi.tmdb_poster_url(getattr(m, "poster_path", None)) if m.source == "tmdb" else None,
        # expose genres to template when eager-loaded
        "genres": getattr(m, "genres", []),
    }

def _owns_movie(m: Movie, user: str | None) -> bool:
    """
    True if:
      - user is set and equals m.owner, OR
      - user is None (anonymous) and the row has no owner.
    """
    return (user and m.owner == user) or (not user and m.owner is None)

@web_bp.get("/")
def html_index():
    q = (request.args.get("q") or "").strip()
    watched = request.args.get("watched")
    order = request.args.get("order", "-created_at")

    qry = Movie.query
    user = current_user()
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

    items = qry.all()
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
    user = current_user()
    if not _owns_movie(m, user):
        flash("Not found.", "error")
        return redirect(url_for("web.html_index"))
    return render_template("edit_movie.html", movie=movie_row(m))

@web_bp.post("/edit/<int:movie_id>")
def html_edit_post(movie_id):
    m = Movie.query.get_or_404(movie_id)
    user = current_user()
    if not _owns_movie(m, user):
        flash("Not found.", "error")
        return redirect(url_for("web.html_index"))

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
    user = current_user()
    if not _owns_movie(m, user):
        flash("Not found.", "error")
        return redirect(url_for("web.html_index"))

    db.session.delete(m)
    db.session.commit()
    flash("Movie deleted.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.get("/recs")
@web_bp.get("/recommendations")
def html_recommendations():
    return render_template("recommendations.html")

@web_bp.get("/login")
def html_login_get():
    return render_template("login.html")

@web_bp.post("/login")
def html_login_post():
    name = (request.form.get("username") or "").strip().lower()
    if not name:
        flash("Please enter a name.", "error")
        return redirect(url_for("web.html_login_get"))
    # session write happens in app.py via Flask; reading is centralized via session_utils.current_user()
    from flask import session
    session["u"] = name
    flash(f"Signed in as {name}.", "success")
    return redirect(url_for("web.html_index"))

@web_bp.get("/logout")
def html_logout():
    from flask import session
    session.pop("u", None)
    flash("Signed out.", "success")
    return redirect(url_for("web.html_index"))
