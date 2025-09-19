from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.auth import bp
from app.auth.forms import LoginForm, RegistrationForm
from app.models import User
from app import db

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('main.dashboard')
            flash(f'Welkom terug, {user.naam}!', 'success')
            return redirect(next_page)
        flash('Ongeldige gebruikersnaam of wachtwoord', 'error')
    return render_template('auth/login.html', title='Inloggen', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    flash('Je bent uitgelogd', 'info')
    return redirect(url_for('main.index'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if username already exists
        if User.query.filter_by(username=form.username.data).first():
            flash('Gebruikersnaam is al in gebruik', 'error')
            return render_template('auth/register.html', title='Registreren', form=form)
        
        # Check if email already exists
        if User.query.filter_by(email=form.email.data).first():
            flash('Email adres is al in gebruik', 'error')
            return render_template('auth/register.html', title='Registreren', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            naam=form.naam.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash('Registratie succesvol! Je kunt nu inloggen.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', title='Registreren', form=form)
