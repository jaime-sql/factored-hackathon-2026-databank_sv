const tokenInput = typeof document === "undefined" ? null : document.getElementById("token");

function renderPacket(panel, view) {
  const actions = (view.actions_taken || [])
    .map((action) => `${action.name} ${action.verification_status}`)
    .join(", ");
  const lines = [
    view.band,
    view.model_version,
    view.model_risk_score == null ? "" : String(view.model_risk_score),
    view.threshold_crossed,
    view.amount,
    view.merchant,
    view.local_time,
    view.utc,
    view.customer_tz,
    actions || "ninguna",
    view.reason_label,
    view.recommended_next_step,
  ];
  panel.textContent = lines.join("\n");
  panel.hidden = false;
}

async function boot() {
  const config = await fetch("/api/auth/config").then((res) => res.json());
  if (config.demo_token && tokenInput) tokenInput.value = config.demo_token;
}

function fillCard(card, item) {
  card.className = "card";
  card.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = item.case_id || "";
  const meta = document.createElement("div");
  meta.className = "meta";
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.textContent = item.band || "";
  meta.append(chip, document.createTextNode(` ${item.amount || ""}`));
  const merchant = document.createElement("div");
  merchant.textContent = item.merchant || "";
  const when = document.createElement("div");
  when.className = "meta";
  when.textContent = item.local_time || "";
  const reason = document.createElement("p");
  reason.textContent = item.reason_label || "";
  const panel = document.createElement("pre");
  panel.className = "packet-panel";
  panel.hidden = true;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Abrir paquete";
  button.addEventListener("click", () => togglePacket(panel, item.case_id));
  const resolve = document.createElement("button");
  resolve.type = "button";
  resolve.textContent = "Resolver";
  resolve.addEventListener("click", () => resolveCase(item.case_id, panel));
  card.append(title, meta, merchant, when, reason, button, resolve, panel);
}

async function loadQueue() {
  const response = await fetch("/api/handoff", {
    headers: { authorization: `Bearer ${tokenInput.value}` },
  });
  const body = await response.json();
  const box = document.getElementById("queue");
  box.replaceChildren();
  if (!response.ok || !body.queue) {
    box.textContent = body.message || "No se pudo leer la cola";
    return;
  }
  for (const item of body.queue) {
    const card = document.createElement("article");
    fillCard(card, item);
    box.appendChild(card);
  }
}

async function togglePacket(panel, caseId) {
  if (!panel.hidden && panel.dataset.loaded === "1") {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}`, {
    headers: { authorization: `Bearer ${tokenInput.value}` },
  });
  if (!response.ok) {
    panel.textContent = "No se pudo abrir el paquete";
    return;
  }
  const body = await response.json();
  renderPacket(panel, body.view || {});
  panel.dataset.loaded = "1";
}

async function resolveCase(caseId, panel) {
  const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}/resolve`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${tokenInput.value}`,
      "content-type": "application/json",
    },
    body: "{}",
  });
  panel.hidden = false;
  panel.textContent = response.ok ? "Resuelto" : "No se pudo resolver";
}

if (typeof document !== "undefined" && document.getElementById("load")) {
  document.getElementById("load").addEventListener("click", loadQueue);
  boot();
}

globalThis.renderPacket = renderPacket;
globalThis.fillCard = fillCard;
