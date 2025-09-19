from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo

class LoginForm(FlaskForm):
    username = StringField('Gebruikersnaam', validators=[DataRequired()])
    password = PasswordField('Wachtwoord', validators=[DataRequired()])
    remember_me = BooleanField('Onthoud mij')
    submit = SubmitField('Inloggen')

class RegistrationForm(FlaskForm):
    username = StringField('Gebruikersnaam', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    naam = StringField('Volledige naam', validators=[DataRequired(), Length(min=2, max=100)])
    password = PasswordField('Wachtwoord', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Herhaal wachtwoord', 
                             validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registreer')