from flask_wtf import FlaskForm
from wtforms import StringField, FileField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, Email, Optional, URL, ValidationError
from wtforms_sqlalchemy.fields import QuerySelectField
from flask_login import current_user
from app.auth.forms import all_party_query
from app.models import User

ROLE_CHOICES = [
    ('gebruiker', 'Gebruiker'),
    ('griffie', 'Griffie'),
    ('bestuursadviseur', 'Bestuursadviseur'),
    ('superadmin', 'Superadmin'),
]


class ProfileUpdateForm(FlaskForm):
    naam = StringField('Naam', validators=[DataRequired(), Length(max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email(), Length(max=120)])
    profile_url = StringField('Profielfoto URL', validators=[Optional(), URL(message='Voer een geldige URL in.')])
    profile_file = FileField('Upload profielfoto (png/jpg/jpeg/webp/svg)')
    partij = QuerySelectField(
        'Partij',
        query_factory=all_party_query,
        get_label='naam',
        allow_blank=True,
        blank_text='Geen partij',
    )
    role = SelectField('Rol', choices=ROLE_CHOICES, validators=[DataRequired()])
    submit = SubmitField('Opslaan')

    def __init__(self, user=None, allow_admin_fields=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user or current_user
        self.show_admin_fields = allow_admin_fields

        if allow_admin_fields:
            self.role.choices = ROLE_CHOICES
            if not self.is_submitted():
                if user and user.role:
                    self.role.data = user.role
                elif not self.role.data:
                    self.role.data = ROLE_CHOICES[0][0]

                if user:
                    self.partij.data = user.partij
        else:
            self._fields.pop('partij', None)
            self._fields.pop('role', None)
            self.partij = None
            self.role = None

    def validate_email(self, field):
        email_norm = (field.data or '').strip().lower()
        query = User.query.filter(User.email == email_norm)
        if self._user and self._user.id:
            query = query.filter(User.id != self._user.id)
        if query.first():
            raise ValidationError('Dit e-mailadres is al in gebruik.')
