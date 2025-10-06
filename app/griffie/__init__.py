from flask import Blueprint

bp = Blueprint('griffie', __name__)

from app.griffie import routes