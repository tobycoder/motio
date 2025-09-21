from flask import Flask, render_template
from flask_login import login_required, current_user
from app.dashboard import bp
from app.models import Motie, Amendementen
from app import db
from sqlalchemy import func    


@bp.route('/')
def home():
    # pak per tabel de maximum(updated_at)
    a_max = db.session.query(func.max(Amendementen.updated_at)).scalar()
    m_max = db.session.query(func.max(Motie.updated_at)).scalar()

    # kies de nieuwste (kan None zijn als beide tabellen leeg zijn)
    if a_max is not None and m_max is not None:
        latest = max(a_max, m_max)
    else:
        latest = a_max or m_max  # één van beide of None
    return render_template('dashboard/index.html', title="Dashboard", latest=latest)