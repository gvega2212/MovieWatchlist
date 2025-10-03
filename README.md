# MovieWatchlist

A Flask app created for tracking movies you’ve watched and want to watch, searching through TMDB, and getting simple recommendations. 
---

## Quick Start

### 1) Create & activate a virtual enviornment
 macOS/Linux

python3 -m venv .venv

source .venv/bin/activate

Windows PowerShell

.\.venv\Scripts\Activate.ps1

### 2) Install the dependencies
pip install -r requirements.txt

### 3) To run the app (app runs at http://127.0.0.1:5000)
python app.py

## Install pytest
pip install -U pip

pip install pytest pytest-cov  

### To run tests
pytest -q

pytest --cov=app_core --cov=movie_api --cov=models --cov-report=term-missing (with summary)


## Project Structure

```text
MovieWatchlist/
├─ app.py                      # Flask app and Blueprint
├─ models.py                   # SQLAlchemy models 
├─ movie_api.py                # TMDB integration 
├─ README.md                   # Project overview
├─ requirements.txt            # Python dependencies
├─ Makefile                    # Handy dev/test commands 
├─ seed.py                     # Data seeding script 
├─ .env                        # Local env vars 
├─ .gitignore
│
├─ app_core/                   # App code 
│  ├─ __init__.py              # Package marker
│  ├─ api.py                   # JSON API 
│  ├─ web.py                   # HTML pages 
│  └─ errors.py                # JSON error handlers + validators 
│
├─ templates/                  # Jinja templates for HTML UI
│  ├─ base.html                # Shared layout 
│  ├─ index.html               # My Watchlist
│  ├─ search.html              # TMDB search 
│  ├─ recommendations.html     # Recommendations page
│  ├─ edit_movie.html          # Edit form (web flow)
│  ├─ add_movie.html           # legacy add form
│  └─ login.html               # Username “login” (session-based)
│
├─ static/
│  └─ styles.css               # App styles and visuals
│
├─ instance/                   # Instance-specific files
│  └─ moviewatchlist.db        # SQLite database (dev)
│
└─ tests/
   ├─ test_api.py              # API + web integration tests
   └─ __pycache__/            








