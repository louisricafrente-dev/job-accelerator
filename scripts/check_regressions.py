"""Local offline checks used by the guarded deployment command."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    for name in ("VERCEL", "RENDER", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
        os.environ.pop(name, None)
    with patch("src.aggregator.get_default_connectors", return_value=[]), patch(
        "socket.socket.connect", side_effect=AssertionError("Live network access is disabled in regression checks")
    ):
        suite = unittest.defaultTestLoader.discover("tests")
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        if not result.wasSuccessful():
            return 1
        from tests.test_auth import test_auth_and_isolation
        from tests.test_server_auth import test_full_auth_and_guest_isolation
        test_auth_and_isolation()
        test_full_auth_and_guest_isolation()
    for command in (["node", "--check", "src/static/app.js"],
                    ["node", "tests/frontend_regressions.cjs"],
                    ["node", "tests/workflow_regressions.cjs"],
                    ["node", "tests/settings_regressions.cjs"],
                    ["git", "diff", "--check"]):
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
