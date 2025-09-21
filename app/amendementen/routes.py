from flask import Flask, render_template, flash, redirect, url_for, request, abort
from app.amendementen import bp
from sqlalchemy import or_, asc, desc
from app.models import Amendementen
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
        "date": Amendementen.created_at,
        "title": Amendementen.titel,
        "status": Amendementen.status
    }
    sort_col = sort_map.get(sort, Amendementen.created_at)
    order_clause = asc(sort_col) if direction == 'asc' else desc(sort_col)

    # Basisquery
    query = db.session.query(Amendementen)

    # Filters toepassen
    if q:
        query = query.filter(
            or_(
                Amendementen.titel.ilike(f'%{q}%'),
                Amendementen.constaterende_dat.ilike(f'%{q}%'),
                Amendementen.overwegende_dat.ilike(f'%{q}%'),
                Amendementen.wijzigingen.ilike(f'%{q}%'),
            )
        )
    
    if status:
        query = query.filter(Amendementen.status == status)

    if date_from:
        query = query.filter(Amendementen.created_at >= date_from)
    
    if date_to:
        query = query.filter(Amendementen.created_at <= date_to)
    
    # Sorteren
    query = query.order_by(order_clause)

    # Pagineren
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    # Dropdowns in filterbalk
    # Komt hier met partijen

    amendementen = Amendementen.query.all()
    return render_template(
        'amendementen/index.html', 
        title="amendementen",
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
        wijzigingen_json = request.form.get('wijzigingen_json') or "[]"
        opdracht_formulering = request.form.get('opdracht_formulering')
        status = request.form.get('status')
        # Verwerk het formulier hier
        amendementen = Amendementen(
            gemeenteraad_datum=gemeenteraad_datum,
            agendapunt=agendapunt,
            titel=titel,
            constaterende_dat=json.loads(const_json),
            overwegende_dat=json.loads(overw_dat),
            wijzigingen=json.loads(wijzigingen_json),
            opdracht_formulering=opdracht_formulering,
            status=status
        )
        # Sla de motie op in de database
        db.session.add(amendementen)
        db.session.commit()
        flash('Geweldig, je amendement is gemaakt', 'success')
        return redirect(url_for('amendementen.bekijken', amen_id=amendementen.id))
    
    return render_template('amendementen/toevoegen.html', title="amendementen")

@bp.route('/<int:amen_id>/bekijken', methods=['GET', 'POST'])
def bekijken(amen_id):
    amendement = Amendementen.query.get_or_404(amen_id)
    return render_template('amendementen/bekijken.html', amendement=amendement, title="Bekijk Amendement")

@bp.route('/<int:amen_id>/bewerken')
def bewerken(amen_id):
    amendement = Amendementen.query.get_or_404(amen_id)
    
    return render_template('amendementen/bewerken.html', 
                           amendement=amendement, 
                           constaterende_dat=as_list(amendement.constaterende_dat),
                           overwegende_dat=as_list(amendement.overwegende_dat),
                           wijzigingen=as_list(amendement.wijzigingen), 
                           title="Bewerk Amendement")

@bp.post('<int:amen_id>/bewerken')
def bewerken_post(amen_id):
    amendement = Amendementen.query.get_or_404(amen_id)
    
    titel = request.form.get('titel').strip()
    const_json = request.form.get('constaterende_dat_json') or "[]"
    overw_json = request.form.get('overwegende_dat_json') or "[]"
    wijzigingen_json = request.form.get('wijzigingen_json') or "[]"
    opdracht_formulering = request.form.get('opdracht_formulering').strip()
    status = request.form.get('status')
    gemeenteraad_datum = request.form.get('gemeenteraad_datum')
    agendapunt = request.form.get('agendapunt')
    
    amendement.titel = titel
    amendement.constaterende_dat = json.loads(const_json)
    amendement.overwegende_dat = json.loads(overw_json)
    amendement.wijzigingen = json.loads(wijzigingen_json)
    amendement.opdracht_formulering = opdracht_formulering
    amendement.status = status
    amendement.gemeenteraad_datum = gemeenteraad_datum
    amendement.agendapunt = agendapunt
    
    db.session.commit()
    flash('Is bijgewerkt.', 'success')
    return redirect(url_for('amendementen.bekijken', amen_id=amendement.id))


@bp.route('/<int:amen_id>/verwijderen', methods=['POST', 'GET'])
def verwijderen(amen_id):
    amendement = Amendementen.query.get_or_404(amen_id)
    db.session.delete(amendement)
    db.session.commit()
    flash('Is verwijderd.', 'success')
    return redirect(url_for('amendementen.index'))