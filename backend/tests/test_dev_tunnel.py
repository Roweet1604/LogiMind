"""npm run dev takes the tunnel address only from cloudflared's success banner (decision 0043).

Runs the Node tests in scripts/tunnel.test.mjs; skipped when Node is not installed.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_tunnel_output_parser():
    r = subprocess.run(["node", "--test", "scripts/tunnel.test.mjs"], cwd=BACKEND, capture_output=True,
                       text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
