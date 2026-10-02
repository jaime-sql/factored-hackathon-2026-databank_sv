const GUIDE = {
  chrome: {
    es: {
      open: "¿Cómo funciona?",
      back: "Anterior",
      next: "Siguiente",
      close: "Cerrar",
    },
    pt: {
      open: "Como funciona?",
      back: "Anterior",
      next: "Seguinte",
      close: "Fechar",
    },
    missing: {
      es: "aparece cuando hay casos",
      pt: "aparece quando há casos",
    },
  },
  pages: {
    client: [
      {
        selector: 'a[href="/"]',
        es: "Esta pantalla es la del cliente: aquí se elige un cargo y se abre el caso.",
        pt: "Esta é a tela do cliente: aqui se escolhe uma cobrança e se abre o caso.",
      },
      {
        selector: 'a[href="/agent"]',
        es: "Consola abre la cola de la persona que revisa los casos.",
        pt: "Console abre a fila da pessoa que revisa os casos.",
      },
      {
        selector: 'a[href="/metrics"]',
        es: "Métricas abre el tablero de conteos.",
        pt: "Métricas abre o painel de contagens.",
      },
      {
        selector: "#lang",
        es: "Este botón cambia el idioma entre español y portugués.",
        pt: "Este botão muda o idioma entre espanhol e português.",
      },
      {
        selector: "#tour",
        es: "Este botón abre la guía y también la cierra.",
        pt: "Este botão abre o guia e também o fecha.",
      },
      {
        selector: '#personas [data-action="persona"]',
        es: "Elija una persona sintética para ver sus cargos.",
        pt: "Escolha uma pessoa sintética para ver as cobranças dela.",
        dynamic: true,
      },
      {
        selector: '#charges [data-action="select-charge"]',
        es: "Este botón elige el cargo que la persona no reconoce.",
        pt: "Este botão escolhe a cobrança que a pessoa não reconhece.",
        dynamic: true,
      },
      {
        selector: "#message",
        es: "Escriba aquí un mensaje sobre el cargo.",
        pt: "Escreva aqui uma mensagem sobre a cobrança.",
      },
      {
        selector: "#send",
        es: "Enviar entrega ese mensaje al asistente.",
        pt: "Enviar entrega essa mensagem ao assistente.",
      },
      {
        selector: "#break-it",
        es: "Intenta romperlo envía un ataque de demostración y muestra la protección.",
        pt: "Tente quebrá-lo envia um ataque de demonstração e mostra a proteção.",
        label: { es: "Intenta romperlo", pt: "Tente quebrá-lo" },
      },
      {
        selector: "details.why summary",
        es: "¿Por qué? muestra la hora local, la banda y el motivo.",
        pt: "Por quê? mostra a hora local, a faixa e o motivo.",
        dynamic: true,
      },
      {
        selector: '#thread [data-action="confirm_block"]',
        es: "Puntaje de fraude mayor a 30. Se bloquea la tarjeta y el caso pasa a una persona.",
        pt: "Pontuação de fraude maior que 30. O cartão é bloqueado e o caso passa a uma pessoa.",
        dynamic: true,
      },
      {
        selector: '#thread [data-action="decline_block"]',
        es: "Si no confirma, la tarjeta no se bloquea.",
        pt: "Se não confirmar, o cartão não é bloqueado.",
        dynamic: true,
      },
      {
        selector: '#thread [data-action="contest"]',
        es: "Este botón pide que una persona revise un cargo pendiente o revertido.",
        pt: "Este botão pede que uma pessoa revise uma cobrança pendente ou revertida.",
        dynamic: true,
      },
      {
        selector: '#thread [data-action="recognize"]',
        es: "Este botón indica que el cliente reconoce el cargo.",
        pt: "Este botão indica que o cliente reconhece a cobrança.",
        dynamic: true,
      },
      {
        selector: '#thread [data-action="open_dispute"]',
        es: "Riesgo bajo. El sistema explica el cargo, y el cliente puede pedir hablar con una persona.",
        pt: "Risco baixo. O sistema explica a cobrança, e o cliente pode pedir para falar com uma pessoa.",
        dynamic: true,
      },
      {
        selector: '#thread [data-band="review"]',
        es: "El modelo no puede descartar fraude, así que una persona revisa el cargo.",
        pt: "O modelo não pode descartar fraude, então uma pessoa revisa a cobrança.",
        dynamic: true,
      },
    ],
    agent: [
      {
        selector: 'a[href="/"]',
        es: "Cliente vuelve a la pantalla donde se abre un caso.",
        pt: "Cliente volta à tela onde se abre um caso.",
      },
      {
        selector: 'a[href="/agent"]',
        es: "Esta pantalla es la consola: la cola de casos para una persona.",
        pt: "Esta tela é o console: a fila de casos para uma pessoa.",
      },
      {
        selector: 'a[href="/metrics"]',
        es: "Métricas abre el tablero de conteos.",
        pt: "Métricas abre o painel de contagens.",
      },
      {
        selector: "#lang",
        es: "Este botón cambia el idioma entre español y portugués.",
        pt: "Este botão muda o idioma entre espanhol e português.",
      },
      {
        selector: "#tour",
        es: "Este botón abre la guía y también la cierra.",
        pt: "Este botão abre o guia e também o fecha.",
      },
      {
        selector: "#token",
        es: "Escriba el token del agente para leer la cola.",
        pt: "Escreva o token do agente para ler a fila.",
      },
      {
        selector: "#load",
        es: "Ver cola pide los casos que esperan a una persona.",
        pt: "Ver fila pede os casos que esperam uma pessoa.",
        label: { es: "Ver cola", pt: "Ver fila" },
      },
      {
        selector: "#queue article.card",
        es: "Cada tarjeta muestra la banda, el monto, el comercio enmascarado, la hora local y el motivo.",
        pt: "Cada cartão mostra a faixa, o valor, o comércio mascarado, a hora local e o motivo.",
        dynamic: true,
      },
      {
        selector: '#queue [data-action="packet"]',
        es: "Abrir paquete muestra el caso verificado, sin el texto crudo del cliente.",
        pt: "Abrir pacote mostra o caso verificado, sem o texto cru do cliente.",
        label: { es: "Abrir paquete", pt: "Abrir pacote" },
        dynamic: true,
      },
      {
        selector: '#queue [data-action="resolve"]',
        es: "Resolver cierra ese caso en la cola.",
        pt: "Resolver fecha esse caso na fila.",
        dynamic: true,
      },
    ],
    metrics: [
      {
        selector: 'a[href="/"]',
        es: "Cliente abre la pantalla donde se elige un cargo.",
        pt: "Cliente abre a tela onde se escolhe uma cobrança.",
      },
      {
        selector: 'a[href="/agent"]',
        es: "Consola abre la cola de la persona que revisa los casos.",
        pt: "Console abre a fila da pessoa que revisa os casos.",
      },
      {
        selector: 'a[href="/metrics"]',
        es: "Esta pantalla es el tablero de conteos.",
        pt: "Esta tela é o painel de contagens.",
      },
      {
        selector: "#lang",
        es: "Este botón cambia el idioma entre español y portugués.",
        pt: "Este botão muda o idioma entre espanhol e português.",
      },
      {
        selector: "#tour",
        es: "Este botón abre la guía y también la cierra.",
        pt: "Este botão abre o guia e também o fecha.",
      },
      {
        selector: "#include-eval",
        es: "Este interruptor incluye o deja fuera los casos de evaluación.",
        pt: "Este interruptor inclui ou deixa de fora os casos de avaliação.",
      },
      {
        selector: '[data-metric="cases"]',
        es: "Esta ficha cuenta los casos que entran en el tablero.",
        pt: "Este cartão conta os casos que entram no painel.",
        dynamic: true,
      },
      {
        selector: '[data-metric="handoff"]',
        es: "Esta ficha mide la proporción de casos cerrados que pasaron a una persona.",
        pt: "Este cartão mede a proporção de casos fechados que passaram a uma pessoa.",
        dynamic: true,
      },
      {
        selector: '[data-metric="containment"]',
        es: "Esta ficha mide la proporción de casos cerrados que no pasaron a una persona.",
        pt: "Este cartão mede a proporção de casos fechados que não passaram a uma pessoa.",
        dynamic: true,
      },
      {
        selector: '[data-metric="eval"]',
        es: "Esta ficha cuenta los casos de evaluación que quedaron fuera de estas cifras.",
        pt: "Este cartão conta os casos de avaliação que ficaram fora destas cifras.",
        dynamic: true,
      },
      {
        selector: "#health",
        es: "Salud del sistema muestra las llamadas, la latencia y el costo.",
        pt: "Saúde do sistema mostra as chamadas, a latência e o custo.",
      },
      {
        selector: "#raw",
        es: "Este bloque es el mismo cálculo en JSON, para leer el detalle.",
        pt: "Este bloco é o mesmo cálculo em JSON, para ler o detalhe.",
      },
    ],
  },
};

const PAGE_TITLES = {
  client: "Cliente (`/`)",
  agent: "Consola (`/agent`)",
  metrics: "Métricas (`/metrics`)",
};

function guideMarkdown(guide) {
  const lines = [
    "# ¿Cómo funciona?",
    "",
    "Texto de la guía para el video. La fuente es `GUIDE` en `static/js/tour.js`.",
    "",
    `Controles: ${guide.chrome.es.back} / ${guide.chrome.es.next} / ${guide.chrome.es.close}. El contador se ve como 2/7. Esc cierra.`,
    `PT: ${guide.chrome.pt.back} / ${guide.chrome.pt.next} / ${guide.chrome.pt.close}.`,
    `Si el elemento no está en pantalla: «${guide.chrome.missing.es}».`,
    `PT: «${guide.chrome.missing.pt}».`,
    "",
  ];
  for (const page of ["client", "agent", "metrics"]) {
    lines.push(`## ${PAGE_TITLES[page]}`, "");
    guide.pages[page].forEach((step, index) => {
      lines.push(`### ${index + 1}. \`${step.selector}\``, "");
      lines.push(step.es, "");
      lines.push(`PT: ${step.pt}`, "");
      if (step.dynamic) {
        lines.push(`Dinámico. Si no está en pantalla: ${guide.chrome.missing.es}`, "");
      }
    });
  }
  return `${lines.join("\n")}\n`;
}

function installTour() {
  if (typeof document === "undefined") return;
  const page = document.body && document.body.dataset.tourPage;
  const opener = document.getElementById("tour");
  const steps = page && GUIDE.pages[page];
  if (!opener || !steps) return;

  const shade = document.createElement("div");
  shade.className = "tour-shade";
  shade.hidden = true;
  const tip = document.createElement("div");
  tip.className = "tour-tip";
  tip.setAttribute("role", "dialog");
  tip.setAttribute("aria-modal", "true");
  tip.hidden = true;
  const text = document.createElement("p");
  const note = document.createElement("p");
  note.className = "tour-note";
  note.hidden = true;
  const bar = document.createElement("div");
  bar.className = "tour-bar";
  const count = document.createElement("span");
  count.className = "tour-count";
  const back = document.createElement("button");
  back.type = "button";
  const next = document.createElement("button");
  next.type = "button";
  const close = document.createElement("button");
  close.type = "button";
  bar.append(count, back, next, close);
  tip.append(text, note, bar);
  document.body.append(shade, tip);

  let index = 0;
  let open = false;
  let target = null;

  function language() {
    return document.documentElement.lang === "pt" ? "pt" : "es";
  }

  function stepSentence(step, lang) {
    const sentence = step[lang];
    if (!step.label) return sentence;
    const source = document.querySelector(step.selector);
    const live = source && String(source.textContent || "").trim();
    const baked = step.label[lang];
    if (!live || !baked || !sentence.startsWith(baked)) return sentence;
    return `${live}${sentence.slice(baked.length)}`;
  }

  function clearTarget() {
    if (target) target.classList.remove("tour-target");
    target = null;
  }

  function headerFloor() {
    const header = document.querySelector("header");
    if (!header || typeof header.getBoundingClientRect !== "function") return 12;
    const bottom = header.getBoundingClientRect().bottom;
    return Math.max(12, bottom + 12);
  }

  function place(el) {
    tip.style.transform = "none";
    const margin = 12;
    const floor = headerFloor();
    if (!el) {
      tip.style.left = "50%";
      tip.style.top = `${floor}px`;
      tip.style.transform = "translateX(-50%)";
      return;
    }
    const rect = el.getBoundingClientRect();
    const box = tip.getBoundingClientRect();
    let top = Math.max(rect.bottom + margin, floor);
    if (top + box.height > window.innerHeight - margin) {
      const above = rect.top - box.height - margin;
      if (above >= floor) top = above;
    }
    if (top < floor) top = floor;
    let left = rect.left;
    if (left + box.width > window.innerWidth - margin) left = window.innerWidth - box.width - margin;
    if (left < margin) left = margin;
    tip.style.top = `${top}px`;
    tip.style.left = `${left}px`;
  }

  function render() {
    const step = steps[index];
    const lang = language();
    const chrome = GUIDE.chrome[lang];
    clearTarget();
    const el = document.querySelector(step.selector);
    opener.textContent = chrome.open;
    text.textContent = stepSentence(step, lang);
    if (el) {
      target = el;
      el.classList.add("tour-target");
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
      note.hidden = true;
      note.textContent = "";
    } else {
      note.hidden = false;
      note.textContent = GUIDE.chrome.missing[lang];
    }
    count.textContent = `${index + 1}/${steps.length}`;
    back.textContent = chrome.back;
    next.textContent = chrome.next;
    close.textContent = chrome.close;
    back.disabled = index === 0;
    next.disabled = index === steps.length - 1;
    place(el);
  }

  function setOpen(value) {
    open = value;
    shade.hidden = !value;
    tip.hidden = !value;
    opener.setAttribute("aria-expanded", value ? "true" : "false");
    if (value) render();
    else clearTarget();
  }

  opener.addEventListener("click", () => {
    if (open) setOpen(false);
    else {
      index = 0;
      setOpen(true);
    }
  });
  back.addEventListener("click", () => {
    if (index > 0) {
      index -= 1;
      render();
    }
  });
  next.addEventListener("click", () => {
    if (index < steps.length - 1) {
      index += 1;
      render();
    }
  });
  close.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (open && event.key === "Escape") setOpen(false);
  });
  window.addEventListener("resize", () => {
    if (open) place(target);
  });
  function onLanguage() {
    if (open) render();
    else opener.textContent = GUIDE.chrome[language()].open;
  }

  const langButton = document.getElementById("lang");
  if (langButton) langButton.addEventListener("click", onLanguage);
  document.addEventListener("hd-lang", onLanguage);
  opener.textContent = GUIDE.chrome[language()].open;
}

installTour();

if (typeof module !== "undefined" && module.exports) {
  module.exports = { GUIDE, guideMarkdown };
}
