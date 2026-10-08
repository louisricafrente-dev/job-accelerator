import os
import json
import bottle
from src.database import get_jobs, update_job_status, get_stats
from src.aggregator import Aggregator

def create_app(db_path: str = "data/jobs.db") -> bottle.Bottle:
    app = bottle.Bottle()
    aggregator = Aggregator(db_path=db_path)

    @app.hook("after_request")
    def enable_cors():
        bottle.response.headers["Access-Control-Allow-Origin"] = "*"
        bottle.response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        bottle.response.headers["Access-Control-Allow-Headers"] = "Content-Type"

    @app.route("/api/jobs", method="GET")
    def api_get_jobs():
        status = bottle.request.query.get("status", "new")
        role = bottle.request.query.get("role", "All")
        level = bottle.request.query.get("experience_level", "All")
        tier_str = bottle.request.query.get("tier", "")
        search = bottle.request.query.get("search", "")
        date_filter = bottle.request.query.get("date_filter", "all")
        tier = int(tier_str) if tier_str.isdigit() else None

        jobs = get_jobs(
            db_path=db_path,
            status=status if status != "all" else None,
            role_category=role,
            experience_level=level,
            tier=tier,
            search=search,
            date_filter=date_filter,
            limit=200
        )
        bottle.response.content_type = "application/json"
        return json.dumps({"jobs": jobs, "count": len(jobs)})

    @app.route("/api/jobs/<job_id:int>/status", method=["POST", "PUT"])
    def api_update_status(job_id: int):
        data = bottle.request.json or {}
        new_status = data.get("status", "applied")
        notes = data.get("notes")
        success = update_job_status(db_path, job_id, new_status, notes)
        bottle.response.content_type = "application/json"
        return json.dumps({"success": success})

    @app.route("/api/stats", method="GET")
    def api_get_stats():
        stats = get_stats(db_path)
        bottle.response.content_type = "application/json"
        return json.dumps(stats)

    @app.route("/api/sync", method="POST")
    def api_sync():
        stats = aggregator.run_sync()
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
