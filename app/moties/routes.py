from flask import Flask, render_template, flash, redirect, url_for, send_file, request, abort, make_response, jsonify
from app.moties.forms import MotieForm
from sqlalchemy import or_, asc, desc
from app.models import Motie, Amendementen, User, motie_medeindieners
from app import db
import json
from sqlalchemy.orm import Session, selectinload
from app.moties import bp
from app.exporters.motie_docx import render_motie_to_docx_bytes
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
from flask_login import current_user, login_required    

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

@bp.route('/', methods=['GET', 'POST'])
@login_required
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

@bp.route('/toevoegen', methods=['GET', 'POST'])
@login_required
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
        raw_ids = request.form.getlist('mede_indieners')  # ['3','12',...]
        mede_ids = {int(x) for x in raw_ids if x.strip().isdigit()}
        if mede_ids:
            # (optioneel) voorkom dubbele opname van primaire indiener:
            if motie.indiener_id: mede_ids.discard(motie.indiener_id)
            users = User.query.filter(User.id.in_(mede_ids)).all()
            for u in users:
                motie.mede_indieners.append(u)

        db.session.add(motie)
        db.session.commit()
        flash('Great! Your motion has been created.', 'success')
        return redirect(url_for('moties.bekijken', motie_id=motie.id))

    # GET: lijst gebruikers meesturen voor de select
    alle_users = User.query.order_by(User.naam.asc()).all()
    return render_template('moties/toevoegen.html', title="moties", alle_users=alle_users)

@bp.route('/<int:motie_id>/bekijken', methods=['GET', 'POST'])
@login_required
def bekijken(motie_id):
    motie = (Motie.query
            .options(
                selectinload(Motie.mede_indieners).selectinload(User.partij)  # alleen als je User.partij-relatie hebt
            )
            .get_or_404(motie_id)
        )
    medeindieners = sorted(
        motie.mede_indieners,
        key=lambda u: ( (u.partij.afkorting if getattr(u, "partij", None) else ""), u.naam.casefold() )
    )

    return render_template(
        'moties/bekijken.html',
        motie=motie,
        title="Bekijk Motie",
        mede_indieners=medeindieners
    )


@bp.route('/<int:motie_id>/bewerken', methods=['GET', 'POST'])
@login_required
def bewerken(motie_id):
    # Laad motie + huidige mede-indieners efficiënt
    motie = (Motie.query
        .options(selectinload(Motie.mede_indieners))
        .get_or_404(motie_id)
    )

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

        if to_add:
            toe_te_voegen = User.query.filter(User.id.in_(to_add)).all()
            for u in toe_te_voegen:
                motie.mede_indieners.append(u)

        db.session.commit()
        flash("Motie bijgewerkt.", "success")
        return redirect(url_for('moties.bekijken', motie_id=motie.id))

    # GET: alle users voor de select + huidige selectie
    alle_users = User.query.order_by(User.naam.asc()).all()
    huidige_mede_ids = {u.id for u in motie.mede_indieners}

    return render_template(
        'moties/bewerken.html',
        motie=motie,
        constaterende_dat=as_list(motie.constaterende_dat),
        overwegende_dat=as_list(motie.overwegende_dat),
        draagt_op=as_list(motie.draagt_college_op),
        alle_users=alle_users,
        huidige_mede_ids=huidige_mede_ids,
        title="Bewerk Motie"
    )


@bp.route('/<int:motie_id>/verwijderen', methods=['POST', 'GET'])
@login_required
def verwijderen(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    db.session.delete(motie)
    db.session.commit()
    flash('Is verwijderd.', 'success')
    return redirect(url_for('moties.index'))

@bp.route("/<int:motie_id>/export/docx")
@login_required
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

@bp.route("/export/bulk", methods=["POST"])
@login_required
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
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    zip_name = f"Moties_{stamp}.zip"

    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name,
        max_age=0,
    )