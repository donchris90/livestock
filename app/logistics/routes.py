from flask import Blueprint, render_template
from flask_login import login_required

logistics_bp = Blueprint('logistics', __name__, url_prefix='/logistics')

@logistics_bp.route('/dashboard')
@login_required
def logistics_dashboard():
    return render_template('logistics/dashboard.html')
