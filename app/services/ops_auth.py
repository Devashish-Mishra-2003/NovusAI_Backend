import time
import requests
from typing import Optional
from app.config import settings

OPS_TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
USER_AGENT = "NovusAI/1.0 (contact: research@novusai.local)"

_access_token: Optional[str] = None
_token_expiry_ts: float = 0.0


def get_access_token() -> str:
    global _access_token, _token_expiry_ts

    now = time.time()
    if _access_token and now < _token_expiry_ts - 60:
        return _access_token

    resp = requests.post(
        OPS_TOKEN_URL,
        auth=(settings.CONSUMER_KEY, settings.CONSUMER_SECRET),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    resp.raise_for_status()

    data = resp.json()
    _access_token = data["access_token"]
    _token_expiry_ts = now + int(data.get("expires_in", 1200))
    return _access_token
