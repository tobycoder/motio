from dotenv import load_dotenv
load_dotenv()

from flask import Flask, current_app, g, request
import os
from jinja2 import BaseLoader, FileSystemLoader, TemplateNotFound
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

    @app.context_processor
    def inject_griffie_counts():
        from app.models import Motie
        try:
            if hasattr(current_user, 'role') and (current_user.has_role('griffie') or current_user.has_role('superadmin')):
                advice_count = Motie.query.filter(Motie.status.ilike('Advies griffie')).count()
                submit_count = Motie.query.filter(Motie.status.ilike('Klaar om in te dienen')).count()
                return { 'griffie_advice_count': advice_count, 'griffie_submit_count': submit_count }
        except Exception:
            pass
        return { 'griffie_advice_count': 0, 'griffie_submit_count': 0 }

    with app.app_context():
        url = db.engine.url
        try:
            safe_url = url.set(password="***")
        except Exception:
            safe_url = url
        app.logger.info(f"DB connected: {safe_url}")

    # ====== Multi-tenant resolver (eerste aanzet) ======
    @app.before_request
    def _resolve_tenant():
        try:
            from app.models import TenantDomain  # imported lazily
            host = (request.host or '').split(':')[0].lower()
            td = TenantDomain.query.filter(TenantDomain.hostname.ilike(host)).first()
            g.tenant = td.tenant if td else None
        except Exception:
            g.tenant = None

    @app.context_processor
    def inject_tenant_context():
        tenant_name = None
        tenant_settings = {}
        tenant_slug = None
        try:
            if getattr(g, 'tenant', None):
                tenant_name = g.tenant.naam
                tenant_settings = g.tenant.settings or {}
                tenant_slug = getattr(g.tenant, 'slug', None)
        except Exception:
            pass
        if not tenant_name:
            # fallback naar configuratie
            tenant_name = current_app.config.get('GEMEENTE_NAAM') or 'Motio'
        return {
            'tenant': getattr(g, 'tenant', None),
            'tenant_name': tenant_name,
            'tenant_slug': tenant_slug,
            'tenant_settings': tenant_settings,
        }

    # ====== Tenant-aware Jinja loader (per-tenant template overrides) ======
    class TenantAwareLoader(BaseLoader):
        def __init__(self, fallback_loader):
            self.fallback_loader = fallback_loader

        def get_source(self, environment, template):
            try:
                slug = getattr(getattr(g, 'tenant', None), 'slug', None)
                if slug:
                    tenant_templates_dir = os.path.join(app.root_path, 'templates_tenants', slug)
                    if os.path.isdir(tenant_templates_dir):
                        tenant_loader = FileSystemLoader(tenant_templates_dir)
                        try:
                            return tenant_loader.get_source(environment, template)
                        except TemplateNotFound:
                            pass
            except Exception:
                # buiten request-context of bij fouten: val terug
                pass
            # Fallback naar standaard loader
            return self.fallback_loader.get_source(environment, template)

    # Wrap de bestaande loader zodat templates eerst in templates_tenants/<slug>/ gezocht worden
    app.jinja_loader = TenantAwareLoader(app.jinja_loader)

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

    # Admin (superadmin-only)
    from .admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    return app


app = create_app()

# ====== Multi-tenant: zet tenant_id automatisch op nieuwe records (voorbeeld) ======
from sqlalchemy import event
from flask import g

@event.listens_for(db.session, "before_flush")
def _mt_set_tenant(session, flush_context, instances):
    tenant = getattr(g, 'tenant', None)
    if not tenant:
        return
    for obj in session.new:
        if hasattr(obj, 'tenant_id') and getattr(obj, 'tenant_id', None) is None:
            try:
                obj.tenant_id = tenant.id
            except Exception:
                pass


@event.listens_for(db.session, "do_orm_execute")
def _mt_scope_queries(execute_state):
    """Voeg tenant filters toe aan SELECTs v    Dit is een voorzichtige, niet-destructieve eerste versie.
oor modellen met tenant_id.
    """
    from sqlalchemy.orm import with_loader_criteria
    if not execute_state.is_select:
        return
    tenant = getattr(g, 'tenant', None)
    if not tenant:
        return
    try:
        from app.models import (
            Motie, User, Party, MotieShare, Notification, AdviceSession, MotieVersion, DashboardLayout
        )
        for model in (Motie, User, Party, MotieShare, Notification, AdviceSession, MotieVersion, DashboardLayout):
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(model, lambda cls: cls.tenant_id == tenant.id, include_aliases=True)
            )
    except Exception:
        # In geval van import issues in vroege app lifecycle, stilletjes overslaan
        pass
