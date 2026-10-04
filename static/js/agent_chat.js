// AI agent chat. Loaded after desk.js; does nothing unless /api/agent/config says enabled.
// Free text goes to /api/agent/message. Charge buttons, demos and Intenta romperlo keep
// the guided flow. A card block still needs the customer's tap on "Confirmo el bloqueo".
(function () {
  const agent = {
    enabled: false,
    copy: {},
    conversationId: null,
    history: [],
    busy: false,
  };
  globalThis.HD_AGENT = agent;

  function lang() {
    return state.language === "pt" ? "pt" : "es";
  }

  function t(key) {
    const table = agent.copy[lang()] || agent.copy.es || {};
    return table[key] || "";
  }

  function thread() {
    return document.getElementById("thread");
  }

  function el(tag, className, textValue) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (textValue !== undefined && textValue !== null) node.textContent = String(textValue);
    return node;
  }

  function remember(role, textValue) {
    if (!textValue) return;
    agent.history.push({ role, text: String(textValue).slice(0, 500) });
    agent.history = agent.history.slice(-6);
  }

  function reset() {
    agent.conversationId = null;
    agent.history = [];
    const box = thread();
    if (box && box.dataset && box.dataset.agent === "1") {
      box.replaceChildren();
      delete box.dataset.agent;
    }
  }

  function startThread() {
    const box = thread();
    if (!box) return null;
    if (!box.dataset || box.dataset.agent !== "1") {
      box.replaceChildren();
      if (box.dataset) box.dataset.agent = "1";
    }
    return box;
  }

  function stepList(box) {
    const list = el("ol", "agent-steps");
    list.setAttribute("aria-live", "polite");
    box.appendChild(list);
    return list;
  }

  function addRunning(list, label) {
    const item = el("li", "agent-step");
    item.dataset.state = "running";
    const icon = el("span", "agent-step-icon");
    icon.setAttribute("aria-hidden", "true");
    item.append(icon, el("span", "agent-step-label", label));
    list.appendChild(item);
    return item;
  }

  function finishStep(list, step) {
    let item = null;
    for (const node of Array.from(list.children)) {
      if (node.dataset && node.dataset.state === "running") item = node;
    }
    if (!item) item = addRunning(list, step.label);
    item.dataset.state = step.ok ? "done" : "failed";
    item.dataset.tool = step.tool || "";
    const icon = item.querySelector(".agent-step-icon");
    if (icon) icon.textContent = step.ok ? "✓" : "–";
    const label = item.querySelector(".agent-step-label");
    if (label) label.textContent = step.label;
  }

  function chargeCard(charge) {
    const card = el("div", "agent-charge");
    card.append(el("strong", "", charge.comercio || ""));
    card.append(
      el(
        "span",
        "meta",
        [charge.fecha_corta, charge.monto, charge.estado_texto].filter(Boolean).join(" · ")
      )
    );
    return card;
  }

  function bubble(result) {
    const card = el("article", "card agent-bubble");
    const caseBody = result.case || null;
    if (caseBody && caseBody.band) card.setAttribute("data-band", caseBody.band);
    card.appendChild(el("span", "agent-label", result.label || t("agent_label")));
    const copy = text();
    if (result.protected) {
      card.appendChild(el("p", "protected", copy ? copy.protected : "Protegido"));
    }
    card.appendChild(el("p", "reply", shownReply({ reply: result.reply, protected: result.protected })));
    if (result.charge && !result.protected) card.appendChild(chargeCard(result.charge));
    const actions = (caseBody && caseBody.actions) || [];
    if (actions.length) {
      const row = el("div", "agent-actions");
      for (const action of actions) {
        const button = el("button", action.emphasis === "primary" ? "primary" : "", action.label);
        button.type = "button";
        button.setAttribute("data-action", action.id);
        button.addEventListener("click", () => act(caseBody.case_id, action.id, row));
        row.appendChild(button);
      }
      card.appendChild(row);
    }
    if ((result.candidates || []).length) {
      const chips = el("div", "agent-chips");
      for (const charge of result.candidates) {
        const chip = el("button", "agent-chip");
        chip.type = "button";
        chip.setAttribute("data-action", "pick-charge");
        chip.setAttribute("data-transaction", charge.transaction_key);
        chip.textContent = [charge.comercio, charge.fecha_corta, charge.monto]
          .filter(Boolean)
          .join(" · ");
        chip.addEventListener("click", () => {
          for (const other of Array.from(chips.children)) other.disabled = true;
          send(chip.textContent, charge.transaction_key);
        });
        chips.appendChild(chip);
      }
      card.appendChild(chips);
    }
    if (result.protected || (caseBody && caseBody.protected)) {
      card.appendChild(el("p", "meta", copy ? copy.no_money : "No se movió dinero"));
    }
    if (result.mode === "guided" && result.note) {
      card.appendChild(el("p", "agent-guided", result.note));
    }
    return card;
  }

  function showResult(box, result) {
    agent.conversationId = result.conversation_id || agent.conversationId;
    const card = bubble(result);
    box.appendChild(card);
    remember("assistant", result.reply);
    const caseBody = result.case;
    if (caseBody && caseBody.case_id) {
      state.caseId = caseBody.case_id;
      attachWhy(card, caseBody.case_id, caseBody.guardrail_flags || []);
    }
    if (typeof card.scrollIntoView === "function") card.scrollIntoView({ block: "nearest" });
  }

  async function act(caseId, action, row) {
    for (const button of Array.from(row.children)) button.disabled = true;
    const box = startThread();
    let body;
    try {
      const response = await fetch(`/cases/${encodeURIComponent(caseId)}/actions`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${state.token}` },
        body: JSON.stringify({ action }),
      });
      body = await response.json();
    } catch {
      showConnectError();
      return;
    }
    const card = el("article", "card agent-bubble");
    if (body.band) card.setAttribute("data-band", body.band);
    card.appendChild(el("span", "agent-label", t("agent_label")));
    card.appendChild(el("p", "reply", body.reply || body.message || ""));
    box.appendChild(card);
    remember("assistant", body.reply);
    if (body.case_id) attachWhy(card, body.case_id, body.guardrail_flags || []);
  }

  async function readStream(response, list, box) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let final = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (value) buffer += decoder.decode(value, { stream: true });
      let index = buffer.indexOf("\n");
      while (index >= 0) {
        const line = buffer.slice(0, index).trim();
        buffer = buffer.slice(index + 1);
        index = buffer.indexOf("\n");
        if (!line) continue;
        let event;
        try {
          event = JSON.parse(line);
        } catch {
          continue;
        }
        if (event.type === "start") {
          const thinking = list.querySelector('[data-thinking="1"]');
          if (thinking) thinking.remove();
          addRunning(list, event.label || t("thinking"));
        } else if (event.type === "step") {
          const thinking = list.querySelector('[data-thinking="1"]');
          if (thinking) thinking.remove();
          finishStep(list, event);
        } else if (event.type === "final") {
          final = event.result;
        }
      }
      if (done) break;
    }
    const thinking = list.querySelector('[data-thinking="1"]');
    if (thinking) thinking.remove();
    if (!final) {
      showConnectError();
      return;
    }
    if (!list.children.length) list.remove();
    showResult(box, final);
  }

  async function send(message, transactionKey) {
    if (agent.busy || !state.token) return;
    agent.busy = true;
    const box = startThread();
    if (message) box.appendChild(el("p", "agent-user", message));
    const list = stepList(box);
    const thinking = addRunning(list, t("thinking"));
    thinking.dataset.thinking = "1";
    const headers = { "content-type": "application/json", authorization: `Bearer ${state.token}` };
    if (state.testMode && state.testToken) headers["X-Test-Token"] = state.testToken;
    const payload = {
      message: message || "",
      language: state.language,
      conversation_id: agent.conversationId,
      transaction_key: transactionKey || null,
      history: agent.history,
      stream: true,
    };
    remember("user", message);
    try {
      const response = await fetch("/api/agent/message", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      if (!response.ok || !response.body) throw new Error("agent");
      await readStream(response, list, box);
    } catch {
      list.remove();
      showConnectError();
    } finally {
      agent.busy = false;
    }
  }

  agent.send = send;

  async function boot() {
    try {
      const config = await fetch("/api/agent/config").then((res) => res.json());
      agent.enabled = Boolean(config && config.enabled);
      agent.copy = (config && config.copy) || {};
    } catch {
      agent.enabled = false;
    }
    if (!agent.enabled) return;
    const original = globalThis.signIn;
    if (typeof original === "function") {
      globalThis.signIn = async function (persona) {
        if (persona !== state.persona) reset();
        return original(persona);
      };
    }
  }

  boot();
})();
