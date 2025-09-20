from flask_wtf import Form, FlaskForm
from wtforms_alchemy import ModelForm
from app.models import Party

class PartyForm(ModelForm, FlaskForm):
    class Meta:
        model = Party