from dotenv import load_dotenv
load_dotenv()

# motie_tool/__init__.py
from flask import Flask, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from .config import Config
from flask_mail import Mail, Message
import smtplib, logging
import re, difflib
from markupsafe import Markup

def _diff_html(a: str, b: str) -> str:
    # tokeniseer op woorden + spaties + leestekens
    token = re.compile(r'\w+|\s+|[^\w\s]', re.UNICODE)
    A = token.findall(a or '')
    B = token.findall(b or '')

    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B).get_opcodes():
        if op == 'equal':
            out.append(''.join(A[i1:i2]))
        elif op == 'delete':
            out.append(f'<del class="tc-del">{"".join(A[i1:i2])}</del>')
        elif op == 'insert':
            out.append(f'<ins class="tc-ins">{"".join(B[j1:j2])}</ins>')
        elif op == 'replace':
            out.append(f'<del class="tc-del">{"".join(A[i1:i2])}</del><ins class="tc-ins">{"".join(B[j1:j2])}</ins>')
    return ''.join(out)

def register_filters(app):
    @app.template_filter('trackdiff')
    def trackdiff_filter(original: str, edited: str):
        return Markup(_diff_html(original or '', edited or ''))


# Initialiseer extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
PUBLIC_ENDPOINTS = {
    "auth.login", "auth.register", "auth.logout",  # wat jij openbaar wilt
    "main.index",                                  # bijv. homepage
    "health.ping",                                 # healthcheck
    "static",                                      # nodig voor /static/*
}


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    register_filters(app)
    # Initialiseer extensions met app
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Log in om toegang te krijgen tot deze pagina.'
    
    mail.init_app(app)
    # Importeer models
    from .models import User, Party, Motie
    from .auth.utils import user_has_role
    
    # User loader voor Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @app.context_processor
    def inject_role_helpers():
        return dict(user_has_role=user_has_role)

    from flask_login import current_user
    from app.models import Notification  # jouw model import

    @app.context_processor
    def inject_notif_unread():
        if getattr(current_user, "is_authenticated", False):
            count = Notification.query.filter(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None)
            ).count()

            return {"notif_unread": count}
        return {"notif_unread": 0}
    
    @app.context_processor
    def inject_notifications():
        # Lazy import om cirkelimports te voorkomen
        from app.models import Notification

        if getattr(current_user, "is_authenticated", False):
            # laatste 10 voor het dropdownlijstje
            notifs = (Notification.query
                    .filter(Notification.user_id == current_user.id)
                    .order_by(Notification.created_at.desc())
                    .limit(10)
                    .all())
            # totaal ongelezen voor het rode bolletje/badge
            unread = (Notification.query
                    .filter(Notification.user_id == current_user.id,
                            Notification.read_at.is_(None))
                    .count())
            return {"notifications": notifs, "notif_unread": unread}
        return {"notifications": [], "notif_unread": 0}
    
    with app.app_context():
        url = db.engine.url
        try:
            safe_url = url.set(password="***")   # SQLAlchemy 1.4+/2.0
        except Exception:
            safe_url = url
        app.logger.info(f"DB connected: {safe_url}")
    # Registreer blueprints
    from .moties import bp as moties_bp
    app.register_blueprint(moties_bp, url_prefix='/moties')

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .advies import bp as advies_bp
    app.register_blueprint(advies_bp, url_prefix='/advies')

    from .gebruikers import bp as gebruikers_bp
    app.register_blueprint(gebruikers_bp, url_prefix='/gebruikers')

    from .partijen import bp as partijen_bp
    app.register_blueprint(partijen_bp, url_prefix='/partijen')

    from .profiel import bp as profielen_bp
    app.register_blueprint(profielen_bp, url_prefix='/profiel')

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    from .settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix='/instellingen')
    
    from .diag import bp as diag_bp
    app.register_blueprint(diag_bp, url_prefix='/diag')

    return app

# Voor backwards compatibility
app = create_app()

