from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from flask import url_for
from sqlalchemy.types import TypeDecorator, Text
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

class JSONEncodedList(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value)
    def process_result_value(self, value, dialect):
        return json.loads(value) if value else []

# --- M2M-tabel: Motie ↔ User (mede-indieners)
motie_medeindieners = db.Table(
    "motie_medeindieners",
    db.Column("motie_id", db.Integer, db.ForeignKey("motie.id", ondelete="CASCADE"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.UniqueConstraint("motie_id", "user_id", name="uq_motie_user")
)

class User(UserMixin, db.Model):
    __tablename__ = "user"
    __table_args__ = {'quote': True} 
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    naam = db.Column(db.String(100), nullable=False)
    partij_id = db.Column(db.Integer, db.ForeignKey('party.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(120), default="gebruiker")
    profile_url = db.Column(db.String(512), nullable=True)
    profile_filename = db.Column(db.String(255), nullable=True, default='placeholder_profile.png')

    @property
    def profile_src(self):
        if self.profile_url:
            return self.profile_url
        if self.profile_filename:
            from flask import url_for
            return url_for('static', filename=f'img/users/{self.profile_filename}', _external=False)
        return None

    # Relaties
    partij = db.relationship('Party', backref='leden')

    # ✅ Moties waar deze user de primaire indiener van is
    ingediende_moties = db.relationship(
        'Motie',
        back_populates='indiener',
        foreign_keys='Motie.indiener_id'
    )

    # ✅ Moties waar deze user mede-indiener van is (M2M)
    mede_moties = db.relationship(
        'Motie',
        secondary=motie_medeindieners,
        back_populates='mede_indieners'
    )

    def generate_reset_token(self) -> str:
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps({'uid': self.id}, salt=current_app.config['SECURITY_PASSWORD_SALT'])

    @staticmethod
    def verify_reset_token(token: str, max_age: int = 3600):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, salt=current_app.config['SECURITY_PASSWORD_SALT'], max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        return User.query.get(data['uid'])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

    def has_role(self, *roles: str) -> bool:
        role = (self.role or "").lower()
        if role == "superadmin":
            return True
        wanted = {r.lower() for r in roles}
        return role in wanted
    
class Party(db.Model):
    __tablename__ = "party"

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False, unique=True)
    afkorting = db.Column(db.String(10), nullable=False, unique=True)
    actief = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    logo_url = db.Column(db.String(512), nullable=True)
    logo_filename = db.Column(db.String(255), nullable=True)

    @property
    def logo_src(self):
        if self.logo_url:
            return self.logo_url
        if self.logo_filename:
            from flask import url_for
            return url_for('static', filename=f'img/partijen/{self.logo_filename}', _external=False)
        return None

    def __repr__(self):
        return f'<Partij {self.naam}>'


# ⬇️ Voeg dit toe in je bestaande Motie-model (NIET dubbel definiëren).
#    Laat alle bestaande kolommen van Motie staan; voeg/aanpas alleen onderstaande relaties.

class Motie(db.Model):
    __tablename__ = "motie"
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    constaterende_dat = db.Column(JSONEncodedList)
    overwegende_dat = db.Column(JSONEncodedList)
    opdracht_formulering = db.Column(db.Text, nullable=False)
    draagt_college_op = db.Column(JSONEncodedList)
    status = db.Column(db.String(20), default='concept')
    gemeenteraad_datum = db.Column(db.String(40))
    agendapunt = db.Column(db.String(40))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ✅ Primaire indiener (1:N)
    indiener_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    indiener = db.relationship(
        'User',
        back_populates='ingediende_moties',
        foreign_keys=[indiener_id]
    )

    # ✅ Mede-indieners (M2M)
    mede_indieners = db.relationship(
        'User',
        secondary=motie_medeindieners,
        back_populates='mede_moties',
        order_by='User.naam'
    )

    def add_mede_indiener(self, user):
        if not self.mede_indieners.filter_by(id=user.id).first():
            self.mede_indieners.append(user)

    def remove_mede_indiener(self, user):
        if self.mede_indieners.filter_by(id=user.id).first():
            self.mede_indieners.remove(user)

    def __repr__(self):
        return f'<Motie {getattr(self, "titel", self.id)}>'



# -------------------------------------------------------
# Oude definitie van Motie (voor referentie; NIET dubbel definiëren)
# -------------------------------------------------------

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
    indiener_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, default=1)
    
    # Many-to-many relationship with parties
    #partijen = db.relationship('Party', secondary=motie_partijen, lazy='subquery', backref=db.backref('moties', lazy=True))
    
    def __repr__(self):
        return f'<Motie {self.titel}>'