from flask_login import current_user

VALID_ROLES = {"gebruiker", "raadslid", "griffie", "superadmin"}

def user_has_role(*roles: str) -> bool:
    """True als current_user ingelogd is en de juiste rol heeft.
    'superadmin' mag altijd alles."""
    if not current_user.is_authenticated:
        return False
    role = (current_user.role or "").lower()
    if role == "superadmin":
        return True
    wanted = {r.lower() for r in roles}
    return role in wanted

from functools import wraps
from flask import abort, redirect, url_for, request, flash
from flask_login import current_user

def roles_required(*roles, redirect_endpoint=None):
    """Laat toe als user één van de gegeven rollen heeft (ANY).
    superadmin heeft altijd toegang.
    - redirect_endpoint: optioneel endpoint om naartoe te sturen i.p.v. 403.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                # naar login met 'next'
                return redirect(url_for("auth.login", next=request.url))
            # gebruik de gedeelde check
            if current_user.has_role(*roles):
                return view(*args, **kwargs)
            flash("Je hebt geen toegang tot deze pagina.", "danger")
            if redirect_endpoint:
                return redirect(url_for(redirect_endpoint))
            return abort(403)
        return wrapped
    return decorator