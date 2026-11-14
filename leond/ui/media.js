/* The media tile.
   The pane carries artwork, the track and artist, a scrub bar with the two
   times, the three transport buttons, a volume slider with its number and the
   lyric sheet. All of that fits the 470 x 170 panel as two stacked rows plus
   the lyrics underneath.

   Python reads the Windows media session; this file only paints and calls back. */

RENDERERS.media = function mediaView(body, payload) {
  const art = h("div", { className: "art" }, h("span", { className: "artglyph" }, "♪"));
  const title = h("div", { className: "track" }, "Nothing playing");
  const sub = h("div", { className: "artist" }, "");
  const elapsed = h("span", { className: "at" }, "0:00");
  const total = h("span", { className: "at" }, "0:00");
  const fill = h("i");
  const scrub = h("div", { className: "scrub", title: "Click to seek" }, fill);
  const volume = h("input", {
    type: "range",
    min: "0",
    max: "100",
    step: "1",
    value: "50",
    className: "vol",
    title: "System volume",
  });
  const volumeNum = h("span", { className: "at" }, "—");
  const list = h("div", { className: "lyrics" });
  const note = hint("");
  const form = h("div", { className: "lyrform", hidden: true });

  const prev = button("⏮", () => skip("previous"));
  const play = button("▶", () => skip("playpause"), "primary act");
  const next = button("⏭", () => skip("next"));

  let key = null;
  let index = -2;
  let polling = false;
  let duration = 0;
  let position = 0;
  let artKey = null;
  let volumeKnown = false;

  const time = (seconds) => {
    const whole = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(whole / 60);
    return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
  };

  const paintActive = () => {
    [...list.children].forEach((node, at) => node.classList.toggle("on", at === index));
    const active = list.children[index];
    if (!active || !active.classList.contains("ly")) return;
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
    list.replaceChildren(...result.lines.map((text) => h("div", { className: "ly" }, text || "·")));
    if (!result.lines.length) list.append(hint("No lyrics saved for this track yet."));
    index = result.index;
    paintActive();
  }

  async function paintArt(name) {
    if (!name || name === artKey) return;
    artKey = name;
    const result = await run("media", "art");
    if (result && result.ok && result.data_url) {
      art.style.backgroundImage = `url("${result.data_url}")`;
      art.classList.add("has");
    } else {
      art.style.backgroundImage = "";
      art.classList.remove("has");
    }
  }

  function paint(data) {
    if (!data.ok) {
      title.textContent = "Nothing playing";
      sub.textContent = "";
      note.textContent = data.error;
      list.replaceChildren();
      return;
    }
    const track = data.track;
    const playing = Boolean(data.playing);
    const trackTitle = track && track.title ? track.title : "Nothing playing";
    title.textContent = trackTitle;
    title.title = trackTitle;
    title.classList.toggle("glide", trackTitle.length > 28 && playing);
    sub.textContent = track ? [track.artist, track.album].filter(Boolean).join(" · ") : "";
    play.textContent = playing ? "⏸" : "▶";
    note.textContent = track ? "" : "Start something in your player, then reopen this tile.";
    duration = track ? track.duration || 0 : 0;
    position = track ? track.position || 0 : 0;
    elapsed.textContent = time(position);
    total.textContent = duration ? time(duration) : "0:00";
    fill.style.width = `${duration ? Math.min(100, (position / duration) * 100) : 0}%`;

    if (typeof data.volume === "number" && data.volume >= 0) {
      volumeKnown = true;
      volume.value = String(data.volume);
      volumeNum.textContent = String(data.volume);
      volume.disabled = false;
    } else if (!volumeKnown) {
      volumeNum.textContent = "—";
      volume.disabled = true;
      volume.title = data.volume_hint || "Volume needs the Windows audio bindings.";
    }

    if (track) paintArt(`${track.artist} - ${track.title}`);

    if (!data.lyrics) return;
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

  const seek = async (event) => {
    if (!duration) return;
    const box = scrub.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    position = fraction * duration;
    elapsed.textContent = time(position);
    fill.style.width = `${fraction * 100}%`;
    await run("media", "seek", position.toFixed(2));
    refresh();
  };

  scrub.addEventListener("click", seek);
  volume.addEventListener("input", () => {
    volumeNum.textContent = volume.value;
  });
  volume.addEventListener("change", async () => {
    const result = await run("media", "volume", volume.value);
    if (!result.ok) {
      volumeNum.textContent = "—";
      note.textContent = result.error;
    }
  });

  const area = h("textarea", {
    className: "field",
    rows: 3,
    spellcheck: false,
    placeholder: "[00:12.34] first line\n[00:17.90] the next one",
  });

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
  );

  body.append(
    h(
      "div",
      { className: "nowbar" },
      art,
      h(
        "div",
        { className: "nowmeta" },
        title,
        sub,
        h("div", { className: "volrow" }, h("span", { className: "volglyph" }, "🔈"), volume, volumeNum),
      ),
      h("div", { className: "transport" }, prev, play, next),
    ),
    h("div", { className: "scrubrow" }, elapsed, scrub, total),
    h(
      "div",
      { className: "lyrrow" },
      list,
      button(
        "Lyrics",
        () => {
          form.hidden = !form.hidden;
          if (!form.hidden) area.focus();
        },
      ),
    ),
    note,
    form,
  );

  paint(payload);
  TOOLS.poll = setInterval(refresh, 500);
};
