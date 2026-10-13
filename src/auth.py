import os
import time
import json
import base64
import hmac
import hashlib
import struct
import shutil
import uuid
import urllib.parse
from typing import Optional, Tuple, Dict, Any
from src.database import get_user_setting, set_user_setting

# Universal session signing key (fallback to stable local key if not in env)
SERVER_SECRET_KEY = os.environ.get("SESSION_SECRET", "job-accel-auth-secret-key-2026-secure-session")

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

def create_session_token(role: str, identifier: str = "", max_age: int = 30 * 86400) -> str:
    """Create a signed HMAC stateless session token."""
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
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def resolve_guest_db_path(guest_id: str, master_db_path: str) -> str:
    """
    Return the isolated database path for a guest user.
    If the guest database does not exist, initialize a fresh, lightweight
    local database pre-populated with public seed jobs so Admin's personal
    data, notes, and applications are 100% protected and untouched.
    """
    base_dir = os.path.dirname(os.path.abspath(master_db_path))
    guests_dir = os.path.join(base_dir, "guests")
    os.makedirs(guests_dir, exist_ok=True)
    
    # Sanitize guest_id to alphanumeric only
    clean_id = "".join(c for c in guest_id if c.isalnum() or c in ("-", "_"))[:32]
    if not clean_id:
        clean_id = "sandbox"
        
    guest_db_path = os.path.join(guests_dir, f"guest_{clean_id}.db")
    
    # If not yet created, initialize fresh lightweight database with sample jobs
    if not os.path.exists(guest_db_path):
        from src.database import init_db
        from src.seed import seed_sample_data
        init_db(guest_db_path)
        try:
            seed_sample_data(guest_db_path)
        except Exception:
            pass
            
    return guest_db_path

def reset_guest_db(guest_id: str, master_db_path: str) -> str:
    """Re-clones a fresh sandbox database for the guest."""
    base_dir = os.path.dirname(os.path.abspath(master_db_path))
    guests_dir = os.path.join(base_dir, "guests")
    clean_id = "".join(c for c in guest_id if c.isalnum() or c in ("-", "_"))[:32]
    guest_db_path = os.path.join(guests_dir, f"guest_{clean_id}.db")
    if os.path.exists(guest_db_path):
        try:
            os.remove(guest_db_path)
        except Exception:
            pass
    return resolve_guest_db_path(guest_id, master_db_path)
