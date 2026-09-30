const tokenInput = typeof document === "undefined" ? null : document.getElementById("token");

const queueCopy = {
  es: {
    lang: "Español",
    empty: "No hay casos en la cola. Abre un caso desde la vista Cliente.",
    invalid: "Token inválido",
    failed: "No se pudo leer la cola.",
    loading: "Cargando la cola…",
  },
  pt: {
    lang: "Português",
    empty: "Não há casos na fila. Abra um caso na vista Cliente.",
    invalid: "Token inválido",
    failed: "Não foi possível ler a fila.",
    loading: "Carregando a fila…",
  },
};

const consoleState = { language: "es" };

function queueNotice(status, body, language) {
  const copy = queueCopy[language === "pt" ? "pt" : "es"];
  if (status === 401 || status === 403) return { kind: "error", text: copy.invalid };
  if (!status || status >= 400) return { kind: "error", text: copy.failed };
  const queue = body && body.queue;
  if (!Array.isArray(queue)) return { kind: "error", text: copy.failed };
  if (queue.length === 0) return { kind: "empty", text: copy.empty };
  return { kind: "cards", text: "" };
}

function showQueueStatus(box, kind, text) {
  box.replaceChildren();
  const note = document.createElement("p");
  note.className = `queue-status ${kind}`;
  note.textContent = text;
  box.appendChild(note);
}

function renderPacket(panel, view, trail) {
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
  if (view.band_evidence) lines.push(view.band_evidence);
  for (const step of (trail && trail.steps) || []) {
    if (step.kind === "action") {
      const action = `${step.action || ""} ${step.verification || ""}`.trim();
      lines.push([step.at, action].filter(Boolean).join(" · "));
    } else {
      lines.push(
        [
          step.at,
          step.rule_or_model,
          step.band,
          step.threshold,
          (step.guardrail_flags || []).join(","),
          step.handoff,
          step.reason_label,
        ]
          .filter(Boolean)
          .join(" · "),
      );
    }
  }
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

function agentToken() {
  const input = typeof document === "undefined" ? null : document.getElementById("token");
  return input ? input.value : "";
}

async function loadQueue() {
  const box = document.getElementById("queue");
  const copy = queueCopy[consoleState.language === "pt" ? "pt" : "es"];
  showQueueStatus(box, "loading", copy.loading);
  box.setAttribute("aria-busy", "true");
  let status = 0;
  let body = null;
  try {
    const response = await fetch("/api/handoff", {
      headers: { authorization: `Bearer ${agentToken()}` },
    });
    status = response.status;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
  } catch {
    status = 0;
    body = null;
  }
  box.removeAttribute("aria-busy");
  const notice = queueNotice(status, body, consoleState.language);
  if (notice.kind !== "cards") {
    showQueueStatus(box, notice.kind, notice.text);
    return;
  }
  box.replaceChildren();
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
  const headers = { authorization: `Bearer ${tokenInput.value}` };
  const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}`, { headers });
  if (!response.ok) {
    panel.textContent = "No se pudo abrir el paquete";
    return;
  }
  const body = await response.json();
  let trail = { steps: [] };
  const trailResponse = await fetch(`/api/cases/${encodeURIComponent(caseId)}/trail`, { headers });
  if (trailResponse.ok) trail = await trailResponse.json();
  renderPacket(panel, body.view || {}, trail);
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

function applyConsoleLanguage() {
  const copy = queueCopy[consoleState.language === "pt" ? "pt" : "es"];
  document.documentElement.lang = consoleState.language === "pt" ? "pt" : "es";
  const button = document.getElementById("lang");
  if (button) button.textContent = copy.lang;
}

if (typeof document !== "undefined" && document.getElementById("load")) {
  const langButton = document.getElementById("lang");
  if (langButton) {
    langButton.addEventListener("click", () => {
      consoleState.language = consoleState.language === "es" ? "pt" : "es";
      applyConsoleLanguage();
    });
    applyConsoleLanguage();
  }
  document.getElementById("load").addEventListener("click", loadQueue);
  boot();
}

globalThis.renderPacket = renderPacket;
globalThis.fillCard = fillCard;
globalThis.queueNotice = queueNotice;
globalThis.loadQueue = loadQueue;
globalThis.consoleState = consoleState;
