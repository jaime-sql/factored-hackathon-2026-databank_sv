const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const TOKEN = "qa-local-test-token";
const seen = [];

function el(id) {
  return {
    id: id || "",
    hidden: id === "test-mode-form",
    textContent: "",
    placeholder: "",
    value: "",
    className: "",
    children: [],
    dataset: {},
    listeners: {},
    addEventListener(type, fn) {
      this.listeners[type] = this.listeners[type] || [];
      this.listeners[type].push(fn);
    },
    appendChild(child) {
      this.children.push(child);
    },
    replaceChildren() {
      this.children = [];
    },
    focus() {},
    attributes: {},
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    getAttribute(name) {
      return name in this.attributes ? this.attributes[name] : null;
    },
  };
}

const nodes = {
  composer: el("composer"),
  lang: el("lang"),
  "test-badge": el("test-badge"),
  "test-mode-link": el("test-mode-link"),
  "test-mode-form": el("test-mode-form"),
  "test-token": el("test-token"),
  "test-mode-send": el("test-mode-send"),
  "test-mode-status": el("test-mode-status"),
  "test-ok-row": Object.assign(el("test-ok-row"), { hidden: true }),
  "test-ok-chip": el("test-ok-chip"),
  "test-mode-change": el("test-mode-change"),
  "test-mode-hint": Object.assign(el("test-mode-hint"), { hidden: true }),
  "test-token-error": Object.assign(el("test-token-error"), { hidden: true }),
  personas: el("personas"),
  charges: el("charges"),
  message: el("message"),
  send: el("send"),
  thread: el("thread"),
  "page-title": el("page-title"),
  lede: el("lede"),
  tour: el("tour"),
};

const document = {
  documentElement: { lang: "es" },
  getElementById(id) {
    return nodes[id] || null;
  },
  querySelector() {
    return null;
  },
  querySelectorAll() {
    return [];
  },
  createElement: () => el(""),
  createTextNode: (value) => ({ textContent: String(value) }),
};

const location = { search: `?test=${TOKEN}&keep=1`, href: `http://127.0.0.1/?test=${TOKEN}&keep=1` };
let posted = false;
let releasePost = null;

const context = {
  console,
  document,
  location,
  URLSearchParams,
  fetch: async (url, options = {}) => {
    seen.push({ url: String(url), options });
    if (String(url).includes("/api/i18n")) {
      return {
        ok: true,
        json: async () => ({
          es: { test_badge: "MODO PRUEBA", test_arm: "Modo de prueba", test_arm_send: "Activar" },
          pt: {},
        }),
      };
    }
    if (String(url).includes("/api/personas")) {
      return { ok: true, json: async () => ({ personas: [] }) };
    }
    if (String(url).includes("/api/test-mode")) {
      const isPost = options.method === "POST";
      const good = isPost && options.headers["X-Test-Token"] === TOKEN;
      if (good) posted = true;
      if (isPost && releasePost) await new Promise((resolve) => (releasePost.fn = resolve));
      return { ok: true, json: async () => ({ is_test: posted, accepted: good }) };
    }
    return { ok: true, json: async () => ({}) };
  },
};
context.window = context;
context.globalThis = context;
vm.runInNewContext(fs.readFileSync("static/js/catalog.js", "utf8"), context, {
  filename: "static/js/catalog.js",
});
vm.runInNewContext(fs.readFileSync("static/js/desk.js", "utf8"), context, { filename: "desk.js" });

setTimeout(async () => {
  const early = seen.filter((call) => call.options.method === "POST");
  assert.equal(early.length, 0, "a token in the URL must not be posted");
  assert.equal(location.search, `?test=${TOKEN}&keep=1`);
  assert.equal(nodes["test-badge"].hidden, true);
  assert.equal(nodes["test-mode-link"].textContent, "Modo de prueba");

  assert.equal(nodes["test-mode-form"].hidden, true, "token field hidden until Modo de prueba");
  nodes["test-mode-link"].listeners.click[0]({ preventDefault() {} });
  assert.equal(nodes["test-mode-form"].hidden, false);
  assert.equal(nodes["test-mode-link"].getAttribute("aria-expanded"), "true");
  // rejected token: red error under the field, aria-invalid, no chip, field stays open
  nodes["test-token"].value = "wrong-token";
  await nodes["test-mode-form"].listeners.submit[0]({ preventDefault() {} });
  assert.equal(nodes["test-token-error"].hidden, false);
  assert.equal(nodes["test-token-error"].textContent, "Token no válido");
  assert.equal(nodes["test-token"].getAttribute("aria-invalid"), "true");
  assert.equal(nodes["test-ok-row"].hidden, true, "no chip before the server accepts a token");
  assert.equal(nodes["test-mode-form"].hidden, false);
  assert.equal(nodes["test-badge"].hidden, true);

  // accepted token: double submit is ignored while the request is in flight
  releasePost = {};
  nodes["test-token"].value = TOKEN;
  const first = nodes["test-mode-form"].listeners.submit[0]({ preventDefault() {} });
  assert.equal(nodes["test-mode-send"].disabled, true, "send disabled while validating");
  nodes["test-token"].value = TOKEN;
  await nodes["test-mode-form"].listeners.submit[0]({ preventDefault() {} });
  await new Promise((resolve) => setTimeout(resolve, 0));
  releasePost.fn();
  await first;
  releasePost = null;
  const posts = seen.filter((call) => call.options.method === "POST" && call.url.includes("/api/test-mode"));
  assert.equal(posts.length, 2, "one request for the wrong token, one for the good one");
  assert.equal(posts[1].options.headers["X-Test-Token"], TOKEN);
  assert.equal(nodes["test-token"].value, "");
  assert.equal(location.href.includes("/api/test-mode"), false);
  const blob = JSON.stringify(nodes);
  assert.equal(blob.includes(TOKEN), false);
  assert.equal(nodes["test-badge"].hidden, false);
  assert.equal(nodes["test-badge"].textContent, "MODO PRUEBA");
  assert.equal(nodes["test-ok-row"].hidden, false, "chip shown once accepted");
  assert.equal(nodes["test-ok-chip"].textContent, "Modo de prueba activo ✓");
  assert.equal(nodes["test-mode-hint"].hidden, false);
  assert.equal(nodes["test-mode-hint"].textContent, "Ahora elige un cliente y escribe tu mensaje.");
  assert.equal(nodes["test-token-error"].hidden, true);
  assert.equal(nodes["test-token"].getAttribute("aria-invalid"), "false");
  assert.equal(nodes["test-mode-form"].hidden, true, "field hidden after success");
  assert.equal(nodes["test-mode-change"].hidden, false);
  assert.equal(nodes["test-mode-link"].getAttribute("aria-expanded"), "false");
  nodes["test-mode-change"].listeners.click[0]({ preventDefault() {} });
  assert.equal(nodes["test-mode-form"].hidden, false, "Cambiar reopens the field");
  assert.equal(nodes["test-mode-change"].hidden, true);
  nodes["test-mode-link"].listeners.click[0]({ preventDefault() {} });
  assert.equal(nodes["test-mode-form"].hidden, true, "Modo de prueba hides the field again");
  assert.equal(nodes["test-mode-link"].getAttribute("aria-expanded"), "false");

  const html = fs.readFileSync("static/index.html", "utf8");
  const form = html.slice(html.indexOf('<form id="test-mode-form"'), html.indexOf("</form>", html.indexOf('<form id="test-mode-form"')));
  assert.ok(/<form id="test-mode-form"[^>]*\shidden[\s>]/.test(html), "form starts hidden");
  assert.equal((html.match(/<label[^>]*for="test-token"/g) || []).length, 1, "one label for the token field");
  assert.ok(/<label class="visually-hidden" id="test-token-label" for="test-token">/.test(form), form);
  assert.ok(/<input id="test-token" type="password"/.test(form), form);
  assert.ok(/aria-controls="test-mode-form"/.test(html));
  const css = fs.readFileSync("static/css/app.css", "utf8");
  assert.ok(/#composer input,\s*#test-token \{[^}]*border-radius: 999px/.test(css), "token field shares the composer input style");
  const status = html.slice(html.indexOf('<div id="test-mode-status"'), html.indexOf("</div>", html.indexOf('<div id="test-mode-status"')));
  assert.ok(/aria-live="polite"/.test(status), status);
  assert.ok(status.includes('id="test-ok-chip"') && status.includes('id="test-token-error"'), "chip and error sit inside the live region");
  assert.ok(/aria-describedby="test-token-error"/.test(form));
  assert.ok(/\.test-ok-chip \{[^}]*border-radius: 999px[^}]*\}/.test(css), "chip uses the field's rounded style");
  assert.ok(/#test-token\[aria-invalid="true"\] \{ border-color: #b3261e; \}/.test(css));
  const lum = (hex) => {
    const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const ratio = (a, b) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
  const card = (css.match(/--card:\s*(#[0-9a-fA-F]{6})/) || [null, "#ffffff"])[1];
  const chipColor = css.match(/\.test-ok-chip \{[^}]*color: (#[0-9a-fA-F]{6})/)[1];
  const errColor = css.match(/\.test-token-error \{[^}]*color: (#[0-9a-fA-F]{6})/)[1];
  assert.ok(ratio(chipColor, card) >= 4.5, `chip contrast ${ratio(chipColor, card)}`);
  assert.ok(ratio(errColor, card) >= 4.5, `error contrast ${ratio(errColor, card)}`);
  const catalogText = fs.readFileSync("app/i18n.py", "utf8");
  for (const phrase of ["Modo de teste ativo ✓", "Alterar", "Token inválido", "Agora escolha um cliente e escreva sua mensagem."]) {
    assert.ok(catalogText.includes(phrase), phrase);
  }
  console.log("test mode js ok");
}, 50);
