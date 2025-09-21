from flask import Blueprint

bp = Blueprint('amendementen', __name__)

from app.amendementen import routes