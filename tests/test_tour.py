"""The walkthrough script is on every page, and each step target is real or dynamic."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tour_script_and_selectors() -> None:
    completed = subprocess.run(
        ["node", "tests/test_tour.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
