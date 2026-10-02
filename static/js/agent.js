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

function storedLanguage() {
  try {
    return localStorage.getItem("hd_lang") === "pt" ? "pt" : "es";
  } catch {
    return "es";
  }
}

function persistLanguage(language) {
  try {
    localStorage.setItem("hd_lang", language === "pt" ? "pt" : "es");
  } catch {
    /* ignore */
  }
}

function notifyLanguage() {
  if (typeof document === "undefined") return;
  if (typeof document.dispatchEvent !== "function" || typeof Event !== "function") return;
  document.dispatchEvent(new Event("hd-lang"));
}

function revealCopy() {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (!root || !root.classList || typeof root.classList.remove !== "function") return;
  root.classList.remove("i18n-pending");
}

const consoleState = { language: storedLanguage() };
if (typeof document !== "undefined" && document.documentElement) {
  document.documentElement.lang = consoleState.language === "pt" ? "pt" : "es";
}
let catalog = null;
let queueSeen = false;

function textPack() {
  return catalog && catalog[consoleState.language === "pt" ? "pt" : "es"];
}

function ui(key, fallback) {
  const pack = textPack();
  return (pack && pack[key]) || fallback;
}

const PACKET_LABELS = {
  es: {
    bands: { high: "Alto", low: "Bajo", review: "Revisión", out_of_scope: "Fuera de alcance" },
    actions: {
      "block_card verified": "Bloqueo de tarjeta verificado",
      "block_card failed": "Bloqueo de tarjeta fallido",
      "handoff verified": "Traspaso verificado",
      "handoff failed": "Traspaso fallido",
      "decline_block not_applicable": "Bloqueo no aplicado",
      "contest not_applicable": "Impugnación registrada",
      "open_dispute not_applicable": "Disputa abierta",
    },
    decisions: { handoff: "Traspaso" },
  },
  pt: {
    bands: { high: "Alto", low: "Baixo", review: "Revisão", out_of_scope: "Fora de escopo" },
    actions: {
      "block_card verified": "Bloqueio de cartão verificado",
      "block_card failed": "Bloqueio de cartão falhou",
      "handoff verified": "Repasse verificado",
      "handoff failed": "Repasse falhou",
      "decline_block not_applicable": "Bloqueio não aplicado",
      "contest not_applicable": "Contestação registrada",
      "open_dispute not_applicable": "Disputa aberta",
    },
    decisions: { handoff: "Repasse" },
  },
};

function packetLanguage() {
  return consoleState.language === "pt" ? "pt" : "es";
}

function localizedToken(group, key) {
  const cleaned = String(key || "").trim();
  if (!cleaned) return "";
  const lang = packetLanguage();
  const pack = textPack();
  const fromCatalog = pack && pack[group] && pack[group][cleaned];
  if (fromCatalog) return fromCatalog;
  const fallback = PACKET_LABELS[lang][group][cleaned];
  return fallback || cleaned;
}

function bandLabel(band) {
  return localizedToken("bands", band);
}

function actionLabel(name, status) {
  return localizedToken("actions", `${name || ""} ${status || ""}`.trim());
}

function decisionLabel(decision) {
  return localizedToken("decisions", decision);
}

const FIELD_LABELS = {
  es: {
    field_band: "Banda",
    field_score: "Puntaje vs umbral",
    field_amount: "Monto",
    field_merchant: "Comercio enmascarado",
    field_time: "Hora local",
    field_step: "Siguiente paso",
  },
  pt: {
    field_band: "Faixa",
    field_score: "Pontuação vs limiar",
    field_amount: "Valor",
    field_merchant: "Comércio mascarado",
    field_time: "Horário local",
    field_step: "Próximo passo",
  },
};

function fieldLabel(key) {
  const pack = textPack();
  if (pack && pack[key]) return pack[key];
  return FIELD_LABELS[packetLanguage()][key] || key;
}

function scoreTooltip(view) {
  if (
    (view.band === "low" || view.band === "review") &&
    view.model_risk_score != null &&
    view.t_low != null
  ) {
    return `${view.model_risk_score} · t_low ${view.t_low}`;
  }
  if (view.band === "high" && view.fraud_score != null && view.high_value != null) {
    return `${view.fraud_score} · ${view.high_value}`;
  }
  return "";
}

function cardTitle(item) {
  const short = String(item.case_id || "").slice(0, 8);
  return [item.merchant || "", item.amount || "", short].join(" · ");
}

function adoptCatalog(payload) {
  catalog = payload;
  if (!payload) return;
  for (const lang of ["es", "pt"]) {
    const text = payload[lang];
    if (!text) continue;
    queueCopy[lang].lang = text.lang_name;
    queueCopy[lang].empty = text.queue_empty;
    queueCopy[lang].invalid = text.queue_invalid;
    queueCopy[lang].failed = text.queue_failed;
    queueCopy[lang].loading = text.queue_loading;
  }
}

function applyNav(copy) {
  const links = { "/": copy.nav_client, "/agent": copy.nav_agent, "/metrics": copy.nav_metrics };
  for (const anchor of document.querySelectorAll("a")) {
    const href = anchor.getAttribute("href");
    if (links[href]) anchor.textContent = links[href];
  }
}

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

function scoreFieldValue(line) {
  return String(line || "").replace(/^(?:Puntaje|Pontuação):\s*/, "");
}

function packetLines(view, trail) {
  const actions = (view.actions_taken || [])
    .map((action) => actionLabel(action.name, action.verification_status))
    .filter(Boolean)
    .join(", ");
  const lines = [];
  if (view.is_test) lines.push({ text: ui("test_chip", "Prueba") });
  lines.push({ text: `${fieldLabel("field_band")}: ${bandLabel(view.band)}` });
  if (view.model_version) lines.push({ text: view.model_version });
  const scoreText = scoreFieldValue(view.score_line);
  lines.push({
    text: `${fieldLabel("field_score")}: ${scoreText}`,
    score: true,
    value: scoreText,
  });
  lines.push({ text: `${fieldLabel("field_amount")}: ${view.amount || ""}` });
  lines.push({ text: `${fieldLabel("field_merchant")}: ${view.merchant || ""}` });
  lines.push({ text: `${fieldLabel("field_time")}: ${view.local_time || ""}` });
  if (view.utc) lines.push({ text: view.utc });
  if (view.customer_tz) lines.push({ text: view.customer_tz });
  lines.push({ text: actions || ui("no_actions", "ninguna") });
  if (view.reason_label) lines.push({ text: view.reason_label });
  lines.push({ text: `${fieldLabel("field_step")}: ${view.recommended_next_step || ""}` });
  if (view.band_evidence) lines.push({ text: view.band_evidence });
  for (const step of (trail && trail.steps) || []) {
    if (step.kind === "action") {
      const action = actionLabel(step.action, step.verification);
      lines.push({ text: [step.at, action].filter(Boolean).join(" · ") });
    } else {
      lines.push({
        text: [
          step.at,
          step.rule_or_model,
          bandLabel(step.band),
          step.threshold,
          (step.guardrail_flags || []).join(","),
          decisionLabel(step.handoff),
          step.reason_label,
        ]
          .filter(Boolean)
          .join(" · "),
      });
    }
  }
  return lines;
}

function renderPacket(panel, view, trail) {
  const lines = packetLines(view, trail);
  panel.hidden = false;
  const canDom =
    typeof document !== "undefined" &&
    typeof document.createElement === "function" &&
    typeof panel.replaceChildren === "function";
  if (!canDom) {
    panel.textContent = lines.map((line) => line.text).join("\n");
    appendDraft(panel, view);
    return;
  }
  const nodes = lines.map((line) => {
    const row = document.createElement("span");
    row.className = "packet-line";
    if (!line.score) {
      row.textContent = line.text;
      return row;
    }
    const name = document.createElement("span");
    name.textContent = `${fieldLabel("field_score")}: `;
    const value = document.createElement("span");
    value.className = "score-line";
    value.dataset.band = view.band || "";
    value.textContent = line.value;
    const tip = scoreTooltip(view);
    if (tip) value.title = tip;
    row.append(name, value);
    return row;
  });
  panel.replaceChildren(...nodes);
  appendDraft(panel, view);
}

function appendDraft(panel, view) {
  if (!view.reply_draft || typeof document === "undefined" || !panel.appendChild) return;
  const form = document.createElement("form");
  form.className = "draft";
  const label = document.createElement("p");
  label.className = "meta";
  label.textContent = ui("draft_label", "Borrador IA");
  const badge = document.createElement("span");
  badge.className = "grounded";
  badge.dataset.grounded = view.reply_grounded ? "1" : "0";
  badge.textContent = view.reply_grounded
    ? ui("grounded_ok", "Fundamentado")
    : ui("grounded_bad", "Sin fundamento");
  label.append(" ");
  label.appendChild(badge);
  const area = document.createElement("textarea");
  area.value = view.reply_sent || view.reply_draft;
  const send = document.createElement("button");
  send.type = "submit";
  send.textContent = ui("send_reply", "Enviar respuesta");
  const note = document.createElement("p");
  note.className = "meta";
  if (view.reply_sent) note.textContent = ui("reply_sent_label", "Respuesta registrada");
  const caseId = panel.dataset.caseId || "";
  area.addEventListener("input", async () => {
    if (!caseId) return;
    const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}/draft-check`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${tokenInput.value}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ text: area.value }),
    });
    if (!response.ok) return;
    const checked = await response.json();
    badge.dataset.grounded = checked.ok ? "1" : "0";
    badge.textContent = checked.ok
      ? ui("grounded_ok", "Fundamentado")
      : ui("grounded_bad", "Sin fundamento");
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!caseId) return;
    const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}/reply`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${tokenInput.value}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ text: area.value }),
    });
    if (!response.ok) return;
    note.textContent = ui("reply_sent_label", "Respuesta registrada");
    const checked = await response.json();
    badge.dataset.grounded = checked.ok ? "1" : "0";
    badge.textContent = checked.ok
      ? ui("grounded_ok", "Fundamentado")
      : ui("grounded_bad", "Sin fundamento");
  });
  form.append(label, area, send, note);
  panel.appendChild(form);
}

function showTestBadge(on) {
  const badge = document.getElementById("test-badge");
  if (!badge) return;
  const pack = textPack();
  badge.textContent = (pack && pack.test_badge) || "MODO PRUEBA";
  badge.hidden = !on;
}

async function boot() {
  const config = await fetch("/api/auth/config").then((res) => res.json());
  if (config.demo_token && tokenInput) tokenInput.value = config.demo_token;
  try {
    const status = await fetch("/api/test-mode").then((res) => res.json());
    showTestBadge(Boolean(status && status.is_test));
  } catch {
    showTestBadge(false);
  }
}

function fillCard(card, item) {
  card.className = "card";
  card.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = cardTitle(item);
  const meta = document.createElement("div");
  meta.className = "meta";
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.textContent = bandLabel(item.band);
  meta.append(chip, document.createTextNode(` ${item.amount || ""}`));
  if (item.is_test) {
    const testChip = document.createElement("span");
    testChip.className = "chip";
    testChip.setAttribute("data-chip", "test");
    testChip.textContent = ui("test_chip", "Prueba");
    meta.append(document.createTextNode(" "), testChip);
  }
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
  button.setAttribute("data-action", "packet");
  button.textContent = ui("open_packet", "Abrir paquete");
  button.addEventListener("click", () => togglePacket(panel, item.case_id));
  const resolve = document.createElement("button");
  resolve.type = "button";
  resolve.setAttribute("data-action", "resolve");
  resolve.textContent = ui("resolve", "Resolver");
  resolve.addEventListener("click", () => resolveCase(item.case_id, panel));
  card.append(title, meta, merchant, when, reason, button, resolve, panel);
}

function agentToken() {
  const input = typeof document === "undefined" ? null : document.getElementById("token");
  return input ? input.value : "";
}

async function loadQueue() {
  queueSeen = true;
  const box = document.getElementById("queue");
  const copy = queueCopy[consoleState.language === "pt" ? "pt" : "es"];
  showQueueStatus(box, "loading", copy.loading);
  box.setAttribute("aria-busy", "true");
  let status = 0;
  let body = null;
  try {
    const response = await fetch(`/api/handoff?language=${consoleState.language}`, {
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
  const response = await fetch(
    `/api/handoff/${encodeURIComponent(caseId)}?language=${consoleState.language}`,
    { headers },
  );
  if (!response.ok) {
    panel.textContent = ui("packet_error", "No se pudo abrir el paquete");
    return;
  }
  const body = await response.json();
  let trail = { steps: [] };
  const trailResponse = await fetch(
    `/api/cases/${encodeURIComponent(caseId)}/trail?language=${consoleState.language}`,
    { headers },
  );
  if (trailResponse.ok) trail = await trailResponse.json();
  panel.dataset.caseId = caseId;
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
  panel.textContent = response.ok
    ? ui("resolved", "Resuelto")
    : ui("resolve_error", "No se pudo resolver");
}

function applyConsoleLanguage() {
  const copy = queueCopy[consoleState.language === "pt" ? "pt" : "es"];
  document.documentElement.lang = consoleState.language === "pt" ? "pt" : "es";
  const button = document.getElementById("lang");
  if (button) button.textContent = copy.lang;
  const pack = textPack();
  if (!pack) return;
  const title = document.getElementById("page-title");
  if (title) title.textContent = pack.agent_title;
  const lede = document.getElementById("lede");
  if (lede) lede.textContent = pack.agent_lede;
  applyNav(pack);
  const tour = document.getElementById("tour");
  if (tour) tour.textContent = pack.tour_open;
  const token = document.getElementById("token");
  if (token) token.placeholder = pack.token_placeholder;
  const load = document.getElementById("load");
  if (load) load.textContent = pack.load_queue;
  for (const packet of document.querySelectorAll('[data-action="packet"]')) {
    packet.textContent = pack.open_packet;
  }
  for (const resolve of document.querySelectorAll('[data-action="resolve"]')) {
    resolve.textContent = pack.resolve;
  }
  for (const chip of document.querySelectorAll('[data-chip="test"]')) {
    chip.textContent = pack.test_chip || "Prueba";
  }
  const badge = document.getElementById("test-badge");
  if (badge) badge.textContent = pack.test_badge || "MODO PRUEBA";
  if (pack.nav_agent) document.title = `${pack.nav_agent} · Harbor Desk`;
  revealCopy();
  notifyLanguage();
}

if (typeof document !== "undefined" && document.getElementById("load")) {
  adoptCatalog(globalThis.HD_CATALOG || null);
  const langButton = document.getElementById("lang");
  if (langButton) {
    langButton.addEventListener("click", () => {
      consoleState.language = consoleState.language === "es" ? "pt" : "es";
      persistLanguage(consoleState.language);
      applyConsoleLanguage();
      if (queueSeen) loadQueue();
    });
  }
  applyConsoleLanguage();
  document.getElementById("load").addEventListener("click", loadQueue);
  boot();
}

globalThis.renderPacket = renderPacket;
globalThis.fillCard = fillCard;
globalThis.queueNotice = queueNotice;
globalThis.loadQueue = loadQueue;
globalThis.consoleState = consoleState;
