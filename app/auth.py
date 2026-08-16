"""Single-login, signed-cookie session -- mirrors the sibling PO Bridge
app's own auth pattern, simplified further since this app only ever has
one real user (no tenant/admin split, no signup flow)."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import HTTPException, Request

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.app_secret_key, salt="sars-logbook-session")

COOKIE_NAME = "sars_logbook_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


class NotAuthenticated(Exception):
    """Raised by require_login for page routes; app.main's exception
    handler turns this into a redirect to /login."""


def create_session_cookie() -> str:
    return _serializer.dumps({"authenticated": True})


def is_valid_session(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    try:
        data = _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
        return bool(data.get("authenticated"))
    except (BadSignature, SignatureExpired):
        return False


def require_login(request: Request) -> None:
    """Dependency for server-rendered page routes -- redirects to /login."""
    if not is_valid_session(request.cookies.get(COOKIE_NAME)):
        raise NotAuthenticated()


def require_login_api(request: Request) -> None:
    """Dependency for JSON API routes -- returns a 401, no redirect (a
    redirect response makes no sense for a fetch() call from the PWA JS)."""
    if not is_valid_session(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Not authenticated")
