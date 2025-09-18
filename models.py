from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Movie(db.Model):
    __tablename__ = "movie" # explicit table name so we avoid potential conflicts
    id = db.Column(db.Integer, primary_key=True) # we are auto-incrementing primary key
    title = db.Column(db.String(255), nullable=False, index=True)
    year = db.Column(db.String(10))                
    external_id = db.Column(db.String(64))         # for ex, IMDb ID
    source = db.Column(db.String(16))              # 
    personal_rating = db.Column(db.Integer)        # 0–10
    watched = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Movie {self.id} {self.title!r}>"
