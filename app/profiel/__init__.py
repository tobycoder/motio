from flask import Blueprint

bp = Blueprint('profiel', __name__)

from app.profiel import routes