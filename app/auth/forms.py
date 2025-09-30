from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    FileField,
    SelectField,
    BooleanField,
    SubmitField,
    ValidationError,
)
from wtforms.validators import DataRequired, Length, Email, EqualTo
from wtforms_sqlalchemy.fields import QuerySelectField
from app.models import Party, User


def active_party_query():
    """Return only active parties ordered by name."""
    return Party.query.filter_by(actief=True).order_by(Party.naam.asc())


def all_party_query():
    """Return all parties ordered by name."""
    return Party.query.order_by(Party.naam.asc())


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Wachtwoord', validators=[DataRequired()])
    remember_me = BooleanField('Onthoud mij')
    submit = SubmitField('Inloggen')


class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    naam = StringField('Volledige naam', validators=[DataRequired(), Length(min=2, max=100)])
    password = PasswordField('Wachtwoord', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        'Herhaal wachtwoord',
        validators=[DataRequired(), EqualTo('password')]
    )
    partijen = QuerySelectField(
        'Partij',
        query_factory=active_party_query,
        get_label='naam',
        allow_blank=True,
        blank_text='Geen partij'
    )
    role = SelectField(
        'Rol',
        choices=[('gebruiker', 'Gebruiker'),
                 ('griffie', 'Griffie'),
                 ('superadmin', 'Superadmin')],
        validators=[DataRequired()],
    )
    profile_file = FileField('Profielfoto (optioneel, png/jpg/jpeg/webp/svg)')
    profile_url = StringField('Profielfoto URL (optioneel)')

    def validate_email(self, field):
        exists = User.query.filter_by(email=field.data.strip().lower()).first()
        if exists:
            raise ValidationError('Dit e-mailadres is al in gebruik.')


class ResetPassword(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])


class ResetPasswordStepTwo(FlaskForm):
    password = PasswordField('Wachtwoord', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        'Herhaal wachtwoord',
        validators=[DataRequired(), EqualTo('password')]
    )


class UserCreateForm(FlaskForm):
    naam = StringField('Naam', validators=[DataRequired(), Length(max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email(), Length(max=120)])
    partij = QuerySelectField(
        'Partij',
        query_factory=all_party_query,
        get_label='naam',
        allow_blank=True,
        blank_text='Geen partij',
    )
    role = SelectField(
        'Rol',
        choices=[('gebruiker', 'Gebruiker'),
                 ('griffie', 'Griffie'),
                 ('superadmin', 'Superadmin')],
        validators=[DataRequired()],
    )
    submit = SubmitField('Gebruiker aanmaken')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError('Dit e-mailadres bestaat al.')
