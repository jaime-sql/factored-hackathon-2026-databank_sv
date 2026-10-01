const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const TOKEN = "qa-local-test-token";
const seen = [];
const replaced = [];

function el(id) {
  return {
    id: id || "",
    hidden: true,
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
  };
}

const nodes = {
  composer: el("composer"),
  lang: el("lang"),
  "test-badge": el("test-badge"),
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

const location = { search: `?test=${TOKEN}&keep=1` };
const history = {
  replaceState(_state, _title, url) {
    replaced.push(url);
    location.search = "";
  },
};

const context = {
  console,
  document,
  location,
  history,
  URLSearchParams,
  fetch: async (url, options = {}) => {
    seen.push({ url: String(url), options });
    if (String(url).includes("/api/i18n")) {
      return { ok: true, json: async () => ({ es: { test_badge: "MODO PRUEBA" }, pt: {} }) };
    }
    if (String(url).includes("/api/personas")) {
      return { ok: true, json: async () => ({ personas: [] }) };
    }
    if (String(url).includes("/api/test-mode")) {
      return { ok: true, json: async () => ({ is_test: true }) };
    }
    return { ok: true, json: async () => ({}) };
  },
};
context.window = context;
context.globalThis = context;
vm.runInNewContext(fs.readFileSync("static/js/desk.js", "utf8"), context, { filename: "desk.js" });

setTimeout(() => {
  const post = seen.find((call) => call.options.method === "POST" && call.url.includes("/api/test-mode"));
  assert.ok(post, "expected a test-mode request");
  assert.equal(post.options.headers["X-Test-Token"], TOKEN);
  assert.equal(JSON.stringify(post.options).includes(TOKEN), true);
  assert.equal(replaced.includes("/?keep=1"), true);
  assert.equal(location.search.includes(TOKEN), false);
  const blob = JSON.stringify(nodes);
  assert.equal(blob.includes(TOKEN), false);
  assert.equal(nodes["test-badge"].hidden, false);
  assert.equal(nodes["test-badge"].textContent, "MODO PRUEBA");
  console.log("test mode js ok");
}, 50);
