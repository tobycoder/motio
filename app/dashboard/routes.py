from flask import Flask, render_template, request
from flask_login import login_required, current_user
from app.dashboard import bp
from app.models import Motie, Amendementen, User, motie_medeindieners
from app import db
from sqlalchemy import func, or_,  case, cast, Float
from sqlalchemy.orm import selectinload    


@bp.route('/')
@login_required
def home():
    # pak per tabel de maximum(updated_at)
    a_max = db.session.query(func.max(Amendementen.updated_at)).scalar()
    m_max = db.session.query(func.max(Motie.updated_at)).scalar()
    mmi = motie_medeindieners  # je assoc. table

# totaal aantal indieners per motie = (1 als er een primaire indiener is, anders 0) + # mede-indieners
    per_motie = (
        db.session.query(
            Motie.id.label("motie_id"),
            (
                case((Motie.indiener_id.isnot(None), 1), else_=0)
                + func.count(mmi.c.user_id)
            ).label("totaal_indieners")
        )
        .outerjoin(mmi, mmi.c.motie_id == Motie.id)
        .group_by(Motie.id)
    ).subquery()

    avg_indieners = db.session.query(
        cast(func.avg(per_motie.c.totaal_indieners), Float)
    ).scalar()
    # kies de nieuwste (kan None zijn als beide tabellen leeg zijn)
    if a_max is not None and m_max is not None:
        latest = max(a_max, m_max)
    else:
        latest = a_max or m_max  # één van beide of None

    q = (
        Motie.query
        .options(
            selectinload(Motie.mede_indieners),   # eager load om N+1 te voorkomen
            selectinload(Motie.indiener),         # als je de primaire indiener toont
        )
        .filter(
            or_(
                Motie.indiener_id == current_user.id,
                Motie.mede_indieners.any(User.id == current_user.id),
            )
        )
        .order_by(Motie.created_at.desc())
    )

    # (optioneel) pagineren
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    items = q.offset((page-1)*per_page).limit(per_page).all()
    total = q.count()

    return render_template('dashboard/index.html', title="Dashboard", avg_indieners=avg_indieners, latest=latest, total=total, per_page=per_page, page=page, items=items)