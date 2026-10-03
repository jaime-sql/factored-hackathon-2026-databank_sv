"""The desktop guide sits below the header so the tour button can close it."""

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


def test_guide_stays_below_the_nav(tmp_path: Path) -> None:
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
        ["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
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
            "--window-size=1440,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http(f"http://127.0.0.1:{port}/", server)
        _wait_http(f"http://127.0.0.1:{debug}/json/version", chrome)
        completed = subprocess.run(
            ["node", "-e", _SCRIPT, f"http://127.0.0.1:{port}", str(debug)],
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


_SCRIPT = r"""
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
  function call(method, params, sessionId) {
    const next = ++id;
    return new Promise((resolve) => {
      pending.set(next, resolve);
      const payload = { id: next, method, params };
      if (sessionId) payload.sessionId = sessionId;
      ws.send(JSON.stringify(payload));
    });
  }
  const created = await call("Target.createTarget", { url: "about:blank" });
  const session = await call("Target.attachToTarget", {
    targetId: created.result.targetId,
    flatten: true,
  });
  const sessionId = session.result.sessionId;
  const send = (method, params) => call(method, params, sessionId);
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1280,
    height: 800,
    deviceScaleFactor: 1,
    mobile: false,
  });
  const failures = [];
  const sizes = [[1280, 800], [1440, 900]];
  for (const [width, height] of sizes) {
    await send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: false,
    });
    await send("Page.navigate", { url: base + "/" });
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const opened = await send("Runtime.evaluate", {
      expression: "document.getElementById('tour').click(); 'ok'",
      returnByValue: true,
    });
    if (!opened.result || !opened.result.result) failures.push({ width, height, step: "open" });
    for (const step of [1, 2]) {
      const measured = await send("Runtime.evaluate", {
        expression: `(() => {
          const tour = document.getElementById('tour');
          const tip = document.querySelector('.tour-tip');
          const header = document.querySelector('header');
          const tourBox = tour.getBoundingClientRect();
          const tipBox = tip.getBoundingClientRect();
          const headerBox = header.getBoundingClientRect();
          const hit = document.elementFromPoint(
            tourBox.left + tourBox.width / 2,
            tourBox.top + tourBox.height / 2
          );
          const overlaps = !(
            tipBox.bottom <= headerBox.top || tipBox.top >= headerBox.bottom ||
            tipBox.right <= headerBox.left || tipBox.left >= headerBox.right
          );
          return JSON.stringify({
            count: document.querySelector('.tour-count').textContent,
            hidden: tip.hidden,
            hitTour: hit === tour,
            overlaps,
            tipTop: tipBox.top,
            headerBottom: headerBox.bottom,
          });
        })()`,
        returnByValue: true,
      });
      const value = JSON.parse(measured.result.result.value);
      const covered = value.hidden || !value.count.startsWith(step + "/");
      const blocked = !value.hitTour || value.overlaps || value.tipTop < value.headerBottom - 1;
      if (covered || blocked) {
        failures.push({ width, height, step, ...value });
      }
      if (step === 1) {
        await send("Runtime.evaluate", {
          expression: "document.querySelectorAll('.tour-tip button')[1].click()",
          returnByValue: true,
        });
      }
    }
    const closed = await send("Runtime.evaluate", {
      expression: `(() => {
        document.getElementById('tour').click();
        return JSON.stringify({ hidden: document.querySelector('.tour-tip').hidden });
      })()`,
      returnByValue: true,
    });
    const after = JSON.parse(closed.result.result.value);
    if (!after.hidden) failures.push({ width, height, step: "close", ...after });
  }
  console.log(JSON.stringify({ failures }));
  ws.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
