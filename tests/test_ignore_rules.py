"""Image ignore files must keep static/data and drop only the root data directory."""

from __future__ import annotations

import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rules(text: str) -> list[tuple[bool, str, bool, bool]]:
    parsed: list[tuple[bool, str, bool, bool]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line[1:] if negate else line
        directory_only = pattern.endswith("/")
        if directory_only:
            pattern = pattern[:-1]
        anchored = pattern.startswith("/")
        if anchored:
            pattern = pattern[1:]
        parsed.append((negate, pattern, anchored, directory_only))
    return parsed


def _matches(path: str, pattern: str, *, anchored: bool, directory_only: bool) -> bool:
    path = path.strip("/")
    parts = path.split("/") if path else []
    if anchored:
        if directory_only:
            return path == pattern or path.startswith(pattern + "/")
        if fnmatch.fnmatch(path, pattern):
            return True
        parent: list[str] = []
        for part in parts[:-1]:
            parent.append(part)
            if fnmatch.fnmatch("/".join(parent), pattern):
                return True
        return False
    if "/" in pattern:
        folder = pattern.rstrip("/")
        return fnmatch.fnmatch(path, pattern) or path == folder or path.startswith(folder + "/")
    for index, part in enumerate(parts):
        if not fnmatch.fnmatch(part, pattern):
            continue
        if directory_only and index == len(parts) - 1:
            continue
        return True
    return False


def ignored(path: str, text: str) -> bool:
    state = False
    for negate, pattern, anchored, directory_only in _rules(text):
        if _matches(path, pattern, anchored=anchored, directory_only=directory_only):
            state = not negate
    return state


def test_static_data_is_not_excluded_from_the_image() -> None:
    for name in (".gcloudignore", ".dockerignore"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert ignored("static/data/x.json", text) is False
        assert ignored("data/bank.sqlite", text) is True
        assert ignored("data/ops.sqlite", text) is True
        assert "\ndata\n" not in f"\n{text}"
        assert "\n/data\n" in f"\n{text}"
