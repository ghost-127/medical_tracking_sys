import os
from dotenv import load_dotenv

# Load .env with override so fresh values always win over stale env
load_dotenv(override=True)

class Config:
    @staticmethod
    def _get(key, default=None):
        """Always read from live os.environ (supports reload)."""
        return os.environ.get(key, default)

    @property
    def SUPABASE_URL(self):
        return os.environ.get('SUPABASE_URL')

    @property
    def SUPABASE_KEY(self):
        return os.environ.get('SUPABASE_KEY')

    @property
    def SUPABASE_SERVICE_KEY(self):
        return os.environ.get('SUPABASE_SERVICE_KEY')

    # Also expose as class-level for backwards compat (read at call time via staticmethod)
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')

    @staticmethod
    def validate():
        load_dotenv(override=True)
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')
        svc = os.environ.get('SUPABASE_SERVICE_KEY')
        if not url or not key:
            raise ValueError(
                "Missing SUPABASE_URL or SUPABASE_KEY in environment variables. "
                "Make sure you have a .env file in the project root."
            )
        if not svc:
            import warnings
            warnings.warn(
                "SUPABASE_SERVICE_KEY is not set. Write operations will be blocked by RLS.",
                stacklevel=2
            )
