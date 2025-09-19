from flask import Blueprint

bp = Blueprint('partijen', __name__)

from app.partijen import routes