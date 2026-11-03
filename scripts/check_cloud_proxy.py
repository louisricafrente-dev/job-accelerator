"""Read saved web proxy settings and verify HTTPS tunnels without changing jobs/settings."""
import concurrent.futures
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from src.database import is_turso_active
from src.proxy_manager import get_proxy_settings


def probe(proxy):
    with requests.Session() as session:
        session.trust_env = False
        route = {"http": proxy, "https": proxy}
        try:
            response = session.get("https://api.ipify.org?format=json", proxies=route, timeout=15)
            response.raise_for_status()
            if not response.json().get("ip"):
                return {"status": "error", "reason": "No exit IP returned"}
        except requests.RequestException as error:
            status = getattr(error.response, "status_code", None)
            return {"status": "error", "reason": "HTTPS tunnel failed", "http_status": status}
        result = {"status": "ok", "https_tunnel": True}
        try:
            response = session.get("http://ip-api.com/json/?fields=status,country,isp,hosting,proxy",
                                   proxies=route, timeout=8)
            data = response.json()
            if data.get("status") == "success":
                result.update({key: data.get(key) for key in ("country", "isp", "hosting", "proxy")})
        except (requests.RequestException, ValueError):
            pass
        return result


def main():
    db = "data/jobs.db"
    if not is_turso_active(db):
        raise SystemExit("Shared Turso credentials required; refusing local fallback")
    config = get_proxy_settings(db)
    proxies = config["proxies"][:2]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(probe, proxies))
    print(json.dumps({"runner": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
                      "mode": config["mode"], "configured": len(config["proxies"]),
                      "sampled": len(results), "results": results,
                      "classification": "Provider identity and residential status require provider verification"}))
    if not results or not all(result["status"] == "ok" for result in results):
        raise SystemExit("Saved proxy tunnel check failed")


if __name__ == "__main__":
    main()
