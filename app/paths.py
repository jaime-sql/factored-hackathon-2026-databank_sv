"""Repository paths. The image keeps source on disk and does not install the project."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    override = os.environ.get("APP_ROOT", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent
