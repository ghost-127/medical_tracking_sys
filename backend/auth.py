from functools import wraps
from flask import request, jsonify
try:
    from backend.supabase_client import get_db_client, get_admin_client
except ImportError:
    from supabase_client import get_db_client, get_admin_client

def get_auth_token():
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ")[1]

def get_user_from_token(token):
    """Retrieve user and profile from Supabase Auth token or Dev token."""
    if token == "dev-token-admin":
        class DevUser:
            id = "00000000-0000-0000-0000-000000000000"
            email = "dev.admin@medipulse.org"
        dev_profile = {
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "Developer Admin",
            "role": "ADMIN",
            "department": "Engineering & Ops",
            "is_active": True
        }
        return DevUser(), dev_profile

    if token == "dev-token-nurse":
        class DevNurseUser:
            id = "11111111-1111-1111-1111-111111111111"
            email = "nurse@medipulse.org"
        dev_nurse_profile = {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Sarah Jenkins, RN",
            "role": "NURSE",
            "department": "Cardiology & ICU",
            "is_active": True
        }
        return DevNurseUser(), dev_nurse_profile


    supabase = get_db_client()   # anon client for auth.get_user
    db = get_admin_client()       # admin client for profiles table (bypasses RLS)
    try:
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            return None, None
        
        user_id = user_res.user.id
        profile_res = db.table('profiles').select('*').eq('id', user_id).execute()
        profile = profile_res.data[0] if profile_res.data else None
        
        return user_res.user, profile
    except Exception as e:
        print(f"Auth verification error: {e}")
        return None, None

def require_auth(allowed_roles=None):
    """
    Decorator to protect Flask routes.
    :param allowed_roles: List of allowed user roles e.g. ['ADMIN', 'NURSE']
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = get_auth_token()
            if not token:
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Missing or invalid Authorization header."
                }), 401
            
            user, profile = get_user_from_token(token)
            if not user or not profile:
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Invalid session token or profile not found."
                }), 401

            if not profile.get('is_active', True):
                return jsonify({
                    "error": "Forbidden",
                    "message": "Your account has been disabled."
                }), 403

            if allowed_roles and profile.get('role') not in allowed_roles:
                return jsonify({
                    "error": "Forbidden",
                    "message": f"Access denied. Requires one of roles: {allowed_roles}"
                }), 403

            request.current_user = user
            request.current_profile = profile
            return f(*args, **kwargs)
        return decorated_function
    return decorator
