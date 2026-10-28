"""Poll one targeted flconsole search into the existing cloud dashboard."""
import json
import os
from pathlib import Path
import sys
import time
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    print("Standalone Upwork polling retired; Upwork runs with the midnight scrape.")


if __name__ == "__main__":
    if "--background" in sys.argv:
        log_dir = Path(os.environ["LOCALAPPDATA"]) / "JobAccelerator"
        log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log_dir / "upwork.log", "a", encoding="utf-8", buffering=1)
    main()
