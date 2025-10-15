from flask import Flask, render_template, flash, redirect, url_for, request, abort, current_app
from app.partijen import bp
from app.models import Party
from app.partijen.forms import PartyForm    
from app import db
from werkzeug.utils import secure_filename
import uuid, os
from sqlalchemy import nullslast
from sqlalchemy.exc import IntegrityError
from app.models import User
from app.auth.utils import login_and_active_required, user_has_role
from flask_login import current_user


@bp.before_request
@login_and_active_required
def _partijen_role_guard():
    role = (getattr(current_user, "role", "") or "").lower()
    if role == "bestuursadviseur":
        abort(403)

ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

def _logo_folder():
    # -> .../static/img/partijen
    return os.path.join(current_app.static_folder, "img", "partijen")

def _allowed_logo(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS

def _save_logo_file(file_storage, suggested_slug: str) -> str:
    """Sla het bestand op in static/img/partijen en return bestandsnaam."""
    os.makedirs(_logo_folder(), exist_ok=True)
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    base = secure_filename(suggested_slug) or uuid.uuid4().hex
    filename = f"{base}-{uuid.uuid4().hex[:8]}.{ext}"
    path = os.path.join(_logo_folder(), filename)
    file_storage.save(path)
    return filename

@bp.route('/')
@login_and_active_required
def index():
    partijen = (
        Party.query.order_by(
            nullslast(Party.lijstnummer_volgende.asc()),
            Party.naam.asc(),
        ).all()
    )
    return render_template('partijen/index.html', partijen=partijen, title="Partijen")
    
@bp.route('/toevoegen', methods=['GET', 'POST'])
@login_and_active_required
@user_has_role('griffie')
def toevoegen():
    if request.method == 'POST':
        naam = (request.form.get("naam") or "").strip()
        afkorting = (request.form.get("afkorting") or "").strip()
        actief_raw = (request.form.get("actief") or "").lower()
        actief = actief_raw in {"on", "true", "1", "yes"}
        zetelaantal_raw = (request.form.get("zetelaantal") or "").strip()
        lijstnummer_raw = (request.form.get("lijstnummer_volgende") or "").strip()
        logo_url = (request.form.get("logo_url") or "").strip() or None
        file = request.files.get("logo_file")

        if not naam or not afkorting:
            flash("Naam en afkorting zijn verplicht.", "error")
            return abort(400)

        zetelaantal = None
        if zetelaantal_raw:
            try:
                zetelaantal = int(zetelaantal_raw)
            except ValueError:
                flash("Zetelaantal moet een geheel getal zijn.", "error")
                return abort(400)
            if zetelaantal < 0:
                flash("Zetelaantal kan niet negatief zijn.", "error")
                return abort(400)

        lijstnummer = None
        if lijstnummer_raw:
            try:
                lijstnummer = int(lijstnummer_raw)
            except ValueError:
                flash("Lijstnummer moet een geheel getal zijn.", "error")
                return abort(400)
            if lijstnummer < 0:
                flash("Lijstnummer kan niet negatief zijn.", "error")
                return abort(400)

        party = Party(
            naam=naam,
            afkorting=afkorting,
            actief=actief,
            zetelaantal=zetelaantal,
            lijstnummer_volgende=lijstnummer
        )

        # Logo via URL heeft voorrang; anders proberen we bestand te bewaren
        if logo_url:
            party.logo_url = logo_url
            party.logo_filename = None
        elif file and getattr(file, "filename", ""):
            if not _allowed_logo(file.filename):
                flash("Bestandstype niet toegestaan. Gebruik png, jpg, jpeg, webp of svg.", "error")
                return abort(400)
            try:
                filename = _save_logo_file(file, suggested_slug=afkorting or naam)
            except Exception as e:
                current_app.logger.exception("Logo opslaan mislukt")
                flash(f"Opslaan van logo mislukt: {e}", "error")
                return abort(500)
            party.logo_filename = filename
            party.logo_url = None  # we gebruiken lokaal bestand

        try:
            db.session.add(party)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Naam of afkorting is al in gebruik.", "error")
            return abort(409)

        return redirect(url_for('partijen.bekijken', partij_id=party.id))
    
    return render_template('partijen/toevoegen.html', title="Partij Toevoegen")

@bp.route('/<int:partij_id>/bekijken')
@login_and_active_required
@user_has_role('griffie')
def bekijken(partij_id):
    partij = Party.query.get_or_404(partij_id)
    list_gebruikers = User.query.filter(User.partij_id == partij.id).all()
    return render_template('partijen/bekijken.html', partij=partij, list_gebruikers=list_gebruikers, title=partij.naam)

@bp.route('/<int:partij_id>/verwijderen', methods=['POST'])
@login_and_active_required
@user_has_role('griffie')
def verwijderen(partij_id):
    partij = Party.query.get_or_404(partij_id)
    db.session.delete(partij)
    db.session.commit()
    flash(f"Partij '{partij.naam}' is verwijderd.", "success")
    return redirect(url_for('partijen.index'))

@bp.route('/<int:partij_id>/bewerken', methods=['GET', 'POST'])
@login_and_active_required
@user_has_role('griffie')
def bewerken(partij_id):
    partij = Party.query.get_or_404(partij_id)

    if request.method == 'POST':
        naam = (request.form.get('naam') or '').strip()
        afkorting = (request.form.get('afkorting') or '').strip()
        actief_raw = (request.form.get('actief') or '').lower()
        actief = actief_raw in {'on', 'true', '1', 'yes'}
        logo_url = (request.form.get('logo_url') or '').strip()
        remove_logo = (request.form.get('remove_logo') or '').lower() in {'on', 'true', '1', 'yes'}
        zetelaantal_raw = (request.form.get("zetelaantal") or "").strip()
        lijstnummer_raw = (request.form.get("lijstnummer_volgende") or "").strip()
        file = request.files.get('logo_file')

        if not naam or not afkorting:
            flash('Naam en afkorting zijn verplicht.', 'error')
            return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')

        zetelaantal = None
        if zetelaantal_raw:
            try:
                zetelaantal = int(zetelaantal_raw)
            except ValueError:
                flash('Zetelaantal moet een geheel getal zijn.', 'error')
                return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')
            if zetelaantal < 0:
                flash('Zetelaantal kan niet negatief zijn.', 'error')
                return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')

        lijstnummer = None
        if lijstnummer_raw:
            try:
                lijstnummer = int(lijstnummer_raw)
            except ValueError:
                flash('Lijstnummer moet een geheel getal zijn.', 'error')
                return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')
            if lijstnummer < 0:
                flash('Lijstnummer kan niet negatief zijn.', 'error')
                return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')

        partij.naam = naam
        partij.afkorting = afkorting
        partij.actief = actief
        partij.zetelaantal = zetelaantal
        partij.lijstnummer_volgende = lijstnummer

        if remove_logo:
            partij.logo_url = None
            partij.logo_filename = None
        elif logo_url:
            partij.logo_url = logo_url
            partij.logo_filename = None
        elif file and getattr(file, 'filename', ''):
            if not _allowed_logo(file.filename):
                flash('Bestandstype niet toegestaan. Gebruik png, jpg, jpeg, webp of svg.', 'error')
                return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')
            try:
                filename = _save_logo_file(file, suggested_slug=afkorting or naam)
            except Exception as e:
                current_app.logger.exception('Logo opslaan mislukt')
                flash(f'Opslaan van logo mislukt: {e}', 'error')
                return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')
            else:
                partij.logo_filename = filename
                partij.logo_url = None

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Naam of afkorting is al in gebruik.', 'error')
            return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')

        flash('Partij bijgewerkt.', 'success')
        return redirect(url_for('partijen.bekijken', partij_id=partij.id))

    return render_template('partijen/bewerken.html', partij=partij, title=f'Bewerk {partij.naam}')


