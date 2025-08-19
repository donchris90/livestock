import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user
from app.models import db, Product, User


dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

# -------------------------
# Allowed File Types
# -------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------
# Dashboard Home
# -------------------------


@dashboard_bp.route('/')
@login_required
def home():
    if current_user.role in ['buyer', 'seller']:
        return render_template('seller_dashboard/dashboard.html')
    elif current_user.role == 'agent':
        return redirect(url_for('agents.agent_dashboard'))
    elif current_user.role == 'vet':
        return redirect(url_for('vets.vet_dashboard'))
    elif current_user.role == 'logistics':
        return redirect(url_for('logistics.logistics_dashboard'))
    return "Invalid role", 403



# -------------------------
# Upload Product
# -------------------------
@dashboard_bp.route('/upload-product', methods=['GET', 'POST'])
@login_required
def upload_product():
    user = current_user

    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        type_ = request.form.get('type')
        state = request.form.get('state')
        city = request.form.get('city')
        quantity = request.form.get('quantity')
        description = request.form.get('description')
        price = request.form.get('price')
        open_to_negotiation = request.form.get('open_to_negotiation')
        phone_display = user.phone
        images = request.files.getlist('images')

        # Validate fields and image count
        if not all([title, category, type_, state, city, quantity, price, open_to_negotiation]) or len(images) < 3:
            flash("All fields are required and at least 3 images must be uploaded.", "danger")
            return redirect(url_for('dashboard.upload_product'))

        # Folder for storing images
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)

        image_paths = []
        for image in images[:5]:  # Max 5 images
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                unique_name = f"{uuid.uuid4()}_{filename}"
                save_path = os.path.join(upload_folder, unique_name)
                image.save(save_path)

                # Save path relative to static/
                image_paths.append(f'uploads/{unique_name}')
            else:
                flash("Only image files (jpg, png, gif) are allowed.", "danger")
                return redirect(url_for('dashboard.upload_product'))

        # Save product to database
        product = Product(
            user_id=user.id,
            title=title,
            category=category,
            type=type_,
            state=state,
            city=city,
            quantity=int(quantity),
            description=description,
            price=price,
            open_to_negotiation=open_to_negotiation,
            phone_display=phone_display,
            photos=image_paths
        )

        db.session.add(product)
        db.session.commit()
        flash("Product uploaded successfully!", "success")
        return redirect(url_for('dashboard.my_dashboard'))

    return render_template('upload_product.html', user=user)


# -------------------------
#  Product
# -------------------------
