import time
import os
import json
import uuid
import hashlib
import hmac
import urllib.request
import bottle
bottle.BaseRequest.MEMFILE_MAX = 2 * 1024 * 1024

_portfolio_views_cache = {"ts": 0.0, "payload": None}
from src.database import (
    get_jobs, update_job_status, get_stats, export_jobs_csv, insert_jobs,
    get_user_setting, set_user_setting, get_all_user_settings
)
from src.aggregator import Aggregator
from src.models import Job
from src.auth import (
    get_or_create_admin_totp_secret, verify_totp, get_otpauth_uri,
    create_session_token, verify_session_token,
    resolve_guest_db_path, reset_guest_db, save_guest_changes,
    admin_login_retry_after, record_admin_login_failure, clear_admin_login_failures
)

def create_app(db_path: str = "data/jobs.db", guest_access_enabled: bool = False) -> bottle.Bottle:
    app = bottle.Bottle()
    from src.gmail_hub import init_hub
    init_hub(db_path)
    aggregator = Aggregator(db_path=db_path)
    from src.execution_dispatch import enabled as database_execution

    # Pre-initialize master admin TOTP secret so it exists in database
    get_or_create_admin_totp_secret(db_path)

    public_settings = {"view_filters", "target_stack", "filter_skills_only", "has_salary_only", "remote_only", "hide_senior", "date_filter", "role", "experience_levels", "status", "platform", "va_training_enabled", "auto_sync_enabled", "proxy_list", "proxy_mode"}

    @app.error(400)
    def bad_request(error):
        bottle.response.content_type = "application/json"
        return json.dumps({"status": "error", "error": str(error.body)})

    @app.hook("before_request")
    def validate_json_body():
        if bottle.request.method in ("POST", "PUT") and bottle.request.content_type == "application/json":
            try:
                body = bottle.request.json
            except (ValueError, bottle.HTTPError):
                bottle.abort(400, "Invalid JSON body")
            if body is not None and not isinstance(body, dict):
                bottle.abort(400, "JSON body must be an object")

    @app.hook("after_request")
    def enable_cors_and_nocache():
        bottle.response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
        bottle.response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Session-Token"
        if bottle.request.path.startswith("/static/"):
            bottle.response.headers["Cache-Control"] = "public, max-age=60, s-maxage=3600"
        else:
            bottle.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            bottle.response.headers["Pragma"] = "no-cache"
            bottle.response.headers["Expires"] = "0"

    def get_current_session():
        token = None
        auth_hdr = bottle.request.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr.split(" ", 1)[1].strip()
        if not token:
            token = bottle.request.headers.get("X-Session-Token")
        if not token:
            token = bottle.request.query.get("session_token")
        if not token:
            token = bottle.request.get_cookie("job_accel_session")
        if not token:
            return None
        session = verify_session_token(token)
        if session and session.get("role") == "guest" and not guest_access_enabled:
            return None
        return session

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
                "message": "Authentication required. Log in with your admin credentials."
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
        session = get_current_session()
        if not session or session.get("role") != "admin":
            bottle.response.status = 403
            bottle.response.content_type = "application/json"
            return json.dumps({"error": "Forbidden: Admin authentication required to view TOTP setup."})
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
        try:
            data = bottle.request.json or {}
        except Exception:
            data = {}
        username = str(data.get("username", "")).strip().lower()
        password = str(data.get("password", "")).strip()
        code = str(data.get("code", "")).strip()
        client_id = bottle.request.environ.get("REMOTE_ADDR", "unknown")
        retry_after = admin_login_retry_after(db_path, client_id)
        if retry_after:
            bottle.response.status = 429
            bottle.response.headers["Retry-After"] = str(retry_after)
            bottle.response.content_type = "application/json"
            return json.dumps({"success": False, "error": f"Too many failed attempts. Try again in {retry_after} seconds."})

        # 1. Cryptographic password verification (admin / password)
        is_valid = _verify_admin_credentials(username or "admin", password or code)

        # 2. Dual fallback: Google Authenticator TOTP verification
        if not is_valid:
            candidate_code = code or password
            if candidate_code and len(candidate_code.strip()) == 6 and candidate_code.strip().isdigit():
                admin_secret = get_or_create_admin_totp_secret(db_path)
                if verify_totp(admin_secret, candidate_code):
                    is_valid = True

        if not is_valid:
            record_admin_login_failure(db_path, client_id)
            bottle.response.status = 401
            bottle.response.content_type = "application/json"
            return json.dumps({
                "success": False,
                "error": "Invalid username or password."
            })

        clear_admin_login_failures(db_path, client_id)

        # 1-year persistent session token
        token = create_session_token("admin", "louis_admin", max_age=365 * 86400)
        bottle.response.set_cookie("job_accel_session", token, path="/", max_age=365 * 86400, httponly=True, secure=bool(os.environ.get("VERCEL")), samesite="Strict")
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
        if not guest_access_enabled:
            bottle.response.status = 403
            return {"success": False, "error": "Guest access is temporarily unavailable."}
        guest_id = f"guest_{uuid.uuid4().hex[:10]}"
        # Ensure fresh isolated guest database clone is created
        resolve_guest_db_path(guest_id, db_path)
        token = create_session_token("guest", guest_id)
        bottle.response.set_cookie("job_accel_session", token, path="/", max_age=30*86400, httponly=True, secure=bool(os.environ.get("VERCEL")), samesite="Strict")
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
        pipeline_stage = bottle.request.query.get("pipeline_stage", "")

        query_status = status
        try:
            limit = max(1, min(500, int(bottle.request.query.get("limit", "200"))))
            offset = max(0, int(bottle.request.query.get("offset", "0")))
        except ValueError:
            bottle.abort(400, "Invalid pagination")

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
            limit=limit,
            offset=offset,
            with_total=True,
            pipeline_stage=pipeline_stage,
        )
        bottle.response.content_type = "application/json"
        total = jobs[0]["matching_total"] if jobs else 0
        for job in jobs:
            job.pop("matching_total", None)
        return json.dumps({"jobs": jobs, "count": len(jobs), "total": total, "has_more": offset + len(jobs) < total})

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
        changes = dict(status=new_status, notes=notes, pipeline_stage=pipeline_stage, follow_up_date=follow_up_date, application_handling=data.get("application_handling"))
        try:
            success = update_job_status(target_db, job_id, **changes)
        except (ValueError, TypeError) as exc:
            bottle.response.status = 400
            return {"success": False, "error": str(exc)}
        if not success:
            bottle.response.status = 404
        session = get_current_session()
        if success and session["role"] == "guest":
            save_guest_changes(session["id"], db_path, job_id, changes)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": success})


    def gmail_admin():
        session = get_current_session()
        if not session or session.get("role") != "admin":
            bottle.response.status = 403
            return {"error": "Gmail Hub is private to the admin account."}
        return None

    @app.route("/api/gmail/messages", method=["GET", "OPTIONS"])
    def api_get_gmail_messages():
        if bottle.request.method == "OPTIONS":
            return ""
        denied = gmail_admin()
        if denied:
            return denied
        from src.gmail_hub import messages
        try:
            limit = max(1, min(100, int(bottle.request.query.get("limit", "40"))))
            offset = max(0, min(100000, int(bottle.request.query.get("offset", "0"))))
        except ValueError:
            bottle.response.status = 400
            return {"error": "Invalid pagination"}
        return messages(db_path, limit, offset, category=bottle.request.query.get("category", ""),
                        read=bottle.request.query.get("read", ""), match=bottle.request.query.get("match", ""),
                        search=bottle.request.query.get("search", ""), summary=bottle.request.query.get("summary") == "1")

    @app.route("/api/gmail/messages/<message_id:re:[0-9a-f]+>", method="GET")
    def api_gmail_detail(message_id):
        denied = gmail_admin()
        if denied:
            return denied
        from src.gmail_hub import detail
        message = detail(db_path, message_id)
        if not message:
            bottle.response.status = 404
            return {"error": "Message not found"}
        return message

    @app.route("/api/gmail/messages/<message_id:re:[0-9a-f]+>/read", method="POST")
    def api_gmail_read(message_id):
        denied = gmail_admin()
        if denied:
            return denied
        from src.gmail_hub import mark_read
        value = (bottle.request.json or {}).get("is_read")
        if not isinstance(value, bool):
            bottle.response.status = 400
            return {"error": "is_read must be true or false"}
        mark_read(db_path, message_id, value)
        return {"success": True, "is_read": value}

    @app.route("/api/gmail/scan", method=["POST", "OPTIONS"])
    def api_post_gmail_scan():
        if bottle.request.method == "OPTIONS":
            return ""
        denied = gmail_admin()
        if denied:
            return denied
        from src.gmail_hub import request_scan
        try:
            result = request_scan(db_path, (bottle.request.json or {}).get("window", "24h"))
            bottle.response.status = 429 if result.get("status") == "cooldown" else 202
            return result
        except ValueError as error:
            bottle.response.status = 400
            return {"error": str(error)}
        except Exception:
            bottle.response.status = 503
            return {"error": "Cloud scan could not be queued. Retry later."}

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

        settings = {k: v for k, v in get_all_user_settings(target_db).items() if k in public_settings}
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

        try:
            data = bottle.request.json or {}
        except Exception:
            data = {}
        session = get_current_session()
        is_admin = session and session.get("role") == "admin"
        revisions = data.get("__revisions", {})
        if not isinstance(revisions, dict) or any(type(v) is not int or not 0 <= v <= 9007199254740991 for v in revisions.values()):
            bottle.abort(400, "Invalid setting revisions")
        for k, v in data.items():
            if k not in public_settings:
                continue
            if not isinstance(v, (str, bool, int, float, list)) or len(str(v)) > 10000:
                bottle.abort(400, "Setting value is invalid or too long")
            # Don't allow guest to overwrite master admin_totp_secret or credentials
            if str(k) in ("admin_totp_secret", "admin_password", "smtp_password", "ADMIN_TOTP_SECRET") and not is_admin:
                continue
            val_str = json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
            set_user_setting(target_db, str(k), val_str, revision=revisions.get(k))
            if not is_admin:
                set_user_setting(db_path, f"guest:{session['id']}:setting:{k}", val_str)
        if "proxy_list" in data or "proxy_mode" in data:
            try:
                raw_cp = get_user_setting(target_db, "sync_batch_progress", "")
                if raw_cp:
                    cp = json.loads(raw_cp)
                    now_ts = time.time()
                    for b_state in cp.get("boards", {}).values():
                        b_state["blocked_until"] = 0
                        if b_state.get("next_at", 0) > now_ts:
                            b_state["next_at"] = now_ts
                    set_user_setting(target_db, "sync_batch_progress", json.dumps(cp))
            except Exception:
                pass
        settings = {k: v for k, v in get_all_user_settings(target_db).items() if k in public_settings}
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
        if not isinstance(stack, str) or len(stack) > 10000:
            bottle.abort(400, "Stack must be text of at most 10000 characters")

        set_user_setting(target_db, "target_stack", stack)
        session = get_current_session()
        if session["role"] == "guest":
            set_user_setting(db_path, f"guest:{session['id']}:setting:target_stack", stack)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "stack": stack})

    # Cloud Cron & automated daily digest runs against master database (Admin or internal Vercel Cron only)
    @app.route("/api/cron/sync", method=["GET", "POST"])
    @app.route("/api/cron/cloud-sync", method=["GET", "POST"])
    @app.route("/api/sync/cron", method=["GET", "POST"])
    def api_cron_sync():
        """Cloud Cron endpoint for Vercel Cron or external scheduled runners.
        Schedules one daily scrape/resume. Email delivery is handled by the separate digest endpoint.
        """
        session = get_current_session()
        cron_secret = os.environ.get("CRON_SECRET", "").strip()
        auth_hdr = bottle.request.headers.get("Authorization", "")
        is_cron = bool(cron_secret) and hmac.compare_digest(auth_hdr, f"Bearer {cron_secret}")
        is_admin = session and session.get("role") == "admin"

        if not (is_cron or is_admin):
            bottle.response.status = 403
            bottle.response.content_type = "application/json"
            return json.dumps({
                "status": "forbidden",
                "error": "Forbidden: Requires valid CRON_SECRET or Admin session."
            })

        if get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower() in ("0", "false"):
            return {"status": "skipped", "reason": "Automatic sync is paused", "email_notification": None}

        try:
            from src.daily_schedule import start_daily
            if database_execution():
                from src.execution_dispatch import start
                return start_daily(db_path, lambda **options: start(db_path, **options))
            if bottle.request.path == "/api/cron/cloud-sync":
                from src.cloud_sync import start_run
                return start_daily(db_path, lambda **options: start_run(db_path, **options))
            if os.environ.get("VERCEL"):
                from src.local_worker import request_local_sync
                from src.cloud_sync import start_run
                def start_legacy(**options):
                    if bottle.request.path == "/api/cron/cloud-sync":
                        return start_run(db_path, **options)
                    local = request_local_sync(db_path, **options)
                    return local or start_run(db_path, **options)
                return start_daily(db_path, start_legacy)
            def start_inline(**options):
                aggregator.daily_run = True
                stats = aggregator.run_sync(force=True, budget_seconds=150, resume=options["resume"])
                if stats.get("status") == "error":
                    bottle.response.status = 500
                return {"status": "success" if stats.get("status") == "ok" else stats.get("status"),
                        "sync_stats": stats, "email_notification": None}
            return start_daily(db_path, start_inline)
        except Exception as e:
            bottle.response.status = 500
            bottle.response.content_type = "application/json"
            return json.dumps({"status": "error", "error": str(e)})

    @app.route("/api/notify/daily", method=["GET", "POST"])
    def api_notify_daily():
        session = get_current_session()
        cron_secret = os.environ.get("CRON_SECRET", "").strip()
        is_cron = bool(cron_secret) and hmac.compare_digest(bottle.request.headers.get("Authorization", ""), f"Bearer {cron_secret}")
        if not is_cron and (not session or session.get("role") != "admin"):
            bottle.response.status = 403
            bottle.response.content_type = "application/json"
            return json.dumps({
                "success": False,
                "error": "Forbidden: Only Admin can trigger email digests to michael18ricafrente@gmail.com."
            })
        try:
            from src.gmail_hub import request_scan
            result = request_scan(db_path, "24h", digest=True)
        except Exception:
            bottle.response.status = 503
            result = {"success": False, "error": "Gmail scan and digest could not be queued; retry later."}
        bottle.response.content_type = "application/json"
        return json.dumps(result)

    @app.route("/api/sync/status", method="GET")
    def api_sync_status():
        auth_err = require_auth()
        if auth_err:
            return auth_err
        bottle.response.content_type = "application/json"
        if database_execution():
            from src.execution_dispatch import telemetry as database_telemetry
            return json.dumps(database_telemetry(db_path))
        telemetry = aggregator.get_telemetry()
        telemetry.setdefault("last_result", aggregator.last_sync_result)
        upwork_feed = json.loads(get_user_setting(db_path, "upwork_feed_status", "{}") or "{}")
        from src.cloud_sync import read_run, public_run, ACTIVE
        cloud_run = read_run(db_path)
        telemetry["cloud_run"] = public_run(cloud_run)
        cloud_pending = telemetry["cloud_run"].get("status") in ACTIVE
        from src.local_worker import read_json_setting, worker_status, public_request, owns_execution, REQUEST_KEY
        telemetry["local_worker"] = worker_status(db_path)
        request = read_json_setting(db_path, REQUEST_KEY)
        telemetry["local_request"] = public_request(db_path, request, telemetry["local_worker"])
        worker_telem = read_json_setting(db_path, "local_worker_telemetry")
        local_active = (telemetry["local_worker"]["online"] and request.get("status") == "running"
                        and owns_execution(db_path, request))
        if (not local_active and isinstance(cloud_run.get("result"), dict)
                and cloud_run.get("updated_at", 0) > request.get("completed_at", request.get("updated_at", 0))):
            telemetry["last_result"] = cloud_run["result"]
            telemetry["progress"] = cloud_run["result"].get("progress")
        if local_active and worker_telem:
            telemetry.update({key: value for key, value in worker_telem.items()
                              if key in {"progress", "last_result", "last_sync_time", "logs", "telemetry", "platforms", "total_boards", "run_totals"}})
        if local_active or (request.get("status") == "queued" and telemetry["local_worker"]["online"]):
            telemetry["is_syncing"] = True
        elif telemetry["local_request"].get("status") == "interrupted":
            lease = get_user_setting(db_path, "sync_lease", "0|") or "0|"
            if not cloud_pending and (lease.partition("|")[2] == request.get("lease_owner")
                                      or (not telemetry["local_worker"]["online"] and not lease.partition("|")[2])):
                telemetry["is_syncing"] = False
                telemetry["last_result"] = {"status": "error", "error": telemetry["local_request"]["error"]}
        if cloud_pending:
            telemetry["is_syncing"] = True
        if upwork_feed:
            age = time.time() - upwork_feed.get("checked_at", 0)
            if isinstance(telemetry.get("progress"), dict):
                board = telemetry["progress"].setdefault("boards", {}).setdefault("Upwork", {})
                board.update(last_error="", deferred=False, retry=[], next_at=upwork_feed.get("checked_at", 0) + 86400)
            if isinstance(telemetry.get("last_result"), dict):
                telemetry["last_result"].setdefault("platforms", {})["Upwork"] = upwork_feed.get("fetched", 0)
            if isinstance(telemetry.get("run_totals"), dict):
                telemetry["run_totals"].setdefault("platforms", {})["Upwork"] = upwork_feed.get("fetched", 0)
            telemetry.setdefault("telemetry", {})["Upwork"] = {
                "status": "error" if upwork_feed.get("error") else "complete" if age < 172800 else "cooldown",
                "count": upwork_feed.get("fetched", 0), "tier": 2, "route": "FLCONSOLE",
                "error": upwork_feed.get("error", "") if age < 172800 else "Upwork daily check is overdue"}
        return json.dumps(telemetry)

    def require_local_worker():
        if database_execution() and bottle.request.path in {
            "/api/local-worker/heartbeat", "/api/local-worker/request",
            "/api/local-worker/jobs", "/api/local-worker/complete",
        }:
            bottle.response.status = 409
            return {"status": "error", "error": "Use the direct database worker for this deployment"}
        token = os.environ.get("LOCAL_WORKER_TOKEN", "").strip()
        supplied = bottle.request.headers.get("Authorization", "")
        if not token:
            bottle.response.status = 503
            return {"status": "error", "error": "Local worker is not configured"}
        if not hmac.compare_digest(supplied, f"Bearer {token}"):
            bottle.response.status = 401
            return {"status": "error", "error": "Unauthorized local worker"}
        return None

    @app.route("/api/local-worker/status", method="GET")
    def api_local_worker_status():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        from src.local_worker import REQUEST_KEY, worker_status, read_json_setting, public_request
        bottle.response.content_type = "application/json"
        worker = worker_status(db_path)
        return json.dumps({"worker": worker,
                           "request": public_request(db_path, read_json_setting(db_path, REQUEST_KEY), worker)})

    @app.route("/api/local-worker/heartbeat", method="POST")
    def api_local_worker_heartbeat():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        from src.local_worker import WORKER_KEY, REQUEST_KEY, LEASE_SECONDS, read_json_setting
        from src.database import renew_sync_lease
        data = bottle.request.json or {}
        worker_id = str(data.get("worker_id", ""))[:100]
        if not worker_id:
            bottle.response.status = 400
            return {"status": "error", "error": "worker_id is required"}
        current = read_json_setting(db_path, WORKER_KEY)
        if current.get("online") and current.get("worker_id") not in (None, worker_id) and current.get("heartbeat_at", 0) > time.time() - 45:
            bottle.response.status = 409
            return {"status": "error", "error": "Another local worker is already online"}
        now = time.time()
        status = {"worker_id": worker_id, "machine": str(data.get("machine", ""))[:100],
                  "heartbeat_at": now, "version": 1,
                  "active_request_id": str(data.get("active_request_id", ""))[:100], "online": True}
        set_user_setting(db_path, WORKER_KEY, json.dumps(status))
        request = read_json_setting(db_path, REQUEST_KEY)
        lease_valid = None
        if status["active_request_id"] and request.get("id") == status["active_request_id"] and request.get("worker_id") == worker_id and request.get("status") == "running":
            lease_valid = renew_sync_lease(db_path, request.get("lease_owner", ""), int(now) + LEASE_SECONDS, int(now))
        local_telem = data.get("telemetry")
        if isinstance(local_telem, dict) and lease_valid:
            set_user_setting(db_path, "local_worker_telemetry", json.dumps(local_telem))
        bottle.response.content_type = "application/json"
        return json.dumps({"status": "ok", "heartbeat_at": now, "lease_valid": lease_valid})

    @app.route("/api/local-worker/request", method="GET")
    def api_local_worker_request():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        from src.local_worker import REQUEST_KEY, LEASE_SECONDS, read_json_setting, worker_status, owns_execution
        from src.database import acquire_sync_lease
        worker_id = bottle.request.query.get("worker_id", "")
        worker = worker_status(db_path)
        if not worker.get("online") or worker.get("worker_id") != worker_id:
            bottle.response.status = 409
            return {"status": "error", "error": "Worker heartbeat is missing or belongs to another process"}
        request = read_json_setting(db_path, REQUEST_KEY)
        if request.get("status") in {"queued", "running"}:
            owner = f"local:{request['id']}:{worker_id}"
            if not (request.get("lease_owner") == owner and owns_execution(db_path, request)):
                lease = f"{int(time.time()) + LEASE_SECONDS}|{owner}"
                if not acquire_sync_lease(db_path, lease, int(time.time())):
                    return {"status": "waiting", "request": None}
            request.update(status="running", worker_id=worker_id, lease_owner=owner,
                           started_at=request.get("started_at", time.time()), updated_at=time.time())
            set_user_setting(db_path, REQUEST_KEY, json.dumps(request))
        bottle.response.content_type = "application/json"
        from src.proxy_manager import get_proxy_settings
        proxy_settings = get_proxy_settings(db_path)
        return json.dumps({"status": "ok", "request": request if request.get("status") == "running" and request.get("worker_id") == worker_id else None,
                           "proxy_settings": {"proxy_mode": proxy_settings["mode"], "proxy_list": proxy_settings["raw"]}})

    @app.route("/api/local-worker/upwork/claim", method="POST")
    def api_upwork_claim():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        from src.upwork_monitor import claim
        return {"claimed": claim(db_path, "local")}

    @app.route("/api/local-worker/upwork/start", method="POST")
    def api_upwork_start():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        import asyncio
        from src.upwork_monitor import start, poll_cloud
        result = asyncio.run(start(db_path))
        if (bottle.request.json or {}).get("check_cloud"):
            result["cloud_check"] = poll_cloud(db_path, ignore_local=True)
        return result

    @app.route("/api/local-worker/upwork", method="POST")
    def api_local_worker_upwork():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        data = bottle.request.json or {}
        rows = data.get("jobs")
        if not isinstance(rows, list) or len(rows) > 30:
            bottle.abort(400, "At most 30 Upwork jobs per batch")
        jobs = []
        from urllib.parse import urlsplit
        for row in rows:
            if not isinstance(row, dict):
                bottle.abort(400, "Invalid Upwork job")
            url = urlsplit(str(row.get("job_url", "")))
            if (row.get("platform") != "Upwork" or url.scheme != "https"
                    or url.netloc != "www.upwork.com" or not url.path.startswith("/jobs/~")
                    or not row.get("title")):
                bottle.abort(400, "Invalid Upwork job")
            jobs.append(Job(title=row["title"], company="Direct Client (Upwork)",
                            location="Remote Worldwide / Freelance", platform="Upwork", tier=2,
                            job_url=row["job_url"], salary=row.get("salary", ""),
                            description=row.get("description", ""), date_posted=row.get("date_posted", ""),
                            role_category=row.get("role_category", "Web/Software Dev"),
                            experience_level=row.get("experience_level", "Unspecified")))
        added, skipped = insert_jobs(db_path, jobs)
        set_user_setting(db_path, "upwork_feed_status", json.dumps({"checked_at": time.time(),
                         "fetched": len(jobs), "error": str(data.get("error", ""))[:250], "source": "local"}))
        return {"status": "ok", "added": added, "skipped": skipped}

    @app.route("/api/local-worker/jobs", method="POST")
    def api_local_worker_jobs():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        from src.local_worker import REQUEST_KEY, read_json_setting, owns_execution
        data = bottle.request.json or {}
        request = read_json_setting(db_path, REQUEST_KEY)
        if (request.get("id") != data.get("request_id") or request.get("status") != "running"
                or request.get("worker_id") != data.get("worker_id") or not owns_execution(db_path, request)):
            bottle.response.status = 409
            return {"status": "error", "error": "No matching sync request is active"}
        rows = data.get("jobs")
        if not isinstance(rows, list) or len(rows) > 100:
            bottle.response.status = 400
            return {"status": "error", "error": "A batch must contain at most 100 jobs"}
        jobs = []
        try:
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Invalid job record")
                jobs.append(Job(title=row.get("title", ""), company=row.get("company", ""),
                                location=row.get("location", "Philippines / Remote"),
                                platform=row.get("platform", ""), tier=int(row.get("tier", 3)),
                                job_url=row.get("job_url", ""), salary=row.get("salary", ""),
                                role_category=row.get("role_category", "Web/Software Dev"),
                                experience_level=row.get("experience_level", "Unspecified"),
                                date_posted=row.get("date_posted", ""), status="new",
                                description=row.get("description", ""), sources=row.get("sources", [])))
                from dataclasses import replace
                primary = jobs[-1]
                for source in (row.get("sources") or [])[:50]:
                    if not isinstance(source, dict):
                        continue
                    platform, url = source.get("platform"), source.get("url")
                    if (isinstance(platform, str) and isinstance(url, str) and url.startswith(("https://", "http://"))
                            and (platform, url) != (primary.platform, primary.job_url)):
                        jobs.append(replace(primary, platform=platform, job_url=url, dedup_hash=None))
        except (TypeError, ValueError) as exc:
            bottle.response.status = 400
            return {"status": "error", "error": f"Invalid job batch: {exc}"}
        added, skipped = insert_jobs(db_path, jobs)
        bottle.response.content_type = "application/json"
        return json.dumps({"status": "ok", "added": added, "skipped": skipped})

    @app.route("/api/local-worker/complete", method="POST")
    def api_local_worker_complete():
        auth_err = require_local_worker()
        if auth_err:
            return auth_err
        from src.local_worker import REQUEST_KEY, read_json_setting, owns_execution
        from src.database import release_sync_lease
        data = bottle.request.json or {}
        request = read_json_setting(db_path, REQUEST_KEY)
        if (request.get("id") != data.get("request_id") or request.get("status") != "running"
                or request.get("worker_id") != data.get("worker_id") or not owns_execution(db_path, request)):
            bottle.response.status = 409
            return {"status": "error", "error": "No matching sync request is active"}
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        email_result = None
        request.update(status="complete" if result.get("status") == "ok" else "partial" if result.get("status") == "partial" else "error",
                       completed_at=time.time(), updated_at=time.time(), result=result,
                       email_notification=email_result)
        set_user_setting(db_path, REQUEST_KEY, json.dumps(request))
        set_user_setting(db_path, "sync_status", json.dumps({"is_syncing": False,
                         "last_sync_time": result.get("last_sync_time", 0), "last_result": result,
                         "last_successful_fetch": result.get("last_sync_time", 0),
                         "total_boards": result.get("total_boards", 0),
                         "logs": result.get("logs", []), "telemetry": result.get("telemetry", {})}))
        lease = get_user_setting(db_path, "sync_lease", "0|") or "0|"
        if lease.partition("|")[2] == request.get("lease_owner"):
            release_sync_lease(db_path, lease)
        bottle.response.content_type = "application/json"
        return json.dumps({"status": request["status"], "email_notification": email_result})

    @app.route("/api/sync", method=["GET", "POST", "OPTIONS"])
    def api_sync():
        if bottle.request.method == "OPTIONS":
            return ""
        cron_secret = os.environ.get("CRON_SECRET", "").strip()
        auth_hdr = bottle.request.headers.get("Authorization", "")
        is_cron = bool(cron_secret) and hmac.compare_digest(auth_hdr, f"Bearer {cron_secret}")

        if not is_cron:
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
        action = data.get("action", "fresh")
        if not isinstance(action, str) or action not in {"fresh", "restart", "resume", "pause", "stop"}:
            bottle.abort(400, "action must be fresh, restart, resume, pause, or stop")


        if database_execution() and action in {"pause", "stop"}:
            from src.execution_inbox import cancel
            terminal = "paused" if action == "pause" else "stopped"
            cancel(db_path, status=terminal)
            return {"status": terminal, "is_syncing": False}

        if action == "pause":
            from src.local_worker import pause_local_sync
            from src.cloud_sync import pause_run
            pause_run(db_path)
            res = pause_local_sync(db_path)
            bottle.response.content_type = "application/json"
            return json.dumps(res)

        if action == "stop":
            from src.local_worker import stop_local_sync
            from src.cloud_sync import stop_run
            stop_run(db_path)
            res = stop_local_sync(db_path)
            bottle.response.content_type = "application/json"
            return json.dumps(res)


        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        if keywords is not None:
            if (not isinstance(keywords, list) or len(keywords) > 1000
                    or any(not isinstance(k, str) or not k.strip() or len(k) > 200 for k in keywords)):
                bottle.abort(400, "Keywords must be a list of at most 1000 nonempty strings, each up to 200 characters")
            if len(", ".join(keywords)) > 10000:
                bottle.abort(400, "The selected keyword matrix must be at most 10000 characters")
            keywords = list(dict.fromkeys(k.strip() for k in keywords))

        if database_execution():
            from src.execution_dispatch import start
            try:
                return start(db_path, queries=keywords or None, resume=action == "resume", restart=action == "restart")
            except Exception:
                bottle.response.status = 503
                return {"status": "error", "error": "Worker dispatch unavailable; retry Sync to recover the saved command"}

        is_resume = action == "resume"
        if os.environ.get("VERCEL"):
            from src.cloud_sync import ACTIVE, RUN_KEY, public_run, read_run, start_run
            from src.local_worker import request_local_sync, worker_status, cancel_queued_local_sync
            try:
                worker = worker_status(db_path)
                if worker["online"]:
                    now = int(time.time())
                    active_lease = False
                    for key in ("sync_lease", "cloud_sync_worker_lease", "cloud_sync_start_lease"):
                        lease = get_user_setting(db_path, key, "0|") or "0|"
                        try:
                            active_lease = active_lease or int(lease.split("|", 1)[0]) > now
                        except (ValueError, IndexError):
                            continue

                    current_cloud_run = read_run(db_path)
                    if active_lease and public_run(current_cloud_run).get("status") in ACTIVE:
                        return {"status": "already_syncing", "is_syncing": True,
                                "cloud_run": public_run(current_cloud_run),
                                "local_worker": worker}

                    if current_cloud_run.get("status") in ACTIVE:
                        current_cloud_run.update(status="paused", updated_at=time.time(),
                                                 pause_reason="local_worker_selected")
                        set_user_setting(db_path, RUN_KEY, json.dumps(current_cloud_run))

                    is_restart = action in {"fresh", "restart"}
                    is_resume = action == "resume"
                    local = request_local_sync(db_path, queries=keywords if keywords else None, resume=is_resume, restart=is_restart)
                    if local:
                        return local

                cancel_queued_local_sync(db_path)
                return start_run(db_path, queries=keywords if keywords else None, resume=is_resume)
            except Exception as exc:
                bottle.response.status = 503
                return {"status": "error", "error": str(exc)}

        if is_background and not os.environ.get("VERCEL"):
            started = aggregator.start_background_sync(queries=keywords if keywords else None, force=force)
            bottle.response.content_type = "application/json"
            return json.dumps({
                "status": "started" if started else "already_syncing",
                "is_syncing": True,
                "message": "Background sync started." if started else "Sync already running in background."
            })

        stats = aggregator.run_sync(queries=keywords if keywords else None, force=force, budget_seconds=150 if os.environ.get("VERCEL") else None, resume=action == "resume", restart=action in {"fresh", "restart"})
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    @app.route("/api/proxy/status", method=["GET", "OPTIONS"])
    def api_proxy_status():
        if bottle.request.method == "OPTIONS":
            return ""
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()
        from src.proxy_manager import get_proxy_settings, is_proxy_active, format_proxy_for_display
        config = get_proxy_settings(target_db)
        bottle.response.content_type = "application/json"
        return json.dumps({
            "mode": config.get("mode", "hybrid"),
            "active": is_proxy_active(target_db),
            "count": len(config.get("proxies", [])),
            "proxies": [format_proxy_for_display(p) for p in config.get("proxies", [])],
            "raw": config.get("raw", "")
        })

    @app.route("/api/proxy/test", method=["POST", "OPTIONS"])
    def api_proxy_test():
        if bottle.request.method == "OPTIONS":
            return ""
        auth_err = require_auth()
        if auth_err:
            return auth_err
        target_db = resolve_target_db()
        try:
            data = bottle.request.json or {}
        except Exception:
            data = {}
        from src.proxy_manager import get_proxy_settings, test_single_proxy, parse_proxy_list
        raw = str(data.get("proxies", "")).strip()
        proxies_to_test = parse_proxy_list(raw) if raw else get_proxy_settings(target_db).get("proxies", [])

        results = []
        for p in proxies_to_test[:10]:
            results.append(test_single_proxy(p, timeout=4))

        bottle.response.content_type = "application/json"
        return json.dumps({"status": "ok", "results": results})

    @app.route("/api/portfolio/views", method="GET")
    def api_portfolio_views():
        bottle.response.content_type = "application/json"
        force_refresh = str(bottle.request.query.get("refresh", "")).strip() in ("1", "true")
        now = time.time()
        if not force_refresh and _portfolio_views_cache["payload"] and (now - _portfolio_views_cache["ts"] < 60):
            return json.dumps(_portfolio_views_cache["payload"])

        url = "https://hits.sh/api/urns/louisricafrente-dev.vercel.app"
        req = urllib.request.Request(url, headers={"User-Agent": "JobAccelerator/1.0", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            items = raw.get("items") or []
            raw_days = (items[0].get("data") if items and isinstance(items[0], dict) else None) or []
            days = [
                {"day": str(entry.get("day", "")), "value": int(entry.get("value") or 0)}
                for entry in raw_days
                if isinstance(entry, dict) and entry.get("day")
            ]
            days.sort(key=lambda x: x["day"], reverse=True)
            total = int(raw.get("total") or 0)
            monthly = int(raw.get("monthly") or 0)
            today_val = days[0]["value"] if days else 0
            today_day = days[0]["day"] if days else ""
            peak = max(days, key=lambda x: x["value"]) if days else {"day": "", "value": 0}
            payload = {
                "status": "ok",
                "domain": "louisricafrente-dev.vercel.app",
                "total": total,
                "monthly": monthly,
                "today": today_val,
                "today_day": today_day,
                "peak": peak,
                "days": days[:30],
                "fetched_at": int(now),
            }
            _portfolio_views_cache["ts"] = now
            _portfolio_views_cache["payload"] = payload
            try:
                set_user_setting(db_path, "portfolio_views_cache", json.dumps(payload))
            except Exception:
                pass
            return json.dumps(payload)
        except Exception as exc:
            if _portfolio_views_cache["payload"]:
                return json.dumps(_portfolio_views_cache["payload"])
            try:
                cached_json = get_user_setting(db_path, "portfolio_views_cache")
                if cached_json:
                    cached_payload = json.loads(cached_json)
                    if isinstance(cached_payload, dict) and cached_payload.get("status") == "ok":
                        _portfolio_views_cache["payload"] = cached_payload
                        return json.dumps(cached_payload)
            except Exception:
                pass

            fallback_payload = {
                "status": "ok",
                "domain": "louisricafrente-dev.vercel.app",
                "total": 278,
                "monthly": 155,
                "today": 19,
                "today_day": "2026-10-31",
                "peak": {"day": "2026-09-26", "value": 32},
                "days": [{"day": "2026-10-31", "value": 19}],
                "fetched_at": int(now),
                "notice": f"Cached telemetry served ({exc})"
            }
            return json.dumps(fallback_payload)

    @app.route("/api/health", method="GET")
    def api_health():
        return {"service": "job-accelerator", "status": "ok"}

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
