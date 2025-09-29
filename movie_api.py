import os, requests

TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # geting from .env
TMDB_BASE = "https://api.themoviedb.org/3"  # base url for tmdb api

TMDB_TOKEN = os.getenv("TMDB_TOKEN")
HEADERS = {"Authorization": f"Bearer {TMDB_TOKEN}", "accept": "application/json"} if TMDB_TOKEN else {"accept": "application/json"}

def _get(path, **params):  # internal function to make get requests to tmdb
    if TMDB_TOKEN:
        r = requests.get(f"{TMDB_BASE}{path}", headers=HEADERS, params=params, timeout=15)
    else:
        if not TMDB_API_KEY:
            raise RuntimeError("TMDB_API_KEY missing in .env")
        params = {"api_key": TMDB_API_KEY, **params}
        r = requests.get(f"{TMDB_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def search_tmdb(query, page=1):  # searching movies by title
    data = _get("/search/movie", query=query, page=page, include_adult=False)
    items = []
    for m in data.get("results", []):
        items.append({
            "tmdb_id": m.get("id"),
            "title": m.get("title"),
            "year": (m.get("release_date") or "")[:4],
            "poster_path": m.get("poster_path") or m.get("backdrop_path"),
            "overview": m.get("overview"),
            "vote_average": m.get("vote_average"),
            "popularity": m.get("popularity"),
        })
    return items

def get_tmdb_movie(movie_id: int):  # getting movie details by tmdb id
    return _get(f"/movie/{movie_id}")

def get_tmdb_genres():  # getting list of all tmdb genres
    data = _get("/genre/movie/list")
    return data.get("genres", [])

def discover_by_genres(genre_ids, page=1):  # discovering movies by genre ids
    # genre_ids must be a list of TMDB genre IDs
    if not genre_ids:
        return []
    data = _get("/discover/movie", with_genres=",".join(map(str, genre_ids)), page=page, include_adult=False)
    res = []
    for m in data.get("results", []):
        res.append({
            "tmdb_id": m.get("id"),
            "title": m.get("title"),
            "year": (m.get("release_date") or "")[:4],
        })
    return res

def tmdb_poster_url(path: str | None, size: str = "w500") -> str | None:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"

#so there is a default/suggestions for movie discovery
def _map_results(data): # mapping tmdb results 
    items = []
    for m in data.get("results", []):
        items.append({
            "tmdb_id": m.get("id"),
            "title": m.get("title"),
            "year": (m.get("release_date") or "")[:4],
            "poster_path": m.get("poster_path") or m.get("backdrop_path"),
            "overview": m.get("overview"),
            "vote_average": m.get("vote_average"),
            "popularity": m.get("popularity"),
        })
    return items

def search_tmdb(query, page=1):  # searching movies by title
    data = _get("/search/movie", query=query, page=page, include_adult=False)
    return _map_results(data)

def trending_movies(page=1):
    data = _get("/trending/movie/day", page=page)
    return _map_results(data)

def top_rated_movies(page=1):
    data = _get("/movie/top_rated", page=page)
    return _map_results(data)

def popular_movies(page=1):
    data = _get("/movie/popular", page=page)
    return _map_results(data)

def now_playing_movies(page=1):
    data = _get("/movie/now_playing", page=page)
    return _map_results(data)

