from flask import render_template, request, redirect, url_for, flash, g, abort
from flask_login import current_user
from app.settings import bp
from app.auth.utils import login_and_active_required
from app import db
from app.griffie.routes import APPLICATION_REGISTRY
from app.models import Tenant

MANAGEABLE_ROLES = ["griffie", "bestuursadviseur", "gebruiker"]
GLOBAL_TENANT_SLUG = "__global__"


def _resolve_settings_target():
    tenant = getattr(g, "tenant", None)
    if tenant is not None:
        return tenant, False
    fallback = Tenant.query.filter(Tenant.slug == GLOBAL_TENANT_SLUG).first()
    if fallback is None:
        fallback = Tenant(slug=GLOBAL_TENANT_SLUG, naam="Globale instellingen", actief=True, settings={})
        db.session.add(fallback)
        db.session.commit()
    return fallback, True


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
        db.session.commit()
        flash("Toegang tot toepassingen bijgewerkt.", "success")
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
