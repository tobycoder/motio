from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from app.admin import bp
from app.auth.utils import roles_required, login_and_active_required
from app import db
from app.models import Tenant, TenantDomain
from werkzeug.utils import secure_filename
import os
import json


@bp.route('/')
@login_and_active_required
@roles_required('superadmin')
def index():
    return redirect(url_for('admin.tenants_index'))


@bp.route('/tenants')
@login_and_active_required
@roles_required('superadmin')
def tenants_index():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    return render_template('admin/tenants/index.html', tenants=tenants)


@bp.route('/tenants/new', methods=['GET', 'POST'])
@login_and_active_required
@roles_required('superadmin')
def tenants_new():
    if request.method == 'POST':
        slug = (request.form.get('slug') or '').strip()
        naam = (request.form.get('naam') or '').strip()
        actief = True if request.form.get('actief') == 'on' else False
        domains_raw = (request.form.get('domains') or '').strip()
        settings_raw = (request.form.get('settings') or '').strip() or '{}'
        # UI fields (geen JSON vereist)
        phr_over = (request.form.get('phrasing_overwegende') or '').strip() or 'Overwegende dat'
        phr_cons = (request.form.get('phrasing_constaterende') or '').strip() or 'Constaterende dat'
        phr_dcop = (request.form.get('phrasing_draagt') or '').strip() or 'Draagt college op'
        color1 = (request.form.get('brand_color1') or '').strip()
        color2 = (request.form.get('brand_color2') or '').strip()
        color3 = (request.form.get('brand_color3') or '').strip()
        logo_file = request.files.get('logo_file')
        # Optioneel: eenvoudige install-koppeling in settings
        install_url = (request.form.get('install_url') or '').strip()
        install_key = (request.form.get('install_key') or '').strip()

        if not slug or not naam:
            flash('Slug en naam zijn verplicht.', 'warning')
            return redirect(url_for('admin.tenants_new'))

        if Tenant.query.filter(Tenant.slug.ilike(slug)).first():
            flash('Slug bestaat al.', 'danger')
            return redirect(url_for('admin.tenants_new'))

        # Start met eventueel meegegeven JSON en overschrijf met UI-velden
        try:
            settings = json.loads(settings_raw) if settings_raw else {}
            if not isinstance(settings, dict):
                settings = {}
        except Exception:
            settings = {}

        settings.setdefault('phrasing', {})
        settings['phrasing'].update({
            'overwegende': phr_over,
            'constaterende': phr_cons,
            'draagt_op': phr_dcop,
        })
        settings.setdefault('brand', {})
        def _norm_hex(x: str | None) -> str | None:
            if not x:
                return None
            x = x.strip()
            if not x:
                return None
            if not x.startswith('#'):
                x = '#' + x
            return x

        color1 = _norm_hex(color1)
        color2 = _norm_hex(color2)
        color3 = _norm_hex(color3)

        if color1:
            settings['brand']['color1'] = color1
            # compat: zet ook 'color' voor bestaande templates
            settings['brand']['color'] = color1
        if color2:
            settings['brand']['color2'] = color2
        if color3:
            settings['brand']['color3'] = color3

        if install_url or install_key:
            settings.setdefault('install', {})
            if install_url:
                settings['install']['url'] = install_url
            if install_key:
                settings['install']['key'] = install_key

        t = Tenant(slug=slug, naam=naam, actief=actief, settings=settings)
        db.session.add(t)
        db.session.flush()  # zodat t.id bestaat voor domains

        # Domains, gescheiden door newline/komma/spaties
        if domains_raw:
            # splits op niet-alfanumerieke scheidingstekens
            seps = [',', ';', '\n']
            tmp = domains_raw
            for s in seps:
                tmp = tmp.replace(s, ' ')
            for host in [x.strip() for x in tmp.split(' ') if x.strip()]:
                db.session.add(TenantDomain(tenant_id=t.id, hostname=host.lower()))

        # Logo upload (geen URL): sla op onder static/tenants/<slug>/logo.<ext>
        if logo_file and logo_file.filename:
            filename = secure_filename(logo_file.filename)
            # Beperk extensies
            ext = os.path.splitext(filename)[1].lower()
            if ext not in {'.png', '.jpg', '.jpeg', '.svg', '.webp'}:
                flash('Logo moet een van de volgende types zijn: PNG, JPG, SVG, WEBP.', 'danger')
                return redirect(url_for('admin.tenants_new'))
            tenant_dir = os.path.join(current_app.static_folder, 'tenants', slug)
            os.makedirs(tenant_dir, exist_ok=True)
            logo_name = f"logo{ext}"
            save_path = os.path.join(tenant_dir, logo_name)
            logo_file.save(save_path)
            # Zet bronpad zodat templates exact bestand vinden
            new_settings = dict(t.settings or {})
            new_settings['logo_src'] = f"/static/tenants/{slug}/{logo_name}"
            t.settings = new_settings

        db.session.commit()
        flash('Tenant aangemaakt.', 'success')
        return redirect(url_for('admin.tenants_edit', tenant_id=t.id))

    return render_template('admin/tenants/new.html')


@bp.route('/tenants/<int:tenant_id>/edit', methods=['GET', 'POST'])
@login_and_active_required
@roles_required('superadmin')
def tenants_edit(tenant_id: int):
    t = Tenant.query.get_or_404(tenant_id)
    if request.method == 'POST':
        naam = (request.form.get('naam') or '').strip()
        actief = True if request.form.get('actief') == 'on' else False
        settings_raw = (request.form.get('settings') or '').strip() or '{}'
        add_domain = (request.form.get('add_domain') or '').strip().lower()
        install_url = (request.form.get('install_url') or '').strip()
        install_key = (request.form.get('install_key') or '').strip()
        # UI fields
        phr_over = (request.form.get('phrasing_overwegende') or '').strip() or 'Overwegende dat'
        phr_cons = (request.form.get('phrasing_constaterende') or '').strip() or 'Constaterende dat'
        phr_dcop = (request.form.get('phrasing_draagt') or '').strip() or 'Draagt college op'
        color1 = (request.form.get('brand_color1') or '').strip()
        color2 = (request.form.get('brand_color2') or '').strip()
        color3 = (request.form.get('brand_color3') or '').strip()
        logo_file = request.files.get('logo_file')

        if not naam:
            flash('Naam is verplicht.', 'warning')
            return redirect(url_for('admin.tenants_edit', tenant_id=t.id))

        # Lees bestaande settings en merge met eventueel tekstveld
        try:
            extra = json.loads(settings_raw) if settings_raw else {}
            if not isinstance(extra, dict):
                extra = {}
        except Exception:
            extra = {}
        settings = dict(t.settings or {})
        # merge extra
        settings.update(extra)

        if install_url or install_key:
            settings.setdefault('install', {})
            if install_url:
                settings['install']['url'] = install_url
            if install_key:
                settings['install']['key'] = install_key

        t.naam = naam
        t.actief = actief
        # UI fields naar settings
        settings.setdefault('phrasing', {})
        settings['phrasing'].update({
            'overwegende': phr_over,
            'constaterende': phr_cons,
            'draagt_op': phr_dcop,
        })
        settings.setdefault('brand', {})
        def _norm_hex(x: str | None) -> str | None:
            if not x:
                return None
            x = x.strip()
            if not x:
                return None
            if not x.startswith('#'):
                x = '#' + x
            return x

        color1 = _norm_hex(color1)
        color2 = _norm_hex(color2)
        color3 = _norm_hex(color3)

        if color1:
            settings['brand']['color1'] = color1
            settings['brand']['color'] = color1
        if color2:
            settings['brand']['color2'] = color2
        if color3:
            settings['brand']['color3'] = color3
        t.settings = settings

        if add_domain:
            if not TenantDomain.query.filter(TenantDomain.hostname.ilike(add_domain)).first():
                db.session.add(TenantDomain(tenant_id=t.id, hostname=add_domain))
            else:
                flash('Domein bestaat al.', 'warning')

        # Logo upload (vervangt bestaand logo indien geüpload)
        if logo_file and logo_file.filename:
            filename = secure_filename(logo_file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in {'.png', '.jpg', '.jpeg', '.svg', '.webp'}:
                flash('Logo moet een van de volgende types zijn: PNG, JPG, SVG, WEBP.', 'danger')
                return redirect(url_for('admin.tenants_edit', tenant_id=t.id))
            slug = t.slug
            tenant_dir = os.path.join(current_app.static_folder, 'tenants', slug)
            os.makedirs(tenant_dir, exist_ok=True)
            logo_name = f"logo{ext}"
            save_path = os.path.join(tenant_dir, logo_name)
            logo_file.save(save_path)
            new_settings = dict(t.settings or {})
            new_settings['logo_src'] = f"/static/tenants/{slug}/{logo_name}"
            t.settings = new_settings

        db.session.commit()
        flash('Tenant opgeslagen.', 'success')
        return redirect(url_for('admin.tenants_edit', tenant_id=t.id))

    domains = TenantDomain.query.filter(TenantDomain.tenant_id == t.id).order_by(TenantDomain.hostname.asc()).all()
    return render_template('admin/tenants/edit.html', tenant=t, domains=domains)


@bp.route('/tenants/<int:tenant_id>/domains/<int:domain_id>/delete', methods=['POST'])
@login_and_active_required
@roles_required('superadmin')
def tenants_domain_delete(tenant_id: int, domain_id: int):
    t = Tenant.query.get_or_404(tenant_id)
    d = TenantDomain.query.get_or_404(domain_id)
    if d.tenant_id != t.id:
        flash('Ongeldig domein.', 'danger')
        return redirect(url_for('admin.tenants_edit', tenant_id=t.id))
    db.session.delete(d)
    db.session.commit()
    flash('Domein verwijderd.', 'success')
    return redirect(url_for('admin.tenants_edit', tenant_id=t.id))
