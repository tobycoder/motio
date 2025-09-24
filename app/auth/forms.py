from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FileField, BooleanField, SubmitField, ValidationError
from wtforms.validators import DataRequired, Length, Email, EqualTo
from wtforms_sqlalchemy.fields import QuerySelectField
from app.models import Party, User

def party_query():
    return Party.query.filter_by(actief=1).order_by(Party.naam.asc())
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Wachtwoord', validators=[DataRequired()])
    remember_me = BooleanField('Onthoud mij')
    submit = SubmitField('Inloggen')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    naam = StringField('Volledige naam', validators=[DataRequired(), Length(min=2, max=100)])
    password = PasswordField('Wachtwoord', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Herhaal wachtwoord', 
                             validators=[DataRequired(), EqualTo('password')])
    partijen = QuerySelectField('Partij',
                                query_factory=party_query, 
                                get_label='naam', 
                                allow_blank=True,
                                blank_text='Geen partij'
                                )
    profile_file = FileField('Profielfoto (optioneel, png/jpg/jpeg/webp/svg)')
    profile_url = StringField('Profielfoto URL (optioneel)')
    def validate_email(self, field):
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("Dit e-mailadres is al in gebruik.")

class ResetPassword(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
class ResetPasswordStepTwo(FlaskForm):
    password = PasswordField('Wachtwoord', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Herhaal wachtwoord', 
                             validators=[DataRequired(), EqualTo('password')])