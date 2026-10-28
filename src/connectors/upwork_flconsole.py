import json
import os
import urllib.error
import urllib.request

from src.classifier import classify_experience_level, classify_role, is_relevant_opportunity
from src.models import Job

ENDPOINT = "https://mcp.lite.flconsole.com/mcp"
QUERY = "(react OR kotlin OR php) AND (developer OR development)"


def rpc(name, arguments):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Authorization": "Bearer " + os.environ["FLCONSOLE_MCP_TOKEN"],
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(request, timeout=35) as response:
        payload = json.load(response)
    if "error" in payload:
        raise ValueError("flconsole RPC error")
    result = payload["result"]
    if result.get("isError"):
        raise ValueError("flconsole rejected search; check filters, access and quota")
    data = result.get("structuredContent")
    if data is None:
        data = json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))
    return data


def fetch_jobs(connector, limit=30):
    connector.last_route = "FLCONSOLE"
    try:
        data = rpc("find_jobs", {"filters": {"schema_version": 1, "base": {"q": QUERY}},
                                 "lookback_minutes": 30, "limit": limit})
        if not isinstance(data.get("jobs"), list):
            raise ValueError("flconsole returned no jobs array")
        jobs = []
        for item in data["jobs"]:
            uid = str(item.get("upwork_id", ""))
            title, description = item.get("title", ""), item.get("description", "")
            if not uid.isdigit() or not title or not is_relevant_opportunity(title, description):
                continue
            if item.get("job_type") == "hourly":
                low, high = item.get("hourly_rate_from"), item.get("hourly_rate_to")
                salary = f"USD {low:g}-{high:g}/hr" if low is not None and high is not None else ""
            else:
                budget = item.get("fixed_budget")
                salary = f"USD {budget:g} fixed" if budget else ""
            jobs.append(Job(title=title, company="Direct Client (Upwork)", location="Remote Worldwide / Freelance",
                            platform="Upwork", tier=2, job_url=f"https://www.upwork.com/jobs/~{uid}",
                            salary=salary, description=description, date_posted=item.get("publish_at", ""),
                            role_category=classify_role(title, description),
                            experience_level=classify_experience_level(title, description)))
        return jobs
    except urllib.error.HTTPError as exc:
        connector.last_error = f"flconsole HTTP {exc.code}; check authentication or quota"
    except Exception:
        connector.last_error = "flconsole search failed; check connectivity, filters or provider quota"
    return []
