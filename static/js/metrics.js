function storedLanguage() {
  try {
    return localStorage.getItem("hd_lang") === "pt" ? "pt" : "es";
  } catch {
    return "es";
  }
}

function persistLanguage(next) {
  try {
    localStorage.setItem("hd_lang", next === "pt" ? "pt" : "es");
  } catch {
    /* ignore */
  }
}

function notifyLanguage() {
  if (typeof document.dispatchEvent !== "function" || typeof Event !== "function") return;
  document.dispatchEvent(new Event("hd-lang"));
}

function revealCopy() {
  const root = document.documentElement;
  if (!root || !root.classList || typeof root.classList.remove !== "function") return;
  root.classList.remove("i18n-pending");
}

const box = document.getElementById("include-eval");
const label = document.getElementById("eval-label");
let catalog = globalThis.HD_CATALOG || null;
let language = storedLanguage();
let adminToken = "";
let metricsGeneration = 0;
document.documentElement.lang = language;

function pack() {
  return catalog && catalog[language === "pt" ? "pt" : "es"];
}

function applyNav(copy) {
  const links = { "/": copy.nav_client, "/agent": copy.nav_agent, "/metrics": copy.nav_metrics };
  for (const anchor of document.querySelectorAll("a")) {
    const href = anchor.getAttribute("href");
    if (links[href]) anchor.textContent = links[href];
  }
}

function applyMetricsLanguage() {
  document.documentElement.lang = language === "pt" ? "pt" : "es";
  const text = pack();
  if (!text) return;
  const lang = document.getElementById("lang");
  if (lang) lang.textContent = text.lang_name;
  const lede = document.getElementById("lede");
  if (lede) lede.textContent = text.metrics_lede;
  const title = document.getElementById("page-title");
  if (title) title.textContent = text.metrics_title;
  applyNav(text);
  const tour = document.getElementById("tour");
  if (tour) tour.textContent = text.tour_open;
  if (label && !label.dataset.loaded) label.textContent = text.eval_toggle;
  const badge = document.getElementById("test-badge");
  if (badge && text.test_badge) badge.textContent = text.test_badge;
  revealCopy();
  notifyLanguage();
}

function tile(name, caption, value) {
  const article = document.createElement("article");
  article.className = "card tile";
  article.setAttribute("data-metric", name);
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = caption;
  const strong = document.createElement("strong");
  strong.textContent = String(value);
  article.append(meta, strong);
  return article;
}

function showTestBadge(on) {
  const badge = document.getElementById("test-badge");
  if (!badge) return;
  const text = pack();
  badge.textContent = (text && text.test_badge) || "MODO PRUEBA";
  badge.hidden = !on;
}

async function load() {
  const generation = ++metricsGeneration;
  const text = pack();
  const tiles = document.getElementById("tiles");
  if (tiles) {
    const note = document.createElement("p");
    note.className = "queue-status loading";
    note.setAttribute("data-metrics-loading", "1");
    note.textContent = (text && text.metrics_loading) || "Cargando las métricas…";
    tiles.setAttribute("aria-busy", "true");
    tiles.replaceChildren(note);
  }
  const headers = {};
  if (adminToken) headers.authorization = `Bearer ${adminToken}`;
  const response = await fetch(
    `/api/metrics?include_eval=${box.checked ? "1" : "0"}&language=${language}`,
    { headers },
  );
  const body = await response.json();
  if (generation !== metricsGeneration) return;
  if (tiles) tiles.removeAttribute("aria-busy");
  label.dataset.loaded = "1";
  label.textContent = body.eval_toggle_label;
  const cases = tile("cases", text ? text.tile_cases : "Casos", body.k1_volume.total);
  const handoff = tile(
    "handoff",
    text ? text.tile_handoff : "Traspaso a persona",
    body.k5_handoff.display,
  );
  const containment = tile(
    "containment",
    text ? text.tile_containment : "Contención",
    body.k6_containment.display,
  );
  const evalTile = tile(
    "eval",
    text ? text.tile_eval : "Evaluación excluida",
    body.excluded_eval_cases,
  );
  cases.setAttribute("data-metric", "cases");
  handoff.setAttribute("data-metric", "handoff");
  containment.setAttribute("data-metric", "containment");
  evalTile.setAttribute("data-metric", "eval");
  const testTile = tile(
    "test",
    text ? text.tile_test : "Prueba excluida",
    body.excluded_test_cases == null ? 0 : body.excluded_test_cases,
  );
  testTile.setAttribute("data-metric", "test");
  tiles.replaceChildren(cases, handoff, containment, evalTile, testTile);
  renderJudgePanels(body, text);
  document.getElementById("raw").textContent = JSON.stringify(body, null, 2);
}

function clearSection(id) {
  const node = document.getElementById(id);
  if (!node) return null;
  node.replaceChildren();
  node.hidden = true;
  return node;
}

function renderJudgePanels(body, text) {
  renderHealth(body && body.health, text);
  renderTrust(body && body.trust, text);
  renderSimulator(body && body.simulator, text);
  renderFairness(body && body.fairness, text);
}

function renderHealth(health, text) {
  const node = clearSection("health");
  if (!node || !health) return;
  node.hidden = false;
  const title = document.createElement("h2");
  title.textContent = text ? text.health_title : "Salud del sistema";
  node.appendChild(title);
  if (!health.llm_calls) {
    const empty = document.createElement("p");
    empty.textContent = text ? text.health_empty : "Sin llamadas en esta ventana";
    node.appendChild(empty);
    return;
  }
  const line = document.createElement("p");
  line.className = "health-line";
  const cost = health.mean_cost_per_call_usd == null ? "—" : String(health.mean_cost_per_call_usd);
  line.textContent = [
    `${text ? text.health_calls : "Llamadas"}: ${health.llm_calls}`,
    `${text ? text.health_p50 : "Latencia p50"}: ${health.latency_p50_ms}`,
    `${text ? text.health_p95 : "Latencia p95"}: ${health.latency_p95_ms}`,
    `${text ? text.health_cost : "Costo medio por llamada"}: ${cost}`,
  ].join(" · ");
  node.appendChild(line);
}

function renderTrust(rows, text) {
  const node = clearSection("trust");
  if (!node || !Array.isArray(rows) || !rows.length) return;
  node.hidden = false;
  const title = document.createElement("h2");
  title.textContent = text ? text.trust_title : "Confianza de los datos";
  node.appendChild(title);
  const lang = language === "pt" ? "pt" : "es";
  for (const row of rows) {
    const line = document.createElement("p");
    line.className = "trust-line";
    const label = lang === "pt" ? row.label_pt || row.label_es : row.label_es || row.label_pt;
    line.textContent = `${row.ok ? "●" : "○"} ${label || ""}: ${row.value || ""}`;
    node.appendChild(line);
  }
}

function renderSimulator(sim, text) {
  const node = clearSection("simulator");
  if (!node || !sim || !Array.isArray(sim.points)) return;
  node.hidden = false;
  const title = document.createElement("h2");
  title.textContent = text ? text.sim_title : "Simulador de umbral";
  node.appendChild(title);
  const summary = document.createElement("p");
  summary.className = "meta";
  summary.textContent = [
    `${text ? text.sim_split : "Corte"}: ${sim.split || ""}`,
    `${text ? text.sim_model : "Versión del modelo"}: ${sim.model_version || ""}`,
    `${text ? text.sim_default : "Umbral habitual"}: ${sim.t_low_default}`,
    `${text ? text.sim_charges : "Cargos"}: ${sim.n_charges}`,
    `${text ? text.sim_fraud : "Fraude"}: ${sim.n_fraud}`,
    `${text ? text.sim_high : "Riesgo alto"}: ${sim.n_high}`,
    `${text ? text.sim_rule : "Regla"}: ${sim.n_rule}`,
    `${text ? text.sim_fraud_high : "Fraude en riesgo alto"}: ${sim.fraud_in_high}`,
    `${text ? text.sim_fraud_rule : "Fraude en la regla"}: ${sim.fraud_in_rule}`,
  ].join(" · ");
  node.appendChild(summary);
  const table = document.createElement("table");
  table.className = "sim-table";
  const head = document.createElement("tr");
  const headers = [
    text ? text.sim_t : "Umbral",
    text ? text.sim_n_low : "Bajo",
    text ? text.sim_n_review : "Revisión",
    text ? text.sim_auto : "Automatización",
    text ? text.sim_missed_n : "Fraude no visto",
    text ? text.sim_missed_rate : "Tasa de fraude no visto",
    text ? text.sim_ci : "Intervalo",
    text ? text.sim_wrong : "Cierres indebidos por 10 mil",
  ];
  if (sim.show_cost) headers.push(text ? text.sim_cost : "Costo por caso");
  for (const label of headers) {
    const cell = document.createElement("th");
    cell.textContent = label;
    head.appendChild(cell);
  }
  table.appendChild(head);
  for (const point of sim.points) {
    const row = document.createElement("tr");
    if (point.is_default) row.className = "is-default";
    const cells = [
      point.t_low,
      point.n_low,
      point.n_review,
      point.automation_rate,
      point.missed_fraud_n,
      point.missed_fraud_rate,
      `${point.missed_fraud_ci_lo}–${point.missed_fraud_ci_hi}`,
      point.wrongful_autoclose_per_10k,
    ];
    if (sim.show_cost) cells.push(formatCost(point));
    for (const value of cells) {
      const cell = document.createElement("td");
      cell.textContent = value == null ? "" : String(value);
      row.appendChild(cell);
    }
    table.appendChild(row);
  }
  node.appendChild(table);
}

function formatCost(point) {
  const block = point && point.cost_per_case;
  if (block && typeof block === "object") {
    return ["low", "mid", "high"]
      .map((key) => {
        const row = block[key] || {};
        const value = row.expected_cost_per_case_usd;
        return value == null ? "—" : String(value);
      })
      .join(" / ");
  }
  if (typeof block === "number" || typeof block === "string") return String(block);
  const flat = point.cost_per_case_usd ?? point.expected_cost_usd ?? point.cost_usd;
  return flat == null ? "" : String(flat);
}

function renderFairness(payload, text) {
  const node = clearSection("fairness");
  if (!node || payload == null) return;
  node.hidden = false;
  const title = document.createElement("h2");
  title.textContent = text ? text.fair_title : "Equidad";
  node.appendChild(title);
  const groups = payload.by_customer_country;
  if (!groups || typeof groups !== "object" || Array.isArray(groups)) {
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(payload, null, 2);
    node.appendChild(pre);
    return;
  }
  const table = document.createElement("table");
  table.className = "sim-table";
  const head = document.createElement("tr");
  for (const label of [
    text ? text.fair_country : "País",
    text ? text.fair_n : "Casos",
    text ? text.fair_low : "Bajo",
    text ? text.fair_review : "Revisión",
    text ? text.fair_high : "Alto",
    text ? text.fair_missed : "Fraude no visto",
  ]) {
    const cell = document.createElement("th");
    cell.textContent = label;
    head.appendChild(cell);
  }
  table.appendChild(head);
  for (const [country, group] of Object.entries(groups)) {
    const row = document.createElement("tr");
    const missed = group.missed_fraud || {};
    const missedText =
      missed.k == null ? "" : `${missed.k}/${missed.n}`;
    for (const value of [
      country,
      group.n,
      share(group.low_share),
      share(group.review_share),
      share(group.high_share),
      missedText,
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value == null ? "" : String(value);
      row.appendChild(cell);
    }
    table.appendChild(row);
  }
  node.appendChild(table);
}

function share(value) {
  if (typeof value !== "number") return "";
  return `${Math.round(value * 1000) / 10}%`;
}

box.addEventListener("change", load);
const langButton = document.getElementById("lang");
if (langButton) {
  langButton.addEventListener("click", () => {
    language = language === "es" ? "pt" : "es";
    persistLanguage(language);
    applyMetricsLanguage();
    load();
  });
}

applyMetricsLanguage();
fetch("/api/auth/config")
  .then((res) => (res.ok ? res.json() : {}))
  .catch(() => ({}))
  .then((config) => {
    adminToken = (config && config.demo_token) || "";
    return fetch("/api/test-mode")
      .then((res) => (res.ok ? res.json() : {}))
      .catch(() => ({}));
  })
  .then((status) => {
    showTestBadge(Boolean(status && status.is_test));
    return load();
  })
  .catch(() => load());
