"""The Cloud Run image only copies app, triage, static, and migrations."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _copied_roots() -> set[str]:
    roots: set[str] = set()
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("COPY ") or stripped.startswith("COPY --from"):
            continue
        parts = stripped.split()
        destination = parts[-1].removeprefix("./").strip("/")
        if destination in {"", "."}:
            continue
        roots.add(destination.split("/")[0])
    return roots


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path: Path) -> set[str]:
    current = _module_name(path)
    package = current.rsplit(".", 1)[0] if "." in current else current
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom) or node.module is None and not node.level:
            continue
        module = node.module or ""
        if node.level:
            parts = package.split(".")
            if node.level > 1:
                parts = parts[: 1 - node.level]
            base = ".".join(parts)
            module = f"{base}.{module}" if module else base
        if module:
            found.add(module)
    return found


def test_image_import_graph_does_not_reach_evals() -> None:
    copied = _copied_roots()
    assert {"app", "triage", "static", "migrations"} <= copied
    assert "evals" not in copied
    offenders: list[str] = []
    seen: set[str] = set()
    pending = ["app.main"]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        top = name.split(".", 1)[0]
        if (ROOT / top).is_dir() and top not in copied:
            offenders.append(name)
            continue
        file = ROOT.joinpath(*name.split(".")).with_suffix(".py")
        init = ROOT.joinpath(*name.split(".")) / "__init__.py"
        path = file if file.is_file() else init if init.is_file() else None
        if path is None:
            continue
        for imported in _imported_modules(path):
            pending.append(imported)
    assert offenders == []
    for path in (ROOT / "app").rglob("*.py"):
        for imported in _imported_modules(path):
            assert imported != "evals"
            assert not imported.startswith("evals.")
