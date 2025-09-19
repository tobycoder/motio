from flask import Blueprint

bp = Blueprint('gebruikers', __name__)

from app.gebruikers import routes