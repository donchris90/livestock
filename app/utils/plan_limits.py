# app/utils/plan_limits.py
PLAN_UPLOAD_LIMITS = {
    "Free": 2,
    "Basic": 10,
    "Premium": 100
}

def get_upload_limit(plan):
    return PLAN_UPLOAD_LIMITS.get(plan, 2)
