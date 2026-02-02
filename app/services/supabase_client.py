from supabase import create_client, Client
from app.config import settings

SUPABASE_URL = settings.SUPABASE_URL
if not SUPABASE_URL.endswith("/"):
    SUPABASE_URL += "/"

supabase: Client = create_client(
    SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY
)
