const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { GUIDE, guideMarkdown } = require("../static/js/tour.js");

const PAGES = {
  client: "static/index.html",
  agent: "static/agent.html",
  metrics: "static/metrics.html",
};

const HIGH = "Puntaje de fraude mayor a 30. Se bloquea la tarjeta y el caso pasa a una persona.";
const REVIEW = "El modelo no puede descartar fraude, así que una persona revisa el cargo.";
const LOW = "Riesgo bajo. El sistema explica el cargo, y el cliente puede pedir hablar con una persona.";
const BANNED = [/seguro/i, /sin fraude/i, /sem fraude/i];

function templateHas(selector, html) {
  const id = /^#([A-Za-z0-9_-]+)$/.exec(selector);
  if (id) return html.includes(`id="${id[1]}"`);
  const href = /^a\[href="([^"]+)"\]$/.exec(selector);
  if (href) return html.includes(`href="${href[1]}"`);
  return false;
}

const guide = fs.readFileSync("docs/guide.md", "utf8");
assert.equal(guide, guideMarkdown(GUIDE));

const tourSource = fs.readFileSync("static/js/tour.js", "utf8");
assert.equal(tourSource.includes("onclick="), false);

for (const [page, file] of Object.entries(PAGES)) {
  const html = fs.readFileSync(file, "utf8");
  assert.ok(html.includes('src="/static/js/tour.js"'), file);
  assert.ok(html.includes('id="tour"'), file);
  assert.ok(html.includes(`data-tour-page="${page}"`), file);
  assert.ok(html.includes("¿Cómo funciona?"), file);
  const steps = GUIDE.pages[page];
  assert.ok(steps.length > 0, page);
  for (const step of steps) {
    assert.equal(typeof step.selector, "string");
    assert.equal(typeof step.es, "string");
    assert.equal(typeof step.pt, "string");
    for (const pattern of BANNED) {
      assert.equal(pattern.test(step.es), false, step.es);
      assert.equal(pattern.test(step.pt), false, step.pt);
    }
    if (step.dynamic) {
      assert.equal(templateHas(step.selector, html), false, `${page} ${step.selector}`);
    } else {
      assert.equal(templateHas(step.selector, html), true, `${page} ${step.selector}`);
    }
    assert.ok(guide.includes(step.selector), step.selector);
    assert.ok(guide.includes(step.es), step.es);
    assert.ok(guide.includes(step.pt), step.pt);
  }
}

const flat = Object.values(GUIDE.pages).flat();
for (const sentence of [HIGH, REVIEW, LOW]) {
  assert.equal(flat.some((step) => step.es === sentence), true, sentence);
  assert.ok(guide.includes(sentence), sentence);
}
assert.ok(guide.includes(GUIDE.chrome.missing.es));

const desk = fs.readFileSync("static/js/desk.js", "utf8");
assert.match(desk, /data-action", "persona"/);
assert.match(desk, /data-action", "select-charge"/);
assert.match(desk, /data-action", action\.id/);
assert.match(desk, /data-band/);
const agent = fs.readFileSync("static/js/agent.js", "utf8");
assert.match(agent, /data-action", "packet"/);
assert.match(agent, /data-action", "resolve"/);
const metrics = fs.readFileSync("static/js/metrics.js", "utf8");
for (const name of ["cases", "handoff", "containment", "eval"]) {
  assert.ok(
    metrics.includes(`data-metric="${name}"`) || metrics.includes(`"data-metric", "${name}"`),
    name,
  );
}

assert.equal(path.basename("static/js/tour.js"), "tour.js");
console.log("tour ok");
