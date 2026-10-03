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
const { openPage } = require("./tests/cdp_settle.js");
const base = process.argv[1];
const debugPort = process.argv[2];
(async () => {
  const page = await openPage(debugPort);
  const { send, evaluate, waitFor, settle, navigate } = page;
  const failures = [];
  const sizes = [[1280, 800], [1440, 900]];
  for (const [width, height] of sizes) {
    await send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: false,
    });
    await navigate(base + "/");
    // The header is final once the catalog and the persona pills have rendered.
    await waitFor("document.querySelectorAll('#personas button').length > 0", "persona pills");
    await settle();
    await evaluate("document.getElementById('tour').click(); 'ok'");
    for (const step of [1, 2]) {
      await waitFor(`(() => {
        const tip = document.querySelector('.tour-tip');
        const count = document.querySelector('.tour-count');
        return tip && !tip.hidden && count && count.textContent.startsWith('${step}/');
      })()`, `tour step ${step}`);
      await settle();
      const value = JSON.parse(await evaluate(`(() => {
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
        })()`));
      const covered = value.hidden || !value.count.startsWith(step + "/");
      const blocked = !value.hitTour || value.overlaps || value.tipTop < value.headerBottom - 1;
      if (covered || blocked) failures.push({ width, height, step, ...value });
      if (step === 1) await evaluate("document.querySelectorAll('.tour-tip button')[1].click()");
    }
    await evaluate("document.getElementById('tour').click()");
    await waitFor("document.querySelector('.tour-tip').hidden", "tour closed").catch(() => {
      failures.push({ width, height, step: "close" });
    });
  }
  console.log(JSON.stringify({ failures }));
  page.ws.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
