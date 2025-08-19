from app.models import Setting

def get_setting(key):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else None