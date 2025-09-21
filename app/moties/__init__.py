from flask import Blueprint

bp = Blueprint('moties', __name__)

from app.moties import routes