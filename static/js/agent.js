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
    decisions: {
      handoff: "Traspaso",
      abandoned: "Abandonado",
      reply_draft: "Borrador",
      reply_sent: "Respuesta enviada",
    },
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
    decisions: {
      handoff: "Repasse",
      abandoned: "Abandonado",
      reply_draft: "Rascunho",
      reply_sent: "Resposta enviada",
    },
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

function guardrailBlocked(view) {
  if (view && view.guardrail) return true;
  return String((view && view.score_line) || "").includes("Bloqueado por guardrail");
}

function scoreTooltip(view) {
  const pt = packetLanguage() === "pt";
  if (
    (view.band === "low" || view.band === "review") &&
    view.model_risk_score != null &&
    view.t_low != null
  ) {
    const name = pt ? "limiar" : "umbral";
    return `${view.model_risk_score} · ${name} ${view.t_low}`;
  }
  if (view.band === "high" && view.fraud_score != null && view.high_value != null) {
    const name = pt ? "pontuação de fraude" : "puntaje de fraude";
    return `${name} ${view.fraud_score} > ${view.high_value}`;
  }
  if (view.band === "out_of_scope") {
    if (guardrailBlocked(view)) {
      return ui(
        "score_guardrail",
        pt ? "Bloqueado por guardrail · sem pontuação" : "Bloqueado por guardrail · sin puntaje",
      );
    }
    return pt ? "Pendente/Estornado" : "Pendiente/Reversado";
  }
  return "";
}

function displayThreshold(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const pt = packetLanguage() === "pt";
  if (text === "Pending/Reversed") return pt ? "Pendente/Estornado" : "Pendiente/Reversado";
  const fraud = /^fraud_score > (\S+)(.*)$/.exec(text);
  if (fraud) {
    const label = pt ? "pontuação de fraude" : "puntaje de fraude";
    return `${label} > ${fraud[1]}${fraud[2]}`;
  }
  const name = pt ? "limiar" : "umbral";
  const score = /^score (>=|<) (\S+)$/.exec(text);
  if (score) {
    const label = pt ? "pontuação" : "puntaje";
    const op = score[1] === ">=" ? "≥" : "<";
    return `${label} ${op} ${score[2].replaceAll("t_low", name)}`;
  }
  return text.replaceAll("t_low", name);
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

function flagLabel(flag) {
  const key = flag === "prompt_injection" ? "flag_injection" : flag === "pii_masked" ? "flag_pii" : "";
  if (!key) return "";
  const fallback = packetLanguage() === "pt"
    ? { flag_injection: "Injeção bloqueada", flag_pii: "Dados mascarados" }
    : { flag_injection: "Inyección bloqueada", flag_pii: "Datos enmascarados" };
  return ui(key, fallback[key]);
}

function packetRows(view) {
  const actions = (view.actions_taken || [])
    .map((action) => actionLabel(action.name, action.verification_status))
    .filter(Boolean)
    .join(", ");
  const rows = [];
  if (view.is_test) rows.push({ value: ui("test_chip", "Prueba") });
  rows.push({ label: fieldLabel("field_band"), value: bandLabel(view.band) });
  if (view.model_version) rows.push({ value: view.model_version });
  const scoreText = scoreFieldValue(view.score_line);
  rows.push({ label: fieldLabel("field_score"), value: scoreText, score: true });
  rows.push({ label: fieldLabel("field_amount"), value: view.amount || "" });
  rows.push({ label: fieldLabel("field_merchant"), value: view.merchant || "" });
  rows.push({ label: fieldLabel("field_time"), value: view.local_time || "" });
  if (view.utc) rows.push({ value: view.utc });
  if (view.customer_tz) rows.push({ value: view.customer_tz });
  rows.push({ value: actions || ui("no_actions", "ninguna") });
  if (view.reason_label) rows.push({ value: view.reason_label });
  rows.push({ label: fieldLabel("field_step"), value: view.recommended_next_step || "" });
  if (view.band_evidence) rows.push({ value: view.band_evidence });
  return rows;
}

function trailLine(step) {
  if (step.kind === "action") {
    return [step.at, actionLabel(step.action, step.verification)].filter(Boolean).join(" · ");
  }
  const flags = (step.guardrail_flags || []).map(flagLabel).filter(Boolean).join(" · ");
  return [
    step.at,
    step.rule_or_model,
    bandLabel(step.band),
    displayThreshold(step.threshold),
    flags,
    decisionLabel(step.handoff),
    step.reason_label,
  ]
    .filter(Boolean)
    .join(" · ");
}

function packetLines(view, trail) {
  const lines = packetRows(view).map((row) => ({
    text: row.label ? `${row.label}: ${row.value}` : String(row.value || ""),
    score: Boolean(row.score),
    value: row.value,
  }));
  for (const step of (trail && trail.steps) || []) {
    lines.push({ text: trailLine(step) });
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
  const list = document.createElement("dl");
  for (const row of packetRows(view)) {
    if (row.label) {
      const term = document.createElement("dt");
      term.textContent = row.label;
      list.appendChild(term);
    }
    const value = document.createElement("dd");
    if (!row.score) {
      value.textContent = row.value == null ? "" : String(row.value);
    } else {
      const score = document.createElement("span");
      score.className = "score-line";
      score.dataset.band = view.band || "";
      score.textContent = row.value;
      const tip = scoreTooltip(view);
      if (tip) score.title = tip;
      value.appendChild(score);
    }
    list.appendChild(value);
  }
  const steps = (trail && trail.steps) || [];
  const nodes = [list];
  if (steps.length) {
    const why = document.createElement("pre");
    why.className = "why-trail";
    for (const step of steps) {
      const line = document.createElement("span");
      line.className = "packet-line";
      line.textContent = trailLine({ ...step, guardrail_flags: [] });
      const flags = step.guardrail_flags || [];
      if (flags.length) {
        line.appendChild(document.createTextNode(" "));
        for (const flag of flags) {
          const label = flagLabel(flag);
          if (!label) continue;
          const chip = document.createElement("span");
          chip.className = "flag-chip";
          chip.textContent = label;
          line.appendChild(chip);
        }
      }
      why.appendChild(line);
    }
    nodes.push(why);
  }
  panel.replaceChildren(...nodes);
  appendDraft(panel, view);
}

function appendDraft(panel, view) {
  if (!view.reply_draft || typeof document === "undefined" || !panel.appendChild) return;
  const form = document.createElement("form");
  form.className = "draft";
  const caseId = panel.dataset.caseId || "";
  const areaId = `draft-${caseId || "new"}`;
  const label = document.createElement("label");
  label.className = "draft-label";
  label.setAttribute("for", areaId);
  label.textContent = ui("draft_label", "Borrador IA");
  const badge = document.createElement("span");
  badge.className = "grounded";
  badge.dataset.grounded = view.reply_grounded ? "1" : "0";
  badge.textContent = view.reply_grounded
    ? ui("grounded_ok", "Fundamentado")
    : ui("grounded_bad", "Sin fundamento");
  const area = document.createElement("textarea");
  area.id = areaId;
  area.value = view.reply_sent || view.reply_draft;
  const send = document.createElement("button");
  send.type = "submit";
  send.textContent = ui("send_reply", "Revisar y enviar (agente humano)");
  const facts = document.createElement("ul");
  facts.className = "unsupported";
  const note = document.createElement("p");
  note.className = "meta";
  function showFacts(items) {
    if (typeof facts.replaceChildren === "function") facts.replaceChildren();
    else facts.children = [];
    for (const item of items || []) {
      const row = document.createElement("li");
      row.textContent = String(item);
      facts.appendChild(row);
    }
  }
  function paintCheck(checked) {
    const ok = Boolean(checked && checked.ok);
    badge.dataset.grounded = ok ? "1" : "0";
    badge.textContent = ok ? ui("grounded_ok", "Fundamentado") : ui("grounded_bad", "Sin fundamento");
    showFacts(ok ? [] : (checked && checked.unsupported_facts) || []);
  }
  function lockComposer() {
    area.disabled = true;
    send.disabled = true;
  }
  if (view.reply_sent) {
    note.textContent = ui("reply_sent_label", "Respuesta registrada");
    lockComposer();
  }
  paintCheck({
    ok: Boolean(view.reply_grounded),
    unsupported_facts: view.reply_unsupported || [],
  });
  let draftTimer = 0;
  area.addEventListener("input", () => {
    if (!caseId || area.disabled) return;
    if (draftTimer && typeof clearTimeout === "function") clearTimeout(draftTimer);
    const run = async () => {
      const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}/draft-check`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${agentToken()}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ text: area.value }),
      });
      if (!response.ok) return;
      paintCheck(await response.json());
    };
    if (typeof setTimeout === "function") draftTimer = setTimeout(run, 400);
    else run();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!caseId || send.disabled) return;
    send.disabled = true;
    const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}/reply`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${agentToken()}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ text: area.value }),
    });
    if (response.status !== 409 && !response.ok) {
      send.disabled = false;
      return;
    }
    lockComposer();
    note.textContent = ui("reply_sent_label", "Respuesta registrada");
    if (response.ok) paintCheck(await response.json());
  });
  form.append(label, badge, facts, area, send, note);
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
  const panel = document.createElement("div");
  panel.className = "packet-panel";
  panel.hidden = true;
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("data-action", "packet");
  button.textContent = ui("open_packet", "Abrir paquete");
  button.addEventListener("click", () => togglePacket(panel, item.case_id, card));
  const resolve = document.createElement("button");
  resolve.type = "button";
  resolve.disabled = true;
  resolve.setAttribute("data-action", "resolve");
  resolve.textContent = ui("resolve", "Resolver");
  resolve.addEventListener("click", () => resolveCase(item.case_id, panel, card));
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

function enableResolve(card) {
  if (!card || typeof card.querySelector !== "function") return;
  const button = card.querySelector('[data-action="resolve"]');
  if (button) button.disabled = false;
}

async function togglePacket(panel, caseId, card) {
  if (!panel.hidden && panel.dataset.loaded === "1") {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const headers = { authorization: `Bearer ${agentToken()}` };
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
  enableResolve(card || panel.parentElement);
}

async function resolveCase(caseId, panel, card) {
  if (panel.dataset.loaded !== "1") return;
  const host = card || panel.parentElement || panel;
  if (panel.dataset.confirm !== "1") {
    panel.dataset.confirm = "1";
    const note = document.createElement("p");
    note.className = "resolve-confirm";
    note.textContent = ui(
      "resolve_confirm",
      "¿Resolver este caso? Vuelve a pulsar para confirmar.",
    );
    if (typeof host.insertBefore === "function") host.insertBefore(note, panel);
    else host.appendChild(note);
    return;
  }
  const response = await fetch(`/api/handoff/${encodeURIComponent(caseId)}/resolve`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${agentToken()}`,
      "content-type": "application/json",
    },
    body: "{}",
  });
  let result = typeof host.querySelector === "function" ? host.querySelector(".resolve-result") : null;
  if (!result) {
    result = document.createElement("p");
    result.className = "resolve-result";
    host.appendChild(result);
  }
  result.textContent = response.ok
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
  for (const send of document.querySelectorAll(".draft button")) {
    send.textContent = pack.send_reply;
  }
  for (const draftLabel of document.querySelectorAll(".draft-label")) {
    draftLabel.textContent = pack.draft_label;
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
