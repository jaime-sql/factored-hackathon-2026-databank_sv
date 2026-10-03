// Deterministic waits for the headless-Chrome layout tests. No fixed sleeps:
// navigation waits for the load event, then for the network to go idle (no request
// in flight for IDLE_MS), web fonts to finish, and two animation frames, so layout
// is measured after the page has fetched and rendered everything it asked for.
const http = require("http");

const IDLE_MS = 300;
const DEADLINE_MS = 20000;

function getJson(debugPort, path) {
  return new Promise((resolve, reject) => {
    http
      .get({ host: "127.0.0.1", port: debugPort, path }, (res) => {
        let body = "";
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => resolve(JSON.parse(body)));
      })
      .on("error", reject);
  });
}

async function openPage(debugPort) {
  const version = await getJson(debugPort, "/json/version");
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve) => ws.addEventListener("open", resolve));
  let id = 0;
  const pending = new Map();
  const listeners = new Set();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    } else if (message.method) {
      for (const fn of listeners) fn(message);
    }
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
  const attached = await call("Target.attachToTarget", {
    targetId: created.result.targetId,
    flatten: true,
  });
  const sessionId = attached.result.sessionId;
  const send = (method, params) => call(method, params, sessionId);

  const inflight = new Set();
  let lastActivity = Date.now();
  listeners.add((message) => {
    if (message.sessionId !== sessionId) return;
    const requestId = message.params && message.params.requestId;
    if (message.method === "Network.requestWillBeSent") inflight.add(requestId);
    if (message.method === "Network.loadingFinished" || message.method === "Network.loadingFailed") {
      inflight.delete(requestId);
    }
    if (message.method.startsWith("Network.")) lastActivity = Date.now();
  });

  function nextEvent(method) {
    return new Promise((resolve) => {
      const fn = (message) => {
        if (message.sessionId === sessionId && message.method === method) {
          listeners.delete(fn);
          resolve(message);
        }
      };
      listeners.add(fn);
    });
  }

  async function evaluate(expression, awaitPromise = false) {
    const out = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise });
    if (out.result && out.result.exceptionDetails) {
      throw new Error(`evaluate failed: ${expression}: ${JSON.stringify(out.result.exceptionDetails)}`);
    }
    return out.result && out.result.result ? out.result.result.value : undefined;
  }

  async function waitFor(expression, label) {
    const deadline = Date.now() + DEADLINE_MS;
    for (;;) {
      if (await evaluate(`Boolean(${expression})`)) return;
      if (Date.now() > deadline) throw new Error(`timed out waiting for ${label || expression}`);
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }

  async function settle() {
    const deadline = Date.now() + DEADLINE_MS;
    while (inflight.size > 0 || Date.now() - lastActivity < IDLE_MS) {
      if (Date.now() > deadline) throw new Error(`network never went idle (${inflight.size} in flight)`);
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    await waitFor("document.readyState === 'complete'", "readyState complete");
    await evaluate(
      "document.fonts.ready.then(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true)))))",
      true,
    );
  }

  async function navigate(url) {
    const loaded = nextEvent("Page.loadEventFired");
    await send("Page.navigate", { url });
    await loaded;
    await settle();
  }

  async function reload() {
    const loaded = nextEvent("Page.loadEventFired");
    await send("Page.reload", {});
    await loaded;
    await settle();
  }

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  return { ws, send, evaluate, waitFor, settle, navigate, reload };
}

module.exports = { openPage };
