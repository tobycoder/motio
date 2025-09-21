from flask_wtf import Form, FlaskForm
from wtforms_alchemy import ModelForm
from app.models import Motie

class MotieForm(ModelForm, FlaskForm):
    class Meta:
        model = Motie