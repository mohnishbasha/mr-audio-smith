import { activeCueIndex, fetchCues, type Cue } from "./captions";
import { STYLES } from "./styles";
import { createWaveform, parsePeaks, type Waveform } from "./waveform";

export type PlayerState = "idle" | "loading" | "playing" | "paused" | "ended" | "error" | "offline";

export interface Track {
  lang: string;
  label: string;
  src: string;
  captions?: string;
}

const SEEK_STEP = 5;
const SLOW_LOAD_MS = 300;

const SVG = {
  play: '<path d="M8 5v14l11-7z"/>',
  pause: '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>',
  replay: '<path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z"/>',
};

/** Parse the `tracks` attribute. Invalid JSON is ignored with a console warning. */
export function parseTracks(raw: string | null): Track[] {
  if (raw === null || raw.trim() === "") return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    console.warn("audio-smith-player: invalid JSON in tracks attribute, using src");
    return [];
  }
  if (!Array.isArray(data)) return [];
  const out: Track[] = [];
  for (const item of data as unknown[]) {
    if (typeof item !== "object" || item === null) continue;
    const rec = item as Record<string, unknown>;
    const { lang, src, captions } = rec;
    if (typeof lang !== "string" || typeof src !== "string") continue;
    const name = [rec["label"], rec["name"]].find((v): v is string => typeof v === "string");
    const track: Track = { lang, src, label: name ?? lang.toUpperCase() };
    if (typeof captions === "string" && captions !== "") track.captions = captions;
    out.push(track);
  }
  return out;
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function spokenTime(seconds: number): string {
  const s = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  const parts: string[] = [];
  if (m > 0) parts.push(`${m} ${m === 1 ? "minute" : "minutes"}`);
  if (r > 0 || m === 0) parts.push(`${r} ${r === 1 ? "second" : "seconds"}`);
  return parts.join(" ");
}

/** HTMLMediaElement.HAVE_METADATA; a literal because not every DOM implementation exposes the constant. */
const HAVE_METADATA = 1;

function readStore(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStore(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage may be blocked; the player keeps working without it.
  }
}

const TEMPLATE = `<style>${STYLES}</style>
<div class="card" part="card">
<button class="play" type="button" aria-describedby="lbl"><svg viewBox="0 0 24 24" aria-hidden="true"></svg></button>
<span class="label" id="lbl"></span>
<div class="tools"><span class="time"></span><button class="cc" type="button" aria-pressed="false" hidden></button><div class="lang" role="radiogroup" hidden></div><a class="dl" hidden></a></div>
<div class="err" role="alert" hidden><svg viewBox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="M12 2 1 21h22zM11 9h2v6h-2zm0 7h2v2h-2z"/></svg><span class="msg"></span><button class="retry" type="button"></button></div>
<div class="sr status" role="status" aria-live="polite"></div>
</div>
<p class="cap" aria-live="off" hidden></p>`;

export class AudioSmithPlayer extends HTMLElement {
  static readonly observedAttributes = [
    "src",
    "captions",
    "label",
    "size",
    "tracks",
    "theme",
    "peaks",
    "download",
    "artist",
    "captions-on-label",
    "captions-off-label",
    "error-label",
    "retry-label",
    "offline-label",
    "loading-label",
    "paused-label",
    "ended-label",
    "play-label",
    "pause-label",
    "replay-label",
  ];

  readonly #wave: Waveform = createWaveform();
  #audio!: HTMLAudioElement;
  #state: PlayerState = "idle";
  #tracks: Track[] = [];
  #sel = 0;
  #src = "";
  #cues: Cue[] = [];
  #capsOn = false;
  #capsToken = 0;
  #slowTimer: ReturnType<typeof setTimeout> | undefined;
  #lastSave = 0;
  #resume: ((duration: number) => void) | null = null;
  #ready = false;
  #el!: {
    card: HTMLElement;
    play: HTMLButtonElement;
    label: HTMLElement;
    time: HTMLElement;
    cc: HTMLButtonElement;
    lang: HTMLElement;
    dl: HTMLAnchorElement;
    err: HTMLElement;
    msg: HTMLElement;
    retry: HTMLButtonElement;
    status: HTMLElement;
    cap: HTMLElement;
  };

  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    const q = (s: string): never => {
      const found = root.querySelector(s);
      if (!found) throw new Error(`missing ${s}`);
      return found as never;
    };
    this.#el = {
      card: q(".card"),
      play: q(".play"),
      label: q(".label"),
      time: q(".time"),
      cc: q(".cc"),
      lang: q(".lang"),
      dl: q(".dl"),
      err: q(".err"),
      msg: q(".msg"),
      retry: q(".retry"),
      status: q(".status"),
      cap: q(".cap"),
    };
    this.#wave.el.setAttribute("role", "slider");
    this.#wave.el.tabIndex = 0;
    this.#el.label.after(this.#wave.el);
    this.#el.play.addEventListener("click", () => {
      this.#toggle();
    });
    this.#el.cc.addEventListener("click", () => {
      this.#setCaptions(!this.#capsOn);
    });
    this.#el.retry.addEventListener("click", () => {
      this.#retry();
    });
    this.#wave.el.addEventListener("click", (e) => {
      const r = this.#wave.el.getBoundingClientRect();
      if (r.width > 0) this.#seekTo(((e.clientX - r.left) / r.width) * this.#duration());
    });
    root.addEventListener("keydown", (e) => {
      this.#onKey(e as KeyboardEvent);
    });
  }

  get state(): PlayerState {
    return this.#state;
  }

  connectedCallback(): void {
    let audio = this.querySelector("audio");
    if (!audio) {
      audio = document.createElement("audio");
      this.append(audio);
    }
    this.#audio = audio;
    audio.removeAttribute("controls");
    if (!audio.hasAttribute("preload")) audio.preload = "metadata";
    for (const ev of [
      "play",
      "playing",
      "waiting",
      "pause",
      "ended",
      "error",
      "timeupdate",
      "loadedmetadata",
      "durationchange",
    ]) {
      audio.addEventListener(ev, this.#onMedia);
    }
    window.addEventListener("online", this.#onNet);
    window.addEventListener("offline", this.#onNet);
    this.#capsOn = readStore("as:captions") === "true";
    this.#ready = true;
    this.#configure(true);
  }

  disconnectedCallback(): void {
    this.#savePosition(true);
    clearTimeout(this.#slowTimer);
    for (const ev of [
      "play",
      "playing",
      "waiting",
      "pause",
      "ended",
      "error",
      "timeupdate",
      "loadedmetadata",
      "durationchange",
    ]) {
      this.#audio.removeEventListener(ev, this.#onMedia);
    }
    window.removeEventListener("online", this.#onNet);
    window.removeEventListener("offline", this.#onNet);
    this.#ready = false;
  }

  attributeChangedCallback(name: string): void {
    if (this.#ready) this.#configure(name === "src" || name === "tracks");
  }

  #attr(name: string, fallback: string): string {
    return this.getAttribute(name) ?? fallback;
  }

  #log(...args: unknown[]): void {
    if (this.hasAttribute("debug")) console.debug("audio-smith-player", ...args);
  }

  /** Apply attributes to the DOM. `reload` re-derives tracks and the audio source. */
  #configure(reload: boolean): void {
    const e = this.#el;
    const size = this.getAttribute("size") === "kid" ? "kid" : "default";
    e.card.dataset["size"] = size;
    e.cap.dataset["size"] = size;
    const label = this.#attr("label", "Listen");
    e.label.textContent = label;
    e.label.title = label;
    this.#wave.el.setAttribute("aria-label", `Seek, ${label}`);
    this.#wave.setPeaks(parsePeaks(this.getAttribute("peaks")));
    if (reload) {
      this.#tracks = parseTracks(this.getAttribute("tracks"));
      const attrSrc = this.getAttribute("src") ?? this.#audio.getAttribute("src") ?? "";
      const at = this.#tracks.findIndex((t) => t.src === attrSrc);
      this.#sel = at >= 0 ? at : 0;
      const src = attrSrc !== "" ? attrSrc : (this.#tracks[this.#sel]?.src ?? "");
      this.#loadSource(src, true);
    }
    this.#renderLang();
    const dl = this.hasAttribute("download");
    e.dl.hidden = !dl;
    if (dl) {
      e.dl.href = this.#src;
      e.dl.setAttribute("download", "");
      e.dl.textContent = this.#attr("download-label", "Download");
    }
    e.cc.textContent = this.#attr(this.#capsOn ? "captions-on-label" : "captions-off-label", "CC");
    e.retry.textContent = this.#attr("retry-label", "Try again");
    this.#syncCaptionsUi();
    this.#sync();
  }

  #loadSource(src: string, restore: boolean): void {
    this.#src = src;
    if (this.#audio.getAttribute("src") !== src && src !== "") this.#audio.src = src;
    this.#state = "idle";
    this.#resume = null;
    if (restore) {
      const saved = Number(readStore(`as:pos:${src}`));
      if (Number.isFinite(saved) && saved >= 1) {
        this.#resume = (d) => {
          if (saved < d - 2) this.#audio.currentTime = saved;
        };
        // A cached file can report metadata before this element upgrades; apply the resume now.
        const d = this.#audio.duration;
        if (this.#audio.readyState >= HAVE_METADATA && Number.isFinite(d)) {
          const resume = this.#resume;
          this.#resume = null;
          resume(d);
        }
      }
    }
    void this.#loadCaptions();
  }

  async #loadCaptions(): Promise<void> {
    const token = ++this.#capsToken;
    this.#cues = [];
    this.#audio.querySelectorAll("track[data-as]").forEach((t) => {
      t.remove();
    });
    const url = this.#currentCaptions();
    if (url === null) return;
    if (!this.#audio.querySelector('track[kind="captions"]')) {
      const track = document.createElement("track");
      track.kind = "captions";
      track.src = url;
      track.srclang = this.#tracks[this.#sel]?.lang ?? this.lang;
      track.label = this.#tracks[this.#sel]?.label ?? "Captions";
      track.dataset["as"] = "";
      this.#audio.append(track);
    }
    try {
      const cues = await fetchCues(url);
      if (token === this.#capsToken) this.#cues = cues;
    } catch {
      if (token !== this.#capsToken) return;
      this.#capsToken++;
      this.#syncCaptionsUi(false);
      this.#emit("as-error", { kind: "captions" });
      return;
    }
    this.#syncCaptionsUi();
    this.#updateCue();
  }

  #currentCaptions(): string | null {
    const t = this.#tracks[this.#sel];
    if (t) return t.captions ?? null;
    return this.getAttribute("captions");
  }

  #syncCaptionsUi(available = this.#currentCaptions() !== null): void {
    const e = this.#el;
    e.cc.hidden = !available;
    e.cc.setAttribute("aria-pressed", String(this.#capsOn));
    e.cc.textContent = this.#attr(this.#capsOn ? "captions-on-label" : "captions-off-label", "CC");
    e.cap.hidden = !(available && this.#capsOn);
    e.cap.lang = this.#tracks[this.#sel]?.lang ?? this.getAttribute("lang") ?? "";
    this.#updateCue();
  }

  #setCaptions(on: boolean): void {
    this.#capsOn = on;
    writeStore("as:captions", String(on));
    this.#syncCaptionsUi();
  }

  #updateCue(): void {
    const i = activeCueIndex(this.#cues, this.#audio.currentTime);
    this.#el.cap.textContent = this.#cues[i]?.text ?? "";
    this.#el.cap.dataset["cue"] = String(i);
  }

  #renderLang(): void {
    const box = this.#el.lang;
    box.textContent = "";
    box.hidden = this.#tracks.length < 2;
    this.#tracks.forEach((t, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(i === this.#sel));
      b.setAttribute("aria-label", t.label);
      b.textContent = t.lang.toUpperCase();
      b.addEventListener("click", () => {
        this.#selectLanguage(i);
      });
      box.append(b);
    });
    box.setAttribute("aria-label", "Language");
  }

  #selectLanguage(index: number): void {
    const target = this.#tracks[index];
    if (!target || index === this.#sel) return;
    const a = this.#audio;
    const oldTime = a.currentTime;
    const oldDur = this.#duration();
    const wasPlaying = !a.paused;
    this.#sel = index;
    this.#src = target.src;
    a.src = target.src;
    this.#state = "idle";
    this.#resume = (d) => {
      const comparable = oldDur > 0 && Math.abs(d - oldDur) / oldDur <= 0.15;
      a.currentTime = comparable ? (oldTime / oldDur) * d : 0;
      if (wasPlaying) void this.#play();
    };
    this.#renderLang();
    void this.#loadCaptions();
    this.#syncCaptionsUi();
    this.#sync();
    this.#emit("as-language", { lang: target.lang });
  }

  #duration(): number {
    const d = this.#audio.duration;
    return Number.isFinite(d) ? d : 0;
  }

  readonly #onMedia = (ev: Event): void => {
    const a = this.#audio;
    this.#log(ev.type, this.#state);
    switch (ev.type) {
      case "play":
        this.#setState(a.readyState >= 3 ? "playing" : "loading");
        this.#emit("as-play");
        return;
      case "playing":
        this.#setState("playing");
        return;
      case "waiting":
        if (!a.paused) this.#setState("loading");
        return;
      case "pause":
        if (!a.ended && this.#state !== "error" && this.#state !== "offline") {
          this.#setState("paused");
          this.#savePosition(true);
          this.#emit("as-pause");
        }
        return;
      case "ended":
        this.#setState("ended");
        writeStore(`as:pos:${this.#src}`, null);
        this.#emit("as-ended");
        return;
      case "error":
        this.#fail();
        return;
      case "loadedmetadata": {
        const resume = this.#resume;
        this.#resume = null;
        resume?.(this.#duration());
        break;
      }
      case "timeupdate":
        this.#savePosition(false);
        this.#updateCue();
        break;
      default:
        break;
    }
    this.#refreshProgress();
  };

  readonly #onNet = (): void => {
    if (this.#state === "error" && !navigator.onLine) this.#setState("offline");
    else if (this.#state === "offline" && navigator.onLine) this.#sync();
  };

  #fail(): void {
    this.#setState(navigator.onLine ? "error" : "offline");
    this.#emit("as-error", { kind: "audio" });
  }

  #savePosition(force: boolean): void {
    const now = Date.now();
    if (!force && now - this.#lastSave < 1000) return;
    this.#lastSave = now;
    if (this.#src !== "" && this.#state !== "ended" && this.#audio.currentTime > 0) {
      writeStore(`as:pos:${this.#src}`, String(Math.floor(this.#audio.currentTime)));
    }
  }

  #setState(state: PlayerState): void {
    this.#state = state;
    clearTimeout(this.#slowTimer);
    delete this.#el.card.dataset["slow"];
    if (state === "loading") {
      this.#slowTimer = setTimeout(() => {
        this.#el.card.dataset["slow"] = "";
        this.#sync();
      }, SLOW_LOAD_MS);
    }
    this.#sync();
  }

  #toggle(): void {
    if (this.#state === "error" || this.#state === "offline") return;
    if (this.#state === "ended" || this.#audio.ended) this.#audio.currentTime = 0;
    if (this.#audio.paused) void this.#play();
    else this.#audio.pause();
  }

  async #play(): Promise<void> {
    try {
      await this.#audio.play();
      this.#setMediaSession();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (err instanceof DOMException && err.name === "NotAllowedError") this.#setState("idle");
      else this.#fail();
    }
  }

  #retry(): void {
    if (this.#state === "offline" && !navigator.onLine) return;
    this.#state = "idle";
    this.#audio.load();
    this.#sync();
  }

  #seekTo(t: number): void {
    const d = this.#duration();
    const clamped = Math.max(0, d > 0 ? Math.min(d, t) : t);
    this.#audio.currentTime = clamped;
    this.#updateCue();
    this.#refreshProgress();
  }

  #setMediaSession(): void {
    if (!("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    ms.metadata = new MediaMetadata({
      title: this.#attr("label", "Listen"),
      artist: this.getAttribute("artist") ?? "",
    });
    const handlers: [MediaSessionAction, () => void][] = [
      [
        "play",
        () => {
          void this.#play();
        },
      ],
      [
        "pause",
        () => {
          this.#audio.pause();
        },
      ],
      [
        "seekbackward",
        () => {
          this.#seekTo(this.#audio.currentTime - SEEK_STEP);
        },
      ],
      [
        "seekforward",
        () => {
          this.#seekTo(this.#audio.currentTime + SEEK_STEP);
        },
      ],
    ];
    for (const [action, fn] of handlers) {
      try {
        ms.setActionHandler(action, fn);
      } catch {
        // Action not supported by this browser.
      }
    }
  }

  #onKey(e: KeyboardEvent): void {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const onButton = e
      .composedPath()
      .some((n) => n instanceof HTMLButtonElement || n instanceof HTMLAnchorElement);
    const onSlider = e.composedPath().includes(this.#wave.el);
    let handled = true;
    switch (e.key) {
      case " ":
        if (onButton) return; // native button activation handles Space
        this.#toggle();
        break;
      case "k":
      case "K":
        this.#toggle();
        break;
      case "ArrowLeft":
        this.#seekTo(this.#audio.currentTime - SEEK_STEP);
        break;
      case "ArrowRight":
        this.#seekTo(this.#audio.currentTime + SEEK_STEP);
        break;
      case "Home":
        if (!onSlider) return;
        this.#seekTo(0);
        break;
      case "End":
        if (!onSlider) return;
        this.#seekTo(this.#duration());
        break;
      case "c":
      case "C":
        if (this.#el.cc.hidden) return;
        this.#setCaptions(!this.#capsOn);
        break;
      case "l":
      case "L":
        if (this.#tracks.length < 2) return;
        this.#selectLanguage((this.#sel + 1) % this.#tracks.length);
        break;
      default:
        handled = false;
    }
    if (handled) e.preventDefault();
  }

  #emit(name: string, detail: Record<string, string> = {}): void {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }

  #refreshProgress(): void {
    const a = this.#audio;
    const d = this.#duration();
    const t = a.currentTime;
    const e = this.#el;
    this.#wave.update(d > 0 ? t / d : 0, this.#state === "playing");
    const w = this.#wave.el;
    w.setAttribute("aria-valuemin", "0");
    w.setAttribute("aria-valuemax", String(Math.round(d)));
    w.setAttribute("aria-valuenow", String(Math.round(t)));
    w.setAttribute(
      "aria-valuetext",
      d > 0 ? `${spokenTime(t)} of ${spokenTime(d)}` : spokenTime(t),
    );
    const started = t > 0 || this.#state === "playing" || this.#state === "paused";
    e.time.textContent = started
      ? `${formatTime(t)} / ${formatTime(d > 0 ? d : NaN)}`
      : formatTime(d > 0 ? d : NaN);
  }

  /** Apply the current state to the DOM. */
  #sync(): void {
    const e = this.#el;
    const s = this.#state;
    const failed = s === "error" || s === "offline";
    e.card.dataset["state"] = s;
    e.card.toggleAttribute("data-failed", failed);
    e.err.hidden = !failed;
    if (failed) {
      e.msg.textContent =
        s === "offline"
          ? this.#attr(
              "offline-label",
              "You are offline. Audio will play when you are back online.",
            )
          : this.#attr("error-label", "Could not load the audio. Try again.");
      e.retry.disabled = s === "offline" && !navigator.onLine;
    }
    const glyph = s === "playing" || s === "loading" ? "pause" : s === "ended" ? "replay" : "play";
    const name =
      glyph === "pause"
        ? this.#attr("pause-label", "Pause")
        : this.#attr(
            glyph === "replay" ? "replay-label" : "play-label",
            glyph === "replay" ? "Replay" : "Play",
          );
    e.play.setAttribute("aria-label", name);
    const svg = e.play.querySelector("svg");
    if (svg) svg.innerHTML = SVG[glyph];
    const slow = "slow" in e.card.dataset;
    const text =
      s === "loading" && slow
        ? this.#attr("loading-label", "Loading audio")
        : s === "paused"
          ? this.#attr("paused-label", "Paused")
          : s === "ended"
            ? this.#attr("ended-label", "Finished. Play again")
            : "";
    const visible = (s === "loading" && slow) || s === "ended";
    e.status.textContent = text;
    e.status.classList.toggle("sr", !visible);
    this.#refreshProgress();
  }
}
