from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

#table of association
movie_genre = db.Table(
    "movie_genre",
    db.Column("movie_id", db.Integer, db.ForeignKey("movie.id"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genre.id"), primary_key=True),
)

class Movie(db.Model): #movie model
    __tablename__ = "movie"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    year = db.Column(db.String(10))
    external_id = db.Column(db.String(64))     # TMDB id or IMDB id
    source = db.Column(db.String(16))          # "tmdb", "omdb"
    personal_rating = db.Column(db.Integer)    # 0–10 for personal rating
    watched = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    poster_path = db.Column(db.String(255), nullable=True)  
    overview    = db.Column(db.Text, nullable=True)         
    owner = db.Column(db.String(64), index=True)  #username row

    genres = db.relationship("Genre", secondary=movie_genre, lazy="joined") #many-to-many relationship with the genres

    def __repr__(self):
        return f"<Movie {self.id} {self.title!r}>" #rep of the movie object

class Genre(db.Model):
    __tablename__ = "genre"
    id = db.Column(db.Integer, primary_key=True)      # local id
    tmdb_id = db.Column(db.Integer, unique=True)      # TMDB genre id
    name = db.Column(db.String(64), nullable=False, unique=True)

    def __repr__(self):
        return f"<Genre {self.name}>"
