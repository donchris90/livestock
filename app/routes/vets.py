
from ..models import db, User
from flask import Blueprint, request, jsonify, render_template, flash, url_for, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, Product, VerificationRequest, User, AgentProfile
from flask_login import login_required, current_user
from ..forms import AgentProfileForm

vets_bp = Blueprint('vet', __name__)
@vets_bp.route('/dashboard')
@login_required
def vet_dashboard():
    return render_template('vets/dashboard.html')
