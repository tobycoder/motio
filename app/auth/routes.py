from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from app.auth import bp
from app.auth.forms import LoginForm, RegistrationForm, ResetPassword, ResetPasswordStepTwo
from app.models import User
from app import db, mail
import uuid, os
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from io import BytesIO
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Message  

PROFILE_SIZE = 1024  # kies je eigen doelgrootte (bv. 256/512/1024)

def _center_square(img: Image.Image) -> Image.Image:
    """Snij het midden vierkant uit."""
    w, h = img.size
    if w == h:
        return img
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    right = left + side
    bottom = top + side
    return img.crop((left, top, right, bottom))

# Toegestane extensies voor profielfoto's
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

def _profile_folder():
    # /static/img/users
    return os.path.join(current_app.static_folder, "img", "users")

def _allowed_profile(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS

def _save_profile_file(file_storage, suggested_slug: str) -> str:
    os.makedirs(_profile_folder(), exist_ok=True)
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    base = secure_filename(suggested_slug) or uuid.uuid4().hex

    # Voor SVG en andere niet-raster formats: direct opslaan zonder Pillow
    if ext == "svg":
        filename = f"{base}-{uuid.uuid4().hex[:8]}.svg"
        path = os.path.join(_profile_folder(), filename)
        file_storage.save(path)
        return filename

    # Raster: open met Pillow en vierkant maken
    try:
        # Lees naar PIL en corrigeer oriëntatie
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        # Corrigeer EXIF rotatie en converteer naar RGB (weg met alpha voor JPG)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if img.mode == "P" else "RGB")

        # Vierkant croppen, dan resizen
        img = _center_square(img)
        img = img.resize((PROFILE_SIZE, PROFILE_SIZE), Image.LANCZOS)

        # Als de bron alpha had en je wilt transparantie bewaren, kies WEBP/PNG
        has_alpha = (img.mode == "RGBA")
        if has_alpha:
            out_ext = "webp"  # of "png" als je PNG verkiest
        else:
            # JPG is kleiner en overal ondersteund
            out_ext = "jpg"

        filename = f"{base}-{uuid.uuid4().hex[:8]}.{out_ext}"
        path = os.path.join(_profile_folder(), filename)

        # Opslaan met passende opties
        if out_ext == "jpg":
            # JPG kan geen alpha; converteer veilig naar RGB
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(path, format="JPEG", quality=88, optimize=True, progressive=True)
        elif out_ext == "webp":
            img.save(path, format="WEBP", quality=88, method=6)
        else:  # png
            img.save(path, format="PNG", optimize=True)

        return filename

    except Exception:
        # Fallback: als Pillow faalt, sla het bestand dan gewoon raw op
        filename = f"{base}-{uuid.uuid4().hex[:8]}.{ext}"
        path = os.path.join(_profile_folder(), filename)
        file_storage.stream.seek(0)
        file_storage.save(path)
        return filename

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))

    form = LoginForm()
    if form.validate_on_submit():
        email_norm = (form.email.data or "").strip().lower()
        user = User.query.filter_by(email=email_norm).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('dashboard.home')
            flash(f'Welkom terug, {user.naam}!', 'success')
            return redirect(next_page)
        flash('Ongeldige e-mail of wachtwoord', 'error')

    return render_template('auth/login.html', title='Inloggen', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    flash('Je bent uitgelogd', 'info')
    return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        email_norm = (form.email.data or "").strip().lower()
        if User.query.filter_by(email=email_norm).first():
            flash('Email is al in gebruik', 'error')
            return render_template('auth/register.html', title='Registreren', form=form)

        profile_url = (getattr(form, "profile_url", None).data or "").strip() if hasattr(form, "profile_url") else None
        profile_file = request.files.get('profile_file')

        user = User(
            email=email_norm,
            naam=(form.naam.data or "").strip(),
            partij_id=(form.partijen.data.id if getattr(form, "partijen", None) and form.partijen.data else None)
        )
        # Als je username-kolom nog verplicht is in je model:
        if hasattr(user, "username") and user.username is None:
            user.username = email_norm

        user.set_password(form.password.data)

        # Profiel-afbeelding opslaan (URL of upload)
        if profile_url:
            user.profile_url = profile_url
            user.profile_filename = None
        elif profile_file and getattr(profile_file, "filename", ""):
            if not _allowed_profile(profile_file.filename):
                flash("Bestandstype niet toegestaan. Gebruik png, jpg, jpeg, webp of svg.", "error")
                return render_template('auth/register.html', title='Registreren', form=form)
            try:
                filename = _save_profile_file(profile_file, suggested_slug=form.naam.data or "user")
            except Exception as e:
                current_app.logger.exception("Profielafbeelding opslaan mislukt")
                flash(f"Opslaan van profielafbeelding mislukt: {e}", "error")
                return render_template('auth/register.html', title='Registreren', form=form)
            user.profile_filename = filename
            user.profile_url = None  # we gebruiken lokaal bestand

        db.session.add(user)
        db.session.commit()

        flash('Registratie succesvol! Je kunt nu inloggen.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', title='Registreren', form=form)


def _send_reset_email(user):
    token = user.generate_reset_token()
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    msg = Message(
        subject="Wachtwoord resetten",
        recipients=[user.email],
        body=(
            f"Beste {user.naam},\n\n"
            f"Via onderstaande link kun je je wachtwoord resetten (1 uur geldig):\n"
            f"{reset_url}\n\n"
            f"Niet door jou aangevraagd? Negeer deze e-mail."
        ),
    )
    mail.send(msg)

@bp.route("/wachtwoord-vergeten", methods=["GET","POST"])
def forgot_password():
    form = ResetPassword()
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user:
            _send_reset_email(user)
        flash("Als dit e-mailadres bekend is, is er zo een e-mail verstuurd. Check ook je spam!", "info")
        return redirect(url_for("auth.forgot_password"))
    return render_template("auth/wachtwoord_vergeten.html", form=form)

@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.verify_reset_token(token)
    form = ResetPasswordStepTwo()  # 1 uur geldig standaard
    if not user:
        flash("Deze resetlink is ongeldig of verlopen. Vraag een nieuwe aan.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        pw1 = (request.form.get("password") or "").strip()
        pw2 = (request.form.get("confirm_password") or "").strip()

        if pw1 != pw2:
            flash("Wachtwoorden komen niet overeen.", "warning")
            return redirect(url_for("auth.reset_password", token=token))
        if len(pw1) < 8:
            flash("Gebruik minimaal 8 tekens.", "warning")
            return redirect(url_for("auth.reset_password", token=token))

        user.set_password(pw1)
        db.session.commit()
        flash("Je wachtwoord is aangepast. Je kunt nu inloggen.", "success")
        return redirect(url_for("auth.login"))  # pas aan als jouw login-endpoint anders heet

    # GET: toon formulier
    return render_template("auth/wachtwoord_resetten.html", token=token, user=user, form=form)