import os
import tempfile
import json
import sqlite3
import bottle
from src.server import create_app
from src.database import init_db, insert_jobs, get_jobs
from src.auth import get_or_create_admin_totp_secret, verify_totp
import time, struct, hmac, hashlib, base64
import io

def generate_totp_for_secret(secret: str) -> str:
    secret_clean = secret.strip().replace(" ", "").upper()
    missing_padding = len(secret_clean) % 8
    if missing_padding:
        secret_clean += "=" * (8 - missing_padding)
    key = base64.b32decode(secret_clean, casefold=True)
    step = int(time.time()) // 30
    msg = struct.pack(">Q", step)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 0x0f
    token = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
    return f"{token:06d}"

def wsgi_request(app, method, path, body=None, cookie=None):
    headers_out = {}
    status_out = []
    def start_response(status, response_headers, exc_info=None):
        status_out.append(status)
        for k, v in response_headers:
            headers_out[k] = v

    body_bytes = b""
    if body is not None:
        if isinstance(body, dict):
            body_bytes = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body_bytes = body.encode("utf-8")

    query_string = ""
    if "?" in path:
        path, query_string = path.split("?", 1)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "CONTENT_LENGTH": str(len(body_bytes)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(body_bytes),
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    if cookie:
        environ["HTTP_COOKIE"] = cookie

    response_iter = app(environ, start_response)
    response_body = b"".join(response_iter).decode("utf-8")
    status_code = int(status_out[0].split()[0])
    parsed_json = None
    try:
        parsed_json = json.loads(response_body)
    except Exception:
        pass

    return {
        "status": status_code,
        "headers": headers_out,
        "body": response_body,
        "json": parsed_json
    }

def test_full_auth_and_guest_isolation():
    with tempfile.TemporaryDirectory() as tmp:
        master_db = os.path.join(tmp, "jobs.db")
        init_db(master_db)
        
        from src.models import Job
        test_job = Job(
            title="Android Developer",
            company="HeroApps",
            location="Remote",
            platform="JobStreet",
            tier=1,
            job_url="https://example.com/job1",
            salary="PHP 60,000",
            role_category="Mobile / Android",
            experience_level="Junior / Entry"
        )
        added, skipped = insert_jobs(master_db, [test_job])
        assert added == 1
        job_id = get_jobs(master_db)[0]["id"]

        
        app = create_app(master_db, guest_access_enabled=True)
        
        # 1. Unauthenticated request to /api/jobs -> 401
        res = wsgi_request(app, "GET", "/api/jobs")
        assert res["status"] == 401, f"Expected 401, got {res['status']}"
        
        # 2. Admin login with bad code -> 401
        res_bad = wsgi_request(app, "POST", "/api/auth/login-admin", body={"code": "000000"})
        assert res_bad["status"] == 401
        
        # 3. Admin login with valid TOTP -> 200
        admin_secret = get_or_create_admin_totp_secret(master_db)
        valid_code = generate_totp_for_secret(admin_secret)
        res_admin = wsgi_request(app, "POST", "/api/auth/login-admin", body={"code": valid_code})
        assert res_admin["status"] == 200
        assert res_admin["json"]["role"] == "admin"
        admin_token = res_admin["json"]["token"]
        
        # 4. Request with admin token -> 200
        res_jobs = wsgi_request(app, "GET", "/api/jobs", cookie=f"job_accel_session={admin_token}")
        assert res_jobs["status"] == 200
        assert len(res_jobs["json"]["jobs"]) == 1
        
        # 5. Guest Login -> 200
        res_guest = wsgi_request(app, "POST", "/api/auth/login-guest", body={})
        assert res_guest["status"] == 200
        assert res_guest["json"]["role"] == "guest"
        guest_token = res_guest["json"]["token"]
        
        # 6. Guest modifies job status to 'applied' with custom note
        cookie_guest = f"job_accel_session={guest_token}"
        res_mod = wsgi_request(app, "POST", f"/api/jobs/{job_id}/status", body={
            "status": "applied",
            "notes": "GUEST TEST NOTE - MUST NOT BE IN MASTER DB"
        }, cookie=cookie_guest)
        assert res_mod["status"] == 200
        
        # 7. Check guest views modified status
        res_guest_jobs = wsgi_request(app, "GET", "/api/jobs?status=applied", cookie=cookie_guest)
        assert res_guest_jobs["status"] == 200
        assert len(res_guest_jobs["json"]["jobs"]) == 1
        assert res_guest_jobs["json"]["jobs"][0]["notes"] == "GUEST TEST NOTE - MUST NOT BE IN MASTER DB"
        
        # 8. CRUCIAL CHECK: Verify MASTER DB is STILL in 'new' status and has NO guest note!
        master_jobs = get_jobs(master_db, status="new")
        assert len(master_jobs) == 1, "Master DB should still have the job in 'new' status!"
        assert master_jobs[0]["notes"] is None or master_jobs[0]["notes"] == "", "Master DB notes must NOT be modified by guest!"
        
        print("ALL TESTS PASSED: GUEST DATABASE IS COMPLETELY ISOLATED FROM MASTER DB!")

if __name__ == "__main__":
    test_full_auth_and_guest_isolation()
