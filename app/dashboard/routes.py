from flask import Flask, render_template
from flask_login import login_required, current_user
from app.dashboard import bp    


@bp.route('/')
def home():
    return render_template('dashboard/index.html', title="Dashboard")