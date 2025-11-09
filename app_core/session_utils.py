from flask import session

def current_user() -> str | None:
    
    u = (session.get("u") or "").strip().lower()
    return u or None
