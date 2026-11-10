/* LEON dock page.
   The page never talks to the network. It only calls the four methods Python
   exposes on window.pywebview.api, and Python calls back into window.leon. */

const el = {
  thread: document.getElementById("thread"),
  intro: document.getElementById("intro"),
  input: document.getElementById("input"),
  form: document.getElementById("composer"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  thinking: document.getElementById("thinking"),
  stats: document.getElementById("stats"),
  model: document.getElementById("model"),
  dot: document.getElementById("dot"),
  minimise: document.getElementById("minimise"),
  close: document.getElementById("close"),
};

let bridge = null;
let current = null; // the assistant bubble being streamed
let busy = false;

function api() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

function setBusy(value) {
  busy = value;
  el.thinking.hidden = !value;
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

/* handlers Python calls -------------------------------------------------- */

window.leon = {
  delta(piece) {
    if (!current) current = addTurn("leon", "");
    current.textContent += piece;
    current.classList.add("caret");
    follow();
  },

  done(payload) {
    if (current) {
      current.classList.remove("caret");
      if (!current.textContent && payload.text) current.textContent = payload.text;
    }
    current = null;
    setBusy(false);
    if (payload && payload.cancelled) {
      el.stats.textContent = "stopped";
    } else if (payload && payload.stats) {
      const s = payload.stats;
      const first = s.first_ms == null ? "" : `${s.first_ms} ms to first word · `;
      el.stats.textContent = `${first}${s.per_second} tok/s · ${s.seconds}s`;
    }
    el.input.focus();
  },

  error(message) {
    if (current) {
      current.remove();
      current = null;
    }
    const bubble = addTurn("leon error", message);
    bubble.dataset.error = "1";
    setBusy(false);
    el.stats.textContent = "could not answer";
    el.input.focus();
  },

  busy(value) {
    setBusy(Boolean(value));
    if (value) {
      if (!current) current = addTurn("leon", "");
      el.stats.textContent = "thinking…";
      follow();
    }
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
  el.stats.textContent = "thinking…";

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

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && busy) {
    api()?.stop();
    el.stats.textContent = "stopping…";
  }
});

el.stop.addEventListener("click", () => {
  api()?.stop();
  el.stats.textContent = "stopping…";
});

el.minimise.addEventListener("click", () => api()?.minimise());
el.close.addEventListener("click", () => api()?.close());

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
