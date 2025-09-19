from flask import Flask, render_template, flash, redirect, url_for, request, abort
from app.instrumenten import bp
from app.instrumenten.forms import MotieForm
from sqlalchemy import or_, asc, desc
from app.models import Motie
from app import db
import json

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
        'instrumenten/filter_index.html', 
        moties=motie, 
        title="Instrumenten",
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
        titel = request.form.get('titel')
        const_json = request.form.get('constaterende_dat_json') or "[]"
        overw_dat = request.form.get('overwegende_dat_json') or "[]"
        draagt_json = request.form.get('draagt_json') or "[]"
        opdracht_formulering = request.form.get('opdracht_formulering')
        status = request.form.get('status')
        # Verwerk het formulier hier
        motie = Motie(
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
        return redirect(url_for('instrumenten.bekijken', motie_id=motie.id))
    
    return render_template('instrumenten/toevoegen.html', title="Instrumenten")

@bp.route('<int:motie_id>/bekijken', methods=['GET', 'POST'])
def bekijken(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    return render_template('instrumenten/bekijken.html', motie=motie, title="Bekijk Motie")

@bp.route('/<int:motie_id>/bewerken')
def bewerken(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    
    return render_template('instrumenten/bewerken.html', 
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
    
    motie.titel = titel
    motie.constaterende_dat = json.loads(const_json)
    motie.overwegende_dat = json.loads(overw_json)
    motie.draagt_college_op = json.loads(draagt_json)
    motie.opdracht_formulering = opdracht_formulering
    motie.status = status
    motie.gemeenteraad_datum = gemeenteraad_datum
    
    db.session.commit()
    flash('Is bijgewerkt.', 'success')
    return redirect(url_for('instrumenten.bekijken', motie_id=motie.id))


@bp.route('/<int:motie_id>/verwijderen', methods=['POST', 'GET'])
def verwijderen(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    db.session.delete(motie)
    db.session.commit()
    flash('Is verwijderd.', 'success')
    return redirect(url_for('instrumenten.index'))