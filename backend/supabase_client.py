import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Force reload of .env every time this module is imported
load_dotenv(override=True)

try:
    from backend.config import Config
except ImportError:
    from config import Config


def get_db_client() -> Client:
    """
    Returns an anon Supabase client (uses publishable key).
    Use ONLY for supabase.auth.* operations (sign_in, sign_up, get_user).
    """
    load_dotenv(override=True)
    return create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)


def get_admin_client() -> Client:
    """
    Returns a service-role Supabase client that bypasses Row-Level Security (RLS).
    Use for ALL server-side table INSERT / UPDATE / SELECT operations.
    NEVER expose the service role key to the frontend.
    """
    load_dotenv(override=True)
    svc_key = os.environ.get('SUPABASE_SERVICE_KEY') or Config.SUPABASE_KEY
    if not os.environ.get('SUPABASE_SERVICE_KEY'):
        import warnings
        warnings.warn(
            "SUPABASE_SERVICE_KEY is not set. Write operations may be blocked by RLS.",
            stacklevel=2
        )
    return create_client(Config.SUPABASE_URL, svc_key)
