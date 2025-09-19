#just using this to load sample data into the db
from app import app
from models import db, Movie

with app.app_context():
    db.drop_all(); db.create_all()
    rows = [
        Movie(title="The Matrix", year="1999", personal_rating=9, watched=True),
        Movie(title="Inception", year="2010", personal_rating=8, watched=True),
        Movie(title="Dune: Part One", year="2021", personal_rating=None, watched=False),
    ]
    db.session.add_all(rows)
    db.session.commit()
    print("Seeded:", Movie.query.count())
