from flask import Flask, render_template, flash, redirect, url_for, send_file, request, abort, make_response, jsonify, session
from app.moties.forms import MotieForm
from sqlalchemy import or_, asc, desc, and_, case, literal, func, union_all, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import label
from app.models import Motie, User, motie_medeindieners, MotieShare, Party, Notification, MotieVersion, AdviceSession
from app import db, send_email
import json
from app.moties import bp
from app.exporters.motie_docx import render_motie_to_docx_bytes
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import datetime as dt
from flask_login import current_user, login_required  
from app.auth.utils import login_and_active_required, roles_required 
from urllib.parse import urlparse
PERM_ORDER = {"view": 1, "comment": 2, "suggest": 3, "edit": 4}

# Helpers
def as_list(value):
    """Converteer DB-waarde naar list zonder te crashen."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    s = str(value).strip()
    if not s:
        return []
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # tolerante fallback voor oude data met enkele quotes
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            return []

def _unique_name(name: str, existing: set[str]) -> str:
    """Zorgt dat bestandsnamen uniek zijn binnen de zip."""
    if name not in existing:
        existing.add(name)
        return name
    base, ext = (name.rsplit(".", 1) + [""])[:2]
    ext = f".{ext}" if ext else ""
    i = 2
    while f"{base} ({i}){ext}" in existing:
        i += 1
    unique = f"{base} ({i}){ext}"
    existing.add(unique)
    return unique

def _shared_motions_for_user(user):
    """Geef dict: { motie_id: {'permission': 'view|comment|edit|suggest', 'share_ids': [..]} } met hoogste permissie."""
    if not user:
        return {}

    now = dt.datetime.utcnow()
    prio = PERM_ORDER  # {"view":1,"comment":2,"suggest":3,"edit":4}

    q = MotieShare.query.filter(
        MotieShare.actief.is_(True),
        or_(MotieShare.expires_at.is_(None), MotieShare.expires_at > now),
        or_(
            MotieShare.target_user_id == user.id,
            and_(literal(bool(user.partij_id)).is_(True),  # <-- veilig ivm Python int
                MotieShare.target_party_id == user.partij_id)
        )
    )

    result = {}
    for s in q.all():
        entry = result.setdefault(s.motie_id, {"permission": None, "share_ids": []})
        # kies hoogste permissie
        if entry["permission"] is None or prio.get(s.permission, 0) > prio.get(entry["permission"], 0):
            entry["permission"] = s.permission
        entry["share_ids"].append(s.id)
    return result

def _highest_share_permission_for(user, motie: Motie) -> str | None:
    shared = _shared_motions_for_user(user)
    entry = shared.get(motie.id)
    return entry["permission"] if entry else None

def user_can_view_motie(user, motie: Motie) -> bool:
    if user and user.has_role('superadmin'):
        return True
    # indiener of mede-indiener mag altijd bekijken
    if motie.indiener_id == user.id or any(u.id == user.id for u in motie.mede_indieners):
        return True
    perm = _highest_share_permission_for(user, motie)
    return perm in ("view", "comment", "suggest", "edit")

def user_can_view_history(user, motie: Motie) -> bool:
    """Zelfde als user_can_view_motie, maar de griffie mag versiegeschiedenis niet zien.
    Superadmin mag altijd."""
    if user and user.has_role('superadmin'):
        return True
    # Griffie uitgesloten van versiegeschiedenis
    if (getattr(user, 'role', '') or '').lower() == 'griffie':
        return False
    # Indiener of mede-indiener
    if motie.indiener_id == user.id or any(u.id == user.id for u in motie.mede_indieners):
        return True
    perm = _highest_share_permission_for(user, motie)
    return perm in ("view", "comment", "suggest", "edit")

def _motie_snapshot(m: Motie) -> dict:
    """Maak een compacte snapshot van velden die we willen versie-tracken."""
    try:
        mede_ids = [u.id for u in m.mede_indieners]
    except Exception:
        mede_ids = []
    return {
        "titel": m.titel or "",
        "constaterende_dat": as_list(m.constaterende_dat),
        "overwegende_dat": as_list(m.overwegende_dat),
        "draagt_college_op": as_list(m.draagt_college_op),
        "opdracht_formulering": m.opdracht_formulering or "",
        "status": m.status or "",
        "gemeenteraad_datum": m.gemeenteraad_datum or None,
        "agendapunt": m.agendapunt or None,
        "mede_indieners_ids": mede_ids,
    }

def _diff_changed_fields(prev: dict | None, curr: dict) -> list[str]:
    if not prev:
        return list(curr.keys())
    changed: list[str] = []
    for k in curr.keys():
        if prev.get(k) != curr.get(k):
            changed.append(k)
    return changed

def create_motie_version(motie: Motie, author: User | None):
    """Sla een MotieVersion op met snapshot en wijzigingenlijst."""
    snap = _motie_snapshot(motie)
    last = (
        MotieVersion.query
        .filter(MotieVersion.motie_id == motie.id)
        .order_by(MotieVersion.created_at.desc(), MotieVersion.id.desc())
        .first()
    )
    prev_snap = last.snapshot if last else None
    changed = _diff_changed_fields(prev_snap, snap)
    # Sla alleen op als het de eerste versie is of als er wijzigingen zijn
    if (last is None) or changed:
        ver = MotieVersion(
            motie_id=motie.id,
            author_id=(author.id if author else None),
            snapshot=snap,
            changed_fields=changed,
        )
        db.session.add(ver)

def user_can_edit_motie(user, motie: Motie) -> bool:
    # indiener of mede-indiener mag altijd bewerken (pas aan naar wens)
    if motie.indiener_id == user.id or any(u.id == user.id for u in motie.mede_indieners):
        return True
    return _highest_share_permission_for(user, motie) == "edit"

def _safe_back_url(default_endpoint="moties.index"):
    # 1) expliciet meegegeven ?next=
    next_qs = request.args.get("next")
    if next_qs:
        return next_qs

    # 2) wat we eerder in een index-view hebben vastgelegd
    if session.get("last_index_url"):
        return session["last_index_url"]

    # 3) veilige referrer (zelfde host)
    ref = request.referrer
    if ref:
        host = urlparse(request.host_url).netloc
        if host in urlparse(ref).netloc:
            return ref

    # 4) fallback
    return url_for(default_endpoint)

## Notificatie helpers
def _notify(user_id: int, motie: Motie, ntype: str, payload: dict, share: MotieShare | None = None):
    """Maak 1 Notification-record aan (nog niet committen)."""
    n = Notification(
        user_id=user_id,
        motie_id=motie.id if motie else None,
        share_id=share.id if share else None,
        type=ntype,
        payload=payload or {}
    )
    db.session.add(n)
    _send_notification_email(user_id, motie, ntype, payload or {})

def _send_notification_email(user_id: int, motie: Motie | None, ntype: str, payload: dict) -> None:
    user = User.query.get(user_id)
    if not user or not getattr(user, "email", None):
        return
    subject, body = _build_notification_email(user, motie, ntype, payload)
    if not subject or not body:
        return
    send_email(subject=subject, recipients=user.email, text_body=body)

def _build_notification_email(user: User, motie: Motie | None, ntype: str, payload: dict) -> tuple[str | None, str | None]:
    motie_id = motie.id if motie else payload.get("motie_id")
    if motie and getattr(motie, "titel", None):
        motie_title = motie.titel
    else:
        motie_title = payload.get("motie_titel") if payload else None
    if not motie_title and motie_id:
        motie_title = f"Motie #{motie_id}"
    if not motie_title:
        motie_title = "Motie"
    try:
        view_url = url_for("moties.bekijken", motie_id=motie_id, _external=True) if motie_id else None
    except RuntimeError:
        view_url = url_for("moties.bekijken", motie_id=motie_id) if motie_id else None
    greeting = f"Hallo {user.naam}," if getattr(user, "naam", None) else "Hallo,"
    if ntype == "share_received":
        afzender = payload.get("afzender_naam") if payload else None
        permission = payload.get("permission") if payload else None
        message = payload.get("message") if payload else None
        subject = f"Nieuwe motie gedeeld: {motie_title}"
        lines = [
            greeting,
            "",
            f"{afzender or 'Een collega'} heeft de motie '{motie_title}' met je gedeeld.",
        ]
        if permission:
            lines.append(f"Rechten: {permission}.")
        if message:
            lines.extend(["", "Bericht van de afzender:", message])
        if view_url:
            lines.extend(["", f"Bekijk de motie: {view_url}"])
        lines.extend(["", "Groeten,", "Motio"])
        return subject, "\n".join(lines)
    if ntype == "share_revoked":
        revoked_by = payload.get("revoked_by_naam") if payload else None
        subject = f"Toegang ingetrokken: {motie_title}"
        lines = [
            greeting,
            "",
            f"Je toegang tot '{motie_title}' is ingetrokken door {revoked_by or 'een collega'}.",
        ]
        lines.extend(["", "Groeten,", "Motio"])
        return subject, "\n".join(lines)
    if ntype == "coauthor_added":
        toegevoegd_door = payload.get("toegevoegd_door_naam") if payload else None
        subject = f"Toegevoegd als mede-indiener: {motie_title}"
        lines = [
            greeting,
            "",
            f"Je bent toegevoegd als mede-indiener voor '{motie_title}' door {toegevoegd_door or 'een collega'}.",
        ]
        if view_url:
            lines.extend(["", f"Bekijk de motie: {view_url}"])
        lines.extend(["", "Succes met het vervolg!", "Motio"])
        return subject, "\n".join(lines)
    subject = "Nieuwe notificatie in Motio"
    lines = [greeting, "", f"Je hebt een nieuwe notificatie van het type '{ntype}'."]
    if payload:
        lines.append("")
        lines.append("Details:")
        for key, value in payload.items():
            lines.append(f"- {key}: {value}")
    if view_url:
        lines.extend(["", f"Gerelateerde motie: {view_url}"])
    lines.extend(["", "Groeten,", "Motio"])
    return subject, "\n".join(lines)

# --- Griffie advies helpers ---
def _ensure_advice_session_for(motie: Motie, requested_by: User) -> AdviceSession:
    ses = (
        AdviceSession.query
        .filter(AdviceSession.motie_id == motie.id)
        .order_by(AdviceSession.created_at.desc())
        .first()
    )
    if ses and ses.status in ("requested", "in_progress"):
        return ses
    # nieuwe sessie met draft = huidige motie-snapshot
    ses = AdviceSession(
        motie_id=motie.id,
        requested_by_id=requested_by.id,
        reviewer_id=None,
        status='requested',
        draft=_motie_snapshot(motie),
    )
    db.session.add(ses)
    return ses

def _notify_advice_requested(motie: Motie, requested_by: User | None):
    # Notificeer alle griffie- en superadmin-gebruikers
    q = User.query.filter(User.actief.is_(True))
    recipients = [u for u in q.all() if u.has_role('griffie', 'superadmin')]
    payload = {
        "motie_id": motie.id,
        "motie_titel": motie.titel,
        "requested_by_id": requested_by.id if requested_by else None,
        "requested_by_naam": requested_by.naam if requested_by else None,
    }
    for u in recipients:
        _notify(u.id, motie, "advice_requested", payload, None)

def _notify_advice_returned(motie: Motie, reviewer: User | None):
    indiener_id = motie.indiener_id
    if not indiener_id:
        return
    payload = {
        "motie_id": motie.id,
        "motie_titel": motie.titel,
        "reviewer_id": reviewer.id if reviewer else None,
        "reviewer_naam": reviewer.naam if reviewer else None,
    }
    _notify(indiener_id, motie, "advice_returned", payload, None)

def _notify_advice_accepted(motie: Motie, accepted_by: User | None, session: AdviceSession | None):
    # Stuur vooral de reviewer een notificatie; zo niet, dan alle griffie/superadmin
    reviewer_id = getattr(session, 'reviewer_id', None) if session else None
    payload = {
        "motie_id": motie.id,
        "motie_titel": motie.titel,
        "accepted_by_id": accepted_by.id if accepted_by else None,
        "accepted_by_naam": accepted_by.naam if accepted_by else None,
    }
    if reviewer_id:
        _notify(reviewer_id, motie, "advice_accepted", payload, None)
    else:
        q = User.query.filter(User.actief.is_(True))
        for u in q.all():
            if u.has_role('griffie', 'superadmin'):
                _notify(u.id, motie, "advice_accepted", payload, None)

def _notify_share_created(share: MotieShare):
    """Notificaties naar target user of alle actieve leden van de target party."""
    motie = share.motie
    afzender = share.created_by
    payload_base = {
        "motie_id": motie.id,
        "motie_titel": motie.titel,
        "permission": share.permission,
        "message": share.message,
        "afzender_id": afzender.id if afzender else None,
        "afzender_naam": afzender.naam if afzender else None,
    }

    notified: set[int] = set()

    # Geval 1: specifiek naar gebruiker
    if share.target_user_id:
        uid = share.target_user_id
        if uid != (afzender.id if afzender else None):
            _notify(uid, motie, "share_received", payload_base, share)
            notified.add(uid)

    # Geval 2: naar partij -> alle actieve leden
    if share.target_party_id:
        party = share.target_party or Party.query.get(share.target_party_id)
        if party:
            for lid in party.leden:
                if not getattr(lid, "actief", True):
                    continue
                if afzender and lid.id == afzender.id:
                    continue  # geen notificatie naar jezelf
                if lid.id in notified:
                    continue  # voorkom dubbel (bv. user én party in één actie)
                _notify(lid.id, motie, "share_received", payload_base, share)
                notified.add(lid.id)         

def _notify_share_revoked(share: MotieShare):
    """Notificaties naar dezelfde doelgroep als bij aanmaken, maar met type 'share_revoked'."""
    motie = share.motie
    afzender = share.created_by
    payload_base = {
        "motie_id": motie.id,
        "motie_titel": motie.titel,
        "permission": share.permission,
        "revoked_by_id": afzender.id if afzender else None,
        "revoked_by_naam": afzender.naam if afzender else None,
        "revoked_at": dt.datetime.utcnow().isoformat(),
    }

    recipients: list[int] = []
    if share.target_user_id:
        recipients.append(share.target_user_id)
    elif share.target_party_id:
        party = share.target_party or Party.query.get(share.target_party_id)
        if party:
            recipients.extend([u.id for u in party.leden if getattr(u, "actief", True)])

    for uid in set(recipients):
        if afzender and uid == afzender.id:
            continue
        _notify(uid, motie, "share_revoked", payload_base, share)

def _notify_coauthors_added(motie: Motie, user_ids: list[int]):
    """Notificaties naar nieuw toegevoegde mede-indieners."""
    if not user_ids:
        return
    afzender = current_user
    payload = {
        "motie_id": motie.id,
        "motie_titel": motie.titel,
        "toegevoegd_door_id": afzender.id if afzender else None,
        "toegevoegd_door_naam": afzender.naam if afzender else None,
    }
    for uid in set(user_ids):
        if afzender and uid == afzender.id:
            continue
        _notify(uid, motie, "coauthor_added", payload, None)

# Index-views (griffie, raadsleden, superadmin)
@bp.route('/alle', methods=['GET', 'POST'])
@login_and_active_required
@roles_required('superadmin')
def index():
    q = request.args.get('q')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    sort = request.args.get('sort', 'date')
    direction = request.args.get('dir', 'desc')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    # Whitelist sorteerbare velden
    sort_map = {
        "date": Motie.created_at,
        "title": Motie.titel,
        "status": Motie.status
    }
    sort_col = sort_map.get(sort, Motie.created_at)
    order_clause = asc(sort_col) if direction == 'asc' else desc(sort_col)

    # Basisquery
    query = db.session.query(Motie)
    
    # Filters toepassen
    if q:
        query = query.filter(
            or_(
                Motie.titel.ilike(f'%{q}%'),
                Motie.constaterende_dat.ilike(f'%{q}%'),
                Motie.overwegende_dat.ilike(f'%{q}%'),
                Motie.draagt_college_op.ilike(f'%{q}%'),
            )
        )
    
    if status:
        query = query.filter(Motie.status == status)

    if date_from:
        query = query.filter(Motie.created_at >= date_from)
    
    if date_to:
        query = query.filter(Motie.created_at <= date_to)
    
    # Sorteren
    query = query.order_by(order_clause)

    # Pagineren
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    # Dropdowns in filterbalk
    # Komt hier met partijen
    session["last_index_url"] = request.full_path or request.path
    motie = Motie.query.all()
    return render_template(
        'moties/index.html', 
        moties=motie, 
        title="moties",
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        q=q, 
        status=status,
        date_from=date_from, 
        date_to=date_to,
        sort=sort, 
        direction=direction,
)   

@bp.route('/')
@login_and_active_required
def index_personal():
    u = current_user

    # --- Query params ---
    q = request.args.get('q')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    sort = request.args.get('sort', 'date')
    direction = request.args.get('dir', 'desc')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    # --- Sorteer mapping ---
    sort_map = {
        "date": Motie.created_at,
        "title": Motie.titel,
        "status": Motie.status
    }
    sort_col = sort_map.get(sort, Motie.created_at)
    order_clause = asc(sort_col) if direction == 'asc' else desc(sort_col)

    # --- Basisfilters (functie zodat we ze op alle subqueries toepassen) ---
    def apply_filters(query):
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    Motie.titel.ilike(like),
                    Motie.constaterende_dat.ilike(like),
                    Motie.overwegende_dat.ilike(like),
                    Motie.draagt_college_op.ilike(like),
                )
            )
        if status:
            query = query.filter(Motie.status == status)
        if date_from:
            query = query.filter(Motie.created_at >= date_from)
        if date_to:
            query = query.filter(Motie.created_at <= date_to)
        return query


    if u.has_role('superadmin'):
        base_query = apply_filters(
            Motie.query.options(
                selectinload(Motie.indiener),
                selectinload(Motie.mede_indieners),
            )
        )
        total = base_query.count()
        moties = (
            base_query
            .order_by(order_clause, desc(Motie.id))
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        items = [
            {"motie": m, "relation": "superadmin", "share_permission": None}
            for m in moties
        ]
        session["last_index_url"] = request.full_path or request.path
        return render_template(
            "moties/index.html",
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            q=q,
            status=status,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            direction=direction,
        )
    
    # --- Subquery 1: Indiener (Core select) ---
    own_sel = (
        select(
            Motie.id.label("motie_id"),
            literal("indiener").label("relation"),
            literal(None).label("share_permission"),
            literal(3).label("rel_rank"),
            Motie.created_at.label("created_at"),
            Motie.updated_at.label("updated_at"),
            Motie.titel.label("titel"),
            Motie.status.label("status"),
        )
        .where(Motie.indiener_id == u.id)
    )

    # --- Subquery 2: Mede-indiener ---
    co_sel = (
        select(
            Motie.id.label("motie_id"),
            literal("mede_indiener").label("relation"),
            literal(None).label("share_permission"),
            literal(2).label("rel_rank"),
            Motie.created_at.label("created_at"),
            Motie.updated_at.label("updated_at"),
            Motie.titel.label("titel"),
            Motie.status.label("status"),
        )
        .join(motie_medeindieners, motie_medeindieners.c.motie_id == Motie.id)
        .where(motie_medeindieners.c.user_id == u.id)
    )

    # --- Subquery 3: Gedeeld (hoogste permissie per motie) ---
    perm_rank = case(
        (MotieShare.permission == 'view', 1),
        (MotieShare.permission == 'comment', 2),
        (MotieShare.permission == 'suggest', 3),
        (MotieShare.permission == 'edit', 4),
        else_=0
    )
    now = dt.datetime.utcnow()
    shared_agg = (
        db.session.query(
            MotieShare.motie_id.label("motie_id"),
            func.max(perm_rank).label("max_perm_rank")
        )
        .filter(
            MotieShare.actief.is_(True),
            or_(MotieShare.expires_at.is_(None), MotieShare.expires_at > now),
            or_(
                MotieShare.target_user_id == u.id,
                and_(literal(bool(u.partij_id)).is_(True), MotieShare.target_party_id == u.partij_id)
            )
        )
        .group_by(MotieShare.motie_id)
    ).subquery()

    max_rank = shared_agg.c.max_perm_rank
    rank_to_perm = case(
        (max_rank == 4, literal("edit")),
        (max_rank == 3, literal("suggest")),
        (max_rank == 2, literal("comment")),
        (max_rank == 1, literal("view")),
        else_=literal(None)
    )

    shared_sel = (
        select(
            Motie.id.label("motie_id"),
            literal("gedeeld").label("relation"),
            rank_to_perm.label("share_permission"),
            literal(1).label("rel_rank"),
            Motie.created_at.label("created_at"),
            Motie.updated_at.label("updated_at"),
            Motie.titel.label("titel"),
            Motie.status.label("status"),
        )
        .join(shared_agg, shared_agg.c.motie_id == Motie.id)
    )

    # --- Filters toepassen op de drie deelselects ---
    def apply_filters_core(sel):
        if q:
            like = f"%{q}%"
            sel = sel.where(
                or_(
                    Motie.titel.ilike(like),
                    Motie.constaterende_dat.ilike(like),
                    Motie.overwegende_dat.ilike(like),
                    Motie.draagt_college_op.ilike(like),
                )
            )
        if status:
            sel = sel.where(Motie.status == status)
        if date_from:
            sel = sel.where(Motie.created_at >= date_from)
        if date_to:
            sel = sel.where(Motie.created_at <= date_to)
        return sel

    own_sel   = apply_filters_core(own_sel)
    co_sel    = apply_filters_core(co_sel)
    shared_sel= apply_filters_core(shared_sel)

    # --- UNION ALL (Core) + window ranking ---
    union_sq = union_all(own_sel, co_sel, shared_sel).subquery("u")

    rn = func.row_number().over(
        partition_by=union_sq.c.motie_id,
        order_by=desc(union_sq.c.rel_rank)
    ).label("rn")

    ranked = select(
        union_sq.c.motie_id,
        union_sq.c.relation,
        union_sq.c.share_permission,
        union_sq.c.rel_rank,
        union_sq.c.created_at,
        union_sq.c.updated_at,
        union_sq.c.titel,
        union_sq.c.status,
        rn
    ).subquery("r")

    # Eindquery: koppel terug aan Motie en sorteer volgens jouw sort-keuze
    final_q = (
        db.session.query(
            Motie,
            ranked.c.relation,
            ranked.c.share_permission
        )
        .join(ranked, ranked.c.motie_id == Motie.id)
        .filter(ranked.c.rn == 1)
        .order_by(order_clause, desc(Motie.id))
    )

    # --- Tellen & pagineren ---
    total = final_q.count()
    items_rows = (final_q
                  .offset((page - 1) * per_page)
                  .limit(per_page)
                  .all())

    # Vorm voor template: [{"motie": Motie, "relation": "...", "share_permission": "..."}]
    items = [{"motie": m, "relation": rel, "share_permission": perm} for (m, rel, perm) in items_rows]

    session["last_index_url"] = request.full_path or request.path

    return render_template(
        "moties/index.html",
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        q=q, status=status, date_from=date_from, date_to=date_to, sort=sort, direction=direction
    )

@bp.route('/gedeeld')
@login_and_active_required
def index_shared():
    u = current_user

    # --- Query params ---
    q = request.args.get('q')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    sort = request.args.get('sort', 'date')
    direction = request.args.get('dir', 'desc')
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 20)), 100)

    # --- Sorteer mapping ---
    sort_map = {
        "date": Motie.created_at,
        "title": Motie.titel,
        "status": Motie.status,
    }
    sort_col = sort_map.get(sort, Motie.created_at)
    order_clause = asc(sort_col) if direction == 'asc' else desc(sort_col)

    # --- Aggregatie: hoogste permissie per motie (alleen actief & niet verlopen) ---
    perm_rank = case(
        (MotieShare.permission == 'view', 1),
        (MotieShare.permission == 'comment', 2),
        (MotieShare.permission == 'suggest', 3),
        (MotieShare.permission == 'edit', 4),
        else_=0
    )
    now = dt.datetime.utcnow()
    shared_agg = (
        db.session.query(
            MotieShare.motie_id.label("motie_id"),
            func.max(perm_rank).label("max_perm_rank")
        )
        .filter(
            MotieShare.actief.is_(True),
            or_(MotieShare.expires_at.is_(None), MotieShare.expires_at > now),
            or_(
                MotieShare.target_user_id == u.id,
                and_(literal(bool(u.partij_id)).is_(True), MotieShare.target_party_id == u.partij_id)
            )
        )
        .group_by(MotieShare.motie_id)
    ).subquery()

    max_rank = shared_agg.c.max_perm_rank
    rank_to_perm = case(
        (max_rank == 4, literal("edit")),
        (max_rank == 3, literal("suggest")),
        (max_rank == 2, literal("comment")),
        (max_rank == 1, literal("view")),
        else_=literal(None)
    ).label("share_permission")

    # --- Basisquery: alleen gedeelde moties ---
    q_base = (
        db.session.query(Motie, rank_to_perm)
        .join(shared_agg, shared_agg.c.motie_id == Motie.id)
        .options(
            selectinload(Motie.mede_indieners),
            selectinload(Motie.indiener),
        )
    )

    # --- Filters ---
    if q:
        like = f"%{q}%"
        q_base = q_base.filter(
            or_(
                Motie.titel.ilike(like),
                Motie.constaterende_dat.ilike(like),
                Motie.overwegende_dat.ilike(like),
                Motie.draagt_college_op.ilike(like),
            )
        )
    if status:
        q_base = q_base.filter(Motie.status == status)
    if date_from:
        q_base = q_base.filter(Motie.created_at >= date_from)
    if date_to:
        q_base = q_base.filter(Motie.created_at <= date_to)

    # --- Sorteren + pagineren ---
    q_base = q_base.order_by(order_clause, desc(Motie.id))
    total = q_base.count()
    rows = q_base.offset((page - 1) * per_page).limit(per_page).all()

    # --- Shape voor template (zelfde index-template) ---
    items = [{"motie": m, "relation": "gedeeld", "share_permission": perm} for (m, perm) in rows]
    
    session["last_index_url"] = request.full_path or request.path

    return render_template(
        "moties/index.html",
        title="Gedeeld met mij",
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        q=q, status=status, date_from=date_from, date_to=date_to, sort=sort, direction=direction,
    )

# AEVD Routes
@bp.route('/toevoegen', methods=['GET', 'POST'])
@login_and_active_required
def toevoegen():
    back_url = _safe_back_url()
    if request.method == 'POST':
        gemeenteraad_datum = request.form.get('gemeenteraad_datum')
        agendapunt = request.form.get('agendapunt')
        titel = (request.form.get('titel') or '').strip()
        if not titel:
            flash('Titel is verplicht.', 'danger')
            alle_users = User.query.order_by(User.naam.asc()).all()
            alle_partijen = Party.query.order_by(Party.afkorting.asc()).all()
            return render_template(
                'moties/toevoegen.html',
                title="Nieuwe motie",
                alle_users=alle_users,
                alle_partijen=alle_partijen,
                back_url=back_url,
            )
        const_json = request.form.get('constaterende_dat_json') or "[]"
        overw_dat = request.form.get('overwegende_dat_json') or "[]"
        draagt_json = request.form.get('draagt_json') or "[]"
        opdracht_formulering = request.form.get('opdracht_formulering')
        status = request.form.get('status')

        motie = Motie(
            gemeenteraad_datum=gemeenteraad_datum,
            agendapunt=agendapunt,
            titel=titel,
            constaterende_dat=json.loads(const_json),
            overwegende_dat=json.loads(overw_dat),
            draagt_college_op=json.loads(draagt_json),
            opdracht_formulering=opdracht_formulering,
            status=status,
        )

        motie.indiener_id = current_user.id

        raw_ids = request.form.getlist('mede_indieners')
        mede_ids = {int(x) for x in raw_ids if x.strip().isdigit()}

        added_user_ids: list[int] = []
        if mede_ids:
            if motie.indiener_id:
                mede_ids.discard(motie.indiener_id)
            users = User.query.filter(User.id.in_(mede_ids)).all()
            for u in users:
                motie.mede_indieners.append(u)
                added_user_ids.append(u.id)

        db.session.add(motie)
        db.session.flush()  # zorg dat motie.id bestaat voor notificaties

        # Versiegeschiedenis: initiële versie
        create_motie_version(motie, current_user)

        _notify_coauthors_added(motie, added_user_ids)

        db.session.commit()

    alle_users = User.query.order_by(User.naam.asc()).all()
    alle_partijen = Party.query.order_by(Party.afkorting.asc()).all()
    return render_template(
        'moties/toevoegen.html',
        title="Nieuwe motie",
        alle_users=alle_users,
        alle_partijen=alle_partijen,
        back_url=back_url,
    )

@bp.route('/<int:motie_id>/bekijken', methods=['GET', 'POST'])
@login_and_active_required
def bekijken(motie_id):

    q = MotieShare.query.filter(
            or_(
                MotieShare.target_user_id == current_user.id,
                MotieShare.target_party_id == current_user.partij_id
                )
        ).all()
    motie = (Motie.query
                .options(
                    selectinload(Motie.mede_indieners).selectinload(User.partij)  # alleen als je User.partij-relatie hebt
                )
                .get_or_404(motie_id)
            )
    if user_can_view_motie(current_user, motie) == True:
        medeindieners = sorted(
            motie.mede_indieners,
            key=lambda u: ( (u.partij.afkorting if getattr(u, "partij", None) else ""), u.naam.casefold() )
        )

        return render_template(
            'moties/bekijken.html',
            motie=motie,
            title="Bekijk Motie",
            mede_indieners=medeindieners,
            back_url=_safe_back_url()
        )
    
    else:
        flash('Je hebt helaas geen toegang meer tot deze motie', 'danger')
        return redirect(url_for('moties.index_personal'))

@bp.route('/<int:motie_id>/bewerken', methods=['GET', 'POST'])
@login_and_active_required
def bewerken(motie_id):
    motie = (
        Motie.query
        .options(selectinload(Motie.mede_indieners))
        .get_or_404(motie_id)
    )

    # Lock voor raadsleden wanneer advies gevraagd is (behalve griffie/superadmin)
    if (motie.status or '').lower() == 'advies griffie' and not current_user.has_role('griffie', 'superadmin'):
        flash('Deze motie is in advies bij de griffie en tijdelijk vergrendeld voor bewerken.', 'warning')
        return redirect(url_for('moties.bekijken', motie_id=motie.id))
    if not user_can_edit_motie(current_user, motie):
        flash('Je mag deze motie niet bewerken. Vraag de eigenaar naar toegang', 'danger')
        return redirect(url_for('moties.index_personal'))

    back_url = _safe_back_url()

    def render_form():
        alle_users = User.query.order_by(User.naam.asc()).all()
        alle_partijen = Party.query.order_by(Party.afkorting.asc()).all()
        huidige_mede_ids = {u.id for u in motie.mede_indieners}
        actieve_shares = (
            MotieShare.query
            .filter(
                MotieShare.motie_id == motie.id,
                MotieShare.actief.is_(True),
                or_(
                    MotieShare.expires_at.is_(None),
                    MotieShare.expires_at > dt.datetime.utcnow(),
                ),
            )
            .all()
        )
        return render_template(
            'moties/bewerken.html',
            motie=motie,
            constaterende_dat=as_list(motie.constaterende_dat),
            overwegende_dat=as_list(motie.overwegende_dat),
            draagt_op=as_list(motie.draagt_college_op),
            alle_users=alle_users,
            alle_partijen=alle_partijen,
            actieve_shares=actieve_shares,
            huidige_mede_ids=huidige_mede_ids,
            title="Bewerk Motie",
            back_url=back_url,
        )

    if request.method == 'POST':
        old_status = motie.status
        titel = (request.form.get('titel') or '').strip()
        if not titel:
            flash('Titel is verplicht.', 'danger')
            return render_form()

        motie.gemeenteraad_datum = request.form.get('gemeenteraad_datum') or motie.gemeenteraad_datum
        motie.agendapunt = request.form.get('agendapunt')
        motie.titel = titel
        motie.opdracht_formulering = request.form.get('opdracht_formulering') or motie.opdracht_formulering
        motie.status = request.form.get('status') or motie.status

        const_json = request.form.get('constaterende_dat_json') or "[]"
        overw_json = request.form.get('overwegende_dat_json') or "[]"
        draagt_json = request.form.get('draagt_json') or "[]"

        try:
            motie.constaterende_dat = json.loads(const_json)
            motie.overwegende_dat = json.loads(overw_json)
            motie.draagt_college_op = json.loads(draagt_json)
        except json.JSONDecodeError:
            flash("Kon de dynamische lijsten niet opslaan (ongeldige JSON).", 'danger')
            return render_form()

        raw_ids = request.form.getlist('mede_indieners')
        nieuwe_ids = {int(x) for x in raw_ids if x.strip().isdigit()}

        if motie.indiener_id:
            nieuwe_ids.discard(motie.indiener_id)

        huidige_ids = {u.id for u in motie.mede_indieners}

        to_add = nieuwe_ids - huidige_ids
        to_remove = huidige_ids - nieuwe_ids

        if to_remove:
            motie.mede_indieners[:] = [u for u in motie.mede_indieners if u.id not in to_remove]

        added_user_ids: list[int] = []
        if to_add:
            toe_te_voegen = User.query.filter(User.id.in_(to_add)).all()
            for u in toe_te_voegen:
                motie.mede_indieners.append(u)
                added_user_ids.append(u.id)

        _notify_coauthors_added(motie, added_user_ids)

        # Indien status naar 'Advies griffie' gaat -> advies-sessie + notificaties
        new_status = (request.form.get('status') or motie.status or '').strip()
        if new_status:
            motie.status = new_status
        if (old_status or '').lower() != (motie.status or '').lower() and (motie.status or '').lower() == 'advies griffie':
            ses = _ensure_advice_session_for(motie, current_user)
            # notify griffie
            _notify_advice_requested(motie, current_user)

        # Versiegeschiedenis: nieuwe versie na bewerken
        create_motie_version(motie, current_user)

        db.session.commit()
        flash("Motie bijgewerkt.", "success")
        return redirect(url_for('moties.bekijken', motie_id=motie.id))

    return render_form()

@bp.route('/<int:motie_id>/advies_aanvragen', methods=['POST'])
@login_and_active_required
def advies_aanvragen(motie_id: int):
    m = db.session.get(Motie, motie_id)
    if not m:
        abort(404)
    if current_user.id != m.indiener_id and not current_user.has_role('superadmin'):
        abort(403)
    old = (m.status or '').lower()
    m.status = 'Advies griffie'
    if old != 'advies griffie':
        ses = _ensure_advice_session_for(m, current_user)
        _notify_advice_requested(m, current_user)
    db.session.commit()
    flash('Advies bij de griffie aangevraagd.', 'success')
    return redirect(url_for('moties.bekijken', motie_id=m.id))

# --- Indiener: advies review & accepteren ---
@bp.route('/<int:motie_id>/advies', methods=['GET', 'POST'])
@login_and_active_required
def advies_review(motie_id: int):
    m = db.session.get(Motie, motie_id)
    if not m:
        abort(404)
    # Alleen primaire indiener mag reviewen
    if current_user.id != m.indiener_id and not current_user.has_role('superadmin'):
        flash('Alleen de indiener kan het advies reviewen.', 'danger')
        return redirect(url_for('moties.bekijken', motie_id=m.id))

    # Pak laatste advies-sessie
    # Pak meest recente teruggestuurde advies-sessie expliciet
    ses = (
        AdviceSession.query
        .filter(
            AdviceSession.motie_id == m.id,
            AdviceSession.status == 'returned'
        )
        .order_by(AdviceSession.returned_at.desc().nullslast(), AdviceSession.created_at.desc())
        .first()
    )
    if not ses or not ses.draft:
        flash('Er is nog geen advies beschikbaar.', 'warning')
        return redirect(url_for('moties.bekijken', motie_id=m.id))

    # Voor UI: vergelijk originele velden met draft
    curr = _motie_snapshot(m)
    draft = ses.draft or {}
    fields_order = [
        "titel",
        "status",
        "gemeenteraad_datum",
        "agendapunt",
        "constaterende_dat",
        "overwegende_dat",
        "opdracht_formulering",
        "draagt_college_op",
    ]
    def _fmt(key, snap):
        if key in ("constaterende_dat", "overwegende_dat", "draagt_college_op"):
            vals = snap.get(key) or []
            return "\n".join([f"• {v}" for v in vals])
        if key == 'mede_indieners_ids':
            # optioneel: namen ophalen, voor nu IDs
            return ", ".join([str(x) for x in (snap.get(key) or [])])
        return str(snap.get(key) or "")
    items = []
    for k in fields_order:
        items.append({
            'key': k,
            'label': {
                'titel': 'Titel',
                'status': 'Status',
                'gemeenteraad_datum': 'Vergaderdatum',
                'agendapunt': 'Agendapunt',
                'opdracht_formulering': 'Opdracht',
                'constaterende_dat': 'Constaterende dat',
                'overwegende_dat': 'Overwegende dat',
                'draagt_college_op': 'Draagt het college op',
                'mede_indieners_ids': 'Mede‑indieners',
            }.get(k, k),
            'old': _fmt(k, curr),
            'new': _fmt(k, draft),
            'changed': curr.get(k) != draft.get(k),
        })

    adv_comment = draft.get('advies_commentaar') if isinstance(draft, dict) else None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'accept':
            # Schrijf draft naar motie velden
            snap = draft
            m.titel = snap.get('titel') or m.titel
            m.constaterende_dat = snap.get('constaterende_dat') or []
            m.overwegende_dat = snap.get('overwegende_dat') or []
            m.draagt_college_op = snap.get('draagt_college_op') or []
            m.opdracht_formulering = snap.get('opdracht_formulering') or m.opdracht_formulering
            m.status = 'Klaar om in te dienen'
            # mede‑indieners ids niet automatisch aanpassen in deze flow
            create_motie_version(m, current_user)
            # markeer sessie geaccepteerd
            ses.status = 'accepted'
            ses.accepted_at = dt.datetime.utcnow()
            # Notify griffie (reviewer)
            _notify_advice_accepted(m, current_user, ses)
            db.session.commit()
            flash('Advieswijzigingen geaccepteerd. Status gezet op "Klaar om in te dienen".', 'success')
            return redirect(url_for('moties.bekijken', motie_id=m.id))
        elif action == 'needs_changes':
            m.status = 'Nog niet gereed'
            db.session.commit()
            flash('Status gezet op "Nog niet gereed". Je kunt verder bewerken of opnieuw advies vragen.', 'info')
            return redirect(url_for('moties.bekijken', motie_id=m.id))

    return render_template('moties/advies_review.html', motie=m, items=items, advies_commentaar=adv_comment)

@bp.route('/<int:motie_id>/geschiedenis')
@login_and_active_required
def geschiedenis(motie_id: int):
    motie = (
        Motie.query
        .options(selectinload(Motie.mede_indieners), selectinload(Motie.indiener))
        .get_or_404(motie_id)
    )
    if not user_can_view_history(current_user, motie):
        flash('Je mag de versiegeschiedenis van deze motie niet bekijken.', 'danger')
        return redirect(url_for('moties.bekijken', motie_id=motie.id))

    # Haal versies op en bereid timeline-items voor UI diffs
    versies_all = (
        MotieVersion.query
        .filter(MotieVersion.motie_id == motie.id)
        .order_by(MotieVersion.created_at.asc(), MotieVersion.id.asc())
        .all()
    )

    # Map user-id -> naam voor weergave van mede-indieners
    def _format_value(key: str, snap: dict, user_name_by_id: dict[int, str]) -> str:
        v = snap.get(key) if snap else None
        if key in ("constaterende_dat", "overwegende_dat", "draagt_college_op"):
            items = v or []
            if not isinstance(items, list):
                return str(items) if items is not None else ""
            lines = []
            for it in items:
                lines.append(f"• {it}")
            return "\n".join(lines)
        if key == "mede_indieners_ids":
            ids = v or []
            if not isinstance(ids, list):
                return ""
            names = [user_name_by_id.get(uid, f"User #{uid}") for uid in ids]
            return ", ".join(names)
        # strings / simpele waarden
        return "" if v is None else str(v)

    # Verzamel alle user-ids voor mede-indieners over alle versies
    user_ids: set[int] = set()
    for ver in versies_all:
        try:
            for uid in (ver.snapshot or {}).get("mede_indieners_ids", []) or []:
                if isinstance(uid, int):
                    user_ids.add(uid)
        except Exception:
            pass
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    user_name_by_id = {u.id: (u.naam or u.email or f"User #{u.id}") for u in users}

    fields_order = [
        "titel",
        "status",
        "gemeenteraad_datum",
        "agendapunt",
        "opdracht_formulering",
        "constaterende_dat",
        "overwegende_dat",
        "draagt_college_op",
        "mede_indieners_ids",
    ]

    timeline_items = []
    prev_snap = None
    for ver in versies_all:
        curr = ver.snapshot or {}
        changed = ver.changed_fields or []
        # fallback berekening als changed_fields leeg is
        if not changed:
            changed = _diff_changed_fields(prev_snap, curr)
        fields = []
        for key in fields_order:
            old_val = _format_value(key, prev_snap, user_name_by_id)
            new_val = _format_value(key, curr, user_name_by_id)
            fields.append({
                "key": key,
                "label": {
                    "titel": "Titel",
                    "status": "Status",
                    "gemeenteraad_datum": "Vergaderdatum",
                    "agendapunt": "Agendapunt",
                    "opdracht_formulering": "Opdracht",
                    "constaterende_dat": "Constaterende dat",
                    "overwegende_dat": "Overwegende dat",
                    "draagt_college_op": "Draagt het college op",
                    "mede_indieners_ids": "Mede‑indieners",
                }.get(key, key),
                "old": old_val,
                "new": new_val,
                "changed": key in changed,
            })
        changed_labels = [f["label"] for f in fields if f["changed"]]
        timeline_items.append({
            "ver": ver,
            "fields": fields,
            "changed_keys": [k for k in fields_order if k in changed],
            "changed_labels": changed_labels,
        })
        prev_snap = curr

    # Nieuwste eerst in UI
    timeline_items = list(reversed(timeline_items))

    return render_template(
        'moties/geschiedenis.html',
        motie=motie,
        timeline_items=timeline_items,
        title=f"Versiegeschiedenis: {motie.titel}",
        back_url=_safe_back_url('moties.bekijken')
    )

@bp.route('/<int:motie_id>/verwijderen', methods=['POST', 'GET'])
@login_and_active_required
def verwijderen(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    db.session.delete(motie)
    db.session.commit()
    flash('Is verwijderd.', 'success')
    return redirect(url_for('moties.index'))

@bp.route('/<int:motie_id>/share', methods=['POST', 'GET'])
@login_and_active_required
def share_create(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    if request.method == 'POST':    
        motie = Motie.query.get_or_404(motie_id)

        permission  = request.form.get('permission')   # 'view' | 'comment' | 'suggest'
        message     = request.form.get('message') or None
        expires_str = request.form.get('expires_at') or None

        if permission not in ('view', 'comment', 'suggest', 'edit'):
            flash("Onbekende rechtenkeuze.", "danger")
            return redirect(url_for('moties.bewerken', motie_id=motie.id))

        expires_at = None
        if expires_str:
            try:
                expires_at = dt.datetime.strptime(expires_str, "%Y-%m-%d")
            except ValueError:
                flash("Ongeldige verloopdatum (gebruik YYYY-MM-DD).", "warning")
        
        # 🔑 Nieuw: meerdere doelen in één keer
        user_ids  = [int(x) for x in request.form.getlist('share_user_ids')  if x.strip().isdigit()]
        party_ids = [int(x) for x in request.form.getlist('share_party_ids') if x.strip().isdigit()]

        if not user_ids and not party_ids:
            flash("Kies ten minste één gebruiker of één partij om mee te delen.", "warning")
            return redirect(url_for('moties.bewerken', motie_id=motie.id))

        created, skipped = 0, 0
        for uid in user_ids:
            share = MotieShare(
                motie_id=motie.id,
                created_by_id=current_user.id,
                permission=permission,
                message=message,
                expires_at=expires_at,
                actief=True,
                target_user_id=uid
            )
            try:
                db.session.add(share)
                db.session.flush()
                _notify_share_created(share)
                created += 1
            except Exception:
                db.session.rollback()
                skipped += 1  # vaak duplicate actieve share

        for pid in party_ids:
            share = MotieShare(
                motie_id=motie.id,
                created_by_id=current_user.id,
                permission=permission,
                message=message,
                expires_at=expires_at,
                actief=True,
                target_party_id=pid
            )
            try:
                db.session.add(share)
                db.session.flush()
                _notify_share_created(share) 
                created += 1
            except Exception:
                db.session.rollback()
                skipped += 1

        db.session.commit()
        
        if created and skipped:
            flash(f"{created} gedeeld, {skipped} overgeslagen (bestond al).", "info")
        elif created:
            flash(f"Gedeeld met {created} ontvanger(s).", "success")
        else:
            flash("Geen nieuwe delen toegevoegd (mogelijk bestond alles al).", "warning")

        return redirect(url_for('moties.share_create', motie_id=motie.id))
    
    actieve_shares = (
        MotieShare.query
        .filter(
            MotieShare.motie_id == motie_id,
            MotieShare.actief.is_(True),
            # alleen niet-verlopen of zonder einddatum
            or_(MotieShare.expires_at.is_(None), MotieShare.expires_at > func.now())
        )
        .all()
    )

    # Lijsten voor select
    alle_users = User.query.order_by(User.naam.asc()).all()
    alle_partijen = Party.query.order_by(Party.afkorting.asc()).all()
    
    return render_template('moties/delen.html', actieve_shares=actieve_shares, alle_users=alle_users, alle_partijen=alle_partijen, motie=motie, back_url=_safe_back_url())

@bp.route('/<int:motie_id>/share/<int:share_id>/revoke', methods=['POST', 'GET'])
@login_and_active_required
def share_revoke(motie_id, share_id):
    motie = Motie.query.get_or_404(motie_id)
    share = MotieShare.query.get_or_404(share_id)
    if share.motie_id != motie.id:
        abort(404)

    if not share.actief:
        flash("Deze share was al ingetrokken.", "info")
        return redirect(url_for('moties.bewerken', motie_id=motie.id))

    share.revoke()
    _notify_share_revoked(share)
    db.session.commit()
    flash("Toegang ingetrokken.", "success")
    return redirect(url_for('moties.share_create', motie_id=motie.id))

# Exporters
@bp.route("/<int:motie_id>/export/docx")
@login_and_active_required
def export_motie_docx(motie_id: int):
    motie = db.session.get(Motie, motie_id)
    if not motie:
        abort(404, "Motie niet gevonden")

    # Optioneel kun je datum/vergadering meegeven vanuit querystring of motie
    file_bytes, filename = render_motie_to_docx_bytes(motie)

    resp = make_response(file_bytes)
    resp.headers.set(
        "Content-Type",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    # Zorgt voor directe download + bestandsnaam "Motie <titel>.docx"
    resp.headers.set("Content-Disposition", f'attachment; filename="{filename}"')
    return resp

@bp.route("/export/bulk", methods=["POST"])
@roles_required('griffie')
@login_and_active_required
def export_bulk_zip():
    """
    Accepteert:
      - POST form: motie_ids=<id>&motie_ids=<id>...
      - of JSON: {"ids": [1,2,3]}
    Geeft een ZIP met 'Motie <titel>.docx' per motie terug.
    """
    ids = []
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        ids = payload.get("ids", [])
    else:
        # checkboxes met name="motie_ids"
        ids = request.form.getlist("motie_ids")

    # normaliseer ids -> ints
    try:
        ids = [int(x) for x in ids]
    except Exception:
        abort(400, "Ongeldige motie-ids")

    if not ids:
        abort(400, "Geen moties geselecteerd")

    # (optioneel) limiet om geheugen te sparen
    if len(ids) > 200:
        abort(400, "Selecteer maximaal 200 moties per export")

    moties = (
        db.session.query(Motie)
        .filter(Motie.id.in_(ids))
        .order_by(Motie.id.asc())
        .all()
    )
    if not moties:
        abort(404, "Geen moties gevonden")

    zip_buf = BytesIO()
    name_set: set[str] = set()

    with ZipFile(zip_buf, "w", ZIP_DEFLATED) as zf:
        for m in moties:
            doc_bytes, filename = render_motie_to_docx_bytes(m)
            filename = _unique_name(filename, name_set)
            zf.writestr(filename, doc_bytes)

    zip_buf.seek(0)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    zip_name = f"Moties_{stamp}.zip"

    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name,
        max_age=0,
    )
