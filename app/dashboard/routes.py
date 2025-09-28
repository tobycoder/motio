from flask import Flask, render_template, request
from flask_login import login_required, current_user
from app.auth.utils import login_and_active_required
from app.dashboard import bp
from app.models import Motie, User, motie_medeindieners, MotieShare
from app import db
from sqlalchemy import func, or_,  case, and_, cast, Float
from sqlalchemy.orm import selectinload    
from datetime import datetime

@bp.route('/')
@login_and_active_required
def home():
    # pak per tabel de maximum(updated_at)
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
    latest = m_max

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

    gedeeld_q = (
        db.session.query(Motie)
        .join(MotieShare, MotieShare.motie_id == Motie.id)
        .filter(
            MotieShare.actief.is_(True),
            or_(
                MotieShare.target_user_id == current_user.id,
                and_(
                    MotieShare.target_party_id.isnot(None),
                    MotieShare.target_party_id == current_user.partij_id
                )
            ),
            or_(
                MotieShare.expires_at.is_(None),
                MotieShare.expires_at > datetime.now()
            )
        )
        .options(
            selectinload(Motie.indiener),
            selectinload(Motie.mede_indieners)
        )
        .order_by(Motie.updated_at.desc())
        .distinct()
    )
    gedeeld_met_mij = gedeeld_q.all()
    gedeeld_total = gedeeld_q.count()

    return render_template('dashboard/index.html', 
                           title="Dashboard", 
                           avg_indieners=avg_indieners, 
                           latest=latest, 
                           total=total, 
                           per_page=per_page, 
                           page=page, 
                           gedeeld_total=gedeeld_total,
                           gedeeld_met_mij=gedeeld_met_mij,
                           items=items
                           )