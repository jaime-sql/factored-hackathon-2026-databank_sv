const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/js/agent.js", "utf8");
assert.equal(source.includes("onclick="), false);
assert.match(source, /authorization: `Bearer \$\{tokenInput\.value\}`/);
assert.match(source, /\/api\/handoff\/\$\{encodeURIComponent\(caseId\)\}/);
assert.match(source, /addEventListener\("click"/);

const context = { console, globalThis: {} };
context.globalThis = context;
vm.runInNewContext(source, context);

const panel = { textContent: "", hidden: true, dataset: {} };
context.renderPacket(panel, {
  band: "high",
  model_version: "rule_fs_gt30_v1",
  model_risk_score: null,
  threshold_crossed: "fraud_score > 30",
  amount: "220.00 MXN",
  merchant: "U•••",
  local_time: "15 ene 2026, 12:00 CST",
  utc: "2026-01-15T18:00:00+00:00",
  customer_tz: "America/Mexico_City",
  actions_taken: [{ name: "block_card", verification_status: "verified" }],
  reason_label: "Riesgo alto: tarjeta bloqueada",
  recommended_next_step: "Revisar la tarjeta bloqueada.",
});
assert.equal(panel.hidden, false);
assert.equal(panel.textContent.split("\n").includes(""), false);
for (const part of [
  "Alto",
  "rule_fs_gt30_v1",
  "fraud_score > 30",
  "220.00 MXN",
  "U•••",
  "15 ene 2026, 12:00 CST",
  "America/Mexico_City",
  "Bloqueo de tarjeta verificado",
  "Riesgo alto: tarjeta bloqueada",
  "Revisar la tarjeta bloqueada.",
]) {
  assert.ok(panel.textContent.includes(part), part);
}
assert.equal(panel.textContent.includes("block_card"), false);
assert.equal(panel.textContent.includes("\nhigh\n") || panel.textContent.startsWith("high\n"), false);
assert.equal(panel.textContent.includes("fraud rate"), false);
assert.equal(panel.textContent.includes("Prueba"), false);

const testPacket = { textContent: "", hidden: true, dataset: {} };
context.renderPacket(
  testPacket,
  {
    band: "review",
    model_version: "lgbm:v",
    model_risk_score: null,
    threshold_crossed: "score >= 0.0002756",
    amount: "10.00 MXN",
    merchant: "U•••",
    local_time: "15 ene 2026, 12:00 CST",
    utc: "2026-01-15T18:00:00+00:00",
    customer_tz: "America/Mexico_City",
    actions_taken: [],
    reason_label: "Modelo: revisión",
    recommended_next_step: "Revisar",
    is_test: true,
  },
  { steps: [] },
);
assert.ok(testPacket.textContent.includes("Prueba"));

const withTrail = { textContent: "", hidden: true, dataset: {} };
context.renderPacket(
  withTrail,
  {
    band: "review",
    model_version: "lgbm:v",
    threshold_crossed: "score >= 0.0002756",
    amount: "1,400.00 MXN",
    merchant: "T•••••",
    reason_label: "Modelo: revisión",
    recommended_next_step: "Revisar",
    band_evidence:
      "band review, crossed threshold 0.0002756039, fraud rate in this band on val 1.2% (CI 0.8–1.7%)",
  },
  {
    steps: [
      {
        kind: "decision",
        at: "15 ene 2026, 12:00 CST",
        rule_or_model: "lgbm:v",
        band: "review",
        threshold: "score >= 0.0002756",
        guardrail_flags: [],
        handoff: "handoff",
        reason_label: "Modelo: revisión",
      },
      { kind: "action", at: "15 ene 2026, 12:01 CST", action: "handoff", verification: "verified" },
    ],
  },
);
assert.ok(withTrail.textContent.includes("fraud rate in this band on val 1.2%"));
assert.ok(withTrail.textContent.includes("lgbm:v"));
assert.ok(withTrail.textContent.includes("Traspaso verificado"));
assert.equal(withTrail.textContent.includes("handoff verified"), false);
assert.ok(withTrail.textContent.includes("Revisión"));
context.consoleState.language = "pt";
const portuguese = { textContent: "", hidden: true, dataset: {} };
context.renderPacket(
  portuguese,
  {
    band: "low",
    model_version: "lgbm:v",
    threshold_crossed: "score < 0.0002756",
    amount: "10.00 MXN",
    merchant: "U•••",
    local_time: "15 jan 2026, 12:00 CST",
    utc: "2026-01-15T18:00:00+00:00",
    customer_tz: "America/Mexico_City",
    actions_taken: [{ name: "block_card", verification_status: "verified" }],
    reason_label: "Cliente pediu uma pessoa",
    recommended_next_step: "Revisar",
  },
  {
    steps: [
      { kind: "action", at: "15 jan 2026, 12:01 CST", action: "handoff", verification: "verified" },
    ],
  },
);
assert.ok(portuguese.textContent.includes("Baixo"));
assert.ok(portuguese.textContent.includes("Bloqueio de cartão verificado"));
assert.ok(portuguese.textContent.includes("Repasse verificado"));
assert.equal(portuguese.textContent.includes("block_card"), false);
assert.equal(portuguese.textContent.includes("handoff verified"), false);
context.consoleState.language = "es";

assert.match(source, /\/api\/cases\/\$\{encodeURIComponent\(caseId\)\}\/trail/);
const desk = fs.readFileSync("static/js/desk.js", "utf8");
assert.match(desk, /¿Por qué\?/);
assert.match(desk, /copy\.why/);
const i18n = fs.readFileSync("app/i18n.py", "utf8");
assert.match(i18n, /Por quê\?/);
assert.match(desk, /Protegido/);
assert.match(desk, /className = "protected"/);
assert.match(desk, /\/api\/cases\/\$\{encodeURIComponent\(caseId\)\}\/trail/);
assert.equal(desk.includes("onclick="), false);

assert.equal(
  context.queueNotice(200, { queue: [] }, "es").text,
  "No hay casos en la cola. Abre un caso desde la vista Cliente.",
);
assert.equal(
  context.queueNotice(200, { queue: [] }, "pt").text,
  "Não há casos na fila. Abra um caso na vista Cliente.",
);
assert.equal(context.queueNotice(401, { message: "Agent sign-in required" }, "es").text, "Token inválido");
assert.equal(context.queueNotice(403, {}, "pt").text, "Token inválido");
assert.equal(context.queueNotice(500, null, "es").kind, "error");
assert.equal(context.queueNotice(0, null, "es").text, "No se pudo leer la cola.");
assert.equal(context.queueNotice(200, { queue: [{ case_id: "x" }] }, "es").kind, "cards");

async function checkLoadQueue() {
  const box = {
    kids: [],
    replaceChildren() {
      this.kids = [];
    },
    appendChild(node) {
      this.kids.push(node);
    },
    setAttribute(name, value) {
      this[name] = value;
    },
    removeAttribute(name) {
      delete this[name];
    },
  };
  context.document = {
    documentElement: { lang: "es" },
    getElementById(id) {
      if (id === "queue") return box;
      if (id === "token") return { value: "not-a-token" };
      return null;
    },
    createElement() {
      return { className: "", textContent: "" };
    },
  };
  let releaseFetch;
  context.fetch = () =>
    new Promise((resolve) => {
      releaseFetch = resolve;
    });
  const running = context.loadQueue();
  await Promise.resolve();
  assert.equal(box["aria-busy"], "true");
  assert.ok(box.kids.some((node) => node.className.includes("loading")));
  assert.ok(box.kids.some((node) => node.textContent === "Cargando la cola…"));
  releaseFetch({
    status: 200,
    json: async () => ({ queue: [] }),
  });
  await running;
  assert.equal(box["aria-busy"], undefined);
  assert.ok(box.kids.some((node) => node.textContent.includes("No hay casos en la cola")));

  context.consoleState.language = "pt";
  context.fetch = async () => ({ status: 401, json: async () => ({ message: "no" }) });
  await context.loadQueue();
  assert.ok(box.kids.some((node) => node.textContent === "Token inválido"));
  assert.ok(box.kids.some((node) => node.className.includes("error")));

  context.fetch = async () => {
    throw new Error("offline");
  };
  await context.loadQueue();
  assert.ok(box.kids.some((node) => node.textContent === "Não foi possível ler a fila."));
  context.consoleState.language = "es";

  function node() {
    return {
      className: "",
      textContent: "",
      hidden: false,
      dataset: {},
      children: [],
      append(...items) {
        this.children.push(...items);
      },
      addEventListener() {},
      setAttribute() {},
      replaceChildren() {
        this.children = [];
      },
    };
  }
  context.document = {
    createElement: () => node(),
    createTextNode: (value) => ({ textContent: String(value), children: [] }),
    getElementById: () => null,
    querySelectorAll: () => [],
  };
  const flagged = node();
  context.fillCard(flagged, {
    case_id: "c1",
    band: "review",
    amount: "10 MXN",
    is_test: true,
    merchant: "M",
    local_time: "t",
    reason_label: "r",
  });
  const texts = [];
  function walk(el) {
    if (el.textContent && !(el.children && el.children.length)) texts.push(el.textContent);
    for (const child of el.children || []) walk(child);
  }
  walk(flagged);
  assert.ok(texts.includes("Prueba"));
  const plain = node();
  context.fillCard(plain, {
    case_id: "c2",
    band: "low",
    amount: "1",
    is_test: false,
    merchant: "M",
    local_time: "t",
    reason_label: "r",
  });
  const plainTexts = [];
  function walkPlain(el) {
    if (el.textContent && !(el.children && el.children.length)) plainTexts.push(el.textContent);
    for (const child of el.children || []) walkPlain(child);
  }
  walkPlain(plain);
  assert.equal(plainTexts.includes("Prueba"), false);
}

checkLoadQueue()
  .then(() => console.log("agent console js ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
