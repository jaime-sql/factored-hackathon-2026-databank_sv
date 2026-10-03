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
  if (typeof document.dispatchEvent !== "function" || typeof Event !== "function") return;
  document.dispatchEvent(new Event("hd-lang"));
}

function isMexico(country) {
  const key = String(country || "").trim().toLowerCase();
  return key === "mx" || key === "mexico" || key === "méxico";
}

function formatMoney(amount, currency, country) {
  const value = Number(amount);
  if (!Number.isFinite(value)) return "";
  const negative = value < 0;
  const [whole, frac] = Math.abs(value).toFixed(2).split(".");
  const groups = [];
  let digits = whole;
  while (digits) {
    groups.unshift(digits.slice(-3));
    digits = digits.slice(0, -3);
  }
  const mexico = isMexico(country);
  const number = `${groups.join(mexico ? "," : ".")}${mexico ? "." : ","}${frac}`;
  const code = String(currency || "").trim().toUpperCase();
  if (!code) return `${negative ? "-" : ""}${number}`;
  const label = code === "USD" ? "US$" : code;
  return `${negative ? "-" : ""}${label}${mexico ? "" : " "}${number}`;
}

function revealCopy() {
  const root = document.documentElement;
  if (!root || !root.classList || typeof root.classList.remove !== "function") return;
  root.classList.remove("i18n-pending");
}

const state = {
  language: storedLanguage(),
  token: "",
  caseId: null,
  catalog: globalThis.HD_CATALOG || null,
  personas: [],
  persona: "",
  testMode: false,
  testToken: "",
};
document.documentElement.lang = state.language;

function text() {
  return state.catalog && state.catalog[state.language === "pt" ? "pt" : "es"];
}

function applyNav(copy) {
  const links = { "/": copy.nav_client, "/agent": copy.nav_agent, "/metrics": copy.nav_metrics };
  for (const anchor of document.querySelectorAll("a")) {
    const href = anchor.getAttribute("href");
    if (links[href]) anchor.textContent = links[href];
  }
}

function applyLanguage() {
  document.documentElement.lang = state.language === "pt" ? "pt" : "es";
  const copy = text();
  if (!copy) return;
  const lang = document.getElementById("lang");
  if (lang) lang.textContent = copy.lang_name;
  const lede = document.getElementById("lede");
  if (lede) lede.textContent = copy.client_lede;
  const title = document.getElementById("page-title");
  if (title) title.textContent = copy.client_title;
  applyNav(copy);
  const tour = document.getElementById("tour");
  if (tour) tour.textContent = copy.tour_open;
  const message = document.getElementById("message");
  if (message) message.placeholder = copy.message_placeholder;
  const messageLabel = document.getElementById("message-label");
  if (messageLabel && copy.message_placeholder) messageLabel.textContent = copy.message_placeholder;
  const send = document.getElementById("send");
  if (send) send.textContent = copy.send;
  const why = document.querySelector("details.why summary");
  if (why) why.textContent = copy.why;
  const heading = document.querySelector("#charges h2");
  if (heading) heading.textContent = copy.charges_title;
  showTestBadge(state.testMode);
  const testLink = document.getElementById("test-mode-link");
  if (testLink && copy.test_arm) testLink.textContent = copy.test_arm;
  const testSend = document.getElementById("test-mode-send");
  if (testSend && copy.test_arm_send) testSend.textContent = copy.test_arm_send;
  const testToken = document.getElementById("test-token");
  if (testToken && copy.test_token) testToken.placeholder = copy.test_token;
  const testTokenLabel = document.getElementById("test-token-label");
  if (testTokenLabel && copy.test_token) testTokenLabel.textContent = copy.test_token;
  const breakIt = document.getElementById("break-it");
  if (breakIt && copy.break_it) breakIt.textContent = copy.break_it;
  for (const item of document.querySelectorAll("details.why li")) {
    if (!item.dataset) continue;
    item.textContent = [item.dataset.at, bandText(item.dataset.band), item.dataset.reason]
      .filter(Boolean)
      .join(" · ");
  }
  revealCopy();
  notifyLanguage();
  for (const button of document.querySelectorAll('#charges [data-action="select-charge"]')) {
    button.textContent = copy.dispute;
  }
  renderPersonas();
  renderDemos();
}

function renderPersonas() {
  const box = document.getElementById("personas");
  if (!box) return;
  box.replaceChildren();
  for (const persona of state.personas) {
    const button = document.createElement("button");
    button.setAttribute("data-action", "persona");
    button.setAttribute("data-persona", persona.id);
    button.setAttribute("aria-pressed", state.persona === persona.id ? "true" : "false");
    const notes = persona.notes || {};
    const note = notes[state.language] || persona.note || "";
    const labels = persona.labels || {};
    const label = labels[state.language] || persona.label || "";
    const suffix = note ? ` · ${note}` : "";
    button.textContent = `${label}${suffix}`;
    button.addEventListener("click", () => signIn(persona.id));
    box.appendChild(button);
  }
}

// Real charges from the challenge data that land in each outcome on every run.
const DEMOS = [
  { id: "high", persona: "teo", transaction: "TXN_c9d2185cbd2ab37f95d7" },
  { id: "review", persona: "teo", transaction: "TXN_eef1352d123d275d7602" },
  { id: "pending", persona: "maria", transaction: "TXN_ddcd20809f49f3b0a60c" },
];
const DEMO_FALLBACK = {
  es: {
    demo_title: "Demos rápidas",
    demo_high: "Teo · Tijuana · cargo de riesgo alto",
    demo_review: "Teo · Tijuana · cargo dudoso",
    demo_pending: "María · Ciudad de México · cargo pendiente",
    demo_chip_high: "Bloqueo · HIGH",
    demo_chip_review: "Revisión humana",
    demo_chip_pending: "Pendiente",
    dispute: "No reconozco este cargo",
  },
  pt: {
    demo_title: "Demos rápidas",
    demo_high: "Teo · Tijuana · cobrança de risco alto",
    demo_review: "Teo · Tijuana · cobrança duvidosa",
    demo_pending: "María · Cidade do México · cobrança pendente",
    demo_chip_high: "Bloqueio · HIGH",
    demo_chip_review: "Revisão humana",
    demo_chip_pending: "Pendente",
    dispute: "Não reconheço esta cobrança",
  },
};

function demoText(key) {
  const copy = text();
  if (copy && copy[key]) return copy[key];
  return DEMO_FALLBACK[state.language === "pt" ? "pt" : "es"][key] || "";
}

function renderDemos() {
  const box = document.getElementById("demos");
  if (!box) return;
  const title = document.getElementById("demos-title");
  if (title) title.textContent = demoText("demo_title");
  for (const old of Array.from(box.querySelectorAll ? box.querySelectorAll("button") : [])) old.remove();
  for (const demo of DEMOS) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("data-action", "demo");
    button.setAttribute("data-demo", demo.id);
    const label = document.createElement("span");
    label.textContent = demoText(`demo_${demo.id}`);
    const chip = document.createElement("span");
    chip.className = "demo-chip";
    chip.setAttribute("data-outcome", demo.id);
    chip.textContent = demoText(`demo_chip_${demo.id}`);
    button.append(label, chip);
    button.addEventListener("click", () => runDemo(demo));
    box.appendChild(button);
  }
}

async function runDemo(demo) {
  await signIn(demo.persona);
  if (!state.token) return;
  const shown = await postCase({
    transaction_key: demo.transaction,
    message: demoText("dispute"),
    language: state.language,
  });
  const details = shown && shown.why ? await shown.why : null;
  const target = details || (shown && shown.card);
  if (target && typeof target.scrollIntoView === "function") {
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function markPersona() {
  const box = document.getElementById("personas");
  if (!box || !box.children) return;
  for (const button of Array.from(box.children)) {
    if (!button.getAttribute || !button.setAttribute) continue;
    const id = button.getAttribute("data-persona");
    button.setAttribute("aria-pressed", id && id === state.persona ? "true" : "false");
  }
}

async function loadPersonas() {
  const payload = await fetch("/api/personas").then((res) => res.json());
  state.personas = payload.personas || [];
  renderPersonas();
}

function renderCharges(charges) {
  const copy = text();
  const box = document.getElementById("charges");
  box.replaceChildren();
  const heading = document.createElement("h2");
  heading.textContent = copy ? copy.charges_title : "";
  box.appendChild(heading);
  for (const tx of charges.transactions || []) {
    const card = document.createElement("article");
    card.className = "card";
    const strong = document.createElement("strong");
    const typeLabel = copy && copy.types && tx.transaction_type ? copy.types[tx.transaction_type] : "";
    strong.textContent = tx.merchant_label || tx.merchant_name || typeLabel || "";
    const meta = document.createElement("div");
    meta.className = "meta";
    const status = tx.status_label || (copy && copy.status && copy.status[tx.transaction_status]) || "";
    const amount = tx.amount_label || formatMoney(tx.amount, tx.currency, tx.customer_country);
    const place = String(tx.place || tx.transaction_city || "").trim();
    meta.textContent = [tx.local_time, place, amount, status]
      .map((part) => String(part || "").trim())
      .filter(Boolean)
      .join(" · ");
    const button = document.createElement("button");
    button.className = "primary";
    button.setAttribute("data-action", "select-charge");
    button.textContent = copy ? copy.dispute : "";
    button.addEventListener("click", () => openCase(tx.transaction_key, button.textContent));
    card.append(strong, meta, button);
    box.appendChild(card);
  }
}

async function refreshCharges() {
  if (!state.token) return;
  const charges = await fetch(`/api/transactions?language=${state.language}`, {
    headers: { authorization: `Bearer ${state.token}` },
  }).then((res) => res.json());
  renderCharges(charges);
}

async function signIn(persona) {
  const headers = { "content-type": "application/json" };
  if (state.testMode && state.testToken) headers["X-Test-Token"] = state.testToken;
  const response = await fetch("/api/session", {
    method: "POST",
    headers,
    body: JSON.stringify({ persona }),
  });
  const body = await response.json();
  state.token = body.token;
  state.persona = body.token ? persona : "";
  markPersona();
  if (body.is_test) state.testMode = true;
  showTestBadge(state.testMode);
  await refreshCharges();
}

function showTestBadge(on) {
  const badge = document.getElementById("test-badge");
  if (!badge) return;
  const copy = text();
  badge.textContent = (copy && copy.test_badge) || (state.language === "pt" ? "MODO TESTE" : "MODO PRUEBA");
  badge.hidden = !on;
}

async function refreshTestMode() {
  try {
    const status = await fetch("/api/test-mode").then((res) => res.json());
    state.testMode = Boolean(status && status.is_test);
  } catch {
    state.testMode = false;
  }
  showTestBadge(state.testMode);
}

function bindTestArm() {
  const link = document.getElementById("test-mode-link");
  const form = document.getElementById("test-mode-form");
  if (link && form) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      form.hidden = !form.hidden;
      link.setAttribute("aria-expanded", form.hidden ? "false" : "true");
      if (form.hidden) return;
      const input = document.getElementById("test-token");
      if (input && input.focus) input.focus();
    });
  }
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("test-token");
    const token = input ? String(input.value || "") : "";
    if (input) input.value = "";
    if (!token) return;
    state.testToken = token;
    await fetch("/api/test-mode", {
      method: "POST",
      headers: { "X-Test-Token": token },
    });
    await refreshTestMode();
    if (!state.testMode) state.testToken = "";
  });
}

function connectError() {
  const copy = text();
  if (copy && copy.connect_error) return copy.connect_error;
  return state.language === "pt"
    ? "Não foi possível conectar. Tente novamente."
    : "No pudimos conectar. Intenta de nuevo.";
}

function showConnectError() {
  const box = document.getElementById("thread");
  if (!box || typeof box.replaceChildren !== "function") return;
  const note = document.createElement("p");
  note.className = "queue-status error";
  note.setAttribute("data-connect-error", "1");
  note.textContent = connectError();
  box.replaceChildren(note);
}

async function postCase(body) {
  let response;
  try {
    response = await fetch("/cases", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    showConnectError();
    return null;
  }
  return render(await response.json());
}

async function openCase(transactionKey, message) {
  await postCase({
    transaction_key: transactionKey,
    message,
    language: state.language,
  });
}

async function sendAction(action) {
  const response = await fetch(`/cases/${state.caseId}/actions`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${state.token}`,
    },
    body: JSON.stringify({ action }),
  });
  render(await response.json());
}

function bandText(band) {
  const copy = text();
  const fromCatalog = copy && copy.bands && copy.bands[band];
  if (fromCatalog) return fromCatalog;
  const fallback = state.language === "pt"
    ? { high: "Alto", low: "Baixo", review: "Revisão", out_of_scope: "Fora de escopo" }
    : { high: "Alto", low: "Bajo", review: "Revisión", out_of_scope: "Fuera de alcance" };
  return fallback[band] || "";
}

function flagText(flag) {
  const copy = text();
  const key = flag === "prompt_injection" ? "flag_injection" : flag === "pii_masked" ? "flag_pii" : "";
  if (key && copy && copy[key]) return copy[key];
  const fallback = state.language === "pt"
    ? { prompt_injection: "Injeção bloqueada", pii_masked: "Dados mascarados" }
    : { prompt_injection: "Inyección bloqueada", pii_masked: "Datos enmascarados" };
  return fallback[flag] || "";
}

function shownReply(body) {
  let reply = String(body.reply || body.message || "");
  if (body.protected) reply = reply.replace(/^Protegido\.\s*/, "");
  return reply;
}

function render(body) {
  state.caseId = body.case_id;
  const box = document.getElementById("thread");
  box.replaceChildren();
  const card = document.createElement("article");
  card.className = "card";
  if (body.band) card.setAttribute("data-band", body.band);
  const copy = text();
  if (body.protected) {
    const notice = document.createElement("p");
    notice.className = "protected";
    notice.textContent = copy ? copy.protected : "Protegido";
    card.appendChild(notice);
    const score = document.createElement("p");
    score.className = "score-line";
    score.dataset.band = "out_of_scope";
    score.textContent = copy ? copy.score_guardrail : "Bloqueado por protección · sin puntaje";
    card.appendChild(score);
  }
  const reply = document.createElement("p");
  reply.className = "reply";
  reply.textContent = shownReply(body);
  card.appendChild(reply);
  for (const action of body.actions || []) {
    const button = document.createElement("button");
    button.setAttribute("data-action", action.id);
    button.textContent = action.label;
    if (action.emphasis === "primary") button.className = "primary";
    button.addEventListener("click", () => sendAction(action.id));
    card.appendChild(button);
  }
  if (body.protected || body.demo_attack) {
    const money = document.createElement("p");
    money.className = "meta";
    const copy = text();
    money.textContent = copy ? copy.no_money : "No se movió dinero";
    card.appendChild(money);
  }
  if (body.demo_attack) {
    const masked = document.createElement("p");
    masked.className = "meta";
    masked.textContent = `${copy ? copy.masked_label : "Texto enmascarado"}: ${body.masked_message || ""}`;
    card.appendChild(masked);
    const audit = body.audit || {};
    const details = document.createElement("details");
    details.className = "audit-row";
    const summary = document.createElement("summary");
    summary.textContent = copy ? copy.audit_label : "Fila de auditoría";
    details.appendChild(summary);
    const row = document.createElement("p");
    const decision = (copy && copy.decisions && copy.decisions[audit.decision]) || "";
    row.appendChild(document.createTextNode(decision));
    for (const flag of audit.guardrail_flags || []) {
      const label = flagText(flag);
      if (!label) continue;
      const chip = document.createElement("span");
      chip.className = "flag-chip";
      chip.textContent = label;
      row.appendChild(document.createTextNode(" "));
      row.appendChild(chip);
    }
    details.appendChild(row);
    card.appendChild(details);
  }
  box.appendChild(card);
  const flags = (body.audit && body.audit.guardrail_flags) || body.guardrail_flags || [];
  const why = body.case_id ? attachWhy(card, body.case_id, flags) : null;
  if ((body.demo_attack || body.protected) && typeof card.scrollIntoView === "function") {
    card.scrollIntoView({ block: "nearest" });
  }
  if ((body.demo_attack || body.protected) && why && typeof why.then === "function") {
    why.then((details) => {
      const target = details || card;
      if (typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ block: "center" });
      }
    });
  }
  return { card, why };
}

async function attachWhy(card, caseId, flags) {
  const response = await fetch(`/api/cases/${encodeURIComponent(caseId)}/trail`, {
    headers: { authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) return null;
  const body = await response.json();
  const details = document.createElement("details");
  details.className = "why";
  const summary = document.createElement("summary");
  const copy = text();
  summary.textContent = copy ? copy.why : "¿Por qué?";
  details.appendChild(summary);
  const chips = document.createElement("div");
  chips.className = "flag-chips";
  for (const flag of flags || []) {
    const label = flagText(flag);
    if (!label) continue;
    const chip = document.createElement("span");
    chip.className = "flag-chip";
    chip.textContent = label;
    chips.appendChild(chip);
  }
  if (chips.children.length) details.appendChild(chips);
  const list = document.createElement("ol");
  for (const step of body.steps || []) {
    const item = document.createElement("li");
    item.dataset.at = step.at || "";
    item.dataset.band = step.band || "";
    item.dataset.reason = step.reason || "";
    item.textContent = [item.dataset.at, bandText(item.dataset.band), item.dataset.reason]
      .filter(Boolean)
      .join(" · ");
    list.appendChild(item);
  }
  details.appendChild(list);
  card.appendChild(details);
  return details;
}

document.getElementById("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.token) return;
  const input = document.getElementById("message");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  await postCase({ message, language: state.language });
});

const breakButton = document.getElementById("break-it");
if (breakButton) breakButton.addEventListener("click", async () => {
  if (!state.token) {
    const first = (state.personas || [])[0];
    if (!first) return;
    await signIn(first.id);
  }
  if (!state.token) return;
  await postCase({
    demo_attack: true,
    language: state.language,
  });
});

document.getElementById("lang").addEventListener("click", () => {
  state.language = state.language === "es" ? "pt" : "es";
  persistLanguage(state.language);
  applyLanguage();
  refreshCharges();
});

function bootstrap() {
  applyLanguage();
  bindTestArm();
  refreshTestMode();
  loadPersonas();
}

bootstrap();
