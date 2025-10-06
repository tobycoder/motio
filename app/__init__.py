from dotenv import load_dotenv
load_dotenv()

from flask import Flask, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import resend
from resend.exceptions import ResendError
from .config import Config
import re
import difflib
from markupsafe import Markup


def _diff_html(a: str, b: str) -> str:
    token = re.compile(r"\w+|\s+|[^\w\s]", re.UNICODE)
    A = token.findall(a or "")
    B = token.findall(b or "")

    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B).get_opcodes():
        if op == "equal":
            out.append("".join(A[i1:i2]))
        elif op == "delete":
            out.append(f"<del class=\"tc-del\">{''.join(A[i1:i2])}</del>")
        elif op == "insert":
            out.append(f"<ins class=\"tc-ins\">{''.join(B[j1:j2])}</ins>")
        elif op == "replace":
            out.append(
                f"<del class=\"tc-del\">{''.join(A[i1:i2])}</del><ins class=\"tc-ins\">{''.join(B[j1:j2])}</ins>"
            )
    return "".join(out)


def register_filters(app):
    @app.template_filter("trackdiff")
    def trackdiff_filter(original: str, edited: str):
        return Markup(_diff_html(original or "", edited or ""))


db = SQLAlchemy()
login_manager = LoginManager()
PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.register",
    "auth.logout",
    "main.index",
    "health.ping",
    "static",
}


def _ensure_resend_client():
    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        return False
    if resend.api_key != api_key:
        resend.api_key = api_key
    return True


def send_email(*, subject: str, recipients, text_body: str, html_body: str | None = None) -> bool:
    if not _ensure_resend_client():
        current_app.logger.warning("Resend niet geconfigureerd; mail '%s' niet verstuurd", subject)
        return False

    from_address = current_app.config.get("RESEND_DEFAULT_FROM")
    if not from_address:
        current_app.logger.warning("RESEND_DEFAULT_FROM ontbreekt; mail '%s' niet verstuurd", subject)
        return False

    to_list = recipients if isinstance(recipients, (list, tuple, set)) else [recipients]
    payload = {
        "from": from_address,
        "to": list(to_list),
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body

    try:
        resend.Emails.send(payload)
        return True
    except ResendError as exc:  # pragma: no cover
        current_app.logger.error("ResendError bij versturen mail '%s': %s", subject, exc, exc_info=True)
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Onbekende mailfout bij '%s': %s", subject, exc)
    return False


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    register_filters(app)

    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Log in om toegang te krijgen tot deze pagina."

    if app.config.get("RESEND_API_KEY"):
        resend.api_key = app.config["RESEND_API_KEY"]
    else:  # pragma: no cover
        app.logger.warning("RESEND_API_KEY ontbreekt; e-mails worden niet verstuurd")

    from .models import User  # noqa: F401
    from .auth.utils import has_role
    from flask_login import current_user
    from app.models import Notification

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_role_helpers():
        def current_user_has_role(*roles: str, allow_superadmin: bool = True) -> bool:
            return has_role(current_user, roles, allow_superadmin=allow_superadmin)

        return {"user_has_role": current_user_has_role}

    @app.context_processor
    def inject_notif_unread():
        if getattr(current_user, "is_authenticated", False):
            count = Notification.query.filter(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None),
            ).count()
            return {"notif_unread": count}
        return {"notif_unread": 0}

    @app.context_processor
    def inject_notifications():
        from app.models import Notification as NotificationModel

        if getattr(current_user, "is_authenticated", False):
            notifs = (
                NotificationModel.query
                .filter(NotificationModel.user_id == current_user.id)
                .order_by(NotificationModel.created_at.desc())
                .limit(10)
                .all()
            )
            unread = (
                NotificationModel.query
                .filter(
                    NotificationModel.user_id == current_user.id,
                    NotificationModel.read_at.is_(None),
                )
                .count()
            )
            return {"notifications": notifs, "notif_unread": unread}
        return {"notifications": [], "notif_unread": 0}

    with app.app_context():
        url = db.engine.url
        try:
            safe_url = url.set(password="***")
        except Exception:
            safe_url = url
        app.logger.info(f"DB connected: {safe_url}")

    from .moties import bp as moties_bp
    app.register_blueprint(moties_bp, url_prefix="/moties")

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from .griffie import bp as griffie_bp
    app.register_blueprint(griffie_bp, url_prefix="/griffie")

    from .gebruikers import bp as gebruikers_bp
    app.register_blueprint(gebruikers_bp, url_prefix="/gebruikers")

    from .partijen import bp as partijen_bp
    app.register_blueprint(partijen_bp, url_prefix="/partijen")

    from .profiel import bp as profielen_bp
    app.register_blueprint(profielen_bp, url_prefix="/profiel")

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    from .settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix="/instellingen")

    from .diag import bp as diag_bp
    app.register_blueprint(diag_bp, url_prefix="/diag")

    return app


app = create_app()
