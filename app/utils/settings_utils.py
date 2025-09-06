from app.models import Setting

def get_setting(key):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else None


import os
from werkzeug.utils import secure_filename
from flask import current_app
import uuid

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file, folder):
    if not file:
        return None

    if allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add a unique ID to prevent overwriting files
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', folder)
        os.makedirs(upload_folder, exist_ok=True)  # create folder if not exists
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        # Return relative path to store in DB
        return f"uploads/{folder}/{unique_filename}"
    else:
        raise ValueError("File type not allowed")
