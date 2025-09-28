from flask import render_template, redirect, url_for, request, abort, flash
from flask_login import login_required, current_user
from sqlalchemy import func
import datetime as dt

from app import db
from app.models import Motie, User, AdviceSession, Notification
from . import bp

def _is_griffie(user: User) -> bool:
    return getattr(user, 'role', None) in ('griffier', 'raadsadviseur', 'beheerder')

def _notify(user_id, motie_id, ntype, payload):
    db.session.add(Notification(user_id=user_id, motie_id=motie_id, type=ntype, payload=payload))

def motie_to_editable_dict(m: 'Motie') -> dict:
    """Neem exact de velden mee die de griffie inhoudelijk mag aanpassen."""
    return {
        "titel": m.titel or "",
        "toelichting": m.toelichting or "",
        # pas deze aan op jouw modelvelden:
        "constaterende": [c.tekst for c in m.constaterende] if hasattr(m, "constaterende") else [],
        "overwegende": [o.tekst for o in m.overwegende] if hasattr(m, "overwegende") else [],
        "draagt_op":    [d.tekst for d in m.draagt_op] if hasattr(m, "draagt_op") else [],
    }


@bp.post('/moties/<int:motie_id>/advies/start')
@login_required
def start(motie_id):
    motie = Motie.query.get_or_404(motie_id)
    if motie.indiener_id != current_user.id:
        abort(403)

    # kies reviewer (simpelste: eerste griffier)
    reviewer = User.query.filter(User.role.in_(('griffier'))).first()
    draft = motie_to_editable_dict(motie)

    s = AdviceSession(
        motie_id=motie.id,
        requested_by_id=current_user.id,
        reviewer_id=reviewer.id if reviewer else None,
        status='requested',
        draft=draft
    )
    db.session.add(s)
    db.session.flush()

    # notificatie naar reviewer
    if reviewer:
        _notify(reviewer.id, motie.id, "advice_requested", {
            "motie_titel": motie.titel, "session_id": s.id, "requested_by": current_user.naam
        })

    db.session.commit()
    flash("Motie aangeboden voor advies.", "success")
    return redirect(url_for('moties.bekijken', motie_id=motie.id))

@bp.get('/<int:session_id>/bewerken')
@login_required
def edit(session_id):
    s = AdviceSession.query.get_or_404(session_id)
    if not _is_griffie(current_user):
        abort(403)
    # eenvoudige bewerkpagina; render velden uit s.draft
    return render_template('advies/edit.html', s=s)

@bp.post('/<int:session_id>/opslaan')
@login_required
def save(session_id):
    s = AdviceSession.query.get_or_404(session_id)
    if not _is_griffie(current_user):
        abort(403)

    # lees velden uit formulier; pas aan naar jouw namen
    d = dict(s.draft)  # kopie
    d["titel"] = request.form.get("titel", d.get("titel",""))
    d["toelichting"] = request.form.get("toelichting", d.get("toelichting",""))
    d["constaterende"] = [x for x in request.form.getlist("constaterende[]") if x.strip()]
    d["overwegende"]   = [x for x in request.form.getlist("overwegende[]")   if x.strip()]
    d["draagt_op"]     = [x for x in request.form.getlist("draagt_op[]")     if x.strip()]

    s.draft = d
    s.status = 'in_review'
    db.session.commit()
    flash("Adviesconcept opgeslagen.", "success")
    return redirect(url_for('advies.compare', session_id=s.id))

@bp.get('/<int:session_id>/vergelijk')
@login_required
def compare(session_id):
    s = AdviceSession.query.get_or_404(session_id)
    motie = s.motie
    # iedereen met linkrechten mag de vergelijking zien:
    if current_user.id not in {s.requested_by_id, getattr(s.reviewer, 'id', None), motie.indiener_id} and not _is_griffie(current_user):
        abort(403)
    orig = motie_to_editable_dict(motie)
    new = s.draft
    return render_template('advies/compare.html', s=s, orig=orig, new=new, motie=motie)

@bp.post('/<int:session_id>/indienen')
@login_required
def submit_advice(session_id):
    s = AdviceSession.query.get_or_404(session_id)
    if not _is_griffie(current_user):
        abort(403)
    s.status = 'returned'
    s.returned_at = dt.datetime.utcnow()
    _notify(s.requested_by_id, s.motie_id, "advice_ready",
            {"motie_titel": s.motie.titel, "session_id": s.id, "reviewer": current_user.naam})
    db.session.commit()
    flash("Advies teruggekoppeld aan indiener.", "success")
    return redirect(url_for('advies.compare', session_id=s.id))

@bp.post('/<int:session_id>/accepteer_alles')
@login_required
def accept_all(session_id):
    s = AdviceSession.query.get_or_404(session_id)
    motie = s.motie
    if motie.indiener_id != current_user.id:
        abort(403)
    # schrijf advies terug naar motie (ALLE wijzigingen)
    d = s.draft
    motie.titel = d.get("titel","")
    motie.toelichting = d.get("toelichting","")
    # TODO: ververs jouw lijsten/child-tabellen volgens je eigen model
    s.status = 'accepted'
    s.accepted_at = dt.datetime.utcnow()

    _notify(getattr(s.reviewer, 'id', None), motie.id, "advice_accepted",
            {"motie_titel": motie.titel, "session_id": s.id, "accepted_by": current_user.naam})
    db.session.commit()
    flash("Alle wijzigingen uit het advies zijn overgenomen.", "success")
    return redirect(url_for('moties.bekijken', motie_id=motie.id))
