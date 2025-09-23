from flask import Flask, render_template, flash, redirect, url_for, send_file, request, abort, make_response, jsonify
from app.moties.forms import MotieForm
from sqlalchemy import or_, asc, desc
from app.models import Motie, Amendementen
from app import db
import json
from sqlalchemy.orm import Session
from app.moties import bp
from app.exporters.motie_docx import render_motie_to_docx_bytes
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime

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
        # Verwerk het formulier hier
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
        # Sla de motie op in de database
        db.session.add(motie)
        db.session.commit()
        flash('Great! Your motion has been created.', 'success')
        return redirect(url_for('moties.bekijken', motie_id=motie.id))
    
    return render_template('moties/toevoegen.html', title="moties")

@bp.route('/<int:motie_id>/bekijken', methods=['GET', 'POST'])
def bekijken(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    return render_template('moties/bekijken.html', motie=motie, title="Bekijk Motie")

@bp.route('/<int:motie_id>/bewerken')
def bewerken(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    
    return render_template('moties/bewerken.html', 
                           motie=motie, 
                           constaterende_dat=as_list(motie.constaterende_dat),
                           overwegende_dat=as_list(motie.overwegende_dat),
                           draagt_op=as_list(motie.draagt_college_op), 
                           title="Bewerk Motie")

@bp.post('/<int:motie_id>/bewerken')
def bewerken_post(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    
    titel = request.form.get('titel').strip()
    const_json = request.form.get('constaterende_dat_json') or "[]"
    overw_json = request.form.get('overwegende_dat_json') or "[]"
    draagt_json = request.form.get('draagt_json') or "[]"
    opdracht_formulering = request.form.get('opdracht_formulering').strip()
    status = request.form.get('status')
    gemeenteraad_datum = request.form.get('gemeenteraad_datum')
    agendapunt = request.form.get('agendapunt')
    
    motie.titel = titel
    motie.constaterende_dat = json.loads(const_json)
    motie.overwegende_dat = json.loads(overw_json)
    motie.draagt_college_op = json.loads(draagt_json)
    motie.opdracht_formulering = opdracht_formulering
    motie.status = status
    motie.gemeenteraad_datum = gemeenteraad_datum
    motie.agendapunt = agendapunt
    
    db.session.commit()
    flash('Is bijgewerkt.', 'success')
    return redirect(url_for('moties.bekijken', motie_id=motie.id))


@bp.route('/<int:motie_id>/verwijderen', methods=['POST', 'GET'])
def verwijderen(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    db.session.delete(motie)
    db.session.commit()
    flash('Is verwijderd.', 'success')
    return redirect(url_for('moties.index'))

@bp.route("/<int:motie_id>/export/docx")
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