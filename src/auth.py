import os
import time
import json
import base64
import hmac
import hashlib
import struct
import secrets
import urllib.parse
from typing import Optional, Dict, Any
from src.database import get_user_setting, set_user_setting, get_db_connection

SERVER_SECRET_KEY = os.environ.get("SESSION_SECRET", "").strip()
if not SERVER_SECRET_KEY:
    if os.environ.get("VERCEL") or os.environ.get("RENDER"):
        raise RuntimeError("SESSION_SECRET must be configured before starting the web deployment")
    SERVER_SECRET_KEY = secrets.token_hex(48)

def _login_client_key(client_id: str) -> str:
    return hmac.new(SERVER_SECRET_KEY.encode(), client_id.encode("utf-8"), hashlib.sha256).hexdigest()

def admin_login_retry_after(db_path: str, client_id: str, max_attempts: int = 6, window_seconds: int = 900) -> int:
    """Return seconds until another admin login is allowed, or zero."""
    key = _login_client_key(client_id or "unknown")
    now = int(time.time())
    conn = get_db_connection(db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS admin_login_attempts (client_key TEXT PRIMARY KEY, window_started INTEGER NOT NULL, attempts INTEGER NOT NULL)")
        conn.execute("DELETE FROM admin_login_attempts WHERE window_started < ?", (now - window_seconds,))
        row = conn.execute("SELECT window_started, attempts FROM admin_login_attempts WHERE client_key = ?", (key,)).fetchone()
        if not row or row[0] <= now - window_seconds or row[1] < max_attempts:
            return 0
        return max(1, window_seconds - (now - row[0]))
    finally:
        conn.close()

def record_admin_login_failure(db_path: str, client_id: str, window_seconds: int = 900) -> None:
    key = _login_client_key(client_id or "unknown")
    now = int(time.time())
    cutoff = now - window_seconds
    conn = get_db_connection(db_path)
    try:
        conn.execute("""
            INSERT INTO admin_login_attempts (client_key, window_started, attempts)
            VALUES (?, ?, 1)
            ON CONFLICT(client_key) DO UPDATE SET
                window_started = CASE WHEN admin_login_attempts.window_started <= ? THEN excluded.window_started ELSE admin_login_attempts.window_started END,
                attempts = CASE WHEN admin_login_attempts.window_started <= ? THEN 1 ELSE admin_login_attempts.attempts + 1 END
        """, (key, now, cutoff, cutoff))
        conn.commit()
    finally:
        conn.close()

def clear_admin_login_failures(db_path: str, client_id: str) -> None:
    conn = get_db_connection(db_path)
    try:
        conn.execute("DELETE FROM admin_login_attempts WHERE client_key = ?", (_login_client_key(client_id or "unknown"),))
        conn.commit()
    finally:
        conn.close()

def generate_totp_secret() -> str:
    """Generate a clean 32-character Base32 secret string (A-Z, 2-7)."""
    raw = os.urandom(20)
    return base64.b32encode(raw).decode("utf-8").replace("=", "").upper()

def get_or_create_admin_totp_secret(db_path: str) -> str:
    """
    Retrieve admin TOTP secret from environment variable or master SQLite settings.
    If none exists, generate a persistent one and save it to SQLite.
    """
    env_secret = os.environ.get("ADMIN_TOTP_SECRET") or os.environ.get("TOTP_SECRET")
    if env_secret and len(env_secret.strip()) >= 16:
        return env_secret.strip().upper()

    existing = get_user_setting(db_path, "admin_totp_secret", "")
    if existing and len(existing.strip()) >= 16:
        return existing.strip().upper()

    new_secret = generate_totp_secret()
    set_user_setting(db_path, "admin_totp_secret", new_secret)
    return new_secret

def get_otpauth_uri(secret: str, account_name: str = "Louis Michael Ricafrente", issuer: str = "Job Accelerator") -> str:
    """Build standard otpauth:// URI for Google Authenticator QR Code."""
    account_encoded = urllib.parse.quote(account_name)
    issuer_encoded = urllib.parse.quote(issuer)
    return f"otpauth://totp/{issuer_encoded}:{account_encoded}?secret={secret}&issuer={issuer_encoded}&algorithm=SHA1&digits=6&period=30"

def verify_totp(secret: str, code: str, window: int = 2) -> bool:
    """
    Verify RFC 6238 TOTP 6-digit code against base32 secret.
    Window = 2 checks ±60 seconds to accommodate minor time drifts.
    """
    if not code:
        return False
    code_str = str(code).strip().replace(" ", "")
    if len(code_str) != 6 or not code_str.isdigit():
        return False

    secret_clean = secret.strip().replace(" ", "").upper()
    missing_padding = len(secret_clean) % 8
    if missing_padding:
        secret_clean += "=" * (8 - missing_padding)

    try:
        key = base64.b32decode(secret_clean, casefold=True)
    except Exception:
        return False

    current_step = int(time.time()) // 30
    for offset in range(-window, window + 1):
        step = current_step + offset
        msg = struct.pack(">Q", step)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset_idx = h[19] & 0x0f
        code_int = (struct.unpack(">I", h[offset_idx:offset_idx+4])[0] & 0x7fffffff) % 1000000
        if f"{code_int:06d}" == code_str:
            return True
    return False

def create_session_token(role: str, identifier: str = "", max_age: int = 30 * 86400, expiry_hours: Optional[int] = None) -> str:
    """Create a signed HMAC stateless session token."""
    if expiry_hours is not None:
        max_age = expiry_hours * 3600
    payload_data = {
        "role": role,
        "id": identifier,
        "exp": int(time.time()) + max_age
    }
    raw_payload = json.dumps(payload_data, separators=(",", ":"))
    b64_payload = base64.urlsafe_b64encode(raw_payload.encode()).decode().rstrip("=")
    sig = hmac.new(SERVER_SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"

def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a signed HMAC session token."""
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, sig = parts
        expected_sig = hmac.new(SERVER_SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # Restore base64 padding
        rem = len(b64_payload) % 4
        if rem:
            b64_payload += "=" * (4 - rem)

        payload = json.loads(base64.urlsafe_b64decode(b64_payload.encode()).decode())
        if not isinstance(payload, dict):
            return None
        if payload.get("role") not in ("admin", "guest"):
            return None
        if not isinstance(payload.get("id"), str) or not payload["id"]:
            return None
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
