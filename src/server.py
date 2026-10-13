import os
import json
import uuid
import hashlib
import hmac
import bottle
from src.database import (
    get_jobs, update_job_status, get_stats, export_jobs_csv, 
    get_user_setting, set_user_setting, get_all_user_settings
)
from src.aggregator import Aggregator
from src.auth import (
    get_or_create_admin_totp_secret, verify_totp, get_otpauth_uri,
    create_session_token, verify_session_token,
    resolve_guest_db_path, reset_guest_db
)

def create_app(db_path: str = "data/jobs.db") -> bottle.Bottle:
    app = bottle.Bottle()
    aggregator = Aggregator(db_path=db_path)

    # Pre-initialize master admin TOTP secret so it exists in database
    get_or_create_admin_totp_secret(db_path)

    @app.hook("after_request")
    def enable_cors_and_nocache():
        bottle.response.headers["Access-Control-Allow-Origin"] = "*"
        bottle.response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
        bottle.response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-Token"
        bottle.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        bottle.response.headers["Pragma"] = "no-cache"
        bottle.response.headers["Expires"] = "0"

    def get_current_session():
        token = bottle.request.get_cookie("job_accel_session")
        if not token:
            auth_hdr = bottle.request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                token = auth_hdr.split(" ", 1)[1].strip()
        if not token:
            token = bottle.request.headers.get("X-Session-Token")
        if not token:
            token = bottle.request.query.get("session_token")
        if not token:
            return None
        return verify_session_token(token)

    def resolve_target_db() -> str:
        session = get_current_session()
        if session and session.get("role") == "guest":
            guest_id = session.get("id") or "guest_sandbox"
            return resolve_guest_db_path(guest_id, db_path)
        # Default / Admin points strictly to master db_path
        return db_path

    def require_auth():
        session = get_current_session()
        if not session:
            bottle.response.status = 401
            bottle.response.content_type = "application/json"
            return json.dumps({
                "error": "Unauthorized", 
                "auth_required": True,
                "message": "Authentication required. Log in with Google Authenticator or continue as Guest."
            })
        return None

    # -------------------------------------------------------------------------
    # AUTHENTICATION & ACCESS CONTROL ENDPOINTS
    # -------------------------------------------------------------------------
    @app.route("/api/auth/status", method=["GET", "OPTIONS"])
    def api_auth_status():
        if bottle.request.method == "OPTIONS":
            return ""
        session = get_current_session()
        bottle.response.content_type = "application/json"
        if not session:
            return json.dumps({
                "authenticated": False,
                "role": None,
                "guest_id": None,
                "is_admin": False
            })
        return json.dumps({
            "authenticated": True,
            "role": session.get("role"),
            "guest_id": session.get("id"),
            "is_admin": session.get("role") == "admin"
        })

    @app.route("/api/auth/setup", method=["GET", "OPTIONS"])
    def api_auth_setup():
        if bottle.request.method == "OPTIONS":
            return ""
        admin_secret = get_or_create_admin_totp_secret(db_path)
        otpauth_uri = get_otpauth_uri(admin_secret, "Louis Michael Ricafrente", "Job Accelerator")
        bottle.response.content_type = "application/json"
        return json.dumps({
            "secret": admin_secret,
            "otpauth_uri": otpauth_uri,
            "issuer": "Job Accelerator",
            "account": "Louis Michael Ricafrente"
        })

    def _verify_admin_credentials(user_val: str, pass_val: str) -> bool:
        if not user_val or not pass_val:
            return False
        env_user = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
        if user_val.strip().lower() != env_user:
            return False
        env_pwd = os.environ.get("ADMIN_PASSWORD")
        if env_pwd:
            return hmac.compare_digest(pass_val.strip(), env_pwd.strip())
        # Cryptographic salted PBKDF2 hash (source code safe: zero plain text password)
        salt = b"job_accelerator_auth_salt_2026"
        calc = hashlib.pbkdf2_hmac("sha256", pass_val.strip().encode("utf-8"), salt, 100000).hex()
        EXPECTED_HASH = "fd73cf8251fafa8faad80e4691722757acbf7fd0f9a08f52b7b788662b667909"
        return hmac.compare_digest(calc, EXPECTED_HASH)

    @app.route("/api/auth/login-admin", method=["POST", "OPTIONS"])
    def api_login_admin():
        if bottle.request.method == "OPTIONS":
            return ""
        data = bottle.request.json or {}
        username = str(data.get("username", "")).strip().lower()
        password = str(data.get("password", "")).strip()
        code = str(data.get("code", "")).strip()

        # Cryptographic verification: zero plain text password in source code
        is_valid = _verify_admin_credentials(username or "admin", password or code)
        
        if not is_valid:
            bottle.response.status = 401
            bottle.response.content_type = "application/json"
            return json.dumps({
                "success": False, 
                "error": "Invalid username or password."
            })
            
        # 1-year persistent session token
        token = create_session_token("admin", "louis_admin", max_age=365 * 86400)
        bottle.response.set_cookie("job_accel_session", token, path="/", max_age=365 * 86400, httponly=False, samesite="Lax")
        bottle.response.content_type = "application/json"
        return json.dumps({
            "success": True,
            "role": "admin",
            "token": token,
            "message": "Welcome back, Admin! Session saved permanently."
        })


    @app.route("/api/auth/login-guest", method=["POST", "OPTIONS"])
    def api_login_guest():
        if bottle.request.method == "OPTIONS":
            return ""
        guest_id = f"guest_{uuid.uuid4().hex[:10]}"
        # Ensure fresh isolated guest database clone is created
        resolve_guest_db_path(guest_id, db_path)
        token = create_session_token("guest", guest_id)
        bottle.response.set_cookie("job_accel_session", token, path="/", max_age=30*86400, httponly=False, samesite="Lax")
        bottle.response.content_type = "application/json"
        return json.dumps({
            "success": True,
            "role": "guest",
            "guest_id": guest_id,
            "token": token,
            "message": "Guest sandbox database initialized. Your changes are private and will not affect the Admin database."
        })

    @app.route("/api/auth/reset-sandbox", method=["POST", "OPTIONS"])
    def api_reset_sandbox():
        if bottle.request.method == "OPTIONS":
            return ""
        session = get_current_session()
        if not session or session.get("role") != "guest":
            bottle.response.status = 400
            bottle.response.content_type = "application/json"
            return json.dumps({"success": False, "error": "Sandbox reset is only available for guest sessions."})
            
        guest_id = session.get("id", "guest_sandbox")
        reset_guest_db(guest_id, db_path)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "message": "Guest sandbox re-cloned to fresh state."})

    @app.route("/api/auth/logout", method=["POST", "OPTIONS"])
    def api_logout():
        if bottle.request.method == "OPTIONS":
            return ""
        bottle.response.set_cookie("job_accel_session", "", path="/", max_age=0, httponly=False, samesite="Lax")
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "message": "Logged out and dashboard locked."})

    # -------------------------------------------------------------------------
    # CORE JOB ACCELERATOR DATA API (SESSION-ROUTED TO MASTER OR GUEST DB)
    # -------------------------------------------------------------------------
    @app.route("/api/jobs/export/csv", method="GET")
    def api_export_csv():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()
        status = bottle.request.query.get("status", "applied")
        csv_text = export_jobs_csv(target_db, status=status)
        bottle.response.content_type = "text/csv; charset=utf-8"
        bottle.response.headers["Content-Disposition"] = 'attachment; filename="job_applications.csv"'
        return csv_text

    @app.route("/api/jobs", method="GET")
    def api_get_jobs():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()

        status = bottle.request.query.get("status", "new")
        role = bottle.request.query.get("role", "All")
        level = bottle.request.query.get("experience_level", "All")
        tier_str = bottle.request.query.get("tier", "")
        search = bottle.request.query.get("search", "")
        date_filter = bottle.request.query.get("date_filter", "all")
        has_salary = bottle.request.query.get("has_salary", "0") in ("1", "true", "True")
        remote_only = bottle.request.query.get("remote_only", "0") in ("1", "true", "True")
        hide_senior = bottle.request.query.get("hide_senior", "0") in ("1", "true", "True")
        include_va = bottle.request.query.get("include_va", "0") in ("1", "true", "True")
        platform = bottle.request.query.get("platform", "All")
        tier = int(tier_str) if tier_str.isdigit() else None

        query_status = status

        jobs = get_jobs(
            db_path=target_db,
            status=query_status if status != "all" else None,
            role_category=role,
            experience_level=level,
            tier=tier,
            search=search,
            date_filter=date_filter,
            has_salary=has_salary,
            remote_only=remote_only,
            hide_senior=hide_senior,
            include_va=include_va,
            platform=platform,
            limit=200
        )
        bottle.response.content_type = "application/json"
        return json.dumps({"jobs": jobs, "count": len(jobs)})

    @app.route("/api/jobs/<job_id:int>/status", method=["POST", "PUT"])
    def api_update_status(job_id: int):
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()

        data = bottle.request.json or {}
        new_status = data.get("status")
        notes = data.get("notes")
        pipeline_stage = data.get("stage") or data.get("pipeline_stage")
        follow_up_date = data.get("follow_up_date")
        success = update_job_status(
            db_path=target_db,
            job_id=job_id,
            status=new_status,
            notes=notes,
            pipeline_stage=pipeline_stage,
            follow_up_date=follow_up_date
        )
        bottle.response.content_type = "application/json"
        return json.dumps({"success": success})

    @app.route("/api/stats", method="GET")
    def api_get_stats():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()
        stats = get_stats(target_db)
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    DEFAULT_TARGET_STACK = "Kotlin, Jetpack Compose, React, Next.js, TypeScript, Node.js, Express, MySQL, Tailwind CSS, Junior / Entry"

    @app.route("/api/settings", method=["GET", "OPTIONS"])
    def api_get_all_settings():
        if bottle.request.method == "OPTIONS":
            return ""
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()

        settings = get_all_user_settings(target_db)
        if "target_stack" not in settings:
            settings["target_stack"] = DEFAULT_TARGET_STACK
        bottle.response.content_type = "application/json"
        return json.dumps(settings)

    @app.route("/api/settings", method=["POST", "PUT"])
    def api_save_settings():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()

        data = bottle.request.json or {}
        for k, v in data.items():
            # Don't allow guest to overwrite master admin_totp_secret
            if k == "admin_totp_secret":
                continue
            val_str = json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
            set_user_setting(target_db, str(k), val_str)
        settings = get_all_user_settings(target_db)
        if "target_stack" not in settings:
            settings["target_stack"] = DEFAULT_TARGET_STACK
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "settings": settings})

    @app.route("/api/settings/stack", method=["GET", "OPTIONS"])
    def api_get_stack_setting():
        if bottle.request.method == "OPTIONS":
            return ""
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()

        stack = get_user_setting(target_db, "target_stack", DEFAULT_TARGET_STACK)
        bottle.response.content_type = "application/json"
        return json.dumps({"stack": stack})

    @app.route("/api/settings/stack", method=["POST", "PUT"])
    def api_save_stack_setting():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()

        data = bottle.request.json or {}
        stack = data.get("stack", "")
        if isinstance(stack, list):
            stack = ", ".join(str(s).strip() for s in stack if str(s).strip())
        elif isinstance(stack, str):
            stack = stack.strip()

        set_user_setting(target_db, "target_stack", stack)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "stack": stack})

    # System cron & automated daily digest runs against master database (Admin or internal Vercel Cron only)
    @app.route("/api/notify/daily", method=["GET", "POST"])
    def api_notify_daily():
        session = get_current_session()
        is_cron = bool(bottle.request.headers.get("x-vercel-cron"))
        if not is_cron and (not session or session.get("role") != "admin"):
            bottle.response.status = 403
            bottle.response.content_type = "application/json"
            return json.dumps({
                "success": False,
                "error": "Forbidden: Only Admin can trigger email digests to michael18ricafrente@gmail.com."
            })
        try:
            from scripts.daily_notifier import send_daily_email
            result = send_daily_email(db_path)
        except Exception as e:
            result = {"success": False, "error": str(e)}
        bottle.response.content_type = "application/json"
        return json.dumps(result)

    @app.route("/api/sync/status", method="GET")
    def api_sync_status():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        bottle.response.content_type = "application/json"
        telemetry = aggregator.get_telemetry()
        telemetry["last_result"] = aggregator.last_sync_result
        return json.dumps(telemetry)

    @app.route("/api/sync", method=["POST", "OPTIONS"])
    def api_sync():
        if bottle.request.method == "OPTIONS":
            return ""
        auth_err = require_auth()
        if auth_err:
            return auth_err

        session = get_current_session()
        # Strictly admin only! Adding/harvesting jobs is reserved exclusively for Admin.
        if not session or session.get("role") != "admin":
            bottle.response.status = 403
            bottle.response.content_type = "application/json"
            return json.dumps({
                "status": "forbidden",
                "error": "Forbidden: Only Admin can harvest and add new job opportunities to the system. Guests can explore, filter, save, and star existing opportunities.",
                "is_admin_only": True
            })

        data = bottle.request.json or {}
        keywords = data.get("keywords")
        is_background = data.get("background", False) or (bottle.request.query.get("background") in ("1", "true"))
        force = data.get("force", False)

        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        if is_background:
            started = aggregator.start_background_sync(queries=keywords if keywords else None, force=force)
            bottle.response.content_type = "application/json"
            return json.dumps({
                "status": "started" if started else "already_syncing",
                "is_syncing": True,
                "message": "Background sync started." if started else "Sync already running in background."
            })

        stats = aggregator.run_sync(queries=keywords if keywords else None, force=force)
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    @app.route("/")
    def index():
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return bottle.static_file("index.html", root=static_dir)

    @app.route("/favicon.ico")
    def favicon_ico():
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return bottle.static_file("favicon.ico", root=static_dir)

    @app.route("/favicon.svg")
    def favicon_svg():
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return bottle.static_file("favicon.svg", root=static_dir, mimetype="image/svg+xml")

    @app.route("/apple-touch-icon.png")
    def apple_touch_icon():
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return bottle.static_file("apple-touch-icon.png", root=static_dir)

    @app.route("/static/<filepath:path>")
    def static_files(filepath: str):
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return bottle.static_file(filepath, root=static_dir)

    return app
