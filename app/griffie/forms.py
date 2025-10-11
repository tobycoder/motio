from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class SpeakingTimeForm(FlaskForm):
    committee = SelectField("Commissie", validators=[DataRequired()])
    meeting_date = DateField(
        "Vergaderdatum",
        validators=[DataRequired()],
        format="%Y-%m-%d",
        default=date.today,
    )
    total_minutes = IntegerField(
        "Bruto spreektijd (minuten)",
        validators=[DataRequired(), NumberRange(min=1, max=720)],
        default=180,
    )
    chair_minutes = IntegerField(
        "Voorzitterstijd (minuten)",
        validators=[DataRequired(), NumberRange(min=0, max=240)],
        default=27,
    )
    speakers_count = IntegerField(
        "Aantal insprekers",
        validators=[NumberRange(min=0, max=50)],
        default=0,
    )
    pause_minutes = IntegerField(
        "Pauze (minuten)",
        validators=[NumberRange(min=0, max=120)],
        default=0,
    )
    college_minutes = IntegerField(
        "Spreektijd college (minuten)",
        validators=[DataRequired(), NumberRange(min=0, max=180)],
        default=30,
    )
    speaker_slot_minutes = IntegerField(
        "Minuten per inspreker",
        validators=[DataRequired(), NumberRange(min=1, max=30)],
        default=5,
    )
    preview = SubmitField("Voorbeeld berekenen")
    export_pdf = SubmitField("Download PDF")
