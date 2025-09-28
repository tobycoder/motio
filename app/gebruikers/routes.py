from flask import render_template, current_app, request, flash, redirect, url_for, abort
from app.models import User, Party, Notification
from app.gebruikers import bp
from flask_login import login_required, current_user
from app.auth.forms import RegistrationForm
from app import db, mail
from app.auth.forms import UserCreateForm
from flask_mail import Message
import secrets
from werkzeug.security import generate_password_hash
from app.auth.utils import user_has_role, roles_required, login_and_active_required
from sqlalchemy import func

@bp.route('/')
@login_and_active_required
@roles_required('griffie')
def index():
    users = User.query.all()
    return render_template('gebruikers/index.html', users=users, title="gebruikers")

@bp.route('/<int:user_id>/bekijken')
@login_and_active_required
@roles_required('griffie')
def bekijken(user_id):
    user =  User.query.get_or_404(user_id)
    return render_template('gebruikers/bekijken.html', user=user)

@bp.route('/<int:user_id>/bewerken', methods=['POST', 'GET'])
@login_and_active_required
@roles_required('griffie')
def bewerken(user_id):
    user = User.query.get_or_404(user_id)
    form = UserCreateForm(obj=user)
    
    if request.method == 'GET':
        form.partij.data = Party.query.get(user.partij_id) if user.partij_id else None

    if request.method == 'POST':
        user =  User.query.get_or_404(user_id)
        user.naam = form.naam.data
        user.email = form.email.data
        user.partij = form.partij.data
        user.role = form.role.data
        db.session.commit()
        flash("Gebruiker bijgewerkt", "success")
        return redirect(url_for('gebruikers.bekijken', user_id=user.id))
    
    return render_template('gebruikers/bewerken.html', form=form, user=user)

@bp.route('/<int:user_id>/verwijderen', methods=['POST', 'GET'])
@login_and_active_required
@roles_required('superadmin')
def verwijderen(user_id):
    
    if user_id == current_user.id:
        flash('Je kan niet jezelf verwijderen', 'danger')
        return redirect(url_for('gebruikers.index'))
    
    else:
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
    msg = Message(subject=subject,
                  recipients=[user.email])
    msg.body = (
        f"Hallo {user.naam},\n\n"
        f"Er is een account voor je aangemaakt. Klik op onderstaande link om je wachtwoord in te stellen:\n\n"
        f"{reset_url}\n\n"
        f"Let op: deze link verloopt na 60 minuten.\n\n"
        f"Met vriendelijke groet,\nDe griffie"
    )
    mail.send(msg)

@bp.route("/toevoegen", methods=["GET", "POST"])
@login_and_active_required
@roles_required("superadmin")
def toevoegen():
    form = UserCreateForm()

    if form.validate_on_submit():
        # 1) Maak user zonder dat superadmin wachtwoord kent
        #    -> zet een onbruikbaar random wachtwoord (model eist non-null)
        tmp_pw_hash = generate_password_hash(secrets.token_urlsafe(32))

        user = User(
            naam=form.naam.data.strip(),
            email=form.email.data.strip().lower(),
            role=form.role.data,
            password_hash=tmp_pw_hash,
        )

        # partij (QuerySelectField geeft Party instance of None)
        user.partij = form.partij.data

        db.session.add(user)
        db.session.commit()

        # 2) Stuur e-mail met resetlink zodat gebruiker zelf wachtwoord instelt
        try:
            send_password_setup_email(user)
            flash("Gebruiker aangemaakt. E-mail met wachtwoord-instellen is verzonden.", "success")
        except Exception as e:
            current_app.logger.exception("Fout bij verzenden e-mail")
            flash("Gebruiker is aangemaakt, maar e-mail verzenden mislukte. Stuur handmatig een resetlink.", "warning")

        # 3) Door naar overzicht (pas endpointnaam aan naar jouw overzicht)
        return redirect(url_for("gebruikers.index"))

    return render_template("gebruikers/toevoegen.html", form=form)

# Notificatie afdeling
@bp.route('/alles-lezen')
@login_and_active_required
def mark_all_read():
    q = Notification.query.filter(
        Notification.user_id == current_user.id,
        Notification.read_at.is_(None)
    )
    updated = q.update({Notification.read_at: func.now()}, synchronize_session=False)
    db.session.commit()

    # JSON-klant? -> JSON terug
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
        n.read_at = func.now()          # of: dt.datetime.utcnow()
        db.session.commit()

    # Bepaal waarheen we gaan
    target = request.args.get('next')
    if not target:
        # Slimme default: naar de motie, of anders naar home
        if n.motie_id:
            target = url_for('moties.bekijken', motie_id=n.motie_id)
        elif n.payload and n.payload.get('link'):
            target = n.payload['link']
        else:
            target = url_for('dashboard.home')

    return redirect(target)