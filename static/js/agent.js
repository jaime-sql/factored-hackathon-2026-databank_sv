const tokenInput = document.getElementById("token");

async function boot() {
  const config = await fetch("/api/auth/config").then((res) => res.json());
  if (config.demo_token) tokenInput.value = config.demo_token;
}

async function loadQueue() {
  const response = await fetch("/api/handoff", {
    headers: { authorization: `Bearer ${tokenInput.value}` },
  });
  const body = await response.json();
  const box = document.getElementById("queue");
  box.innerHTML = "";
  for (const item of body.queue || []) {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `<strong>${item.case_id}</strong>
      <div class="meta">${item.status} · ${item.band || ""} · ${item.language || ""}</div>
      <p>${item.recommended_next_step || ""}</p>`;
    const button = document.createElement("button");
    button.textContent = "Abrir paquete";
    button.addEventListener("click", () => openPacket(item.case_id));
    card.appendChild(button);
    box.appendChild(card);
  }
  if (!body.queue) {
    box.textContent = body.message || "No se pudo leer la cola";
  }
}

async function openPacket(caseId) {
  const response = await fetch(`/api/handoff/${caseId}`, {
    headers: { authorization: `Bearer ${tokenInput.value}` },
  });
  document.getElementById("packet").textContent = JSON.stringify(await response.json(), null, 2);
}

document.getElementById("load").addEventListener("click", loadQueue);
boot();
