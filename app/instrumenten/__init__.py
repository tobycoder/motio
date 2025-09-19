from flask import Blueprint

bp = Blueprint('instrumenten', __name__)

from app.instrumenten import routes