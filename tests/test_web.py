import os, sys, pytest

# allow importing the app package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import db, Movie

@pytest.fixture()
def web_client(tmp_path):
    # isolated app for web routes
    os.environ["SECRET_KEY"] = "test"
    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path/'web.db'}",
    )
    with app.app_context():
        db.drop_all(); db.create_all()
    c = app.test_client()
    yield app, c
    with app.app_context():
        db.session.remove()
        try:
            engine = db.get_engine()
        except Exception:
            engine = db.engine
        engine.dispose()

def _login_session(client, username="tester"):
    # put a username into the session for owner-gated routes
    with client.session_transaction() as sess:
        sess["u"] = username

def test_index_page_renders(web_client):
    app, c = web_client
    r = c.get("/")
    assert r.status_code == 200
    assert b"MovieWatchlist" in r.data

def test_login_page_renders(web_client):
    app, c = web_client
    r = c.get("/login")
    assert r.status_code == 200
    assert b"Login" in r.data

def test_search_and_recommendations_pages_render(web_client):
    app, c = web_client
    assert c.get("/search").status_code == 200
    # both /recs and /recommendations map to the same handler
    assert c.get("/recs").status_code == 200
    assert c.get("/recommendations").status_code == 200

def test_edit_flow_owner_gated(web_client):
    app, c = web_client
    # login as alice
    _login_session(c, "alice")

    # create a movie owned by alice (explicit owner; event hook won't run outside request)
    with app.app_context():
        m = Movie(title="Edit Me", year="2010", watched=False, owner="alice")
        db.session.add(m); db.session.commit()
        mid = m.id

    # alice can GET the edit form without redirect
    r = c.get(f"/edit/{mid}")
    assert r.status_code == 200
    assert b"Edit:" in r.data

    # update via POST (web form)
    r = c.post(
        f"/edit/{mid}",
        data={
            "title": "Edited",
            "year": "2011",
            "personal_rating": "7",
            "watched": "on",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with app.app_context():
        m2 = Movie.query.get(mid)
        assert m2.title == "Edited"
        assert m2.year == "2011"
        assert m2.personal_rating == 7
        assert m2.watched is True

def test_edit_forbidden_for_different_user(web_client):
    app, c = web_client
    # seed a row owned by bob
    with app.app_context():
        m = Movie(title="Owned By Bob", year=None, watched=False, owner="bob")
        db.session.add(m); db.session.commit()
        mid = m.id

    # login as different user and attempt edit -> redirected + flash "Not found."
    _login_session(c, "charlie")
    r = c.get(f"/edit/{mid}", follow_redirects=True)
    assert r.status_code == 200
    assert b"Not found." in r.data
