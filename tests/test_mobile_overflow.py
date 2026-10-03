"""Customer, agent, and metrics pages stay within a 390px viewport."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = shutil.which("google-chrome") or shutil.which("chromium")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, proc: subprocess.Popen[bytes]) -> None:
    import urllib.request

    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"process exited {proc.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {url}")


def test_no_horizontal_overflow_at_390(tmp_path: Path) -> None:
    if CHROME is None:
        pytest.skip("headless Chrome is not available")
    port = _free_port()
    debug = _free_port()
    env = {
        "PATH": shutil.os.environ["PATH"],
        "BANK_DB_PATH": str(tmp_path / "bank.sqlite"),
        "OPS_DB_PATH": str(tmp_path / "ops.sqlite"),
        "DATABASE_URL": "",
        "SESSION_SECRET": "test-session-secret-value",
        "DEMO_AGENT_TOKEN": "demo-agent-local",
        "EVAL_RUNNER_TOKEN": "runner-secret",
        "HOME": str(tmp_path),
    }
    server = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    chrome = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--remote-debugging-port={debug}",
            f"--user-data-dir={tmp_path / 'chrome'}",
            "--window-size=390,844",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http(f"http://127.0.0.1:{port}/health", server)
        _wait_http(f"http://127.0.0.1:{debug}/json/version", chrome)
        script = r"""
const { openPage } = require("./tests/cdp_settle.js");
const base = process.argv[1];
const debugPort = process.argv[2];
const READY = {
  "/": "document.querySelectorAll('#personas button').length > 0",
  "/agent": "document.getElementById('token') !== null",
  "/metrics": "document.querySelectorAll('#tiles .tile').length > 0",
};
(async () => {
  const page = await openPage(debugPort);
  const { send, evaluate, waitFor, navigate, reload, settle } = page;
  await send("Emulation.setDeviceMetricsOverride", {
    width: 390, height: 844, deviceScaleFactor: 1, mobile: false,
  });
  const failures = [];
  for (const lang of ["es", "pt"]) {
    for (const path of ["/", "/agent", "/metrics"]) {
      await navigate(base + path);
      await evaluate(`localStorage.setItem('hd_lang', ${JSON.stringify(lang)})`);
      await reload();
      await waitFor(
        `document.documentElement.lang === ${JSON.stringify(lang)}`,
        `${path} ${lang} lang`,
      );
      await waitFor(READY[path], `${path} rendered`);
      await settle();
      const size = JSON.parse(await evaluate(
        "JSON.stringify({scroll: document.documentElement.scrollWidth, "
        + "client: document.documentElement.clientWidth, body: document.body.scrollWidth})"
      ));
      if (size.scroll > size.client + 1 || size.body > size.client + 1) {
        failures.push({ lang, page: path, ...size });
      }
    }
  }
  console.log(JSON.stringify({ failures }));
  page.ws.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
        completed = subprocess.run(
            ["node", "-e", script, f"http://127.0.0.1:{port}", str(debug)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        assert payload["failures"] == []
    finally:
        chrome.kill()
        server.kill()
        chrome.wait(timeout=5)
        server.wait(timeout=5)
