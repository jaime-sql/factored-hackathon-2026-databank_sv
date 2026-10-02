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
  fraud_score: 45,
  high_value: 30,
  threshold_crossed: "fraud_score > 30",
  score_line: "Puntaje de fraude 45 > 30 → bloqueo",
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
  "Banda: Alto",
  "rule_fs_gt30_v1",
  "Puntaje vs umbral: Puntaje de fraude 45 > 30 → bloqueo",
  "Monto: 220.00 MXN",
  "Comercio enmascarado: U•••",
  "Hora local: 15 ene 2026, 12:00 CST",
  "America/Mexico_City",
  "Bloqueo de tarjeta verificado",
  "Riesgo alto: tarjeta bloqueada",
  "Siguiente paso: Revisar la tarjeta bloqueada.",
]) {
  assert.ok(panel.textContent.includes(part), part);
}
assert.equal(panel.textContent.includes("fraud_score > 30"), false);
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
    score_line: "Puntaje: ≥1.00× umbral · encima → revisión",
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
    score_line: "Puntaje: 1.02× umbral · encima → revisión",
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
assert.ok(withTrail.textContent.includes("Puntaje: 1.02× umbral · encima → revisión"));
assert.ok(withTrail.textContent.includes("score >= 0.0002756"));
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
    score_line: "Pontuação: 0,85× limiar · abaixo → automático",
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
assert.ok(portuguese.textContent.includes("Faixa: Baixo"));
assert.ok(portuguese.textContent.includes("Pontuação vs limiar: Pontuação: 0,85× limiar · abaixo → automático"));
assert.ok(portuguese.textContent.includes("Valor: 10.00 MXN"));
assert.ok(portuguese.textContent.includes("Comércio mascarado: U•••"));
assert.ok(portuguese.textContent.includes("Horário local: 15 jan 2026, 12:00 CST"));
assert.ok(portuguese.textContent.includes("Próximo passo: Revisar"));
assert.equal(portuguese.textContent.includes("score < 0.0002756"), false);
assert.ok(portuguese.textContent.includes("Bloqueio de cartão verificado"));
assert.ok(portuguese.textContent.includes("Repasse verificado"));
assert.equal(portuguese.textContent.includes("block_card"), false);
assert.equal(portuguese.textContent.includes("handoff verified"), false);
context.consoleState.language = "es";

function fakeElement() {
  return {
    className: "",
    textContent: "",
    title: "",
    hidden: false,
    dataset: {},
    children: [],
    append(...items) {
      this.children.push(...items);
    },
    appendChild(node) {
      this.children.push(node);
    },
    replaceChildren(...items) {
      this.children = items;
    },
    addEventListener() {},
    setAttribute() {},
  };
}
context.document = { createElement: () => fakeElement() };

function findScore(node) {
  if (node.className === "score-line") return node;
  for (const child of node.children || []) {
    const found = findScore(child);
    if (found) return found;
  }
  return null;
}

const boundary = fakeElement();
context.renderPacket(boundary, {
  band: "review",
  model_risk_score: 1,
  t_low: 1,
  score_line: "Puntaje: ≥1.00× umbral · encima → revisión",
  amount: "10 MXN",
  merchant: "U•••",
  recommended_next_step: "Revisar",
});
const boundaryScore = findScore(boundary);
assert.equal(boundaryScore.dataset.band, "review");
assert.equal(boundaryScore.textContent, "Puntaje: ≥1.00× umbral · encima → revisión");
assert.equal(boundaryScore.title, "1 · t_low 1");

const belowRounded = fakeElement();
context.renderPacket(belowRounded, {
  band: "low",
  model_risk_score: 0.995,
  t_low: 1,
  score_line: "Puntaje: <1.00× umbral · debajo → automático",
  amount: "1",
  merchant: "M",
  recommended_next_step: "Listo",
});
const belowScore = findScore(belowRounded);
assert.equal(belowScore.dataset.band, "low");
assert.equal(belowScore.textContent, "Puntaje: <1.00× umbral · debajo → automático");
assert.equal(belowScore.title, "0.995 · t_low 1");

const highDom = fakeElement();
context.renderPacket(highDom, {
  band: "high",
  fraud_score: 45,
  high_value: 30,
  score_line: "Puntaje de fraude 45 > 30 → bloqueo",
  amount: "1",
  merchant: "M",
  recommended_next_step: "Bloquear",
});
const highScore = findScore(highDom);
assert.equal(highScore.dataset.band, "high");
assert.equal(highScore.title, "45 · 30");

const pendingDom = fakeElement();
context.renderPacket(pendingDom, {
  band: "out_of_scope",
  score_line: "Pendiente/Revertido → explicación por regla",
  amount: "1",
  merchant: "M",
  recommended_next_step: "Explicar",
});
const pendingScore = findScore(pendingDom);
assert.equal(pendingScore.dataset.band, "out_of_scope");
assert.equal(pendingScore.textContent, "Pendiente/Revertido → explicación por regla");
assert.equal(pendingScore.title, "");
delete context.document;

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
  assert.ok(texts.includes("M · 10 MXN · c1"));
  assert.equal(texts.includes("c1"), false);
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
  const full = "abcdef12-3456-7890-abcd-ef1234567890";
  const titled = node();
  context.fillCard(titled, {
    case_id: full,
    band: "low",
    amount: "20 MXN",
    is_test: false,
    merchant: "A•••",
    local_time: "t",
    reason_label: "r",
  });
  const titleTexts = [];
  function walkTitle(el) {
    if (el.textContent && !(el.children && el.children.length)) titleTexts.push(el.textContent);
    for (const child of el.children || []) walkTitle(child);
  }
  walkTitle(titled);
  assert.ok(titleTexts.includes("A••• · 20 MXN · abcdef12"));
  assert.equal(titleTexts.includes(full), false);
}

checkLoadQueue()
  .then(() => console.log("agent console js ok"))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
