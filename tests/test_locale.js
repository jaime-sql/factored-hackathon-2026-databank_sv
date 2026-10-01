const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const vm = require("node:vm");

const dumped = execFileSync(
  "uv",
  [
    "run",
    "python",
    "-c",
    [
      "import json",
      "from app.i18n import persona_label, persona_note, ui_catalog",
      "ids = ['ana', 'camilo', 'maria', 'teo', 'lucia']",
      "fallback = {'lucia': 'Lucía · Querétaro', 'teo': 'Teo · Tijuana', 'ana': 'Ana · Argentina', 'camilo': 'Camilo · Colombia', 'maria': 'María · Ciudad de México'}",
      "personas = []",
      "for pid in ids:",
      "    personas.append({",
      "        'id': pid,",
      "        'label': persona_label('es', pid, fallback[pid]),",
      "        'labels': {'es': persona_label('es', pid, fallback[pid]), 'pt': persona_label('pt', pid, fallback[pid])},",
      "        'tz': 'America/Mexico_City',",
      "        'note': 'Synthetic persona',",
      "        'notes': {'es': persona_note('es', pid, postgres=False), 'pt': persona_note('pt', pid, postgres=False)},",
      "    })",
      "print(json.dumps({'catalog': ui_catalog(), 'personas': personas}))",
    ].join("\n"),
  ],
  { encoding: "utf8" },
);
const { catalog, personas } = JSON.parse(dumped);

class El {
  constructor(tag) {
    this.tagName = String(tag || "").toUpperCase();
    this.children = [];
    this.id = "";
    this.className = "";
    this.hidden = false;
    this.placeholder = "";
    this.value = "";
    this.text = "";
    this.checked = false;
    this.attrs = {};
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.classList = {
      add: (name) => {
        const names = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
        names.add(name);
        this.className = [...names].join(" ");
      },
      remove: (name) => {
        this.className = String(this.className || "")
          .split(/\s+/)
          .filter((item) => item && item !== name)
          .join(" ");
      },
    };
  }

  scrollIntoView() {}

  getBoundingClientRect() {
    return { top: 0, left: 0, bottom: 0, right: 0, width: 0, height: 0 };
  }

  set textContent(value) {
    this.text = value == null ? "" : String(value);
    this.children = [];
  }

  get textContent() {
    if (this.children.length) return this.children.map((child) => child.textContent).join("");
    return this.text;
  }

  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name === "id") this.id = String(value);
    if (name.startsWith("data-")) {
      const key = name
        .slice(5)
        .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      this.dataset[key] = String(value);
    }
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
  }

  removeAttribute(name) {
    delete this.attrs[name];
  }

  addEventListener(type, fn) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(fn);
  }

  dispatchEvent(event) {
    const type = event && event.type;
    for (const fn of this.listeners[type] || []) fn(event);
  }

  appendChild(child) {
    child.parent = this;
    this.children.push(child);
    return child;
  }

  append(...nodes) {
    for (const node of nodes) this.appendChild(node);
  }

  replaceChildren(...nodes) {
    this.children = [];
    this.text = "";
    for (const node of nodes) this.appendChild(node);
  }

  getElementById(id) {
    if (this.id === id) return this;
    for (const child of this.children) {
      const found = child.getElementById(id);
      if (found) return found;
    }
    return null;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const parts = selector.trim().split(/\s+/);
    let current = [this];
    for (const part of parts) {
      const next = [];
      for (const node of current) {
        for (const el of descendants(node)) {
          if (matches(el, part)) next.push(el);
        }
      }
      current = next;
    }
    return current;
  }
}

function descendants(el) {
  const all = [];
  for (const child of el.children || []) {
    all.push(child);
    all.push(...descendants(child));
  }
  return all;
}

function matches(el, selector) {
  if (selector.startsWith("#")) return el.id === selector.slice(1);
  if (selector.startsWith(".")) return el.className.split(/\s+/).includes(selector.slice(1));
  const attr = /^([a-z]*)\[([^\]]+)="([^"]+)"\]$/i.exec(selector);
  if (attr) {
    if (attr[1] && el.tagName !== attr[1].toUpperCase()) return false;
    return el.getAttribute(attr[2]) === attr[3];
  }
  const tagged = /^([a-z]+)\.([a-z0-9_-]+)$/i.exec(selector);
  if (tagged) {
    return el.tagName === tagged[1].toUpperCase() && el.className.split(/\s+/).includes(tagged[2]);
  }
  if (/^[a-z]+$/i.test(selector)) return el.tagName === selector.toUpperCase();
  return false;
}

function makeDocument(page) {
  const document = new El("#document");
  const html = new El("html");
  const body = new El("body");
  body.dataset.tourPage = page;
  html.appendChild(body);
  document.appendChild(html);
  document.documentElement = html;
  document.body = body;
  document.createElement = (tag) => new El(tag);
  document.createTextNode = (value) => {
    const node = new El("#text");
    node.text = String(value);
    return node;
  };
  return document;
}

function header(document, title, lede) {
  const h1 = document.createElement("h1");
  h1.id = "page-title";
  h1.textContent = title;
  const p = document.createElement("p");
  p.id = "lede";
  p.className = "lede";
  p.textContent = lede;
  const nav = document.createElement("nav");
  for (const [href, label] of [["/", "Cliente"], ["/agent", "Consola"], ["/metrics", "Métricas"]]) {
    const anchor = document.createElement("a");
    anchor.setAttribute("href", href);
    anchor.textContent = label;
    nav.appendChild(anchor);
  }
  const lang = document.createElement("button");
  lang.id = "lang";
  lang.textContent = "Español";
  const tour = document.createElement("button");
  tour.id = "tour";
  tour.textContent = "¿Cómo funciona?";
  nav.append(lang, tour);
  document.body.append(h1, p, nav);
  return { lang, tour };
}

function blob(root) {
  const parts = [];
  function walk(el) {
    const classes = String(el.className || "").split(/\s+/);
    if (classes.includes("reply")) return;
    if (classes.includes("tour-tip") || classes.includes("tour-shade")) return;
    if (el.tagName === "LI") return;
    if (el.id === "raw") return;
    if (el.placeholder) parts.push(el.placeholder);
    if (el.children && el.children.length) {
      for (const child of el.children) walk(child);
    } else if (el.text) parts.push(el.text);
  }
  walk(root);
  return ` ${parts.join("\n")} `;
}

async function flush() {
  for (let i = 0; i < 30; i += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

const memoryStore = new Map();
const localStorage = {
  getItem(key) {
    return memoryStore.has(key) ? memoryStore.get(key) : null;
  },
  setItem(key, value) {
    memoryStore.set(key, String(value));
  },
};

class DomEvent {
  constructor(type) {
    this.type = type;
  }
}

function run(filename, document, fetchImpl) {
  const context = {
    console,
    document,
    fetch: fetchImpl,
    setTimeout,
    clearTimeout,
    URL,
    URLSearchParams,
    localStorage,
    Event: DomEvent,
    innerHeight: 800,
    innerWidth: 1200,
  };
  context.window = context;
  context.globalThis = context;
  context.addEventListener = () => {};
  vm.runInNewContext(fs.readFileSync("static/js/catalog.js", "utf8"), context, {
    filename: "static/js/catalog.js",
  });
  vm.runInNewContext(fs.readFileSync(filename, "utf8"), context, { filename });
  return context;
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const esOnly = [
  catalog.es.client_lede,
  catalog.es.charges_title,
  catalog.es.dispute,
  catalog.es.why,
  catalog.es.tour_open,
  catalog.es.message_placeholder,
  catalog.es.agent_title,
  catalog.es.agent_lede,
  catalog.es.token_placeholder,
  catalog.es.load_queue,
  catalog.es.queue_empty,
  catalog.es.queue_failed,
  catalog.es.queue_loading,
  catalog.es.open_packet,
  catalog.es.packet_error,
  catalog.es.resolved,
  catalog.es.metrics_lede,
  catalog.es.tile_containment,
  catalog.es.tile_eval,
  catalog.es.eval_toggle,
  catalog.es.status.Approved,
  catalog.es.status.Pending,
  catalog.es.status.Reversed,
  "Approved",
  "Pending",
  "Reversed",
  "Challenge data customer",
  "Synthetic persona",
  "Mexico City",
  " may ",
  " ene ",
  "Ciudad de México",
];

const ptOnly = [
  catalog.pt.client_lede,
  catalog.pt.charges_title,
  catalog.pt.dispute,
  catalog.pt.why,
  catalog.pt.tour_open,
  catalog.pt.message_placeholder,
  catalog.pt.agent_title,
  catalog.pt.agent_lede,
  catalog.pt.token_placeholder,
  catalog.pt.load_queue,
  catalog.pt.queue_empty,
  catalog.pt.queue_failed,
  catalog.pt.queue_loading,
  catalog.pt.open_packet,
  catalog.pt.packet_error,
  catalog.pt.resolved,
  catalog.pt.metrics_lede,
  catalog.pt.tile_containment,
  catalog.pt.tile_eval,
  catalog.pt.eval_toggle,
  catalog.pt.status.Approved,
  catalog.pt.status.Pending,
  catalog.pt.status.Reversed,
  "Pessoa sintética",
  " mai ",
  " jan ",
  "Cidade do México",
];

function assertAbsent(text, words, label) {
  for (const word of words) {
    assert.equal(text.includes(word), false, `${label} still shows ${word}`);
  }
}

const ENGLISH = [
  "Handoff",
  "offline",
  "excluded",
  "Approved",
  "Pending",
  "Reversed",
  "Declined",
  "Payment",
  "Deposit",
  "Withdrawal",
  "Transfer",
  "Purchase",
  "Adjustment",
  "HIGH",
  "Eval",
];

function collectStrings(value, out) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectStrings(item, out));
  else if (value && typeof value === "object") {
    for (const item of Object.values(value)) collectStrings(item, out);
  }
}

function englishWord(word) {
  const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![\\p{L}\\p{N}_])${escaped}(?![\\p{L}\\p{N}_])`, "u");
}

function assertNoEnglish(text, label, extra = []) {
  for (const word of [...ENGLISH, ...extra]) {
    assert.equal(englishWord(word).test(text), false, `${label} still shows ${word}`);
  }
}

assert.equal(englishWord("Transfer").test("Transferencia"), false);
assert.equal(englishWord("Transfer").test("Transferência"), false);
assert.equal(englishWord("Transfer").test("tipo Transferencia"), false);
assert.equal(englishWord("Transfer").test("Transfer"), true);
assert.equal(englishWord("Transfer").test("El tipo Transfer."), true);

function catalogText(lang) {
  const out = [];
  collectStrings(catalog[lang], out);
  return out.join("\n");
}

assertNoEnglish(catalogText("es"), "es catalog", ["Console"]);
assertNoEnglish(catalogText("pt"), "pt catalog", ["Consola", "Ver cola", "Abrir paquete"]);
assert.ok(catalogText("pt").includes("Console"));
assert.ok(catalogText("pt").includes("Ver fila"));
assert.ok(catalogText("pt").includes("Abrir pacote"));

const { GUIDE } = require("../static/js/tour.js");
function tourCopy(lang) {
  return Object.values(GUIDE.pages)
    .flat()
    .map((step) => step[lang])
    .join("\n");
}
assertNoEnglish(tourCopy("es"), "tour es", ["Console"]);
assertNoEnglish(tourCopy("pt"), "tour pt", ["Consola", "Ver cola", "Abrir paquete"]);
assert.ok(GUIDE.pages.agent[6].pt.startsWith("Ver fila"));
assert.ok(GUIDE.pages.agent[8].pt.startsWith("Abrir pacote"));
for (const file of ["static/index.html", "static/agent.html", "static/metrics.html"]) {
  const html = fs.readFileSync(file, "utf8");
  assertNoEnglish(html, file, ["Console"]);
  assert.ok(html.includes('localStorage.getItem("hd_lang")'), file);
  assert.ok(html.includes("i18n-pending"), file);
  assert.ok(html.includes("visibility:hidden"), file);
  assert.ok(html.includes('src="/static/js/catalog.js"'), file);
  assert.equal(html.includes("setTimeout"), false, file);
  assert.equal(html.includes("/api/i18n"), false, file);
}
for (const file of ["static/js/desk.js", "static/js/agent.js", "static/js/metrics.js"]) {
  const source = fs.readFileSync(file, "utf8");
  assert.equal(source.includes("/api/i18n"), false, file);
}

function charges(lang) {
  const status = catalog[lang].status;
  const month = lang === "pt" ? "mai" : "may";
  const jan = lang === "pt" ? "jan" : "ene";
  return [
    ["a", "Uber", status.Approved, `19 ${month} 2026, 12:00 CST`, "Ciudad", 10, "MXN", ""],
    ["b", "Farmacia", status.Pending, `15 ${jan} 2026, 12:00 CST`, "Ciudad", 10, "MXN", ""],
    ["c", "Tienda", status.Reversed, "25 abr 2026, 12:00 CST", "Ciudad", 10, "MXN", ""],
    ["d", "Kiosco", status.Declined, `1 ${month} 2026, 12:00 CST`, "", 1645.6, "USD", ""],
    ["e", "", status.Approved, `2 ${month} 2026, 12:00 CST`, "", 10, "MXN", "Payment"],
  ].map(([key, merchant, statusLabel, local, city, amount, currency, type]) => ({
    transaction_key: key,
    merchant_name: merchant,
    merchant_label: merchant,
    transaction_type: type,
    transaction_city: city,
    place: city,
    amount,
    currency,
    transaction_status: "Approved",
    status_label: statusLabel,
    local_time: local,
  }));
}

async function testClient() {
  const document = makeDocument("client");
  header(document, "Harbor Desk", catalog.es.client_lede);
  const personasBox = document.createElement("section");
  personasBox.id = "personas";
  const chargesBox = document.createElement("section");
  chargesBox.id = "charges";
  const form = document.createElement("form");
  form.id = "composer";
  const message = document.createElement("input");
  message.id = "message";
  const send = document.createElement("button");
  send.id = "send";
  form.append(message, send);
  const thread = document.createElement("section");
  thread.id = "thread";
  document.body.append(personasBox, chargesBox, form, thread);
  const fetchImpl = async (url, options = {}) => {
    const href = String(url);
    if (href.includes("/api/i18n")) return jsonResponse(200, catalog);
    if (href.includes("/api/personas")) return jsonResponse(200, { personas });
    if (href.includes("/api/session")) return jsonResponse(200, { token: "t" });
    if (href.includes("/api/transactions")) {
      const lang = href.includes("language=pt") ? "pt" : "es";
      return jsonResponse(200, { transactions: charges(lang) });
    }
    if (href.includes("/cases") && options.method === "POST") {
      return jsonResponse(200, {
        case_id: "case-1",
        reply: "El cargo sigue explicado en español.",
        actions: [],
        band: "low",
      });
    }
    if (href.includes("/trail")) {
      return jsonResponse(200, { steps: [{ at: "15 ene 2026", band: "low", reason: "Explicación del comercio" }] });
    }
    return jsonResponse(404, {});
  };
  run("static/js/desk.js", document, fetchImpl);
  run("static/js/tour.js", document, fetchImpl);
  await flush();
  const maria = document.querySelectorAll("#personas button").find((button) => button.textContent.includes("María"));
  assert.ok(maria, "persona chip missing");
  await maria.listeners.click[0]();
  await flush();
  const dispute = document.querySelector('#charges [data-action="select-charge"]');
  assert.ok(dispute, "charge button missing");
  await dispute.listeners.click[0]();
  await flush();
  const reply = document.querySelector(".reply").textContent;
  let text = blob(document);
  assert.ok(text.includes(catalog.es.dispute), text);
  assert.ok(text.includes(" may "), text);
  assert.ok(text.includes(" ene "), text);
  assert.ok(text.includes(catalog.es.status.Approved), text);
  assertAbsent(text, ["Synthetic persona", "Challenge data customer", "Approved", "Pending", "Reversed", " mai ", " jan "], "client es");
  assertNoEnglish(text, "client es", ["Console"]);
  assert.ok(text.includes(catalog.es.status.Declined), text);
  assert.ok(text.includes(catalog.es.types.Payment), text);
  assert.ok(text.includes("1.645,60"), text);
  assert.equal(text.includes("· ·"), false, text);
  const tourButton = document.getElementById("tour");
  tourButton.listeners.click.forEach((fn) => fn());
  const tip = document.querySelector(".tour-tip");
  assert.equal(tip.hidden, false);
  assert.ok(tip.textContent.includes("Esta pantalla es la del cliente"), tip.textContent);
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  assert.equal(tip.hidden, false);
  assert.ok(tip.textContent.includes("Esta é a tela do cliente"), tip.textContent);
  assert.equal(tip.textContent.includes("Esta pantalla es la del cliente"), false);
  tourButton.listeners.click.forEach((fn) => fn());
  assert.equal(document.querySelector(".tour-shade").hidden, true);
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();

  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.equal(document.querySelector(".reply").textContent, reply);
  assert.ok(text.includes(catalog.pt.dispute), text);
  assert.ok(text.includes(catalog.pt.client_lede), text);
  assert.ok(text.includes(" mai "), text);
  assert.ok(text.includes(" jan "), text);
  assert.ok(text.includes("Pessoa sintética"), text);
  assert.ok(text.includes("Cidade do México"), text);
  assertAbsent(text, esOnly, "client pt");

  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.equal(document.querySelector(".reply").textContent, reply);
  assert.ok(text.includes(catalog.es.client_lede), text);
  assert.ok(text.includes(" may "), text);
  assertAbsent(text, ptOnly, "client es again");
}

async function testAgent() {
  const document = makeDocument("agent");
  header(document, catalog.es.agent_title, catalog.es.agent_lede);
  const token = document.createElement("input");
  token.id = "token";
  token.placeholder = catalog.es.token_placeholder;
  const load = document.createElement("button");
  load.id = "load";
  load.textContent = catalog.es.load_queue;
  const queue = document.createElement("section");
  queue.id = "queue";
  document.body.append(token, load, queue);
  let mode = "empty";
  const fetchImpl = async (url) => {
    const href = String(url);
    if (href.includes("/api/i18n")) return jsonResponse(200, catalog);
    if (href.includes("/api/auth/config")) return jsonResponse(200, { demo_token: "demo-agent-local" });
    if (href.includes("/api/handoff")) {
      const lang = href.includes("language=pt") ? "pt" : "es";
      if (mode === "down") return jsonResponse(500, {});
      if (mode === "card") {
        return jsonResponse(200, {
          queue: [
            {
              case_id: "case-1",
              band: "low",
              amount: "10.00 MXN",
              merchant: "U•••",
              local_time: lang === "pt" ? "19 mai 2026, 12:00 CST" : "19 may 2026, 12:00 CST",
              reason_label: lang === "pt" ? "Cliente pediu uma pessoa (risco baixo)" : "Cliente pidió una persona (riesgo bajo)",
            },
          ],
        });
      }
      return jsonResponse(200, { queue: [] });
    }
    return jsonResponse(404, {});
  };
  run("static/js/agent.js", document, fetchImpl);
  run("static/js/tour.js", document, fetchImpl);
  await flush();
  document.getElementById("load").listeners.click[0]();
  await flush();
  let text = blob(document);
  assert.ok(text.includes(catalog.es.queue_empty), text);
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.pt.queue_empty), text);
  assert.ok(text.includes(catalog.pt.load_queue), text);
  assert.ok(text.includes("Console"), text);
  assertAbsent(text, [catalog.es.queue_empty, catalog.es.load_queue, catalog.es.agent_lede, " may "], "agent empty pt");
  assertNoEnglish(text, "agent empty pt", ["Consola", "Ver cola", "Abrir paquete"]);
  document.getElementById("tour").listeners.click.forEach((fn) => fn());
  const next = document.querySelector(".tour-tip").querySelectorAll("button")[1];
  for (let step = 0; step < 6; step += 1) next.listeners.click.forEach((fn) => fn());
  let tourText = document.querySelector(".tour-tip").textContent;
  assert.ok(tourText.includes("Ver fila"), tourText);
  assert.equal(tourText.includes("Ver cola"), false, tourText);
  for (let step = 0; step < 2; step += 1) next.listeners.click.forEach((fn) => fn());
  tourText = document.querySelector(".tour-tip").textContent;
  assert.ok(tourText.includes("Abrir pacote"), tourText);
  assert.equal(tourText.includes("Abrir paquete"), false, tourText);
  document.getElementById("tour").listeners.click.forEach((fn) => fn());
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.es.queue_empty), text);
  assertAbsent(text, [catalog.pt.queue_empty, catalog.pt.agent_lede], "agent empty es");

  mode = "down";
  document.getElementById("load").listeners.click[0]();
  await flush();
  assert.ok(blob(document).includes(catalog.es.queue_failed));
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.pt.queue_failed), text);
  assertAbsent(text, [catalog.es.queue_failed], "agent error pt");
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();

  mode = "card";
  document.getElementById("load").listeners.click[0]();
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.es.open_packet), text);
  assert.ok(text.includes(" may "), text);
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.pt.open_packet), text);
  assert.ok(text.includes(" mai "), text);
  assertAbsent(text, [catalog.es.open_packet, " may "], "agent card pt");
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.es.open_packet), text);
  assert.ok(text.includes(" may "), text);
  assertAbsent(text, [catalog.pt.open_packet, " mai "], "agent card es");
}

async function testMetrics() {
  const document = makeDocument("metrics");
  header(document, catalog.es.metrics_title, catalog.es.metrics_lede);
  const toggle = document.createElement("input");
  toggle.id = "include-eval";
  toggle.checked = false;
  const evalLabel = document.createElement("span");
  evalLabel.id = "eval-label";
  evalLabel.textContent = catalog.es.eval_toggle;
  const tiles = document.createElement("div");
  tiles.id = "tiles";
  const raw = document.createElement("pre");
  raw.id = "raw";
  document.body.append(toggle, evalLabel, tiles, raw);
  let metricsCalls = 0;
  let releaseMetrics = () => {};
  const fetchImpl = async (url) => {
    const href = String(url);
    const lang = href.includes("language=pt") ? "pt" : "es";
    if (href.includes("/api/i18n")) return jsonResponse(200, catalog);
    if (href.includes("/api/metrics")) {
      metricsCalls += 1;
      if (metricsCalls === 2) {
        await new Promise((resolve) => {
          releaseMetrics = resolve;
        });
      }
      return jsonResponse(200, {
        eval_toggle_label: catalog[lang].eval_toggle,
        excluded_eval_cases: 0,
        k1_volume: { total: 1 },
        k5_handoff: { display: "0 / 1" },
        k6_containment: { display: "1 / 1" },
      });
    }
    return jsonResponse(404, {});
  };
  run("static/js/metrics.js", document, fetchImpl);
  run("static/js/tour.js", document, fetchImpl);
  await flush();
  let text = blob(document);
  assert.ok(text.includes(catalog.es.tile_containment), text);
  assert.ok(text.includes(catalog.es.eval_toggle), text);
  assertAbsent(text, ["Demo sample", catalog.pt.tile_containment, catalog.pt.metrics_lede], "metrics es");
  assertNoEnglish(text, "metrics es", ["Console"]);
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  assert.ok(
    document.querySelector('[data-metrics-loading="1"]'),
    "metrics should show a loading tile",
  );
  assert.ok(blob(document).includes(catalog.pt.metrics_loading));
  releaseMetrics();
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.pt.metrics_lede), text);
  assert.ok(text.includes(catalog.pt.tile_containment), text);
  assert.ok(text.includes(catalog.pt.tile_eval), text);
  assert.ok(text.includes(catalog.pt.eval_toggle), text);
  assert.ok(text.includes("Como funciona?"), text);
  assertAbsent(text, esOnly, "metrics pt");
  assertNoEnglish(text, "metrics pt", ["Consola"]);
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.es.metrics_lede), text);
  assert.ok(text.includes("¿Cómo funciona?"), text);
  assertAbsent(text, ptOnly, "metrics es again");
}

function refuseI18n(url, extras) {
  const href = String(url);
  if (href.includes("/api/i18n")) throw new Error("pages must not fetch /api/i18n");
  return extras(href);
}

async function testBundledPortuguese() {
  memoryStore.set("hd_lang", "pt");
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(String(url));
    return refuseI18n(String(url), (href) => {
      if (href.includes("/api/personas")) return jsonResponse(200, { personas });
      if (href.includes("/api/test-mode")) return jsonResponse(200, { is_test: false });
      if (href.includes("/api/auth/config")) return jsonResponse(200, {});
      if (href.includes("/api/metrics")) {
        return jsonResponse(200, {
          eval_toggle_label: catalog.pt.eval_toggle,
          excluded_eval_cases: 0,
          excluded_test_cases: 0,
          k1_volume: { total: 2 },
          k5_handoff: { display: "0 / 2" },
          k6_containment: { display: "2 / 2" },
        });
      }
      return jsonResponse(404, {});
    });
  };

  const client = makeDocument("client");
  client.documentElement.classList.add("i18n-pending");
  header(client, "Harbor Desk", catalog.es.client_lede);
  const message = client.createElement("input");
  message.id = "message";
  message.placeholder = "Mensaje";
  const send = client.createElement("button");
  send.id = "send";
  send.textContent = "Enviar";
  const composer = client.createElement("form");
  composer.id = "composer";
  composer.append(message, send);
  const testLink = client.createElement("button");
  testLink.id = "test-mode-link";
  testLink.textContent = "Modo de prueba";
  const testLabel = client.createElement("label");
  testLabel.id = "test-token-label";
  testLabel.textContent = "Token de prueba";
  const testToken = client.createElement("input");
  testToken.id = "test-token";
  testToken.placeholder = "Token de prueba";
  const testSend = client.createElement("button");
  testSend.id = "test-mode-send";
  testSend.textContent = "Activar";
  const personasBox = client.createElement("section");
  personasBox.id = "personas";
  const chargesBox = client.createElement("section");
  chargesBox.id = "charges";
  client.body.append(personasBox, chargesBox, composer, testLink, testLabel, testToken, testSend);
  run("static/js/desk.js", client, fetchImpl);
  run("static/js/tour.js", client, fetchImpl);
  await flush();
  let text = blob(client);
  assert.equal(client.documentElement.lang, "pt");
  assert.equal(client.documentElement.className.includes("i18n-pending"), false);
  assert.ok(text.includes(catalog.pt.client_lede), text);
  assert.ok(text.includes(catalog.pt.tour_open), text);
  assert.ok(text.includes(catalog.pt.lang_name), text);
  assert.ok(text.includes("Console"), text);
  assert.ok(text.includes("Mensagem"), text);
  assert.ok(text.includes("Modo de teste"), text);
  assert.ok(text.includes("Token de teste"), text);
  assert.ok(text.includes("Colômbia"), text);
  assert.ok(text.includes("Pessoa sintética"), text);
  assertAbsent(
    text,
    [catalog.es.client_lede, "Consola", "¿Cómo funciona?", "Español", "Mensaje", "Modo de prueba", "Persona sintética"],
    "bundled client pt",
  );

  const agent = makeDocument("agent");
  agent.documentElement.classList.add("i18n-pending");
  header(agent, catalog.es.agent_title, catalog.es.agent_lede);
  const token = agent.createElement("input");
  token.id = "token";
  token.placeholder = catalog.es.token_placeholder;
  const load = agent.createElement("button");
  load.id = "load";
  load.textContent = catalog.es.load_queue;
  const queue = agent.createElement("section");
  queue.id = "queue";
  agent.body.append(token, load, queue);
  run("static/js/agent.js", agent, fetchImpl);
  run("static/js/tour.js", agent, fetchImpl);
  await flush();
  text = blob(agent);
  assert.equal(agent.documentElement.lang, "pt");
  assert.equal(agent.documentElement.className.includes("i18n-pending"), false);
  assert.ok(text.includes(catalog.pt.agent_title), text);
  assert.ok(text.includes(catalog.pt.agent_lede), text);
  assert.ok(text.includes(catalog.pt.token_placeholder), text);
  assert.ok(text.includes(catalog.pt.load_queue), text);
  assert.ok(text.includes(catalog.pt.tour_open), text);
  assertAbsent(
    text,
    [catalog.es.agent_title, catalog.es.agent_lede, catalog.es.token_placeholder, "Ver cola", "¿Cómo funciona?"],
    "bundled agent pt",
  );

  const metrics = makeDocument("metrics");
  metrics.documentElement.classList.add("i18n-pending");
  header(metrics, catalog.es.metrics_title, catalog.es.metrics_lede);
  const toggle = metrics.createElement("input");
  toggle.id = "include-eval";
  const evalLabel = metrics.createElement("span");
  evalLabel.id = "eval-label";
  evalLabel.textContent = catalog.es.eval_toggle;
  const tiles = metrics.createElement("div");
  tiles.id = "tiles";
  const raw = metrics.createElement("pre");
  raw.id = "raw";
  metrics.body.append(toggle, evalLabel, tiles, raw);
  run("static/js/metrics.js", metrics, fetchImpl);
  run("static/js/tour.js", metrics, fetchImpl);
  await flush();
  text = blob(metrics);
  assert.equal(metrics.documentElement.lang, "pt");
  assert.equal(metrics.documentElement.className.includes("i18n-pending"), false);
  assert.ok(text.includes(catalog.pt.metrics_lede), text);
  assert.ok(text.includes(catalog.pt.eval_toggle), text);
  assert.ok(text.includes(catalog.pt.tile_cases), text);
  assert.ok(text.includes(catalog.pt.tile_handoff), text);
  assert.ok(text.includes(catalog.pt.tile_eval), text);
  assert.ok(text.includes("Console"), text);
  assertAbsent(
    text,
    [catalog.es.metrics_lede, catalog.es.eval_toggle, catalog.es.tile_handoff, "¿Cómo funciona?", "Consola"],
    "bundled metrics pt",
  );
  assert.equal(calls.some((url) => url.includes("/api/i18n")), false, calls.join("\n"));
  memoryStore.set("hd_lang", "es");
}

async function testLanguagePersists() {
  memoryStore.set("hd_lang", "pt");
  const document = makeDocument("client");
  header(document, "Harbor Desk", catalog.es.client_lede);
  const composer = document.createElement("form");
  composer.id = "composer";
  document.body.append(composer);
  run("static/js/desk.js", document, async (url) => {
    if (String(url).includes("/api/i18n")) return jsonResponse(200, catalog);
    if (String(url).includes("/api/personas")) return jsonResponse(200, { personas: [] });
    if (String(url).includes("/api/test-mode")) return jsonResponse(200, { is_test: false });
    return jsonResponse(200, {});
  });
  await flush();
  assert.equal(document.documentElement.lang, "pt");
  assert.ok(blob(document).includes(catalog.pt.client_lede));
  assert.equal(localStorage.getItem("hd_lang"), "pt");
  memoryStore.set("hd_lang", "es");
}

testClient()
  .then(() => testAgent())
  .then(() => testMetrics())
  .then(() => testLanguagePersists())
  .then(() => testBundledPortuguese())
  .then(() => console.log("locale ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
