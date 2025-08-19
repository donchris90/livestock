from flask import Blueprint, render_template
from flask_login import login_required

vets_bp = Blueprint('vets', __name__, url_prefix='/vets')

@vets_bp.route('/dashboard')
@login_required
def vet_dashboard():
    return render_template('vets/dashboard.html')
