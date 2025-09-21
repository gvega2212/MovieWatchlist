import os, pytest
from app import create_app
from models import db, Movie

@pytest.fixture()
def client(tmp_path):
    # using a temp sqlite db for testing
    os.environ["SECRET_KEY"] = "test"
    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path/'test.db'}",
    )
    with app.app_context():
        db.drop_all(); db.create_all()
    return app.test_client()

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json["ok"] is True

def test_crud_movie(client): # basic CRUD operations 
    # create
    r = client.post("/api/movies", json={"title": "Inception", "year": "2010"})
    assert r.status_code == 201
    mid = r.json["id"]

    # list
    r = client.get("/api/movies")
    assert r.status_code == 200
    assert r.json["total"] == 1

    # update
    r = client.put(f"/api/movies/{mid}", json={"personal_rating": 8, "watched": True})
    assert r.status_code == 200
    assert r.json["personal_rating"] == 8
    assert r.json["watched"] is True

    # toggle
    r = client.post(f"/api/movies/{mid}/toggle-watched")
    assert r.status_code == 200
    assert r.json["watched"] is False

    # delete
    r = client.delete(f"/api/movies/{mid}")
    assert r.status_code == 200
    r = client.get("/api/movies")
    assert r.json["total"] == 0

    
