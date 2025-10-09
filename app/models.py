from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from flask import url_for
from sqlalchemy.types import TypeDecorator, Text
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.dialects.postgresql import JSONB  # of JSON als je SQLite gebruikt

class JSONEncodedList(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value)
    def process_result_value(self, value, dialect):
        return json.loads(value) if value else []

class JSONEncodedDict(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None:
            return "{}"
        return json.dumps(value)
    def process_result_value(self, value, dialect):
        return json.loads(value) if value else {}

# ===============
# Multi‑tenant basis
# ===============

class Tenant(db.Model):
    __tablename__ = "tenant"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    naam = db.Column(db.String(120), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    settings = db.Column(JSONEncodedDict, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    domains = db.relationship("TenantDomain", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tenant {self.slug}>"


class TenantDomain(db.Model):
    __tablename__ = "tenant_domain"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    hostname = db.Column(db.String(255), unique=True, nullable=False, index=True)

    tenant = db.relationship("Tenant", back_populates="domains")

    def __repr__(self):
        return f"<TenantDomain {self.hostname} -> {self.tenant_id}>"

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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    naam = db.Column(db.String(100), nullable=False)
    partij_id = db.Column(db.Integer, db.ForeignKey('party.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(120), default="gebruiker")
    actief = db.Column(db.Boolean, default=True)    
    profile_url = db.Column(db.String(512), nullable=True)
    profile_filename = db.Column(db.String(255), nullable=True, default='placeholder_profile.png')
    tenant = db.relationship('Tenant')

    @property
    def profile_src(self):
        if self.profile_url:
            return self.profile_url
        if self.profile_filename:
            from flask import url_for
            return url_for('static', filename=f'img/users/{self.profile_filename}', _external=False)
        return None
    
    @property
    def is_active(self) -> bool:
        # Flask-Login leest dit in @login_required-flows
        return bool(self.actief)
    
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    naam = db.Column(db.String(100), nullable=False)
    afkorting = db.Column(db.String(10), nullable=False)
    actief = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    logo_url = db.Column(db.String(512), nullable=True)
    logo_filename = db.Column(db.String(255), nullable=True)
    tenant = db.relationship('Tenant')

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

class Motie(db.Model):
    __tablename__ = "motie"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    titel = db.Column(db.String(200), nullable=False)
    constaterende_dat = db.Column(JSONEncodedList)
    overwegende_dat = db.Column(JSONEncodedList)
    opdracht_formulering = db.Column(db.Text, nullable=False)
    draagt_college_op = db.Column(JSONEncodedList)
    status = db.Column(db.String(64), default='concept')
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

    tenant = db.relationship('Tenant')

    def add_mede_indiener(self, user):
        if not self.mede_indieners.filter_by(id=user.id).first():
            self.mede_indieners.append(user)

    def remove_mede_indiener(self, user):
        if self.mede_indieners.filter_by(id=user.id).first():
            self.mede_indieners.remove(user)

    def __repr__(self):
        return f'<Motie {getattr(self, "titel", self.id)}>'
    
    # Versiegeschiedenis relatie (nieuw)
    versions = db.relationship(
        'MotieVersion',
        back_populates='motie',
        cascade='all, delete-orphan',
        order_by=lambda: MotieVersion.created_at.desc()
    )

    def motie_to_editable_dict(m: 'Motie') -> dict:
        """Neem exact de velden mee die de griffie inhoudelijk mag aanpassen."""
        return {
            "titel": m.titel or "",
            # pas deze aan op jouw modelvelden:
            "constaterende_dat": [c.tekst for c in m.constaterende_dat] if hasattr(m, "constaterende_dat") else [],
            "overwegende_dat": [o.tekst for o in m.overwegende_dat] if hasattr(m, "overwegende_dat") else [],
            "draagt_college_op":    [d.tekst for d in m.draagt_college_op] if hasattr(m, "draagt_college_op") else [],
        }

class MotieVersion(db.Model):
    __tablename__ = 'motie_version'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    motie_id = db.Column(db.Integer, db.ForeignKey('motie.id', ondelete='CASCADE'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Volledige snapshot van relevante velden (JSON als tekst)
    snapshot = db.Column(JSONEncodedDict, nullable=False, default=dict)
    # Optioneel: lijst met veldnamen die gewijzigd zijn t.o.v. vorige snapshot
    changed_fields = db.Column(JSONEncodedList, nullable=False, default=list)

    motie = db.relationship('Motie', back_populates='versions')
    author = db.relationship('User')
    tenant = db.relationship('Tenant')

    def __repr__(self):
        return f"<MotieVersion motie={self.motie_id} id={self.id} at={self.created_at}>"

# === Dashboard layout (per user/rol) ===
class DashboardLayout(db.Model):
    __tablename__ = 'dashboard_layout'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    context = db.Column(db.String(50), nullable=False, index=True)  # bv. 'griffie'
    layout = db.Column(JSONEncodedDict, nullable=False, default=dict)  # {widgets: [...]} volgens front-end schema
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'context', name='uq_dashboard_user_context'),
    )

    user = db.relationship('User')
    tenant = db.relationship('Tenant')

    def __repr__(self):
        return f"<DashboardLayout user={self.user_id} ctx={self.context}>"

# === Delen van moties met partijen of personen (geen mede-indieners) ===
class MotieShare(db.Model):
    __tablename__ = "motie_share"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)

    # Doel-motie + afzender
    motie_id = db.Column(db.Integer, db.ForeignKey("motie.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)

    # Doelwit (exact één van beide invullen): óf persoon, óf partij
    target_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    target_party_id = db.Column(db.Integer, db.ForeignKey("party.id", ondelete="CASCADE"), nullable=True, index=True)

    # Rechten: alleen lezen | commentaar | voorstellen doen
    permission = db.Column(db.String(20), nullable=False, default="view")
    message = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    # Lifecycle
    actief = db.Column(db.Boolean, default=True, nullable=False)  # gebruik i.p.v. partial unique index
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Constraints & indexes (XOR + dubbele actieve shares voorkomen)
    __table_args__ = (
        db.CheckConstraint(
            "(target_user_id IS NOT NULL) <> (target_party_id IS NOT NULL)",
            name="ck_motieshare_target_xor"
        ),
        db.CheckConstraint(
            "permission IN ('view','comment','suggest', 'edit')",
            name="ck_motieshare_permission"
        ),
        db.UniqueConstraint("motie_id", "target_user_id", "actief", name="uq_share_user_active"),
        db.UniqueConstraint("motie_id", "target_party_id", "actief", name="uq_share_party_active"),
    )

    # Relaties
    motie = db.relationship("Motie", backref=db.backref("shares", cascade="all, delete-orphan"))
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    target_user = db.relationship("User", foreign_keys=[target_user_id])
    target_party = db.relationship("Party", foreign_keys=[target_party_id])
    tenant = db.relationship('Tenant')

    def revoke(self):
        """Maak share inactief (intrekken)."""
        if self.actief:
            self.actief = False
            self.revoked_at = datetime.utcnow()

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= datetime.utcnow())

    def __repr__(self):
        tgt = f"user={self.target_user_id}" if self.target_user_id else f"party={self.target_party_id}"
        return f"<MotieShare motie={self.motie_id} {tgt} perm={self.permission} actief={self.actief}>"

# === Notificaties / inbox ===
class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # Handig voor joins/filters in de UI
    motie_id = db.Column(db.Integer, db.ForeignKey("motie.id", ondelete="CASCADE"), nullable=True, index=True)
    share_id = db.Column(db.Integer, db.ForeignKey("motie_share.id", ondelete="CASCADE"), nullable=True, index=True)

    type = db.Column(db.String(50), nullable=False)        # bv. 'share_received'
    payload = db.Column(JSONEncodedDict, nullable=False)   # {titel, permission, message, afzender_naam, ...}

    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("notifications", cascade="all, delete-orphan"))
    motie = db.relationship("Motie")
    share = db.relationship("MotieShare")
    tenant = db.relationship('Tenant')

    def mark_read(self):
        if self.read_at is None:
            self.read_at = datetime.utcnow()

    def __repr__(self):
        return f"<Notification user={self.user_id} type={self.type} motie={self.motie_id}>"

class AdviceSession(db.Model):
    __tablename__ = 'advice_session'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=True, index=True)
    motie_id = db.Column(db.Integer, db.ForeignKey('motie.id'), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(30), default='requested')
    draft = db.Column(db.JSON, nullable=False)     # ← gewoon JSON, geen db.engine check!
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    returned_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    tenant = db.relationship('Tenant')
