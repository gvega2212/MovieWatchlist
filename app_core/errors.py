from flask import request, current_app
from werkzeug.exceptions import HTTPException, BadRequest, UnsupportedMediaType, Unauthorized, Forbidden
from typing import Any, Dict, Tuple
from functools import wraps

# JSON error handlers

def install_json_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http(e: HTTPException):
        return {
            "error": {
                "status": e.code,
                "code": e.name.replace(" ", "_").upper(),
                "message": e.description
            }
        }, e.code

    @app.errorhandler(Exception)
    def handle_generic(e: Exception):
        return {
            "error": {
                "status": 500,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal Server Error"
            }
        }, 500


# validators and helpers

ALLOWED_ORDERS = {"-created_at", "title", "rating", "-rating"}

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

def validate_title(v: Any) -> str: # required, needs to be non-empty
    title = (v or "").strip()
    if not title:
        raise BadRequest("title is required")
    if len(title) > 255:
        raise BadRequest("title must be ≤ 255 chars")
    return title

def validate_year(v: Any) -> str | None: # optional 4-digit year
    year = (v or "").strip()
    if not year:
        return None
    if not (len(year) == 4 and year.isdigit()):
        raise BadRequest("year must be a 4-digit string, e.g. '1999'")
    return year

def parse_bool(v: Any) -> bool: # for watched field
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "1", "yes"}: return True
        if s in {"false", "0", "no"}: return False
    raise BadRequest("watched must be boolean")

def parse_rating(v: Any) -> int | None: # personal_rating 0-10 or null
    if v in (None, ""):
        return None
    try:
        r = int(v)
    except Exception:
        raise BadRequest("personal_rating must be an integer 0–10")
    if not (0 <= r <= 10):
        raise BadRequest("personal_rating must be between 0 and 10")
    return r

def validate_pagination() -> Tuple[int, int]: # returns (page, page_size)
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

# simple auth decorator

def require_auth(fn): # decorator to require Bearer token auth
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = current_app.config.get("API_TOKEN")
        if not token:  # auth disabled if not set
            return fn(*args, **kwargs)
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise Unauthorized("Missing Bearer token")
        supplied = header.split(" ", 1)[1]
        if supplied != token:
            raise Forbidden("Invalid token")
        return fn(*args, **kwargs)
    return wrapper
