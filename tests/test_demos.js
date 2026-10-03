const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const scrolls = [];
const posts = [];

function el(tag, id) {
  return {
    tagName: String(tag || "div").toUpperCase(),
    id: id || "",
    hidden: id === "test-mode-form",
    textContent: "",
    placeholder: "",
    value: "",
    className: "",
    type: "",
    dataset: {},
    children: [],
    attributes: {},
    listeners: {},
    parent: null,
    addEventListener(type, fn) {
      this.listeners[type] = this.listeners[type] || [];
      this.listeners[type].push(fn);
    },
    appendChild(child) {
      child.parent = this;
      this.children.push(child);
      return child;
    },
    append(...items) {
      for (const item of items) this.appendChild(item);
    },
    remove() {
      if (!this.parent) return;
      this.parent.children = this.parent.children.filter((child) => child !== this);
    },
    replaceChildren(...items) {
      this.children = [];
      this.append(...items);
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    getAttribute(name) {
      return name in this.attributes ? this.attributes[name] : null;
    },
    querySelectorAll(selector) {
      if (selector !== "button") return [];
      return this.children.filter((child) => child.tagName === "BUTTON");
    },
    scrollIntoView(options) {
      scrolls.push({ className: this.className, options });
    },
    focus() {},
  };
}

const ids = [
  "composer", "lang", "test-badge", "test-mode-link", "test-mode-form", "test-token",
  "test-mode-send", "personas", "demos", "demos-title", "charges", "message", "send",
  "thread", "page-title", "lede", "tour", "break-it",
];
const nodes = Object.fromEntries(ids.map((id) => [id, el(id === "demos-title" ? "h2" : "section", id)]));

const document = {
  documentElement: { lang: "es" },
  getElementById: (id) => nodes[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => el(tag),
  createTextNode: (value) => ({ textContent: String(value) }),
};

const CASES = {
  TXN_c9d2185cbd2ab37f95d7: { band: "high", actions: [{ id: "confirm_block", label: "Sí, bloquear" }] },
  TXN_eef1352d123d275d7602: { band: "review", actions: [] },
  TXN_ddcd20809f49f3b0a60c: { band: "out_of_scope", actions: [{ id: "contest", label: "Pedir revisión" }] },
};

const json = (body) => ({ ok: true, status: 200, json: async () => body });
const context = {
  console,
  document,
  location: { search: "", href: "http://127.0.0.1/" },
  URLSearchParams,
  localStorage: { getItem: () => null, setItem() {} },
  fetch: async (url, options = {}) => {
    const path = String(url);
    if (path.includes("/api/personas")) return json({ personas: [{ id: "teo", label: "Teo" }, { id: "maria", label: "María" }] });
    if (path.includes("/api/test-mode")) return json({ is_test: false });
    if (path.includes("/api/session")) {
      const persona = JSON.parse(options.body).persona;
      posts.push({ session: persona, testHeader: Boolean(options.headers && options.headers["X-Test-Token"]) });
      return json({ token: `tok-${persona}`, is_test: false });
    }
    if (path.includes("/api/transactions")) return json({ transactions: [] });
    if (path.endsWith("/cases") && options.method === "POST") {
      const body = JSON.parse(options.body);
      posts.push({ case: body.transaction_key, message: body.message, auth: options.headers.authorization, demo: body.demo_case });
      return json({ case_id: `case-${body.transaction_key}`, reply: "ok", ...CASES[body.transaction_key] });
    }
    if (path.includes("/trail")) return json({ steps: [{ at: "1 oct", band: "high", reason: "x" }] });
    return json({});
  },
};
context.globalThis = context;
vm.runInNewContext(fs.readFileSync("static/js/catalog.js", "utf8"), context, { filename: "catalog.js" });
vm.runInNewContext(fs.readFileSync("static/js/desk.js", "utf8"), context, { filename: "desk.js" });

const flush = () => new Promise((resolve) => setTimeout(resolve, 20));

(async () => {
  await flush();
  const catalog = context.HD_CATALOG;
  const buttons = nodes.demos.querySelectorAll("button");
  assert.equal(buttons.length, 3, "three demo buttons");
  assert.deepEqual(buttons.map((b) => b.getAttribute("data-demo")), ["high", "review", "pending"]);
  const chips = buttons.map((b) => b.children[1].textContent);
  assert.deepEqual(chips, ["Bloqueo · riesgo alto", "Revisión humana", "Pendiente"]);
  assert.deepEqual(chips, [catalog.es.demo_chip_high, catalog.es.demo_chip_review, catalog.es.demo_chip_pending]);
  assert.equal(nodes["demos-title"].textContent, catalog.es.demo_title);

  for (const [index, key] of ["TXN_c9d2185cbd2ab37f95d7", "TXN_eef1352d123d275d7602", "TXN_ddcd20809f49f3b0a60c"].entries()) {
    scrolls.length = 0;
    posts.length = 0;
    await buttons[index].listeners.click[0]();
    await flush();
    const persona = index === 2 ? "maria" : "teo";
    assert.deepEqual(posts[0], { session: persona, testHeader: false }, "public mode signs in without a token");
    assert.equal(posts[1].case, key);
    assert.equal(posts[1].message, catalog.es.dispute);
    assert.equal(posts[1].auth, `Bearer tok-${persona}`);
    assert.equal(posts[1].demo, true, "demo buttons flag the case as a demo");
    const smooth = scrolls.find((s) => s.options && s.options.behavior === "smooth");
    assert.ok(smooth, "demo scrolls smoothly");
    assert.equal(smooth.className, "why", "scrolls to the ¿Por qué? panel");
    assert.equal(nodes.thread.children[0].getAttribute("data-band"), CASES[key].band);
  }

  nodes.lang.listeners.click[0]();
  await flush();
  const pt = nodes.demos.querySelectorAll("button");
  assert.equal(pt.length, 3, "language switch re-renders, not duplicates");
  assert.deepEqual(pt.map((b) => b.children[1].textContent), ["Bloqueio · risco alto", "Revisão humana", "Pendente"]);
  assert.equal(pt[2].children[0].textContent, catalog.pt.demo_pending);
  console.log("demos ok");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
