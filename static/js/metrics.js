const box = document.getElementById("include-eval");
const label = document.getElementById("eval-label");
let catalog = null;
let language = "es";

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

async function load() {
  const text = pack();
  const response = await fetch(
    `/api/metrics?include_eval=${box.checked ? "true" : "false"}&language=${language}`,
  );
  const body = await response.json();
  label.dataset.loaded = "1";
  label.textContent = body.eval_toggle_label;
  const tiles = document.getElementById("tiles");
  const cases = tile("cases", text ? text.tile_cases : "Casos", body.k1_volume.total);
  const handoff = tile("handoff", text ? text.tile_handoff : "Handoff", body.k5_handoff.display);
  const containment = tile(
    "containment",
    text ? text.tile_containment : "Contención",
    body.k6_containment.display,
  );
  const evalTile = tile("eval", text ? text.tile_eval : "Eval excluido", body.excluded_eval_cases);
  cases.setAttribute("data-metric", "cases");
  handoff.setAttribute("data-metric", "handoff");
  containment.setAttribute("data-metric", "containment");
  evalTile.setAttribute("data-metric", "eval");
  tiles.replaceChildren(cases, handoff, containment, evalTile);
  document.getElementById("raw").textContent = JSON.stringify(body, null, 2);
}

box.addEventListener("change", load);
const langButton = document.getElementById("lang");
if (langButton) {
  langButton.addEventListener("click", () => {
    language = language === "es" ? "pt" : "es";
    applyMetricsLanguage();
    load();
  });
}

fetch("/api/i18n")
  .then((res) => res.json())
  .then((body) => {
    catalog = body;
    applyMetricsLanguage();
    return load();
  })
  .catch(() => load());
