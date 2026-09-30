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
console.log("agent console js ok");
