const box = document.getElementById("include-eval");
const label = document.getElementById("eval-label");

async function load() {
  const response = await fetch(`/api/metrics?include_eval=${box.checked ? "true" : "false"}`);
  const body = await response.json();
  label.textContent = body.eval_toggle_label;
  const tiles = document.getElementById("tiles");
  const volume = body.k1_volume.total;
  const handoff = body.k5_handoff.display;
  const containment = body.k6_containment.display;
  tiles.innerHTML = `
    <article class="card tile" data-metric="cases"><span class="meta">Casos</span><strong>${volume}</strong></article>
    <article class="card tile" data-metric="handoff"><span class="meta">Handoff</span><strong>${handoff}</strong></article>
    <article class="card tile" data-metric="containment"><span class="meta">Contención</span><strong>${containment}</strong></article>
    <article class="card tile" data-metric="eval"><span class="meta">Eval excluido</span><strong>${body.excluded_eval_cases}</strong></article>
  `;
  document.getElementById("raw").textContent = JSON.stringify(body, null, 2);
}

box.addEventListener("change", load);
load();
