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
for (const part of [
  "high",
  "rule_fs_gt30_v1",
  "fraud_score > 30",
  "220.00 MXN",
  "U•••",
  "15 ene 2026, 12:00 CST",
  "America/Mexico_City",
  "block_card verified",
  "Riesgo alto: tarjeta bloqueada",
  "Revisar la tarjeta bloqueada.",
]) {
  assert.ok(panel.textContent.includes(part), part);
}
assert.equal(panel.textContent.includes("fraud rate"), false);

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
assert.ok(withTrail.textContent.includes("handoff verified"));

assert.match(source, /\/api\/cases\/\$\{encodeURIComponent\(caseId\)\}\/trail/);
const desk = fs.readFileSync("static/js/desk.js", "utf8");
assert.match(desk, /¿Por qué\?/);
assert.match(desk, /Por quê\?/);
assert.match(desk, /Protegido/);
assert.match(desk, /className = "protected"/);
assert.match(desk, /\/api\/cases\/\$\{encodeURIComponent\(caseId\)\}\/trail/);
assert.equal(desk.includes("onclick="), false);
console.log("agent console js ok");
