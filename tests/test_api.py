import os, pytest, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from models import db, Movie
import movie_api as mapi

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

    # validation and tmbd mocks

def test_create_requires_json_content_type(client):
    # missing content-type header
    r = client.post("/api/movies", data='{"title":"X"}')  # no content-type header
    assert r.status_code == 415
    assert r.json["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

def test_create_bad_year_and_bad_rating(client):
    # bad year format
    r = client.post("/api/movies", json={"title": "X", "year": "99"})
    assert r.status_code == 400
    assert "4-digit" in r.json["error"]["message"]

    # rating out of allowed range
    r = client.post("/api/movies", json={"title": "X", "personal_rating": 42})
    assert r.status_code == 400
    assert "between 0 and 10" in r.json["error"]["message"]

def test_list_invalid_order_param(client): # invalid order param
    r = client.get("/api/movies?order=banana")
    assert r.status_code == 400
    assert "one of" in r.json["error"]["message"]

def test_recommendations_param_validation(client):
    # non-integer params
    r = client.get("/api/recommendations?min_rating=x&k=3")
    assert r.status_code == 400
    # out-of-range values
    r = client.get("/api/recommendations?min_rating=11&k=0")
    assert r.status_code == 400

def test_tmdb_search_and_add_from_tmdb_mocked_and_recommendations(client, monkeypatch):
    # mock movie_api functions to avoid real HTTP calls
    def fake_get_tmdb_movie(movie_id: int):
        return {
            "id": movie_id,
            "title": "Blade Runner",
            "release_date": "1982-06-25",
            "genres": [
                {"id": 878, "name": "Science Fiction"},
                {"id": 18, "name": "Drama"},
            ],
            "poster_path": "/poster.jpg",
            "overview": "A blade runner must pursue and terminate replicants...",
        }

    def fake_search_tmdb(query, page=1): # searching movies by title
        return [
            {"tmdb_id": 78, "title": "Blade Runner", "year": "1982"},
            {"tmdb_id": 335984, "title": "Blade Runner 2049", "year": "2017"},
        ]

    def fake_discover_by_genres(genre_ids, page=1): # discovering movies by genre ids
        return [
            {"tmdb_id": 12345, "title": "Suggested Sci-Fi", "year": "2001"},
            {"tmdb_id": 67890, "title": "Another Pick", "year": "1997"},
        ]

    monkeypatch.setattr(mapi, "get_tmdb_movie", fake_get_tmdb_movie)
    monkeypatch.setattr(mapi, "search_tmdb", fake_search_tmdb)
    monkeypatch.setattr(mapi, "discover_by_genres", fake_discover_by_genres)

    # enpoint tests

    # search tmdb
    r = client.get("/api/search/tmdb?q=blade%20runner")
    assert r.status_code == 200
    assert len(r.json["results"]) >= 2

    # add from tmdb (watched + high rating so it influences recs)
    r = client.post("/api/movies/from-tmdb",
                    json={"tmdb_id": 78, "watched": True, "personal_rating": 9})
    assert r.status_code == 201

    # list confirms one movie stored
    r = client.get("/api/movies")
    assert r.status_code == 200
    assert r.json["total"] == 1

        # recommendations should return something from fake_discover_by_genres
    r = client.get("/api/recommendations?min_rating=8&k=3")
    assert r.status_code == 200
    assert len(r.json.get("results", [])) >= 1


def test_bulk_from_tmdb_with_mocks(client, monkeypatch):
    import movie_api as mapi

    # Fake TMDB movie payloads keyed by id
    fake_db = {
        603: {  # The Matrix
            "id": 603,
            "title": "The Matrix",
            "release_date": "1999-03-31",
            "genres": [{"id": 878, "name": "Science Fiction"}, {"id": 28, "name": "Action"}],
            "poster_path": "/matrix.jpg",
            "overview": "A computer hacker learns about the true nature of reality."
        },
        78: {  # Blade Runner
            "id": 78,
            "title": "Blade Runner",
            "release_date": "1982-06-25",
            "genres": [{"id": 878, "name": "Science Fiction"}, {"id": 18, "name": "Drama"}],
            "poster_path": "/br.jpg",
            "overview": "Deckard hunts replicants."
        }
    }

    def fake_get_tmdb_movie(movie_id: int):  # mock function to get movie details by tmdb id
        if movie_id not in fake_db:
            raise RuntimeError("not found")
        return fake_db[movie_id]

    monkeypatch.setattr(mapi, "get_tmdb_movie", fake_get_tmdb_movie)  # patching the real function with the mock

    # first bulk call, creates both
    r = client.post("/api/movies/bulk/from-tmdb", json={
        "tmdb_ids": [603, 78],
        "watched": True,
        "personal_rating": 9
    })
    assert r.status_code == 200
    body = r.json
    assert body["summary"]["requested"] == 2
    assert body["summary"]["created"] == 2
    assert all(item["ok"] for item in body["results"])

    # verifying they exist
    r = client.get("/api/movies")
    assert r.status_code == 200
    assert r.json["total"] == 2

    # second bulk call with one duplicate and one unknown id
    r = client.post("/api/movies/bulk/from-tmdb", json={
        "tmdb_ids": [603, 999999]
    })
    assert r.status_code == 200
    results = r.json["results"]
    # one should be ok (duplicate, created False) and one should be error
    dup = next(x for x in results if x["tmdb_id"] == 603)
    fail = next(x for x in results if x["tmdb_id"] == 999999)
    assert dup["ok"] is True and dup["created"] is False
    assert fail["ok"] is False
