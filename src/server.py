import time
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
    resolve_guest_db_path, reset_guest_db, save_guest_changes,
    admin_login_retry_after, record_admin_login_failure, clear_admin_login_failures
)

def create_app(db_path: str = "data/jobs.db", guest_access_enabled: bool = False) -> bottle.Bottle:
    app = bottle.Bottle()
    aggregator = Aggregator(db_path=db_path)

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
        changes = dict(status=new_status, notes=notes, pipeline_stage=pipeline_stage, follow_up_date=follow_up_date)
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
    @app.route("/api/sync/cron", method=["GET", "POST"])
    def api_cron_sync():
        """Cloud Cron endpoint for Vercel Cron or external scheduled runners.
        Runs scraper across platforms, ingests new listings, and dispatches email digest if new jobs found.
        """
        session = get_current_session()
        cron_secret = os.environ.get("CRON_SECRET", "").strip()
        auth_hdr = bottle.request.headers.get("Authorization", "")
        is_cron = bool(cron_secret) and hmac.compare_digest(auth_hdr, f"Bearer {cron_secret}")
        is_vercel_cron = bottle.request.headers.get("x-vercel-cron") == "1"
        is_admin = session and session.get("role") == "admin"

        if not (is_cron or is_vercel_cron or is_admin):
            bottle.response.status = 403
            bottle.response.content_type = "application/json"
            return json.dumps({
                "status": "forbidden",
                "error": "Forbidden: Requires valid CRON_SECRET, Vercel Cron header, or Admin session."
            })

        if get_user_setting(db_path, "auto_sync_enabled", "1").strip().lower() in ("0", "false"):
            return {"status": "skipped", "reason": "Automatic sync is paused", "email_notification": None}

        try:
            stats = aggregator.run_sync(force=True, budget_seconds=150)
            if os.environ.get("VERCEL"):
                from src.cloud_sync import start_run
                stats["cloud_continuation"] = start_run(db_path, automatic=True)
            added = stats.get("added", 0)
            email_result = None
            if added > 0:
                try:
                    from scripts.daily_notifier import send_daily_email
                    dashboard_url = os.environ.get("VERCEL_URL", "https://job-accelerator-rhettrina.vercel.app")
                    if not dashboard_url.startswith("http"):
                        dashboard_url = "https://" + dashboard_url
                    email_result = send_daily_email(db_path=db_path, dashboard_url=dashboard_url, new_jobs_count=added)
                except Exception as mail_err:
                    email_result = {"status": "error", "error": str(mail_err)}
            bottle.response.content_type = "application/json"
            sync_status = stats.get("status", "error")
            status = "success" if sync_status == "ok" else sync_status
            if sync_status == "error":
                bottle.response.status = 500
            if email_result is not None and (email_result.get("success") is False or email_result.get("status") == "error") and status == "success":
                status = "partial"
            return json.dumps({
                "status": status,
                "sync_stats": stats,
                "email_notification": email_result
            })
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
        telemetry.setdefault("last_result", aggregator.last_sync_result)
        from src.cloud_sync import read_run, public_run, ACTIVE
        cloud_run = read_run(db_path)
        telemetry["cloud_run"] = public_run(cloud_run)
        if cloud_run.get("status") in ACTIVE and cloud_run.get("expires_at", 0) > time.time():
            telemetry["is_syncing"] = True
        return json.dumps(telemetry)

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

        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        if keywords is not None:
            if (not isinstance(keywords, list) or len(keywords) > 1000
                    or any(not isinstance(k, str) or not k.strip() or len(k) > 200 for k in keywords)):
                bottle.abort(400, "Keywords must be a list of at most 1000 nonempty strings, each up to 200 characters")
            if len(", ".join(keywords)) > 10000:
                bottle.abort(400, "The selected keyword matrix must be at most 10000 characters")
            keywords = list(dict.fromkeys(k.strip() for k in keywords))

        if os.environ.get("VERCEL"):
            from src.cloud_sync import start_run
            try:
                return start_run(db_path, queries=keywords if keywords else None)
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

        stats = aggregator.run_sync(queries=keywords if keywords else None, force=force, budget_seconds=150 if os.environ.get("VERCEL") else None)
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
