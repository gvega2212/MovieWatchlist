from typing import Optional
from flask import Request
from .errors import validate_order_param
from models import Movie

def build_movie_query(req_args: Request.args.__class__, user: Optional[str]):
    qry = Movie.query
    if user:
        qry = qry.filter(Movie.owner == user)
    else:
        qry = qry.filter(Movie.owner.is_(None))

    q = (req_args.get("q") or "").strip()
    watched = req_args.get("watched")
    order = validate_order_param()

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

    return qry
