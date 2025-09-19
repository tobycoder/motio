from flask import Blueprint

bp = Blueprint('front', __name__)

from app.front import routes