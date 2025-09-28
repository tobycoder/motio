# app/auth/utils.py
from functools import wraps
from typing import Iterable
from flask import redirect, url_for, flash, abort, request
from flask_login import current_user, login_required, logout_user

# ---------------------------
# 1) Inlog + actief check
# ---------------------------
def login_and_active_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        # hier komen we pas als user.is_authenticated == True
        if not getattr(current_user, "is_active", True):
            logout_user()
            flash("Je account is gedeactiveerd. Neem contact op met de griffie.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return view(*args, **kwargs)
    return wrapped

# ---------------------------
# 2) Rol-helpers (géén current_user aanraken hier)
# ---------------------------
VALID_ROLES = {"gebruiker", "griffie", "superadmin"}

def has_role(user, roles: Iterable[str], allow_superadmin: bool = True) -> bool:
    """Pure helper op basis van een user-object (GEEN current_user hier)."""
    if not getattr(user, "is_authenticated", False):
        return False
    role = (getattr(user, "role", "") or "").lower()
    if allow_superadmin and role == "superadmin":
        return True
    wanted = {r.lower() for r in roles}
    return role in wanted

# ---------------------------
# 3) Decorators voor routes
# ---------------------------
def roles_required(*roles: str, redirect_endpoint: str | None = None, allow_superadmin: bool = True):
    """Toegang als user één van de gegeven rollen heeft (ANY). Superadmin mag standaard altijd."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            # Pas HIER naar current_user kijken (binnen request-context):
            if not getattr(current_user, "is_authenticated", False):
                return redirect(url_for("auth.login", next=request.url))
            if has_role(current_user, roles, allow_superadmin=allow_superadmin):
                return view(*args, **kwargs)
            flash("Je hebt geen toegang tot deze pagina.", "danger")
            if redirect_endpoint:
                return redirect(url_for(redirect_endpoint))
            return abort(403)
        return wrapped
    return decorator

# Alias zodat @user_has_role('griffie') blijft werken als DECORATOR:
def user_has_role(*roles: str, redirect_endpoint: str | None = None, allow_superadmin: bool = True):
    return roles_required(*roles, redirect_endpoint=redirect_endpoint, allow_superadmin=allow_superadmin)
