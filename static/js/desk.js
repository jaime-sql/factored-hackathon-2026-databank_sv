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
  catalog: null,
  personas: [],
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
  revealCopy();
  notifyLanguage();
  for (const button of document.querySelectorAll('#charges [data-action="select-charge"]')) {
    button.textContent = copy.dispute;
  }
  renderPersonas();
}

function renderPersonas() {
  const box = document.getElementById("personas");
  if (!box) return;
  box.replaceChildren();
  for (const persona of state.personas) {
    const button = document.createElement("button");
    button.setAttribute("data-action", "persona");
    const notes = persona.notes || {};
    const note = notes[state.language] || persona.note || "";
    const labels = persona.labels || {};
    const label = labels[state.language] || persona.label || "";
    const suffix = note ? ` · ${note}` : "";
    button.textContent = `${label} · ${persona.tz}${suffix}`;
    button.addEventListener("click", () => signIn(persona.id));
    box.appendChild(button);
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
      form.hidden = false;
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

async function openCase(transactionKey, message) {
  const response = await fetch("/cases", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${state.token}`,
    },
    body: JSON.stringify({
      transaction_key: transactionKey,
      message,
      language: state.language,
    }),
  });
  render(await response.json());
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

function render(body) {
  state.caseId = body.case_id;
  const box = document.getElementById("thread");
  box.replaceChildren();
  const card = document.createElement("article");
  card.className = "card";
  if (body.band) card.setAttribute("data-band", body.band);
  if (body.protected) {
    const notice = document.createElement("p");
    notice.className = "protected";
    const copy = text();
    notice.textContent = copy ? copy.protected : "Protegido";
    card.appendChild(notice);
  }
  const reply = document.createElement("p");
  reply.className = "reply";
  reply.textContent = body.reply || body.message || "";
  card.appendChild(reply);
  for (const action of body.actions || []) {
    const button = document.createElement("button");
    button.setAttribute("data-action", action.id);
    button.textContent = action.label;
    if (action.emphasis === "primary") button.className = "primary";
    button.addEventListener("click", () => sendAction(action.id));
    card.appendChild(button);
  }
  box.appendChild(card);
  if (body.case_id) attachWhy(card, body.case_id);
}

async function attachWhy(card, caseId) {
  const response = await fetch(`/api/cases/${encodeURIComponent(caseId)}/trail`, {
    headers: { authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) return;
  const body = await response.json();
  const details = document.createElement("details");
  details.className = "why";
  const summary = document.createElement("summary");
  const copy = text();
  summary.textContent = copy ? copy.why : "¿Por qué?";
  details.appendChild(summary);
  const list = document.createElement("ol");
  for (const step of body.steps || []) {
    const item = document.createElement("li");
    item.textContent = [step.at, step.band, step.reason].filter(Boolean).join(" · ");
    list.appendChild(item);
  }
  details.appendChild(list);
  card.appendChild(details);
}

document.getElementById("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.token) return;
  const input = document.getElementById("message");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  const response = await fetch("/cases", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${state.token}`,
    },
    body: JSON.stringify({ message, language: state.language }),
  });
  render(await response.json());
});

document.getElementById("lang").addEventListener("click", () => {
  state.language = state.language === "es" ? "pt" : "es";
  persistLanguage(state.language);
  applyLanguage();
  refreshCharges();
});

async function bootstrap() {
  try {
    state.catalog = await fetch("/api/i18n").then((res) => res.json());
  } catch {
    state.catalog = null;
  }
  bindTestArm();
  await refreshTestMode();
  applyLanguage();
  await loadPersonas();
}

bootstrap();
