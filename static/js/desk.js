const state = { language: "es", token: "", caseId: null };

const copy = {
  es: {
    lang: "Español",
    pick: "Elija una persona sintética",
    charges: "Sus cargos, en su hora local",
    dispute: "No reconozco este cargo",
    message: "Mensaje",
    send: "Enviar",
    why: "¿Por qué?",
  },
  pt: {
    lang: "Português",
    pick: "Escolha uma pessoa sintética",
    charges: "Suas cobranças, no seu horário local",
    dispute: "Não reconheço esta cobrança",
    message: "Mensagem",
    send: "Enviar",
    why: "Por quê?",
  },
};

function applyLanguage() {
  document.documentElement.lang = state.language === "pt" ? "pt" : "es";
  document.getElementById("lang").textContent = copy[state.language].lang;
  const message = document.getElementById("message");
  if (message) message.placeholder = copy[state.language].message;
  const send = document.getElementById("send");
  if (send) send.textContent = copy[state.language].send;
}

document.getElementById("lang").addEventListener("click", () => {
  state.language = state.language === "es" ? "pt" : "es";
  applyLanguage();
});

async function loadPersonas() {
  const payload = await fetch("/api/personas").then((res) => res.json());
  const box = document.getElementById("personas");
  box.innerHTML = "";
  for (const persona of payload.personas) {
    const button = document.createElement("button");
    const note = persona.note ? ` · ${persona.note}` : "";
    button.textContent = `${persona.label} · ${persona.tz}${note}`;
    button.addEventListener("click", () => signIn(persona.id));
    box.appendChild(button);
  }
}

async function signIn(persona) {
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ persona }),
  });
  const body = await response.json();
  state.token = body.token;
  const charges = await fetch("/api/transactions", {
    headers: { authorization: `Bearer ${state.token}` },
  }).then((res) => res.json());
  const box = document.getElementById("charges");
  box.innerHTML = `<h2>${copy[state.language].charges}</h2>`;
  for (const tx of charges.transactions) {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `<strong>${tx.merchant_name}</strong>
      <div class="meta">${tx.local_time} · ${tx.transaction_city} · ${tx.amount} ${tx.currency} · ${tx.transaction_status}</div>`;
    const button = document.createElement("button");
    button.className = "primary";
    button.textContent = copy[state.language].dispute;
    button.addEventListener("click", () => openCase(tx.transaction_key, button.textContent));
    card.appendChild(button);
    box.appendChild(card);
  }
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
  box.innerHTML = "";
  const card = document.createElement("article");
  card.className = "card";
  if (body.protected) {
    const notice = document.createElement("p");
    notice.className = "protected";
    notice.textContent = "Protegido";
    card.appendChild(notice);
  }
  const text = document.createElement("p");
  text.className = "reply";
  text.textContent = body.reply || body.message || "";
  card.appendChild(text);
  for (const action of body.actions || []) {
    const button = document.createElement("button");
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
  summary.textContent = copy[state.language].why;
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

applyLanguage();
loadPersonas();
