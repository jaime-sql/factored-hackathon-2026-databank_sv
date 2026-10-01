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

function run(filename, document, fetchImpl) {
  const context = {
    console,
    document,
    fetch: fetchImpl,
    setTimeout,
    clearTimeout,
    URL,
    URLSearchParams,
  };
  context.window = context;
  context.globalThis = context;
  context.addEventListener = () => {};
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

function charges(lang) {
  const status = catalog[lang].status;
  const month = lang === "pt" ? "mai" : "may";
  const jan = lang === "pt" ? "jan" : "ene";
  return [
    ["a", "Uber", status.Approved, `19 ${month} 2026, 12:00 CST`],
    ["b", "Farmacia", status.Pending, `15 ${jan} 2026, 12:00 CST`],
    ["c", "Tienda", status.Reversed, "25 abr 2026, 12:00 CST"],
  ].map(([key, merchant, statusLabel, local]) => ({
    transaction_key: key,
    merchant_name: merchant,
    merchant_label: merchant,
    transaction_city: "Ciudad",
    amount: 10,
    currency: "MXN",
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
  assertAbsent(text, [catalog.es.queue_empty, catalog.es.load_queue, catalog.es.agent_lede, " may "], "agent empty pt");
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
  const fetchImpl = async (url) => {
    const href = String(url);
    const lang = href.includes("language=pt") ? "pt" : "es";
    if (href.includes("/api/i18n")) return jsonResponse(200, catalog);
    if (href.includes("/api/metrics")) {
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
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.pt.metrics_lede), text);
  assert.ok(text.includes(catalog.pt.tile_containment), text);
  assert.ok(text.includes(catalog.pt.tile_eval), text);
  assert.ok(text.includes(catalog.pt.eval_toggle), text);
  assert.ok(text.includes("Como funciona?"), text);
  assertAbsent(text, esOnly, "metrics pt");
  document.getElementById("lang").listeners.click.forEach((fn) => fn());
  await flush();
  text = blob(document);
  assert.ok(text.includes(catalog.es.metrics_lede), text);
  assert.ok(text.includes("¿Cómo funciona?"), text);
  assertAbsent(text, ptOnly, "metrics es again");
}

testClient()
  .then(() => testAgent())
  .then(() => testMetrics())
  .then(() => console.log("locale ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
