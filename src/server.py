import os
import json
import bottle
from src.database import (
    get_jobs, update_job_status, get_stats, export_jobs_csv, 
    get_user_setting, set_user_setting, get_all_user_settings
)
from src.aggregator import Aggregator

def create_app(db_path: str = "data/jobs.db") -> bottle.Bottle:
    app = bottle.Bottle()
    aggregator = Aggregator(db_path=db_path)

    @app.hook("after_request")
    def enable_cors_and_nocache():
        bottle.response.headers["Access-Control-Allow-Origin"] = "*"
        bottle.response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        bottle.response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        bottle.response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        bottle.response.headers["Pragma"] = "no-cache"
        bottle.response.headers["Expires"] = "0"

    @app.route("/api/jobs/export/csv", method="GET")
    def api_export_csv():
        status = bottle.request.query.get("status", "applied")
        csv_text = export_jobs_csv(db_path, status=status)
        bottle.response.content_type = "text/csv; charset=utf-8"
        bottle.response.headers["Content-Disposition"] = 'attachment; filename="job_applications.csv"'
        return csv_text

    @app.route("/api/jobs", method="GET")
    def api_get_jobs():
        status = bottle.request.query.get("status", "new")
        role = bottle.request.query.get("role", "All")
        level = bottle.request.query.get("experience_level", "All")
        tier_str = bottle.request.query.get("tier", "")
        search = bottle.request.query.get("search", "")
        date_filter = bottle.request.query.get("date_filter", "all")
        has_salary = bottle.request.query.get("has_salary", "0") in ("1", "true", "True")
        remote_only = bottle.request.query.get("remote_only", "0") in ("1", "true", "True")
        hide_senior = bottle.request.query.get("hide_senior", "0") in ("1", "true", "True")
        tier = int(tier_str) if tier_str.isdigit() else None

        query_status = status

        jobs = get_jobs(
            db_path=db_path,
            status=query_status if status != "all" else None,
            role_category=role,
            experience_level=level,
            tier=tier,
            search=search,
            date_filter=date_filter,
            has_salary=has_salary,
            remote_only=remote_only,
            hide_senior=hide_senior,
            limit=200
        )
        bottle.response.content_type = "application/json"
        return json.dumps({"jobs": jobs, "count": len(jobs)})

    @app.route("/api/jobs/<job_id:int>/status", method=["POST", "PUT"])
    def api_update_status(job_id: int):
        data = bottle.request.json or {}
        new_status = data.get("status")
        notes = data.get("notes")
        pipeline_stage = data.get("stage") or data.get("pipeline_stage")
        follow_up_date = data.get("follow_up_date")
        success = update_job_status(
            db_path=db_path,
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
        stats = get_stats(db_path)
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    DEFAULT_TARGET_STACK = "Kotlin, Jetpack Compose, React, Next.js, TypeScript, Node.js, Express, MySQL, Tailwind CSS, Junior / Entry"

    @app.route("/api/settings", method=["GET", "OPTIONS"])
    def api_get_all_settings():
        if bottle.request.method == "OPTIONS":
            return ""
        settings = get_all_user_settings(db_path)
        if "target_stack" not in settings:
            settings["target_stack"] = DEFAULT_TARGET_STACK
        bottle.response.content_type = "application/json"
        return json.dumps(settings)

    @app.route("/api/settings", method=["POST", "PUT"])
    def api_save_settings():
        data = bottle.request.json or {}
        for k, v in data.items():
            val_str = json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
            set_user_setting(db_path, str(k), val_str)
        settings = get_all_user_settings(db_path)
        if "target_stack" not in settings:
            settings["target_stack"] = DEFAULT_TARGET_STACK
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "settings": settings})

    @app.route("/api/settings/stack", method=["GET", "OPTIONS"])
    def api_get_stack_setting():
        if bottle.request.method == "OPTIONS":
            return ""
        stack = get_user_setting(db_path, "target_stack", DEFAULT_TARGET_STACK)
        bottle.response.content_type = "application/json"
        return json.dumps({"stack": stack})

    @app.route("/api/settings/stack", method=["POST", "PUT"])
    def api_save_stack_setting():
        data = bottle.request.json or {}
        stack = data.get("stack", "")
        if isinstance(stack, list):
            stack = ", ".join(str(s).strip() for s in stack if str(s).strip())
        elif isinstance(stack, str):
            stack = stack.strip()

        set_user_setting(db_path, "target_stack", stack)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": True, "stack": stack})

    @app.route("/api/notify/daily", method=["GET", "POST"])
    def api_notify_daily():
        try:
            from scripts.daily_notifier import send_daily_email
            result = send_daily_email(db_path)
        except Exception as e:
            result = {"success": False, "error": str(e)}
        bottle.response.content_type = "application/json"
        return json.dumps(result)

    @app.route("/api/sync/status", method="GET")
    def api_sync_status():
        bottle.response.content_type = "application/json"
        telemetry = aggregator.get_telemetry()
        telemetry["last_result"] = aggregator.last_sync_result
        return json.dumps(telemetry)

    @app.route("/api/sync", method=["POST", "OPTIONS"])
    def api_sync():
        if bottle.request.method == "OPTIONS":
            return ""
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

    @app.route("/static/<filepath:path>")
    def static_files(filepath: str):
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        return bottle.static_file(filepath, root=static_dir)

    return app
