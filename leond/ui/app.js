/* LEON dock page.
   The page never touches the network. It calls the methods Python exposes on
   window.pywebview.api, and Python calls back into window.leon. */

const el = {
  island: document.getElementById("island"),
  pill: document.getElementById("pill"),
  thread: document.getElementById("thread"),
  intro: document.getElementById("intro"),
  input: document.getElementById("input"),
  form: document.getElementById("composer"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  stats: document.getElementById("stats"),
  state: document.getElementById("state"),
  model: document.getElementById("model"),
  dot: document.getElementById("dot"),
  toggle: document.getElementById("toggle"),
  approval: document.getElementById("approval"),
  askWhy: document.getElementById("askWhy"),
  askDetail: document.getElementById("askDetail"),
  allow: document.getElementById("allow"),
  deny: document.getElementById("deny"),
};

let current = null;   // assistant bubble being streamed
let busy = false;
let open = false;
let ticket = null;

function api() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

/* island ---------------------------------------------------------------- */

async function setOpen(next) {
  open = next;
  document.body.classList.toggle("open", next);
  await api()?.set_open(next);
  if (next) el.input.focus();
}

el.pill.addEventListener("click", (event) => {
  if (event.target === el.toggle) return;
  if (!open) setOpen(true);
});
el.toggle.addEventListener("click", () => setOpen(!open));

/* helpers --------------------------------------------------------------- */

function setBusy(value) {
  busy = value;
  el.dot.classList.toggle("busy", value);
  el.send.disabled = value;
  el.stop.hidden = !value;
  el.send.hidden = value;
}

function follow() {
  el.thread.scrollTop = el.thread.scrollHeight;
}

function addTurn(kind, text) {
  el.intro?.remove();
  const bubble = document.createElement("div");
  bubble.className = "turn " + kind;
  bubble.textContent = text;
  el.thread.appendChild(bubble);
  follow();
  return bubble;
}

function addNote(text) {
  const note = document.createElement("div");
  note.className = "note";
  note.textContent = text;
  el.thread.appendChild(note);
  follow();
}

function closeApproval() {
  ticket = null;
  el.approval.hidden = true;
}

/* handlers Python calls -------------------------------------------------- */

window.leon = {
  delta(piece) {
    if (!current) current = addTurn("leon", "");
    current.textContent += piece;
    current.classList.add("caret");
    follow();
  },

  state(text) {
    el.state.textContent = text;
  },

  done(payload) {
    if (current) {
      current.classList.remove("caret");
      if (!current.textContent && payload.text) current.textContent = payload.text;
    }
    current = null;
    setBusy(false);
    el.state.textContent = "ready";
    if (payload && payload.cancelled) {
      el.stats.textContent = "stopped";
    } else if (payload && payload.stats) {
      const s = payload.stats;
      const first = s.first_ms == null ? "" : `${s.first_ms} ms to first word · `;
      el.stats.textContent = `${first}${s.per_second} tok/s · ${s.seconds}s`;
    }
  },

  error(message) {
    if (current) {
      current.remove();
      current = null;
    }
    addTurn("leon error", message);
    setBusy(false);
    el.state.textContent = "ready";
    el.stats.textContent = "could not answer";
  },

  busy(value) {
    setBusy(Boolean(value));
    if (value) {
      if (!current) current = addTurn("leon", "");
      el.stats.textContent = "working…";
      follow();
    }
  },

  ask(request) {
    ticket = request.id;
    el.askWhy.textContent = `${request.reason} · ${request.name}`;
    el.askDetail.textContent = request.detail;
    el.approval.hidden = false;
    setOpen(true);
    follow();
  },

  askClosed() {
    closeApproval();
  },
};

/* page events ------------------------------------------------------------ */

async function send() {
  const text = el.input.value.trim();
  if (!text || busy) return;
  const call = api();
  addTurn("me", text);
  el.input.value = "";
  resize();
  current = addTurn("leon", "");
  setBusy(true);
  el.state.textContent = "thinking…";
  el.stats.textContent = "working…";

  if (!call) {
    window.leon.error("The dock is not connected to LEON.");
    return;
  }
  try {
    const result = await call.send(text);
    if (result && result.ok === false) window.leon.error(result.error || "cannot send");
  } catch (err) {
    window.leon.error("LEON did not accept the message.");
  }
}

function resize() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 108) + "px";
}

el.form.addEventListener("submit", (event) => {
  event.preventDefault();
  send();
});

el.input.addEventListener("input", resize);
el.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    send();
  }
});

el.allow.addEventListener("click", () => {
  if (ticket) api()?.answer(ticket, true);
  closeApproval();
});

el.deny.addEventListener("click", () => {
  if (ticket) api()?.answer(ticket, false);
  closeApproval();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (ticket) {
    api()?.answer(ticket, false);
    closeApproval();
  } else if (busy) {
    api()?.stop();
    el.state.textContent = "stopping…";
  } else if (open) {
    setOpen(false);
  }
});

el.stop.addEventListener("click", () => {
  api()?.stop();
  el.state.textContent = "stopping…";
});

/* startup ---------------------------------------------------------------- */

function ready() {
  const call = api();
  if (!call) {
    el.model.textContent = "no bridge";
    el.stats.textContent = "Open the dock with `leon` to connect.";
    return;
  }
  call
    .hello()
    .then((info) => {
      el.model.textContent = info.model;
      el.model.title = `${info.model} at ${info.endpoint}`;
      if (info.accent) document.documentElement.style.setProperty("--accent", info.accent);
      el.stats.textContent = `v${info.version} · local`;
    })
    .catch(() => {
      el.model.textContent = "offline";
    });
}

if (window.pywebview && window.pywebview.api) ready();
else window.addEventListener("pywebviewready", ready);
