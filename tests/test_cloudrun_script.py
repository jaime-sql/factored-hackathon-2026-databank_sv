"""deploy/cloudrun.sh targets the live service, maps the real secrets, and never moves traffic."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "cloudrun.sh"
SECRETS = {
    "DEMO_AGENT_TOKEN": "admin-token",
    "DEMO_JUDGE_TOKEN": "demo-judge-token",
    "QA_TEST_TOKEN": "qa-test-token",
    "EVAL_RUNNER_TOKEN": "eval-runner-token",
    "DATABASE_URL": "database-url",
    "SESSION_SECRET": "session-secret",
    "OPENAI_API_KEY": "openai-api-key",
}


def _dry_run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DRY_RUN": "1"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


needs_git = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs a git checkout"
)


@needs_git
def test_default_deploy_is_no_traffic_next_tag_on_the_live_service() -> None:
    result = _dry_run("next", "HEAD")
    assert result.returncode == 0, result.stderr
    deploy = next(line for line in result.stdout.splitlines() if "run deploy" in line)
    assert "databank-sv-app" in deploy
    assert "--project databank-sv-123456" in deploy
    assert "--region us-central1" in deploy
    assert "--no-traffic" in deploy
    assert "--tag next" in deploy
    assert "--min-instances 1" in deploy
    for env, secret in SECRETS.items():
        assert f"{env}={secret}:latest" in deploy, env
    build = next(line for line in result.stdout.splitlines() if "builds submit" in line)
    assert "us-central1-docker.pkg.dev/databank-sv-123456/databank-sv/app:" in build
    assert "--async" in build


@needs_git
def test_bad_tag_is_refused() -> None:
    result = _dry_run("Not_A_Tag", "HEAD")
    assert result.returncode != 0
    assert "TAG must be" in result.stderr


def test_script_never_moves_traffic_or_handles_secret_values() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    commands = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "--to-latest" not in commands
    assert "update-traffic" not in commands
    assert "secrets versions" not in commands
    assert "secrets create" not in commands
    assert "--source" not in commands
