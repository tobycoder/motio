from flask import Blueprint

bp = Blueprint('diag', __name__)

from app.diag import routes