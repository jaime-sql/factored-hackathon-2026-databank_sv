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
  const rawToggle = document.getElementById("raw-toggle");
  if (rawToggle && text.raw_toggle) rawToggle.textContent = text.raw_toggle;
  if (label && !label.dataset.loaded) label.textContent = text.eval_toggle;
  const badge = document.getElementById("test-badge");
  if (badge && text.test_badge) badge.textContent = text.test_badge;
  revealCopy();
  notifyLanguage();
}

function localeTag() {
  return language === "pt" ? "pt-BR" : "es-MX";
}

function formatCount(value) {
  if (value == null || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString(localeTag());
}

function ratioText(metric) {
  if (!metric || typeof metric !== "object") return "—";
  const k = Number(metric.k);
  const n = Number(metric.n);
  if (metric.k != null && metric.n != null && Number.isFinite(k) && Number.isFinite(n)) {
    return `${formatCount(k)} / ${formatCount(n)}`;
  }
  return metric.display == null ? "—" : String(metric.display);
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
  renderTiles(tiles, body, text);
  renderJudgePanels(body, text);
  document.getElementById("raw").textContent = JSON.stringify(body, null, 2);
}

function renderTiles(tiles, body, text) {
  if (!tiles || !body) return;
  const cases = tile(
    "cases",
    text ? text.tile_cases : "Casos",
    formatCount(body.k1_volume && body.k1_volume.total),
  );
  const handoff = tile(
    "handoff",
    text ? text.tile_handoff : "Traspaso a persona",
    ratioText(body.k5_handoff),
  );
  const containment = tile(
    "containment",
    text ? text.tile_containment : "Contención",
    ratioText(body.k6_containment),
  );
  const evalTile = tile(
    "eval",
    text ? text.tile_eval : "Evaluación excluida",
    formatCount(body.excluded_eval_cases == null ? 0 : body.excluded_eval_cases),
  );
  const testTile = tile(
    "test",
    text ? text.tile_test : "Prueba excluida",
    formatCount(body.excluded_test_cases == null ? 0 : body.excluded_test_cases),
  );
  tiles.replaceChildren(cases, handoff, containment, evalTile, testTile);
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
  renderK11(body, text);
}

function localNumber(value) {
  const text = String(value);
  return language === "pt" ? text.replace(/(\d)\.(\d)/g, "$1,$2") : text;
}

function formatUsd(value) {
  if (value == null || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const digits = number !== 0 && Math.abs(number) < 0.01 ? 4 : 2;
  return `US$${localNumber(number.toFixed(digits))}`;
}

function formatMs(value) {
  if (value == null || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (Math.abs(number) >= 10000) return `${localNumber((number / 1000).toFixed(1))} s`;
  return `${localNumber(Math.round(number))} ms`;
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
  line.textContent = [
    `${text ? text.health_calls : "Llamadas"}: ${health.llm_calls}`,
    `${text ? text.health_p50 : "Latencia p50"}: ${formatMs(health.latency_p50_ms)}`,
    `${text ? text.health_p95 : "Latencia p95"}: ${formatMs(health.latency_p95_ms)}`,
    `${text ? text.health_cost : "Costo medio por llamada"}: ${formatUsd(health.mean_cost_per_call_usd)}`,
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
  const template = text && text.trust_note;
  if (!template) return;
  const when = trustRunTime(rows, text);
  const note = document.createElement("p");
  note.className = "trust-note";
  note.textContent = when
    ? template.replace("{when}", when)
    : template.replace(" ({when})", "").replace("{when}", "");
  node.appendChild(note);
}

// Latest checked_at in trust.json, shown as "3 oct, 10:33 CST" (Mexico City time, UTC-6).
function trustRunTime(rows, text) {
  let latest = null;
  for (const row of rows) {
    const stamp = Date.parse(row && row.checked_at);
    if (Number.isFinite(stamp) && (latest == null || stamp > latest)) latest = stamp;
  }
  if (latest == null) return "";
  const local = new Date(latest - 6 * 60 * 60 * 1000);
  const months = (text && text.months) || [];
  const month = months[local.getUTCMonth()] || String(local.getUTCMonth() + 1);
  const hh = String(local.getUTCHours()).padStart(2, "0");
  const mm = String(local.getUTCMinutes()).padStart(2, "0");
  return `${local.getUTCDate()} ${month}, ${hh}:${mm} CST`;
}

function simLabel(text, key, fallback) {
  return text && text[key] ? text[key] : fallback;
}

function renderSimulator(sim, text) {
  const node = clearSection("simulator");
  if (!node || !sim || !Array.isArray(sim.points) || !sim.points.length) return;
  const points = sim.points.filter((point) => point && typeof point === "object");
  if (!points.length) return;
  points.sort((left, right) => Number(left.t_low) - Number(right.t_low));
  let start = points.findIndex((point) => point.is_default);
  if (start < 0) start = 0;
  node.hidden = false;
  const title = document.createElement("h2");
  title.textContent = simLabel(text, "sim_title", "Simulador de umbral");
  const split = document.createElement("p");
  split.className = "meta";
  split.textContent = simLabel(text, "sim_validation", "conjunto de validación");
  const slider = document.createElement("input");
  slider.type = "range";
  slider.className = "sim-slider";
  slider.min = "0";
  slider.max = String(points.length - 1);
  slider.step = "1";
  slider.value = String(start);
  slider.setAttribute("type", "range");
  slider.setAttribute("min", slider.min);
  slider.setAttribute("max", slider.max);
  slider.setAttribute("aria-label", split.textContent);
  const readout = document.createElement("div");
  readout.className = "sim-readout";
  const fixed = document.createElement("p");
  fixed.className = "sim-fixed";
  fixed.textContent = [
    `${simLabel(text, "sim_high", "Riesgo alto")}: ${sim.n_high}`,
    `${simLabel(text, "sim_fraud_high", "Fraude en riesgo alto")}: ${sim.fraud_in_high}`,
    `${simLabel(text, "sim_rule", "Regla")}: ${sim.n_rule}`,
  ].join(" · ");
  const ruleFraud = document.createElement("p");
  ruleFraud.className = "sim-fixed";
  ruleFraud.textContent = `${simLabel(text, "sim_fraud_rule", "Fraude en la regla")}: ${sim.fraud_in_rule}`;
  function paint() {
    const point = points[Number(slider.value)] || points[start];
    readout.replaceChildren();
    const lines = [
      `${simLabel(text, "sim_t", "Umbral")}: ${localNumber(point.t_low)}`,
      `${simLabel(text, "sim_n_low", "Bajo")}: ${localNumber(point.n_low)}`,
      `${simLabel(text, "sim_n_review", "Revisión")}: ${localNumber(point.n_review)}`,
      `${simLabel(text, "sim_auto", "Automatización")}: ${localNumber(point.automation_rate)}`,
      `${simLabel(text, "sim_missed_n", "Fraude no visto")}: ${localNumber(point.missed_fraud_n)}`,
      `${simLabel(text, "sim_missed_rate", "Tasa de fraude no visto")}: ${localNumber(point.missed_fraud_rate)}`,
      `${simLabel(text, "sim_ci", "Intervalo")}: ${localNumber(point.missed_fraud_ci_lo)}–${localNumber(point.missed_fraud_ci_hi)}`,
      `${simLabel(text, "sim_wrong", "Fraudes cerrados sin revisión humana, por 10k cargos (incluye Pending/Reversed)")}: ${closedWithoutReview(point, sim)}`,
    ];
    if (sim.show_cost) lines.push(`${simLabel(text, "sim_cost", "Costo por caso")}: ${formatCost(point)}`);
    for (const line of lines) {
      const row = document.createElement("p");
      row.textContent = line;
      readout.appendChild(row);
    }
  }
  slider.addEventListener("input", paint);
  paint();
  node.append(title, split, slider, readout, fixed, ruleFraud);
}

// T4: fraud closed without a person = missed fraud in LOW + fraud the Pending/Reversed rule explains,
// per 10k charges. Read from sim_curve.json; fall back to the file's own per-10k value.
function closedWithoutReview(point, sim) {
  const missed = point && point.missed_fraud && typeof point.missed_fraud === "object" ? point.missed_fraud.k : null;
  const k = Number(missed != null ? missed : point && point.missed_fraud_n);
  const rule = Number(sim && sim.fraud_in_rule);
  const total = Number(sim && sim.n_charges);
  let value = null;
  if (Number.isFinite(k) && Number.isFinite(rule) && Number.isFinite(total) && total > 0) {
    value = ((k + rule) / total) * 10000;
  } else if (point && Number.isFinite(Number(point.wrongful_autoclose_per_10k))) {
    value = Number(point.wrongful_autoclose_per_10k);
  }
  if (value == null) return "—";
  return value.toLocaleString(localeTag(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

function fairLabel(text, key, fallback) {
  return text && text[key] ? text[key] : fallback;
}

function renderFairness(payload, text) {
  const node = clearSection("fairness");
  if (!node || payload == null) return;
  node.hidden = false;
  const title = document.createElement("h2");
  title.textContent = fairLabel(text, "fair_title", "Equidad");
  node.appendChild(title);
  const groups = payload.by_customer_country;
  if (!groups || typeof groups !== "object" || Array.isArray(groups)) {
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(payload, null, 2);
    node.appendChild(pre);
    return;
  }
  const pt = language === "pt";
  const lang = pt ? "pt" : "es";
  const caveat = document.createElement("p");
  caveat.className = "fair-caveat";
  caveat.textContent = fairLabel(
    text,
    "fair_caveat",
    pt
      ? "Intervalos de confiança de 95% (conjunto de validação). México: diferença significativa, ver causa."
      : "Intervalos de confianza al 95% (set de validación). México: brecha significativa, ver causa.",
  );
  node.appendChild(caveat);
  const notes = payload.denominator_note;
  if (notes && typeof notes === "object" && typeof notes[lang] === "string" && notes[lang]) {
    const denominator = document.createElement("p");
    denominator.className = "fair-denominator";
    denominator.textContent = notes[lang];
    node.appendChild(denominator);
  }
  const showShares = payload.shares_included === true;
  const headers = [
    fairLabel(text, "fair_country", "País"),
    fairLabel(text, "fair_n", "Casos"),
  ];
  if (showShares) {
    headers.push(
      fairLabel(text, "fair_low", "Bajo"),
      fairLabel(text, "fair_review", "Revisión"),
      fairLabel(text, "fair_high", "Alto"),
    );
  }
  headers.push(
    fairLabel(text, "fair_escalation", pt ? "Razão de encaminhamento" : "Razón de derivación"),
  );
  headers.push(fairLabel(text, "fair_missed", "Fraude no visto"));
  const table = document.createElement("table");
  table.className = "sim-table";
  const head = document.createElement("tr");
  for (const label of headers) {
    const cell = document.createElement("th");
    cell.textContent = label;
    head.appendChild(cell);
  }
  table.appendChild(head);
  for (const [country, group] of Object.entries(groups)) {
    const cause = countryCause(group, lang);
    const row = document.createElement("tr");
    row.setAttribute("data-country", country);
    if (cause) row.className = "fair-gap";
    const missed = (group && group.missed_fraud) || {};
    const values = [null, group && group.n != null ? formatCount(group.n) : null];
    if (showShares) {
      values.push(share(group.low_share), share(group.review_share), share(group.high_share));
    }
    values.push(ratioTimes(group && group.escalation_ratio_vs_overall));
    values.push(missedText(missed, pt));
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 0) fillCountry(cell, country, group, cause, text, pt);
      else cell.textContent = value == null ? "" : String(value);
      row.appendChild(cell);
    });
    table.appendChild(row);
    if (!cause) continue;
    const extra = document.createElement("tr");
    extra.className = "fair-cause-row";
    const cell = document.createElement("td");
    cell.setAttribute("colspan", String(headers.length));
    const paragraph = document.createElement("p");
    paragraph.className = "fair-cause";
    paragraph.textContent = cause;
    cell.appendChild(paragraph);
    const testNote = countryLine(group, "test_note", lang);
    if (testNote) {
      const note = document.createElement("p");
      note.className = "fair-test-note";
      note.textContent = testNote;
      cell.appendChild(note);
    }
    extra.appendChild(cell);
    table.appendChild(extra);
  }
  node.appendChild(table);
  const escalationNote = document.createElement("p");
  escalationNote.className = "fair-escalation-note";
  escalationNote.textContent = fairLabel(
    text,
    "fair_escalation_note",
    pt
      ? "Encaminhamento para revisão humana deste país ÷ o do total (cobranças Aprovadas/Recusadas, conjunto de validação). 1,00× = igual à média."
      : "Derivación a revisión humana de este país ÷ la del total (cargos Aprobados/Rechazados, set de validación). 1.00× = igual al promedio.",
  );
  node.appendChild(escalationNote);
}

function countryCause(group, lang) {
  return countryLine(group, "cause", lang);
}

function countryLine(group, key, lang) {
  if (!group || typeof group !== "object") return "";
  const lines = group[key];
  if (!lines || typeof lines !== "object" || Array.isArray(lines)) return "";
  const line = lines[lang];
  return typeof line === "string" ? line.trim() : "";
}

function countryName(text, country) {
  const names = text && text.countries;
  const name = names && typeof names === "object" ? names[country] : null;
  return typeof name === "string" && name ? name : country;
}

function fillCountry(cell, country, group, cause, text, pt) {
  cell.appendChild(document.createTextNode(countryName(text, country)));
  if (group && group.small_sample === true) {
    const tag = document.createElement("span");
    tag.className = "fair-sample";
    tag.textContent = fairLabel(text, "fair_sample", pt ? "amostra pequena" : "muestra pequeña");
    cell.appendChild(document.createTextNode(" "));
    cell.appendChild(tag);
  }
  if (!cause) return;
  const chip = document.createElement("span");
  chip.className = "fair-gap-chip";
  chip.textContent = fairLabel(text, "fair_gap", pt ? "Lacuna conhecida" : "Brecha conocida");
  cell.appendChild(document.createTextNode(" "));
  cell.appendChild(chip);
}

function missedText(missed, pt) {
  const parts = [];
  if (missed && missed.k != null && missed.n != null) parts.push(`${missed.k}/${missed.n}`);
  const rate = percent(missed && missed.rate, pt);
  const low = percent(missed && missed.ci95_low, pt);
  const high = percent(missed && missed.ci95_high, pt);
  if (rate && low && high) parts.push(`${rate} (${low}–${high})`);
  else if (rate) parts.push(rate);
  return parts.join(" · ");
}

function ratioTimes(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const shown = value.toLocaleString(localeTag(), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${shown}×`;
}

function percent(value, pt) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const rounded = Math.round(value * 1000) / 10;
  const shown = String(rounded);
  return `${pt ? shown.replaceAll(".", ",") : shown}%`;
}

function sampleOk(group) {
  const n = Number(group && group.n);
  return Number.isFinite(n) && n >= 30;
}

function smallSampleNote(text) {
  const note = document.createElement("p");
  note.className = "small-sample";
  note.textContent = text && text.fair_small
    ? text.fair_small
    : "Los grupos con menos de 30 casos quedan fuera";
  return note;
}

function renderK11(body, text) {
  const node = document.getElementById("fairness");
  if (!node || !body || !Array.isArray(body.k11_fairness_handoff)) return;
  let hidden = 0;
  let shown = 0;
  for (const slice of body.k11_fairness_handoff) {
    const groups = Array.isArray(slice && slice.groups) ? slice.groups : [];
    const kept = [];
    for (const group of groups) {
      if (sampleOk(group)) kept.push(group);
      else hidden += 1;
    }
    if (!kept.length) continue;
    shown += kept.length;
    const line = document.createElement("p");
    line.textContent = kept
      .map((group) => `${group.group}: ${group.n}`)
      .join(" · ");
    node.appendChild(line);
  }
  if (!shown && !hidden) return;
  if (hidden) node.appendChild(smallSampleNote(text));
  node.hidden = false;
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
