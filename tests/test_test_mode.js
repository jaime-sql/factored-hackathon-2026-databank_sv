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
      if (isPost) posted = true;
      return { ok: true, json: async () => ({ is_test: isPost || posted }) };
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
  nodes["test-token"].value = TOKEN;
  await nodes["test-mode-form"].listeners.submit[0]({ preventDefault() {} });

  const post = seen.find((call) => call.options.method === "POST" && call.url.includes("/api/test-mode"));
  assert.ok(post, "expected a test-mode request");
  assert.equal(post.options.headers["X-Test-Token"], TOKEN);
  assert.equal(nodes["test-token"].value, "");
  assert.equal(location.href.includes("/api/test-mode"), false);
  const blob = JSON.stringify(nodes);
  assert.equal(blob.includes(TOKEN), false);
  assert.equal(nodes["test-badge"].hidden, false);
  assert.equal(nodes["test-badge"].textContent, "MODO PRUEBA");
  nodes["test-mode-link"].listeners.click[0]({ preventDefault() {} });
  assert.equal(nodes["test-mode-form"].hidden, true, "second click hides the field again");
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
  console.log("test mode js ok");
}, 50);
