/* LEON dock page.
   The page never touches the network. It calls the methods Python exposes on
   window.pywebview.api, and Python calls back into window.leon.

   The shell follows Nook 0.4.2 (MIT): the pill is the whole window, hovering
   opens it after a short debounce, leaving folds it after a grace period, and
   a click pins it open. */

const el = {
  shell: document.getElementById("shell"),
  pill: document.getElementById("pill"),
  thread: document.getElementById("thread"),
  intro: document.getElementById("intro"),
  input: document.getElementById("input"),
  form: document.getElementById("composer"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  stats: document.getElementById("stats"),
  state: document.getElementById("state"),
  clock: document.getElementById("clock"),
  dot: document.getElementById("dot"),
  toggle: document.getElementById("toggle"),
  approval: document.getElementById("approval"),
  chips: document.getElementById("chips"),
  askWhy: document.getElementById("askWhy"),
  askDetail: document.getElementById("askDetail"),
  allow: document.getElementById("allow"),
  deny: document.getElementById("deny"),
};

const HOVER_OPEN_MS = 120; // Nook's hover debounce
const HOVER_CLOSE_MS = 250; // Nook's leave grace

let current = null; // assistant bubble being streamed
let busy = false;
let open = false;
let pinned = false; // clicked open: stays until Esc or another click
let ticket = null;
let timer = null;

function api() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

/* island ---------------------------------------------------------------- */

async function setOpen(next) {
  if (open === next) return;
  open = next;
  document.body.classList.toggle("open", next);
  await api()?.set_open(next);
  if (next) el.input.focus();
  else el.input.blur();
}

function canFold() {
  if (!open || pinned || busy || ticket) return false;
  if (document.activeElement === el.input) return false;
  return !el.input.value.trim();
}

function hoverOpen() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    if (!open) setOpen(true);
  }, HOVER_OPEN_MS);
}

function hoverClose() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    if (canFold()) {
      pinned = false;
      setOpen(false);
    }
  }, HOVER_CLOSE_MS);
}

function togglePin() {
  clearTimeout(timer);
  if (pinned && open) {
    pinned = false;
    if (canFold()) setOpen(false);
    return;
  }
  pinned = true;
  setOpen(true);
}

el.pill.addEventListener("mouseenter", hoverOpen);
el.pill.addEventListener("mouseleave", () => {
  if (!open) clearTimeout(timer);
});
el.shell.addEventListener("mouseenter", () => clearTimeout(timer));
el.shell.addEventListener("mouseleave", hoverClose);
el.pill.addEventListener("click", (event) => {
  if (event.target === el.toggle) return;
  togglePin();
});
el.toggle.addEventListener("click", (event) => {
  event.stopPropagation();
  togglePin();
});

/* clock ----------------------------------------------------------------- */

function tick() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  el.clock.textContent = `${hours}:${minutes}`;
  el.clock.title = now.toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  // Wake on the minute, not every second: the idle pill costs nothing.
  setTimeout(tick, 60000 - (now.getSeconds() * 1000 + now.getMilliseconds()) + 20);
}

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
    pinned = true;
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
  pinned = true;
  if (!open) await setOpen(true);
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

el.chips?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-say]");
  if (!button) return;
  el.input.value = button.dataset.say;
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
    pinned = false;
    setOpen(false);
  }
});

el.stop.addEventListener("click", () => {
  api()?.stop();
  el.state.textContent = "stopping…";
});

/* startup ---------------------------------------------------------------- */

tick();

function ready() {
  const call = api();
  if (!call) {
    el.state.textContent = "no bridge";
    el.stats.textContent = "Open the dock with `leon` to connect.";
    return;
  }
  call
    .hello()
    .then((info) => {
      if (info.accent) document.documentElement.style.setProperty("--accent", info.accent);
      el.stats.textContent = `v${info.version} · ${info.model} · local`;
      el.stats.title = `${info.model} at ${info.endpoint}`;
    })
    .catch(() => {
      el.stats.textContent = "offline";
    });
}

if (window.pywebview && window.pywebview.api) ready();
else window.addEventListener("pywebviewready", ready);
