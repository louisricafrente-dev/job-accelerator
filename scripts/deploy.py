"""Run regression checks before invoking an already-configured Vercel CLI."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / "scripts/check_regressions.py")], cwd=root, check=True)
cli = shutil.which("vercel")
if not cli:
    raise SystemExit("Vercel CLI was not found; checks passed but no deployment was started.")
subprocess.run([cli, *sys.argv[1:]], cwd=root, check=True)
