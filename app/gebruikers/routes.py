from flask import render_template, current_app, request, flash, redirect, url_for, abort
from app.models import User, Party, Notification
from app.gebruikers import bp
from flask_login import login_required, current_user
from app.auth.forms import RegistrationForm, UserCreateForm
from app.gebruikers.forms import ProfileUpdateForm
from app.auth.routes import _allowed_profile, _save_profile_file
from app import db, send_email
from app.email_utils import render_email
import secrets
from werkzeug.security import generate_password_hash
from app.auth.utils import user_has_role, roles_required, login_and_active_required
from sqlalchemy import func


@bp.before_request
@login_and_active_required
def _gebruikers_role_guard():
    role = (getattr(current_user, "role", "") or "").lower()
    if role == "bestuursadviseur":
        allowed = {
            "gebruikers.view_profiel",
            "gebruikers.edit_profiel",
            "gebruikers.settings",
            "gebruikers.email_settings",
            "gebruikers.mark_all_read",
        }
        if request.endpoint not in allowed:
            abort(403)


def _update_user_profile_from_form(user: User, form: ProfileUpdateForm, render_args: dict):
    new_name = (form.naam.data or '').strip()
    new_email = (form.email.data or '').strip().lower()

    profile_url = (form.profile_url.data or '').strip()
    profile_file = request.files.get('profile_file')

    new_profile_url = user.profile_url
    new_profile_filename = user.profile_filename

    if profile_url:
        new_profile_url = profile_url
        new_profile_filename = None
    elif profile_file and getattr(profile_file, 'filename', ''):
        if not _allowed_profile(profile_file.filename):
            flash('Bestandstype niet toegestaan. Gebruik png, jpg, jpeg, webp of svg.', 'warning')
            return render_template('gebruikers/profiel_bewerken.html', **render_args)
        try:
            filename = _save_profile_file(profile_file, suggested_slug=new_name or user.naam or 'user')
        except Exception:
            current_app.logger.exception('Opslaan van profielfoto mislukt')
            flash('Opslaan van profielfoto mislukt. Probeer het opnieuw met een andere afbeelding.', 'danger')
            return render_template('gebruikers/profiel_bewerken.html', **render_args)
        else:
            new_profile_filename = filename
            new_profile_url = None

    user.naam = new_name
    user.email = new_email
    user.profile_url = new_profile_url
    user.profile_filename = new_profile_filename
    return None

@bp.route('/')
@login_and_active_required
@roles_required('gebruiker')
def index_user():
    users = User.query.all()
    return render_template('gebruikers/collegas.html', users=users)

@bp.route('/beheer-overzicht')
@login_and_active_required
@roles_required('griffie')
def index():
    users = User.query.all()
    return render_template('gebruikers/index.html', users=users, title="gebruikers")


@bp.route('/<int:user_id>/bekijken')
@login_and_active_required
def bekijken(user_id):
    user = User.query.get_or_404(user_id)
    return render_template('gebruikers/profiel_bekijken.html', user=user)


@bp.route('/<int:user_id>/bewerken', methods=['GET', 'POST'])
@login_and_active_required
@roles_required('griffie')
def bewerken(user_id):
    user = User.query.get_or_404(user_id)
    form = ProfileUpdateForm(user=user, obj=user, allow_admin_fields=True)

    render_args = {
        'form': form,
        'user': user,
        'title': f'Gebruiker bewerken: {user.naam}',
        'subtitle': user.email,
        'cancel_url': url_for('gebruikers.bekijken', user_id=user.id),
    }

    if request.method == 'GET':
        if user.profile_url:
            form.profile_url.data = user.profile_url
        form.partij.data = user.partij
        form.role.data = user.role or 'gebruiker'

    if form.validate_on_submit():
        response = _update_user_profile_from_form(user, form, render_args)
        if response is not None:
            return response

        user.partij = form.partij.data
        user.role = form.role.data

        db.session.commit()
        flash('Gebruiker bijgewerkt.', 'success')
        return redirect(url_for('gebruikers.bekijken', user_id=user.id))

    return render_template('gebruikers/profiel_bewerken.html', **render_args)


@bp.route('/<int:user_id>/verwijderen', methods=['POST', 'GET'])
@login_and_active_required
@roles_required('superadmin')
def verwijderen(user_id):
    if user_id == current_user.id:
        flash('Je kan niet jezelf verwijderen', 'danger')
        return redirect(url_for('gebruikers.index'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()

    flash(f"Gebruiker '{user.naam}' is verwijderd.", "success")
    return redirect(url_for('gebruikers.index'))


def send_password_setup_email(user: User):
    """Stuur een e-mail met link naar jouw bestaande auth.reset_password route."""
    token = user.generate_reset_token()
    reset_url = url_for("auth.reset_password", token=token, _external=True)

    subject = "Stel je wachtwoord in"
    greeting = f"Hallo {user.naam}," if getattr(user, 'naam', None) else "Hallo,"
    intro = "Er is een account voor je aangemaakt. Gebruik de knop hieronder om je wachtwoord in te stellen."
    paragraphs = ["Let op: deze link verloopt na 60 minuten."]
    text_body, html_body = render_email(
        subject=subject,
        greeting=greeting,
        intro=intro,
        paragraphs=paragraphs,
        cta_label="Wachtwoord instellen",
        cta_url=reset_url,
        footer_lines=["Met vriendelijke groet,", "De griffie"],
    )
    send_email(subject=subject, recipients=user.email, text_body=text_body, html_body=html_body)


@bp.route("/toevoegen", methods=["GET", "POST"])
@login_and_active_required
@roles_required("superadmin")
def toevoegen():
    form = UserCreateForm()

    if form.validate_on_submit():
        tmp_pw_hash = generate_password_hash(secrets.token_urlsafe(32))

        user = User(
            naam=form.naam.data.strip(),
            email=form.email.data.strip().lower(),
            role=form.role.data,
            password_hash=tmp_pw_hash,
        )

        user.partij = form.partij.data

        db.session.add(user)
        db.session.commit()

        try:
            send_password_setup_email(user)
            flash("Gebruiker aangemaakt. E-mail met wachtwoord-instellen is verzonden.", "success")
        except Exception:
            current_app.logger.exception("Fout bij verzenden e-mail")
            flash(
                "Gebruiker is aangemaakt, maar e-mail verzenden mislukte. Stuur handmatig een resetlink.",
                "warning",
            )

        return redirect(url_for("gebruikers.index"))

    return render_template("gebruikers/toevoegen.html", form=form)


@bp.route('/alles-lezen')
@login_and_active_required
def mark_all_read():
    q = Notification.query.filter(
        Notification.user_id == current_user.id,
        Notification.read_at.is_(None)
    )
    updated = q.update({Notification.read_at: func.now()}, synchronize_session=False)
    db.session.commit()

    if request.accept_mimetypes.best == 'application/json' or request.is_json:
        return {"updated": updated}, 200

    flash(f"{updated} notificatie(s) gemarkeerd als gelezen.", "success")
    return redirect(request.referrer or "/")


@bp.get('/<int:notification_id>/open')
@login_and_active_required
def open(notification_id: int):
    n = Notification.query.get_or_404(notification_id)
    if n.user_id != current_user.id:
        abort(403)

    if n.read_at is None:
        n.read_at = func.now()
        db.session.commit()

    target = request.args.get('next')
    if not target:
        if n.motie_id:
            target = url_for('moties.bekijken', motie_id=n.motie_id)
        elif n.payload and n.payload.get('link'):
            target = n.payload['link']
        else:
            target = url_for('dashboard.home')

    return redirect(target)


@bp.route('/mijn-profiel')
@login_and_active_required
def view_profiel():
    user = User.query.get_or_404(current_user.id)
    return render_template('gebruikers/profiel_bekijken.html', user=user, title='Mijn profiel')


@bp.route('/instellingen')
@login_and_active_required
def settings():
    links = []
    # Dashboard
    try:
        links.append({
            'label': 'Mijn profiel bewerken',
            'href': url_for('gebruikers.edit_profiel')
        })
    except Exception:
        pass
    # Griffie dashboard
    from app.auth.utils import has_role
    if has_role(current_user, ['griffie', 'superadmin']):
        try:
            links.append({'label': 'Griffie dashboard', 'href': url_for('griffie.dashboard_view')})
            links.append({'label': 'Dashboard indelen (griffie)', 'href': url_for('griffie.dashboard_builder')})
        except Exception:
            pass
    try:
        links.append({'label': 'E-mailmeldingen', 'href': url_for('gebruikers.email_settings')})
    except Exception:
        pass
    if has_role(current_user, ['superadmin']):
        try:
            links.append({'label': 'Toegang tot toepassingen', 'href': url_for('settings.application_access')})
        except Exception:
            pass
    try:
        links.append({'label': 'Markeer alle notificaties als gelezen', 'href': url_for('gebruikers.mark_all_read')})
    except Exception:
        pass
    return render_template('gebruikers/instellingen.html', links=links, title='Instellingen')

@bp.route('/mijn-profiel/bewerken', methods=['GET', 'POST'])
@login_and_active_required
def edit_profiel():
    user = User.query.get_or_404(current_user.id)
    form = ProfileUpdateForm(user=user, obj=user)

    render_args = {
        'form': form,
        'user': user,
        'title': 'Profiel bewerken',
        'subtitle': 'Werk je persoonlijke gegevens bij.',
        'cancel_url': url_for('gebruikers.view_profiel'),
    }

    if form.validate_on_submit():
        response = _update_user_profile_from_form(user, form, render_args)
        if response is not None:
            return response

        db.session.commit()
        flash('Je profiel is bijgewerkt.', 'success')
        return redirect(url_for('gebruikers.view_profiel'))

    if request.method == 'GET' and user.profile_url:
        form.profile_url.data = user.profile_url

    return render_template('gebruikers/profiel_bewerken.html', **render_args)


@bp.route('/instellingen/email', methods=['GET', 'POST'])
@login_and_active_required
def email_settings():
    user = User.query.get_or_404(current_user.id)

    # Default: alles aan
    defaults = {
        'users.share_received': True,
        'users.coauthor_added': True,
        'users.advice_returned': True,
        'griffie.advice_requested': True,
        'griffie.advice_accepted': True,
        'griffie.share_received': True,
    }

    prefs = dict(defaults)
    try:
        stored = getattr(user, 'email_prefs', None) or {}
        if isinstance(stored, dict):
            prefs.update({k: bool(v) for k, v in stored.items()})
    except Exception:
        pass

    if request.method == 'POST':
        form_vals = request.form
        updated = {}
        for key in defaults.keys():
            # Checkboxes only present when checked
            form_key = f"pref__{key}"
            updated[key] = True if form_vals.get(form_key) == 'on' else False
        user.email_prefs = updated
        db.session.commit()
        flash('E-mailmeldingen opgeslagen.', 'success')
        return redirect(url_for('gebruikers.email_settings'))

    # Alleen griffieblok tonen voor griffie/superadmin
    from app.auth.utils import has_role
    show_griffie = has_role(current_user, ['griffie', 'superadmin'])

    return render_template(
        'gebruikers/instellingen_email.html',
        prefs=prefs,
        show_griffie=show_griffie,
        title='E-mailmeldingen'
    )
