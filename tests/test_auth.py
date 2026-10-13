import os
import tempfile
import sqlite3
from src.auth import (
    get_or_create_admin_totp_secret, verify_totp, 
    create_session_token, verify_session_token,
    resolve_guest_db_path, get_otpauth_uri, reset_guest_db
)
from src.database import init_db

def test_auth_and_isolation():
    with tempfile.TemporaryDirectory() as tmp:
        master_db = os.path.join(tmp, 'master.db')
        init_db(master_db)
        
        # 1. TOTP secret persistence
        secret = get_or_create_admin_totp_secret(master_db)
        assert len(secret) >= 16
        secret2 = get_or_create_admin_totp_secret(master_db)
        assert secret == secret2, "Secret must persist"
        
        # 2. OTPAuth URI
        uri = get_otpauth_uri(secret, "Louis Michael Ricafrente", "Job Accelerator")
        assert "otpauth://totp/" in uri
        assert secret in uri
        
        # 3. Session tokens
        tok_admin = create_session_token("admin", "louis")
        tok_guest = create_session_token("guest", "guest_abc123")
        
        payload_a = verify_session_token(tok_admin)
        assert payload_a is not None
        assert payload_a["role"] == "admin"
        
        payload_g = verify_session_token(tok_guest)
        assert payload_g is not None
        assert payload_g["role"] == "guest"
        assert payload_g["id"] == "guest_abc123"
        
        # 4. Guest DB isolation
        guest_db = resolve_guest_db_path("guest_abc123", master_db)
        assert os.path.exists(guest_db)
        assert os.path.abspath(guest_db) != os.path.abspath(master_db)
        
        # Write to guest db
        conn = sqlite3.connect(guest_db)
        conn.execute("CREATE TABLE guest_custom_marker (id INTEGER)")
        conn.commit()
        conn.close()
        
        # Verify master db has no such table
        conn_m = sqlite3.connect(master_db)
        tables = [r[0] for r in conn_m.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn_m.close()
        assert "guest_custom_marker" not in tables, "Master DB was modified by guest!"
        
        print("ALL AUTH & DATABASE ISOLATION TESTS PASSED!")

if __name__ == "__main__":
    test_auth_and_isolation()
