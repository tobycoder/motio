from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from sqlalchemy.types import TypeDecorator, Text
# Many-to-many table for motion-party relationships
motie_partijen = db.Table('motie_partijen',
    db.Column('motie_id', db.Integer, db.ForeignKey('motie.id'), primary_key=True),
    db.Column('partij_id', db.Integer, db.ForeignKey('party.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    naam = db.Column(db.String(100), nullable=False)
    partij_id = db.Column(db.Integer, db.ForeignKey('party.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    partij = db.relationship('Party', backref='leden')
    moties = db.relationship('Motie', backref='indiener', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Party(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False, unique=True)
    afkorting = db.Column(db.String(10), nullable=False, unique=True)
    actief = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    logo_url = db.Column(db.String(512), nullable=True)
    logo_filename = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<Party {self.naam}>'

    @property
    def logo_src(self):
        """Geeft een bruikbare <img src> terug (lokaal of extern)."""
        if self.logo_url:
            return self.logo_url
        if self.logo_filename:
            from flask import url_for
            return url_for('static', filename=f'img/partijen/{self.logo_filename}', _external=False)
        return None
    def __repr__(self):
        return f'<Partij {self.naam}>'




class JSONEncodedList(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value)
    def process_result_value(self, value, dialect):
        return json.loads(value) if value else []


class Motie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    constaterende_dat = db.Column(JSONEncodedList)
    overwegende_dat = db.Column(JSONEncodedList)
    opdracht_formulering = db.Column(db.Text, nullable=False)
    draagt_college_op = db.Column(JSONEncodedList)
    status = db.Column(db.String(20), default='concept')
    gemeenteraad_datum = db.Column(db.String(40), default='Gemeenteraad')
    agendapunt = db.Column(db.String(40), default='Agendapunt')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, default=1)
    
    # Many-to-many relationship with parties
    partijen = db.relationship('Party', secondary=motie_partijen, lazy='subquery', backref=db.backref('moties', lazy=True))
    
    def __repr__(self):
        return f'<Motie {self.titel}>'
    
class Amendementen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    constaterende_dat = db.Column(JSONEncodedList)
    overwegende_dat = db.Column(JSONEncodedList)
    opdracht_formulering = db.Column(db.Text, nullable=False)
    wijzigingen = db.Column(JSONEncodedList)
    status = db.Column(db.String(20), default='concept')
    gemeenteraad_datum = db.Column(db.String(40), default='Gemeenteraad')
    agendapunt = db.Column(db.String(40), default='Agendapunt')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, default=1)
    
    # Many-to-many relationship with parties
    #partijen = db.relationship('Party', secondary=motie_partijen, lazy='subquery', backref=db.backref('moties', lazy=True))
    
    def __repr__(self):
        return f'<Motie {self.titel}>'