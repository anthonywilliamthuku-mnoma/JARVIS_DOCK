/* LEON's faces.
   Six moods, drawn as inline SVG, small enough for a 43 px island. They blink,
   they wander a little, and their eyes follow the pointer: Python sends the
   pointer's position in window pixels about ten times a second, so a face can
   watch it even when it is nowhere near the dock.

   The page stays dumb on purpose. Python decides the mood and the mode; this
   file only draws them and reports when the user answers an attention ping. */

(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";

  /* One shape and one colour per mood, taken from the reference sheet. */
  const MOODS = {
    calm: { shape: "drop", colour: "#8b8b93" },
    alert: { shape: "triangle", colour: "#3b82f6" },
    glad: { shape: "blob", colour: "#f97316" },
    blank: { shape: "circle", colour: "#0b0b12" },
    listen: { shape: "pill", colour: "#22c55e" },
    think: { shape: "flower", colour: "#b45309" },
  };

  const SHAPES = {
    drop: "M50 4 C70 28 88 46 88 62 A38 38 0 0 1 12 62 C12 46 30 28 50 4 Z",
    triangle: "M50 6 L94 86 Q97 94 88 94 L12 94 Q3 94 6 86 Z",
    blob: "M52 4 C78 2 96 22 94 48 C92 76 72 96 46 94 C20 92 4 72 6 46 C8 22 26 6 52 4 Z",
    circle: "M50 3 A47 47 0 1 1 49.99 3 Z",
    pill: "M32 8 H68 A34 34 0 0 1 68 92 H32 A34 34 0 0 1 32 8 Z",
    flower:
      "M50 10 C62 0 80 8 76 24 C94 22 98 44 82 50 C98 58 90 82 72 76 " +
      "C70 92 50 96 44 80 C32 94 12 84 18 66 C0 60 4 38 22 38 C14 22 34 4 50 10 Z",
  };

  function node(tag, attrs) {
    const made = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) made.setAttribute(key, value);
    return made;
  }

  /* A face is a body plus two eyes. The gaze moves the eyes; the blink scales
     the group they sit in, so the two never fight over one transform. */
  function buildFace(size) {
    const svg = node("svg", {
      viewBox: "0 0 100 100",
      width: String(size),
      height: String(size),
      class: "face",
    });
    const body = node("path", { d: SHAPES.calm, fill: MOODS.calm.colour });
    const eyes = [
      node("g", { class: "eye" }),
      node("g", { class: "eye" }),
    ];
    const left = node("rect", { x: "28", y: "42", width: "11", height: "17", rx: "5.5", fill: "#fff" });
    const right = node("rect", { x: "56", y: "42", width: "11", height: "17", rx: "5.5", fill: "#fff" });
    eyes[0].append(left);
    eyes[1].append(right);
    svg.append(body, eyes[0], eyes[1]);

    return {
      svg,
      set(name) {
        const mood = MOODS[name] || MOODS.calm;
        body.setAttribute("d", SHAPES[mood.shape]);
        body.setAttribute("fill", mood.colour);
      },
      look(x, y) {
        const dx = (Math.max(-1, Math.min(1, x)) * 3.4).toFixed(2);
        const dy = (Math.max(-1, Math.min(1, y)) * 2.6).toFixed(2);
        left.setAttribute("transform", `translate(${dx} ${dy})`);
        right.setAttribute("transform", `translate(${dx} ${dy})`);
      },
      blink(on) {
        svg.classList.toggle("blink", on);
      },
    };
  }

  /* A lane holds one to three faces. They drift inside it on a slow Lissajous
     walk and each blinks on its own clock. The pointer is followed by all of
     them, so the group reads as watching rather than as one moving eye. */
  function Faces(host, { size = 17, count = 1, wander = 3, dot = null } = {}) {
    const faces = [];
    for (let index = 0; index < count; index += 1) {
      const face = buildFace(size);
      host.insertBefore(face.svg, dot || null);
      faces.push({ face, phase: index * 1.9 });
      const loop = () => {
        const wait = 2200 + Math.random() * 3600;
        face.blink(true);
        setTimeout(() => face.blink(false), 105);
        if (Math.random() < 0.25) {
          setTimeout(() => {
            face.blink(true);
            setTimeout(() => face.blink(false), 95);
          }, 190);
        }
        setTimeout(loop, wait);
      };
      setTimeout(loop, 700 + Math.random() * 2400);
    }

    let target = { x: -200, y: -200 };
    let raf = 0;
    let last = 0;
    const started = performance.now();

    function frame(now) {
      raf = requestAnimationFrame(frame);
      if (document.hidden || now - last < 33 || host.offsetParent === null) return;
      last = now;
      const seconds = (now - started) / 1000;
      const box = host.getBoundingClientRect();
      faces.forEach(({ face, phase }, index) => {
        const dx = wander ? Math.sin(seconds * 0.7 + phase) * wander : 0;
        const dy = wander ? Math.cos(seconds * 0.53 + phase * 1.3) * (wander * 0.45) : 0;
        face.svg.style.transform = `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px)`;
        const cx = box.left + box.width * ((index + 0.5) / faces.length);
        const cy = box.top + box.height / 2;
        const reach = Math.max(120, window.innerWidth / 2);
        face.look((target.x - cx) / reach, (target.y - cy) / Math.max(80, window.innerHeight / 2));
      });
    }

    raf = requestAnimationFrame(frame);
    return {
      set(name) {
        for (const { face } of faces) face.set(name);
      },
      eyes(x, y) {
        target = { x, y };
      },
      stop() {
        cancelAnimationFrame(raf);
      },
    };
  }

  /* The waveform. Heights come from the level Python measured on the loopback
     device; when the PC is quiet it breathes instead of going flat, so it still
     reads as alive rather than broken. */
  function Wave(host, { bars = 5, dot = null } = {}) {
    const nodes = [];
    for (let index = 0; index < bars; index += 1) {
      const bar = document.createElement("i");
      host.insertBefore(bar, dot || null);
      nodes.push(bar);
    }
    const shown = nodes.map(() => 0.1);
    let level = 0;
    let raf = 0;
    let last = 0;
    let clock = 0;

    function frame(now) {
      raf = requestAnimationFrame(frame);
      if (document.hidden || now - last < 33 || host.offsetParent === null) return;
      last = now;
      clock += 0.033;
      for (let index = 0; index < bars; index += 1) {
        const swing = Math.abs(Math.sin(clock * 5.2 + index * 1.05));
        const breathe = 0.12 + 0.06 * Math.sin(clock * 1.4 + index * 0.7);
        const want = Math.max(0.08, Math.min(1, breathe + level * (0.45 + 0.55 * swing)));
        shown[index] += (want - shown[index]) * 0.32;
        nodes[index].style.transform = `scaleY(${shown[index].toFixed(3)})`;
      }
    }
    raf = requestAnimationFrame(frame);
    return {
      level(value) {
        level = Math.max(0, Math.min(1, Number(value) || 0));
      },
      stop() {
        cancelAnimationFrame(raf);
      },
    };
  }

  /* wiring ---------------------------------------------------------------- */

  const lane = document.getElementById("lane");
  const corner = document.getElementById("corner");
  const held = document.getElementById("held");
  const glow = document.getElementById("glow");
  const dot = document.getElementById("dot");
  const shell = document.getElementById("shell");
  if (!lane || !dot) return;

  const island = Faces(lane, { size: 17, count: 1, wander: 3.5, dot });
  const wave = Wave(lane, { bars: 5, dot });
  const note = document.createElement("span");
  note.className = "note";
  note.textContent = "♪";
  lane.insertBefore(note, dot);
  const cornerFace = corner ? Faces(corner, { size: 24, count: 1, wander: 1.4 }) : null;

  let beatTimers = [];
  let answered = false;

  function apply(payload) {
    const mood = (payload && payload.mood) || "calm";
    const mode = (payload && payload.mode) || "face";
    document.body.dataset.mood = mood;
    document.body.dataset.mode = mode;
    island.set(mood);
    cornerFace?.set(mood);
    lane.title = (payload && payload.note) || "";
    if (held) held.hidden = !(payload && payload.held);
    if (held && payload && payload.held) held.textContent = `${payload.held} file${payload.held > 1 ? "s" : ""}`;
  }

  function glowOff() {
    for (const timer of beatTimers) clearTimeout(timer);
    beatTimers = [];
    document.body.dataset.attention = "off";
  }

  Object.assign(window.leon, {
    mood: apply,

    eyes(point) {
      if (!point) return;
      island.eyes(point.x, point.y);
      cornerFace?.eyes(point.x, point.y);
    },

    level(value) {
      wave.level(value);
    },

    /* The island glows on the same beats the ping sound plays, and keeps
       pulsing until the user answers: Python pauses the music, so there is
       nothing left to miss while the glow is up. */
    attention(payload) {
      const beats = (payload && payload.beats) || [0];
      answered = false;
      document.body.dataset.attention = "on";
      lane.title = (payload && payload.reason) || "may I have a moment?";
      glowOff();
      document.body.dataset.attention = "on";
      beats.forEach((at, index) => {
        beatTimers.push(
          setTimeout(() => {
            if (!glow) return;
            glow.classList.remove("beat");
            void glow.offsetWidth; // restart the pulse
            glow.classList.add("beat");
          }, at + index * 0),
        );
      });
      beatTimers.push(setTimeout(glowOff, beats[beats.length - 1] + 2600));
    },

    attentionDone() {
      glowOff();
    },
  });

  /* Any click or key means "I am here". */
  function acknowledge() {
    if (document.body.dataset.attention !== "on" || answered) return;
    answered = true;
    glowOff();
    const call = window.pywebview && window.pywebview.api;
    if (call && call.attention_ack) call.attention_ack();
  }

  shell?.addEventListener("pointerdown", acknowledge);
  document.addEventListener("keydown", acknowledge);
})();
