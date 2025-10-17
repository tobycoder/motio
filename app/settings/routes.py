from flask import render_template, request, redirect, url_for, flash, g, abort
from flask_login import current_user
from app.settings import bp
from app.auth.utils import login_and_active_required
from app import db
from app.models import Tenant
from app.griffie.routes import APPLICATION_REGISTRY
from app.tenant_registry.client import LegacyTenant

MANAGEABLE_ROLES = ["griffie", "bestuursadviseur", "gebruiker"]


def _resolve_settings_target():
    tenant = getattr(g, "tenant", None)
    is_global = False
    if tenant is None:
        meta = getattr(g, "tenant_meta", None)
        if meta is not None:
            if isinstance(meta, LegacyTenant):
                tenant = meta
            else:
                try:
                    tenant = meta.as_legacy()
                except AttributeError:
                    tenant = meta
            g.tenant = tenant
        else:
            fallback = (
                Tenant.query.filter(Tenant.slug == "__global__").first()
                or Tenant.query.order_by(Tenant.id.asc()).first()
            )
            if fallback:
                tenant = fallback
                g.tenant = tenant
                is_global = True
    if tenant is not None:
        return tenant, is_global
    abort(404, "Tenant context ontbreekt")


@bp.route("/toepassingen", methods=["GET", "POST"])
@login_and_active_required
def application_access():
    if (current_user.email or "").lower() != "floris@florisdeboer.com":
        abort(403)
    tenant, is_global = _resolve_settings_target()
    settings = dict(tenant.settings or {})
    current_mapping = settings.get("application_roles") or {}

    if request.method == "POST":
        new_mapping = {}
        for app_def in APPLICATION_REGISTRY:
            field_name = f"roles_{app_def['slug']}"
            selected = request.form.getlist(field_name)
            filtered = [role for role in selected if role in MANAGEABLE_ROLES]
            new_mapping[app_def["slug"]] = filtered

        settings["application_roles"] = new_mapping
        tenant.settings = settings
        if hasattr(tenant, "_sa_instance_state"):
            db.session.commit()
            flash("Toegang tot toepassingen bijgewerkt.", "success")
        else:
            flash("Instellingen zijn bijgewerkt voor deze sessie. Persistente opslag via Admotio volgt nog.", "info")
        return redirect(url_for("settings.application_access"))

    registry_with_roles = []
    for app_def in APPLICATION_REGISTRY:
        assigned = current_mapping.get(app_def["slug"], app_def.get("default_roles", []))
        registry_with_roles.append(
            {
                "slug": app_def["slug"],
                "title": app_def["title"],
                "description": app_def["description"],
                "roles": MANAGEABLE_ROLES,
                "selected": assigned,
            }
        )

    return render_template(
        "settings/applications.html",
        applications=registry_with_roles,
        manageable_roles=MANAGEABLE_ROLES,
        title="Toegang tot toepassingen",
        uses_global=is_global,
    )
