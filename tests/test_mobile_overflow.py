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
const http = require("http");
const base = process.argv[1];
const debugPort = process.argv[2];
function get(path) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port: debugPort, path }, (res) => {
      let body = "";
      res.on("data", (chunk) => { body += chunk; });
      res.on("end", () => resolve(JSON.parse(body)));
    }).on("error", reject);
  });
}
function put(path) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: "127.0.0.1", port: debugPort, path, method: "PUT" }, (res) => {
      let body = "";
      res.on("data", (chunk) => { body += chunk; });
      res.on("end", () => resolve(JSON.parse(body)));
    });
    req.on("error", reject);
    req.end();
  });
}
(async () => {
  const version = await get("/json/version");
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve) => ws.addEventListener("open", resolve));
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) pending.get(message.id)(message);
  });
  function call(method, params) {
    const next = ++id;
    return new Promise((resolve) => {
      pending.set(next, resolve);
      ws.send(JSON.stringify({ id: next, method, params }));
    });
  }
  const created = await call("Target.createTarget", { url: "about:blank" });
  const session = await call("Target.attachToTarget", {
    targetId: created.result.targetId,
    flatten: true,
  });
  const sessionId = session.result.sessionId;
  function send(method, params) {
    const next = ++id;
    return new Promise((resolve) => {
      pending.set(next, resolve);
      ws.send(JSON.stringify({ id: next, sessionId, method, params }));
    });
  }
  await send("Page.enable");
  await send("Runtime.enable");
  const pages = ["/", "/agent", "/metrics"];
  const langs = ["es", "pt"];
  const failures = [];
  for (const lang of langs) {
    for (const page of pages) {
      await send("Page.navigate", { url: base + page });
      await new Promise((resolve) => setTimeout(resolve, 700));
      await send("Runtime.evaluate", {
        expression: `localStorage.setItem('hd_lang', ${JSON.stringify(lang)})`,
      });
      await send("Page.reload");
      await new Promise((resolve) => setTimeout(resolve, 900));
      const measured = await send("Runtime.evaluate", {
        expression: [
          "JSON.stringify({",
          "scroll: document.documentElement.scrollWidth,",
          "client: document.documentElement.clientWidth,",
          "body: document.body.scrollWidth",
          "})",
        ].join(""),
        returnByValue: true,
      });
      const size = JSON.parse(measured.result.result.value);
      if (size.scroll > size.client + 1 || size.body > size.client + 1) {
        failures.push({ lang, page, ...size });
      }
    }
  }
  console.log(JSON.stringify({ failures }));
  ws.close();
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
