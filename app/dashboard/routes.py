from flask import render_template, request, jsonify, url_for, current_app
from flask_login import login_required, current_user
from app.auth.utils import login_and_active_required
from app.dashboard import bp
from app.models import Motie, User, motie_medeindieners, MotieShare, Notification
from app import db
from sqlalchemy import func, or_, case, and_, cast, Float
from sqlalchemy.orm import selectinload
from datetime import datetime, date


def _moties_for_user_query(user):
    base = Motie.query.options(
        selectinload(Motie.mede_indieners),
        selectinload(Motie.indiener),
    )
    if getattr(user, 'has_role', None) and user.has_role('superadmin'):
        return base
    return base.filter(
        or_(
            Motie.indiener_id == user.id,
            Motie.mede_indieners.any(User.id == user.id),
        )
    )


def _normalize_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


@bp.route('/')
@login_and_active_required
def home():
    query = _moties_for_user_query(current_user)

    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    items = (
        query.order_by(Motie.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total = query.count()

    mmi = motie_medeindieners
    per_motie = (
        db.session.query(
            Motie.id.label("motie_id"),
            (
                case((Motie.indiener_id.isnot(None), 1), else_=0)
                + func.count(mmi.c.user_id)
            ).label("totaal_indieners"),
        )
        .outerjoin(mmi, mmi.c.motie_id == Motie.id)
        .group_by(Motie.id)
    ).subquery()

    avg_indieners = db.session.query(cast(func.avg(per_motie.c.totaal_indieners), Float)).scalar()
    latest = db.session.query(func.max(Motie.updated_at)).scalar()

    gedeeld_q = (
        db.session.query(Motie)
        .join(MotieShare, MotieShare.motie_id == Motie.id)
        .filter(
            MotieShare.actief.is_(True),
            or_(
                MotieShare.target_user_id == current_user.id,
                and_(
                    MotieShare.target_party_id.isnot(None),
                    MotieShare.target_party_id == current_user.partij_id,
                ),
            ),
            or_(
                MotieShare.expires_at.is_(None),
                MotieShare.expires_at > datetime.utcnow(),
            ),
        )
        .options(selectinload(Motie.indiener), selectinload(Motie.mede_indieners))
        .order_by(Motie.updated_at.desc())
        .distinct()
    )
    gedeeld_met_mij = gedeeld_q.limit(6).all()
    gedeeld_total = gedeeld_q.count()

    status_query = db.session.query(Motie.status, func.count(Motie.id))
    if not current_user.has_role('superadmin'):
        status_query = status_query.filter(
            or_(
                Motie.indiener_id == current_user.id,
                Motie.mede_indieners.any(User.id == current_user.id),
            )
        )
    status_counts = dict(status_query.group_by(Motie.status).all())

    notifications_recent = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    unread_notifications = Notification.query.filter_by(user_id=current_user.id, read_at=None).count()

    meeting_candidates = (
        query.filter(Motie.gemeenteraad_datum.isnot(None))
        .order_by(Motie.gemeenteraad_datum.asc())
        .limit(10)
        .all()
    )
    upcoming_meetings = []
    today = date.today()
    for motie in meeting_candidates:
        normalized = _normalize_date(motie.gemeenteraad_datum)
        if normalized and normalized >= today:
            upcoming_meetings.append((motie, normalized))
        if len(upcoming_meetings) >= 4:
            break

    recent_activity = (
        query.order_by(Motie.updated_at.desc())
        .limit(6)
        .all()
    )

    moties_index_shared_url = (
        url_for('moties.index_shared')
        if 'moties.index_shared' in current_app.view_functions
        else None
    )

    return render_template(
        'dashboard/index.html',
        title="Dashboard",
        avg_indieners=avg_indieners,
        latest=latest,
        total=total,
        per_page=per_page,
        page=page,
        gedeeld_total=gedeeld_total,
        gedeeld_met_mij=gedeeld_met_mij,
        items=items,
        status_counts=status_counts,
        notifications_recent=notifications_recent,
        unread_notifications=unread_notifications,
        upcoming_meetings=upcoming_meetings,
        recent_activity=recent_activity,
        moties_index_shared_url=moties_index_shared_url,
    )


@bp.route('/metrics/moties-per-status')
@login_and_active_required
def moties_per_status():
    status_counts = (
        db.session.query(Motie.status, func.count(Motie.id))
        .filter(
            or_(
                Motie.indiener_id == current_user.id,
                Motie.mede_indieners.any(User.id == current_user.id),
            )
        )
        .group_by(Motie.status)
        .all()
    )
    data = [
        {
            "status": status or "Onbekend",
            "count": count,
        }
        for status, count in status_counts
    ]
    return jsonify(data)


@bp.route('/metrics/collaborators')
@login_and_active_required
def collaborator_overview():
    mmi = motie_medeindieners
    rows = (
        db.session.query(User.naam, func.count(Motie.id).label('aantal'))
        .join(mmi, mmi.c.user_id == User.id)
        .join(Motie, Motie.id == mmi.c.motie_id)
        .filter(Motie.indiener_id == current_user.id)
        .group_by(User.naam)
        .order_by(func.count(Motie.id).desc())
        .limit(5)
        .all()
    )
    return jsonify([
        {"naam": naam, "aantal": aantal}
        for naam, aantal in rows
    ])
