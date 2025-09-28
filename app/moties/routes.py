from flask import Flask, render_template, flash, redirect, url_for, send_file, request, abort, make_response, jsonify, session
from app.moties.forms import MotieForm
from sqlalchemy import or_, asc, desc, and_, case, literal, func, union_all, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import label
from app.models import Motie, User, motie_medeindieners, MotieShare, Party, Notification
from app import db
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
    # indiener of mede-indiener mag altijd bekijken
    if motie.indiener_id == user.id or any(u.id == user.id for u in motie.mede_indieners):
        return True
    perm = _highest_share_permission_for(user, motie)
    return perm in ("view", "comment", "suggest", "edit")

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
    if request.method == 'POST':
        gemeenteraad_datum = request.form.get('gemeenteraad_datum')
        agendapunt = request.form.get('agendapunt')
        titel = request.form.get('titel')
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
            status=status
        )

        # (optioneel) primaire indiener vastleggen:
        motie.indiener_id = current_user.id

        # >>> NIEUW: mede-indieners uit multi-select
        raw_ids = request.form.getlist('mede_indieners')
        mede_ids = {int(x) for x in raw_ids if x.strip().isdigit()}

        added_user_ids = []
        if mede_ids:
            if motie.indiener_id:
                mede_ids.discard(motie.indiener_id)
            users = User.query.filter(User.id.in_(mede_ids)).all()
            for u in users:
                motie.mede_indieners.append(u)
                added_user_ids.append(u.id)

        db.session.add(motie)
        db.session.flush()  # zorg dat motie.id bestaat voor notificaties

        # Notificaties naar nieuw toegevoegde mede-indieners
        _notify_coauthors_added(motie, added_user_ids)

        db.session.commit()
        
    # GET: lijst gebruikers meesturen voor de select
    alle_users = User.query.order_by(User.naam.asc()).all()
    alle_partijen = Party.query.order_by(Party.afkorting.asc()).all()
    return render_template('moties/toevoegen.html', title="Nieuwe motie", alle_users=alle_users, alle_partijen=alle_partijen, back_url=_safe_back_url())

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
    # Laad motie + huidige mede-indieners efficiënt
    motie = (Motie.query
        .options(selectinload(Motie.mede_indieners))
        .get_or_404(motie_id)
    )

    if not user_can_edit_motie(current_user, motie):
        flash('Je mag deze motie niet bewerken. Vraag de eigenaar naar toegang', 'danger')
        return redirect(url_for('moties.index_personal'))

    if request.method == 'POST':
        # --- gewone velden ---
        motie.gemeenteraad_datum = request.form.get('gemeenteraad_datum') or motie.gemeenteraad_datum
        motie.agendapunt = request.form.get('agendapunt')
        motie.titel = request.form.get('titel') or motie.titel
        motie.opdracht_formulering = request.form.get('opdracht_formulering') or motie.opdracht_formulering
        motie.status = request.form.get('status') or motie.status

        # --- JSON arrays ---
        const_json = request.form.get('constaterende_dat_json') or "[]"
        overw_json = request.form.get('overwegende_dat_json') or "[]"
        draagt_json = request.form.get('draagt_json') or "[]"

        try:
            motie.constaterende_dat = json.loads(const_json)
            motie.overwegende_dat = json.loads(overw_json)
            motie.draagt_college_op = json.loads(draagt_json)
        except json.JSONDecodeError:
            flash("Kon de dynamische lijsten niet opslaan (ongeldige JSON).", "danger")
            return redirect(url_for('moties.bewerken', motie_id=motie.id))

        # --- mede-indieners sync ---
        raw_ids = request.form.getlist('mede_indieners')  # ['3','12',...]
        nieuwe_ids = {int(x) for x in raw_ids if x.strip().isdigit()}

        # primaire indiener niet als mede-indiener
        if motie.indiener_id:
            nieuwe_ids.discard(motie.indiener_id)

        huidige_ids = {u.id for u in motie.mede_indieners}

        to_add = nieuwe_ids - huidige_ids
        to_remove = huidige_ids - nieuwe_ids

        if to_remove:
            motie.mede_indieners[:] = [u for u in motie.mede_indieners if u.id not in to_remove]

        added_user_ids = []
        if to_add:
            toe_te_voegen = User.query.filter(User.id.in_(to_add)).all()
            for u in toe_te_voegen:
                motie.mede_indieners.append(u)
                added_user_ids.append(u.id)

        # Notificaties naar nieuw toegevoegde mede-indieners
        _notify_coauthors_added(motie, added_user_ids)

        db.session.commit()        
        flash("Motie bijgewerkt.", "success")
        return redirect(url_for('moties.bekijken', motie_id=motie.id))

    # GET: alle users voor de select + huidige selectie
    alle_users = User.query.order_by(User.naam.asc()).all()
    huidige_mede_ids = {u.id for u in motie.mede_indieners}

    actieve_shares = (
        MotieShare.query
        .filter(
            MotieShare.motie_id == motie.id,
            MotieShare.actief.is_(True),
            # alleen niet-verlopen of zonder einddatum
            or_(MotieShare.expires_at.is_(None), MotieShare.expires_at > dt.datetime.utcnow())
        )
        .all()
    )

    # Lijsten voor select
    alle_users = User.query.order_by(User.naam.asc()).all()
    alle_partijen = Party.query.order_by(Party.afkorting.asc()).all()

    huidige_mede_ids = {u.id for u in motie.mede_indieners}

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
        back_url=_safe_back_url()
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