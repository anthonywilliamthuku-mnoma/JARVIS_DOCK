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
  panel: document.getElementById("panel"),
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

/* `focus` is only ever asked for by a click. If hover focused the box, the
   dock could never fold itself again: canFold() keeps a focused composer. */
async function setOpen(next, { focus = false } = {}) {
  if (open === next) {
    if (next && focus) el.input.focus();
    return;
  }
  open = next;
  document.body.classList.toggle("open", next);
  await api()?.set_open(next);
  if (next && focus) el.input.focus();
  else if (!next) el.input.blur();
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
  setOpen(true, { focus: true });
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

/* Touching anything inside the open panel means the user is using it, so the
   dock stays out of the way until Escape. */
el.panel.addEventListener("click", () => {
  clearTimeout(timer);
  pinned = true;
});

el.input.addEventListener("focus", () => {
  pinned = true;
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
  if (!open) await setOpen(true, { focus: true });
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
  el.input.style.height = Math.min(el.input.scrollHeight, 62) + "px";
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
  if (TOOLS.page) {
    closeTool();
  } else if (ticket) {
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

/* tools ------------------------------------------------------------------
   The grid mirrors Nook's bento: every tile is a real backend action. */

const TOOLS = { tiles: [], page: null, poll: null };

const tabs = document.getElementById("tabs");
const views = {
  chat: document.getElementById("viewChat"),
  tools: document.getElementById("viewTools"),
};
const grid = document.getElementById("grid");
const tool = document.getElementById("tool");
const toolBody = document.getElementById("toolBody");
const toolName = document.getElementById("toolName");
const toolBadge = document.getElementById("toolBadge");

function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  Object.assign(node, props || {});
  for (const kid of kids) {
    if (kid == null) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

function hint(text) {
  return h("p", { className: "hint" }, text);
}

function button(label, onclick, cls) {
  const node = h("button", { type: "button", className: cls || "act" }, label);
  node.addEventListener("click", onclick);
  return node;
}

async function run(toolId, action, arg = "") {
  const call = api();
  if (!call) return { ok: false, error: "no bridge" };
  try {
    return await call.act_tool(toolId, action, String(arg));
  } catch (err) {
    return { ok: false, error: "that did not work" };
  }
}

function showView(name) {
  for (const [key, view] of Object.entries(views)) view.hidden = key !== name;
  for (const tab of tabs.children) tab.classList.toggle("on", tab.dataset.view === name);
  if (name === "tools") loadGrid();
  else if (TOOLS.page) closeTool();
}

tabs.addEventListener("click", (event) => {
  // The tabs sit in the pill, whose click pins the dock: keep that to itself.
  event.stopPropagation();
  const tab = event.target.closest("button[data-view]");
  if (tab) showView(tab.dataset.view);
});

async function loadGrid() {
  const call = api();
  if (!call) return;
  try {
    TOOLS.tiles = await call.tools();
  } catch (err) {
    TOOLS.tiles = [];
  }
  grid.replaceChildren(...TOOLS.tiles.map(tileButton));
}

function tileButton(item) {
  const node = h(
    "button",
    { type: "button", className: `tile ${item.size}`, title: item.blurb },
    item.badge ? h("span", { className: "badge" }, item.badge) : null,
    h("span", { className: "glyph" }, item.glyph),
    h("span", { className: "name" }, item.name),
    h("span", { className: "blurb" }, item.blurb),
  );
  node.addEventListener("click", () => openTool(item.id));
  return node;
}

async function openTool(id) {
  const item = TOOLS.tiles.find((tile) => tile.id === id);
  TOOLS.page = id;
  tool.hidden = false;
  grid.hidden = true;
  toolName.textContent = item ? item.name : id;
  toolBadge.textContent = item && item.badge ? item.badge : "";
  toolBody.replaceChildren(hint("…"));

  const payload = (await api()?.open_tool(id)) || { ok: false, error: "no bridge" };
  toolBody.replaceChildren();
  if (payload.ok === false) {
    toolBody.append(hint(payload.error || "this tool cannot open"));
    return;
  }
  const render = RENDERERS[id];
  if (render) render(toolBody, payload, item);
  else toolBody.append(hint("No view for this tool yet."));
}

function closeTool() {
  TOOLS.page = null;
  if (TOOLS.poll) clearInterval(TOOLS.poll);
  TOOLS.poll = null;
  tool.hidden = true;
  grid.hidden = false;
  loadGrid();
}

document.getElementById("toolBack").addEventListener("click", closeTool);

/* one renderer per tile ------------------------------------------------- */

const RENDERERS = {
  awake(body, payload) {
    const line = h("p", {}, "");
    const paint = (state) => {
      line.textContent = state.on
        ? `Keeping this PC awake${state.until ? " until " + state.until : " until switched off"}.`
        : "The PC may sleep normally.";
    };
    paint(payload.state || { on: false });
    const pick = async (minutes, label) => {
      const result = minutes === null ? await run("awake", "off") : await run("awake", "on", minutes);
      paint(result.state || { on: false });
      toolBadge.textContent = (result.state || {}).on ? "on" : "off";
    };
    body.append(
      line,
      h(
        "div",
        { className: "toolrow" },
        button("15 min", () => pick(15)),
        button("1 hour", () => pick(60)),
        button("Always", () => pick(0)),
        button("Off", () => pick(null), "primary"),
      ),
      hint("Nook's coffee tile, without the cup: Windows is told to keep the display on."),
    );
  },

  timer(body) {
    const readout = h("div", { className: "readout" }, "00:00");
    let left = 0;
    let running = null;
    let elapsed = 0;
    const paint = () => {
      const value = left > 0 ? left : elapsed;
      const minutes = String(Math.floor(value / 60)).padStart(2, "0");
      const seconds = String(value % 60).padStart(2, "0");
      readout.textContent = `${minutes}:${seconds}`;
    };
    const stop = () => {
      if (running) clearInterval(running);
      running = null;
      if (TOOLS.poll) clearInterval(TOOLS.poll);
      TOOLS.poll = null;
    };
    const startCountdown = (minutes) => {
      stop();
      left = minutes * 60;
      elapsed = 0;
      paint();
      running = setInterval(() => {
        left = Math.max(0, left - 1);
        paint();
        if (left === 0) {
          stop();
          run("timer", "beep");
          readout.textContent = "time";
        }
      }, 1000);
      TOOLS.poll = running;
    };
    const startStopwatch = () => {
      stop();
      left = 0;
      running = setInterval(() => {
        elapsed += 1;
        paint();
      }, 1000);
      TOOLS.poll = running;
    };
    body.append(
      readout,
      h(
        "div",
        { className: "toolrow" },
        button("1 min", () => startCountdown(1)),
        button("5 min", () => startCountdown(5)),
        button("25 min", () => startCountdown(25)),
        button("Stopwatch", startStopwatch),
        button("Stop", () => {
          stop();
          paint();
        }, "primary"),
      ),
      hint("Runs in the page; Python only makes the sound at zero."),
    );
  },

  calc(body) {
    const field = h("input", {
      className: "field",
      placeholder: "200 + 15%  ·  20% of 150  ·  5 km to mi",
      spellcheck: false,
    });
    const out = h("div", { className: "readout" }, "");
    let timer = null;
    const solve = async () => {
      const text = field.value.trim();
      if (!text) {
        out.textContent = "";
        return;
      }
      const result = await run("calc", "eval", text);
      out.textContent = result.ok ? result.answer : result.error;
    };
    field.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(solve, 140);
    });
    body.append(field, out, hint("Parsed properly, never executed. Units and 0x/0b included."));
    setTimeout(() => field.focus(), 40);
  },

  system(body, payload) {
    const meters = {};
    const make = (label) => {
      const bar = h("i", { style: "width:0%" });
      const value = h("span", { className: "value" }, "—");
      const row = h(
        "div",
        { className: "meter" },
        h("span", {}, label),
        h("div", { className: "bar" }, bar),
        value,
      );
      body.append(row);
      meters[label] = { bar, value };
    };
    make("CPU");
    make("Memory");
    make("Disk");
    const free = h("p", {}, "");
    body.append(free);

    const paint = (state) => {
      if (!state) return;
      const cpu = Math.max(0, state.cpu);
      meters.CPU.bar.style.width = `${cpu}%`;
      meters.CPU.value.textContent = `${cpu}%`;
      meters.Memory.bar.style.width = `${Math.max(0, state.memory)}%`;
      meters.Memory.value.textContent = `${Math.max(0, state.memory)}%`;
      const used = state.disk_total_gb ? 100 - (state.free_gb / state.disk_total_gb) * 100 : 0;
      meters.Disk.bar.style.width = `${used.toFixed(0)}%`;
      meters.Disk.value.textContent = `${state.free_gb} GB`;
      free.textContent = `${state.free_gb} GB free of ${state.disk_total_gb} GB on this drive.`;
    };
    paint(payload.state);
    const ticker = async () => paint((await run("system", "read")).state);
    TOOLS.poll = setInterval(ticker, 2000);
  },

  qr(body) {
    const field = h("textarea", {
      className: "field",
      rows: 2,
      placeholder: "Text or a link to encode",
    });
    const frame = h("div", {});
    const make = async () => {
      const result = await run("qr", "make", field.value);
      frame.replaceChildren();
      if (!result.ok) {
        frame.className = "";
        frame.append(hint(result.error));
        return;
      }
      frame.className = "qr";
      frame.innerHTML = result.svg;
    };
    body.append(field, button("Make the code", make, "primary act"), frame);
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        make();
      }
    });
  },

  calendar(body, payload) {
    let month = (payload.month && payload.month.month) || "";
    const head = h("div", { className: "toolrow calnav" });
    const sheet = h("div", { className: "cal" });
    const list = h("div", { className: "list" });
    const field = h("input", {
      className: "field",
      placeholder: "2026-11-10 20:30 Dentist",
      spellcheck: false,
    });

    const shift = (delta) => {
      const [year, number] = month.split("-").map(Number);
      const date = new Date(year, number - 1 + delta, 1);
      month = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
      load();
    };

    const paint = (view) => {
      month = view.month;
      head.replaceChildren(
        button("‹", () => shift(-1)),
        h("strong", {}, view.label),
        button("›", () => shift(1)),
      );
      sheet.replaceChildren(...["M", "T", "W", "T", "F", "S", "S"].map((d) => h("span", { className: "head" }, d)));
      for (let i = 0; i < view.first_weekday; i += 1) sheet.append(h("span", { className: "day blank" }));
      for (let day = 1; day <= view.days; day += 1) {
        const key = `${view.month}-${String(day).padStart(2, "0")}`;
        const classes = ["day"];
        if (key === view.today) classes.push("today");
        if (view.events[key]) classes.push("has");
        sheet.append(h("span", { className: classes.join(" "), title: (view.events[key] || []).join(" · ") }, String(day)));
      }
      const entries = Object.entries(view.events).filter(([key]) => key.startsWith(view.month)).slice(0, 3);
      list.replaceChildren(
        ...entries.map(([key, items]) =>
          h("div", { className: "item" }, h("span", { className: "dim" }, key.slice(8)), h("span", { className: "grow" }, items.join(" · "))),
        ),
      );
      if (!entries.length) list.append(hint("Nothing saved this month yet."));
    };

    const load = async () => {
      const result = await run("calendar", "month", month);
      if (result.month) paint(result.month);
    };

    const add = async () => {
      const result = await run("calendar", "add", field.value);
      if (!result.ok) {
        list.prepend(hint(result.error));
        return;
      }
      field.value = "";
      if (result.month) paint(result.month);
    };

    // The panel is only 170 px tall, so the month grid gets the top and the
    // new-event field shares its row with the button.
    body.append(
      head,
      sheet,
      h("div", { className: "toolrow" }, field, button("Add", add, "primary act")),
      list,
    );
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        add();
      }
    });
    paint(payload.month);
  },

  clipboard(body, payload) {
    const list = h("div", { className: "list" });
    const paint = (items) => {
      list.replaceChildren(
        ...items.map((item) =>
          h(
            "div",
            { className: "item" },
            h("span", { className: "dim" }, item.when),
            h("span", { className: "grow" }, item.text.replace(/\s+/g, " ").slice(0, 90)),
            button("copy", async () => run("clipboard", "copy", item.text)),
          ),
        ),
      );
      if (!items.length) list.append(hint("Nothing captured yet."));
    };
    paint(payload.items || []);
    body.append(
      h(
        "div",
        { className: "toolrow" },
        button("Grab from the clipboard", async () => {
          const result = await run("clipboard", "grab");
          paint(result.items || []);
          if (!result.ok) list.prepend(hint(result.error));
        }, "primary act"),
        button("Clear", async () => {
          await run("clipboard", "clear");
          paint([]);
        }),
      ),
      list,
      hint("Kept in memory only, like Nook's, and cleared when the dock closes."),
    );
  },

  notes(body, payload) {
    const reader = h("pre", { className: "hint" }, "");
    const list = h("div", { className: "list" });
    const paint = (notes) => {
      list.replaceChildren(
        ...notes.map((note) =>
          button(note.title || note.name, async () => {
            const result = await run("notes", "read", note.name);
            reader.textContent = result.ok ? result.text : result.error;
          }),
        ),
      );
      if (!notes.length) list.append(hint("No notes yet — ask LEON to write one."));
    };
    paint(payload.notes || []);
    body.append(list, reader, hint("Saved as Markdown in LEON's notes folder."));
  },

  launch(body, payload) {
    const field = h("input", {
      className: "field",
      placeholder: "https://…  or  C:\\Users\\you\\Documents  or  ms-settings:display",
      spellcheck: false,
    });
    const status = hint("");
    const open = async (target) => {
      const result = await run("launch", "open", target);
      status.textContent = result.ok ? result.message : result.error;
    };
    const chips = h("div", { className: "toolrow" });
    for (const app of (payload.apps || []).slice(0, 5)) {
      chips.append(button(app, () => open(app)));
    }
    field.title = "Apps come from LEON's allowlist; folders must already exist.";
    body.append(
      chips,
      field,
      button("Open it", () => {
        open(field.value.trim());
        field.value = "";
      }, "primary act"),
      status,
    );
  },

  colour(body, payload) {
    const swatch = h("div", { className: "swatch", style: "background:#101018" });
    const code = h("div", { className: "readout" }, "—");
    const status = hint("Move the pointer where you want, then pick.");
    let pending = null;
    const pick = () => {
      status.textContent = "Picking in 3 seconds…";
      clearTimeout(pending);
      pending = setTimeout(async () => {
        const result = await run("colour", "pick");
        if (!result.ok) {
          status.textContent = result.error;
          return;
        }
        swatch.style.background = result.colour.hex;
        code.textContent = result.colour.hex;
        status.textContent = `${result.colour.rgb} · copied`;
      }, 3000);
    };
    if (payload.colour && payload.colour.hex) {
      swatch.style.background = payload.colour.hex;
      code.textContent = payload.colour.hex;
    }
    body.append(swatch, code, button("Pick under the cursor", pick, "primary act"), status);
  },

  voice(body) {
    const status = hint("Records the microphone to Music\\Voice memos.");
    const record = async (seconds) => {
      status.textContent = `Recording for ${seconds} seconds…`;
      const result = await run("voice", "record", seconds);
      status.textContent = result.ok ? result.message : result.error;
    };
    body.append(
      h(
        "div",
        { className: "toolrow" },
        button("5 s", () => record(5)),
        button("10 s", () => record(10)),
        button("30 s", () => record(30), "primary"),
      ),
      status,
      hint("Needs the microphone package: `uv add sounddevice`."),
    );
  },

  ocr(body) {
    body.append(
      hint("Reading text off the screen needs Windows OCR: `uv add winsdk`."),
      hint("Until then this tile is a placeholder; the OCR pass is not wired up yet."),
    );
  },

  /* Now playing, with the lyric line that belongs to this second. Python does
     the matching: the page only highlights the index it is given. */
  media(body, payload) {
    const title = h("div", { className: "track" }, "Media");
    const sub = h("div", { className: "artist" }, "");
    const list = h("div", { className: "lyrics" });
    const note = hint("");
    const area = h("textarea", {
      className: "field",
      rows: 4,
      spellcheck: false,
      placeholder: "[00:12.34] first line\n[00:17.90] the next one",
    });
    const form = h("div", { className: "lyrform", hidden: true });
    let key = null;
    let index = -2;
    let polling = false;

    const paintActive = () => {
      [...list.children].forEach((node, at) => node.classList.toggle("on", at === index));
      const active = list.children[index];
      if (!active || !active.classList.contains("ly")) return;
      // Centre the current line, but only when it is not already in view,
      // so a short lyric sheet does not scroll at all.
      const view = list.getBoundingClientRect();
      const line = active.getBoundingClientRect();
      if (line.top < view.top || line.bottom > view.bottom) {
        list.scrollTop += line.top - view.top - (list.clientHeight - line.height) / 2;
      }
    };

    async function paintLines() {
      const result = await run("media", "lines");
      if (!result.ok) {
        list.replaceChildren(hint(result.error));
        return;
      }
      list.replaceChildren(
        ...result.lines.map((text) => h("div", { className: "ly" }, text || "·")),
      );
      if (!result.lines.length) list.append(hint("No lyrics saved for this track yet."));
      index = result.index;
      paintActive();
    }

    function paint(data) {
      if (!data.ok) {
        sub.textContent = "";
        note.textContent = data.error;
        list.replaceChildren();
        return;
      }
      const track = data.track;
      title.textContent = track && track.title ? track.title : "Nothing playing";
      sub.textContent = track ? [track.artist, track.album].filter(Boolean).join(" · ") : "";
      play.textContent = data.playing ? "Pause" : "Play";
      note.textContent = track ? "" : "Start something in your player, then reopen this tile.";
      if (data.lyrics.key !== key) {
        key = data.lyrics.key;
        paintLines();
      } else if (data.lyrics.index !== index) {
        index = data.lyrics.index;
        paintActive();
      }
    }

    const refresh = async () => {
      if (polling) return;
      polling = true;
      try {
        paint(await run("media", "state"));
      } finally {
        polling = false;
      }
    };

    const skip = async (action) => {
      await run("media", action);
      refresh();
    };

    const play = button("Play", () => skip("playpause"), "primary act");

    form.append(
      area,
      h(
        "div",
        { className: "toolrow" },
        button(
          "Save lyrics",
          async () => {
            const result = await run("media", "save", area.value);
            note.textContent = result.ok
              ? `Saved ${result.saved} lines to ${result.file}.`
              : result.error;
            if (result.ok) {
              form.hidden = true;
              key = null;
              refresh();
            }
          },
          "primary act",
        ),
        button("Cancel", () => {
          form.hidden = true;
        }),
      ),
      hint("Paste an .lrc for this track once; LEON keeps it in its lyrics folder and reuses it."),
    );

    body.append(
      h(
        "div",
        { className: "mediabar" },
        h("div", { className: "grow" }, title, sub),
        h(
          "div",
          { className: "toolrow" },
          button("‹", () => skip("previous")),
          play,
          button("›", () => skip("next")),
          button("Lyrics", () => {
            form.hidden = !form.hidden;
            if (!form.hidden) area.focus();
          }),
        ),
      ),
      list,
      note,
      form,
    );

    paint(payload);
    TOOLS.poll = setInterval(refresh, 500);
  },
};

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
}  if (window.pywebview && window.pywebview.api) ready();
else window.addEventListener("pywebviewready", ready);

window.addEventListener("pywebviewready", loadGrid);
