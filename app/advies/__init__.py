from flask import Blueprint

bp = Blueprint('advies', __name__)

from app.advies import routes