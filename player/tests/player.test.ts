import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";
import { formatTime, parseTracks, spokenTime } from "../src/player";
import { flush, mount } from "./helpers";
import { MemStorage } from "./setup";

const TRACKS = JSON.stringify([
  { lang: "en", label: "English", src: "a.mp3", captions: "a.vtt" },
  { lang: "hi", name: "Hindi", src: "a-hi.mp3", captions: "a-hi.vtt" },
]);
const VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:10.000\nHello there.\n";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.localStorage.clear();
});

function keydown(m: ReturnType<typeof mount>, key: string, sel = ".play"): KeyboardEvent {
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, composed: true, cancelable: true });
  m.q(sel).dispatchEvent(ev);
  return ev;
}

describe("attributes", () => {
  test("test_player_attributes_parse_tracks_json", () => {
    const tracks = parseTracks(TRACKS);
    expect(tracks.map((t) => t.label)).toEqual(["English", "Hindi"]);
    expect(tracks[1]?.captions).toBe("a-hi.vtt");
  });

  test("test_player_attributes_invalid_tracks_json_falls_back", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(parseTracks("{nope")).toEqual([]);
    expect(warn).toHaveBeenCalled();
    expect(parseTracks('{"a":1}')).toEqual([]);
    expect(parseTracks('[1,{"lang":"en"},{"lang":"en","src":"x"}]')).toEqual([
      { lang: "en", src: "x", label: "EN" },
    ]);
    expect(parseTracks(null)).toEqual([]);
    warn.mockRestore();
  });

  test("test_player_label_default_and_override", () => {
    const m = mount({ src: "a.mp3" });
    expect(m.q(".label").textContent).toBe("Listen");
    m.el.setAttribute("label", "Listen to Dad");
    expect(m.q(".label").textContent).toBe("Listen to Dad");
    expect(m.q(".label").title).toBe("Listen to Dad");
  });

  test("test_player_size_kid_sets_variant", () => {
    const m = mount({ src: "a.mp3", size: "kid" });
    expect(m.q(".card").dataset["size"]).toBe("kid");
  });

  test("test_player_download_is_opt_in", () => {
    const m = mount({ src: "a.mp3" });
    expect(m.q(".dl").hidden).toBe(true);
    m.el.setAttribute("download", "");
    expect(m.q(".dl").hidden).toBe(false);
    expect(m.q(".dl").getAttribute("href")).toBe("a.mp3");
  });

  test("test_player_theme_attribute_reaches_stylesheet", () => {
    const m = mount({ src: "a.mp3", theme: "dark" });
    const css = m.root.querySelector("style")?.textContent ?? "";
    expect(css).toContain(':host([theme="dark"])');
    expect(css).toContain("prefers-color-scheme:dark");
    expect(css).toContain("--as-focus");
  });
});

describe("adoption and fallback", () => {
  test("test_player_adopts_slotted_audio_and_hides_native_controls", () => {
    const m = mount({ src: "a.mp3" });
    expect(m.el.querySelectorAll("audio")).toHaveLength(1);
    expect(m.audio.hasAttribute("controls")).toBe(false);
  });

  test("test_player_creates_audio_when_none_slotted", () => {
    const m = mount({ src: "a.mp3" }, false);
    expect(m.el.querySelectorAll("audio")).toHaveLength(1);
  });
});

describe("states", () => {
  test("test_player_state_idle_to_playing_to_paused_to_ended", () => {
    const m = mount({ src: "a.mp3" });
    const events: string[] = [];
    for (const n of ["as-play", "as-pause", "as-ended"])
      m.el.addEventListener(n, () => events.push(n));
    expect(m.el.state).toBe("idle");
    m.q(".play").click();
    expect(m.el.state).toBe("playing");
    expect(m.q(".play").getAttribute("aria-label")).toBe("Pause");
    m.q(".play").click();
    expect(m.el.state).toBe("paused");
    expect(m.q(".status").textContent).toBe("Paused");
    m.fire("ended");
    expect(m.el.state).toBe("ended");
    expect(m.q(".play").getAttribute("aria-label")).toBe("Replay");
    expect(m.q(".status").textContent).toBe("Finished. Play again");
    expect(events).toEqual(["as-play", "as-pause", "as-ended"]);
  });

  test("test_player_loading_text_only_after_300ms", () => {
    vi.useFakeTimers();
    const m = mount({ src: "a.mp3" });
    Object.defineProperty(m.audio, "play", {
      value: () => {
        Object.defineProperty(m.audio, "paused", { value: false, configurable: true });
        m.fire("play");
        return Promise.resolve();
      },
    });
    m.q(".play").click();
    expect(m.el.state).toBe("loading");
    expect(m.q(".status").textContent).toBe("");
    vi.advanceTimersByTime(301);
    expect(m.q(".status").textContent).toBe("Loading audio");
    m.fire("playing");
    expect(m.q(".status").textContent).toBe("");
  });

  test("test_player_error_state_has_retry_and_custom_copy", () => {
    const m = mount({ src: "a.mp3", "error-label": "Oops", "retry-label": "Again" });
    const errors: string[] = [];
    m.el.addEventListener("as-error", () => errors.push("e"));
    m.fire("error");
    expect(m.el.state).toBe("error");
    expect(m.q(".err").hidden).toBe(false);
    expect(m.q(".msg").textContent).toBe("Oops");
    expect(m.q(".retry").textContent).toBe("Again");
    m.q(".play").click();
    expect(m.el.state).toBe("error");
    m.q(".retry").click();
    expect(m.el.state).toBe("idle");
    expect(m.q(".err").hidden).toBe(true);
    expect(errors).toHaveLength(1);
  });

  test("test_player_offline_state_disables_retry_until_online", () => {
    const m = mount({ src: "a.mp3" });
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    m.fire("error");
    expect(m.el.state).toBe("offline");
    expect((m.q(".retry") as HTMLButtonElement).disabled).toBe(true);
    expect(m.q(".msg").textContent).toContain("offline");
    m.q(".retry").click();
    expect(m.el.state).toBe("offline");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    window.dispatchEvent(new Event("online"));
    expect((m.q(".retry") as HTMLButtonElement).disabled).toBe(false);
    vi.restoreAllMocks();
  });

  test("test_player_error_while_going_offline_switches_to_offline", () => {
    const m = mount({ src: "a.mp3" });
    m.fire("error");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    expect(m.el.state).toBe("offline");
    vi.restoreAllMocks();
  });

  test("test_player_play_rejection_not_allowed_returns_to_idle", async () => {
    const m = mount({ src: "a.mp3" });
    Object.defineProperty(m.audio, "play", {
      value: () => Promise.reject(new DOMException("blocked", "NotAllowedError")),
    });
    m.q(".play").click();
    await flush();
    expect(m.el.state).toBe("idle");
    Object.defineProperty(m.audio, "play", {
      value: () => Promise.reject(new DOMException("bad", "NotSupportedError")),
    });
    m.q(".play").click();
    await flush();
    expect(m.el.state).toBe("error");
  });

  test("test_player_replay_after_end_restarts_at_zero", () => {
    const m = mount({ src: "a.mp3" });
    m.audio.currentTime = 50;
    m.fire("ended");
    m.q(".play").click();
    expect(m.audio.currentTime).toBe(0);
    expect(m.el.state).toBe("playing");
  });
});

describe("keyboard", () => {
  test("test_player_keyboard_k_and_space_toggle", () => {
    const m = mount({ src: "a.mp3" });
    const k = keydown(m, "k", ".wave");
    expect(k.defaultPrevented).toBe(true);
    expect(m.el.state).toBe("playing");
    keydown(m, " ", ".wave");
    expect(m.el.state).toBe("paused");
  });

  test("test_player_keyboard_space_on_button_left_to_native_click", () => {
    const m = mount({ src: "a.mp3" });
    const ev = keydown(m, " ", ".play");
    expect(ev.defaultPrevented).toBe(false);
    expect(m.el.state).toBe("idle");
  });

  test("test_player_keyboard_arrows_seek_5s_and_clamp", () => {
    const m = mount({ src: "a.mp3" });
    m.audio.currentTime = 20;
    keydown(m, "ArrowRight", ".wave");
    expect(m.audio.currentTime).toBe(25);
    keydown(m, "ArrowLeft", ".wave");
    keydown(m, "ArrowLeft", ".wave");
    expect(m.audio.currentTime).toBe(15);
    m.audio.currentTime = 2;
    keydown(m, "ArrowLeft", ".wave");
    expect(m.audio.currentTime).toBe(0);
    keydown(m, "End", ".wave");
    expect(m.audio.currentTime).toBe(100);
    keydown(m, "Home", ".wave");
    expect(m.audio.currentTime).toBe(0);
    keydown(m, "Home", ".play");
    keydown(m, "End", ".play");
  });

  test("test_player_keyboard_ignores_modifiers_and_unknown_keys", () => {
    const m = mount({ src: "a.mp3" });
    const ev = new KeyboardEvent("keydown", {
      key: "k",
      ctrlKey: true,
      bubbles: true,
      composed: true,
    });
    m.q(".wave").dispatchEvent(ev);
    expect(m.el.state).toBe("idle");
    expect(keydown(m, "ArrowDown", ".wave").defaultPrevented).toBe(false);
  });

  test("test_player_keyboard_c_and_l_ignored_without_captions_or_tracks", () => {
    const m = mount({ src: "a.mp3" });
    expect(keydown(m, "c", ".wave").defaultPrevented).toBe(false);
    expect(keydown(m, "l", ".wave").defaultPrevented).toBe(false);
  });

  test("test_player_waveform_click_seeks", () => {
    const m = mount({ src: "a.mp3" });
    vi.spyOn(m.q(".wave"), "getBoundingClientRect").mockReturnValue({
      left: 0,
      width: 200,
      top: 0,
      right: 200,
      bottom: 10,
      height: 10,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    m.q(".wave").dispatchEvent(new MouseEvent("click", { clientX: 100, bubbles: true }));
    expect(m.audio.currentTime).toBe(50);
  });

  test("test_player_waveform_slider_semantics", () => {
    const m = mount({ src: "a.mp3" });
    m.audio.currentTime = 80;
    m.fire("timeupdate");
    const w = m.q(".wave");
    expect(w.getAttribute("role")).toBe("slider");
    expect(w.getAttribute("aria-valuetext")).toBe("1 minute 20 seconds of 1 minute 40 seconds");
    expect(m.q(".time").textContent).toBe("1:20 / 1:40");
  });
});

describe("captions and languages", () => {
  test("test_player_captions_toggle_shows_cue_and_persists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(VTT))),
    );
    const m = mount({ src: "a.mp3", captions: "a.vtt" });
    await flush();
    expect(m.q(".cc").hidden).toBe(false);
    expect(m.q(".cap").hidden).toBe(true);
    keydown(m, "c", ".wave");
    expect(m.q(".cc").getAttribute("aria-pressed")).toBe("true");
    expect(m.q(".cap").hidden).toBe(false);
    expect(m.q(".cap").textContent).toBe("Hello there.");
    expect(window.localStorage.getItem("as:captions")).toBe("true");
    expect(m.audio.querySelector('track[kind="captions"]')?.getAttribute("src")).toBe("a.vtt");
    const again = mount({ src: "a.mp3", captions: "a.vtt" });
    expect(again.q(".cc").getAttribute("aria-pressed")).toBe("true");
  });

  test("test_player_captions_failure_hides_toggle_without_blocking_audio", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("net"))),
    );
    const m = mount({ src: "a.mp3", captions: "a.vtt" });
    await flush();
    expect(m.q(".cc").hidden).toBe(true);
    expect(m.el.state).toBe("idle");
  });

  test("test_player_no_captions_attribute_hides_toggle", () => {
    const m = mount({ src: "a.mp3" });
    expect(m.q(".cc").hidden).toBe(true);
  });

  test("test_player_captions_labels_overridable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(VTT))),
    );
    const m = mount({
      src: "a.mp3",
      captions: "a.vtt",
      "captions-off-label": "Words",
      "captions-on-label": "Hide words",
    });
    await flush();
    expect(m.q(".cc").textContent).toBe("Words");
    m.q(".cc").click();
    expect(m.q(".cc").textContent).toBe("Hide words");
  });

  test("test_player_language_toggle_only_when_multiple_tracks", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(VTT))),
    );
    const one = mount({ src: "a.mp3", tracks: JSON.stringify([{ lang: "en", src: "a.mp3" }]) });
    expect(one.q(".lang").hidden).toBe(true);
    const two = mount({ src: "a.mp3", tracks: TRACKS });
    expect(two.q(".lang").hidden).toBe(false);
    const buttons = two.root.querySelectorAll(".lang button");
    expect([...buttons].map((b) => b.textContent)).toEqual(["EN", "HI"]);
    expect(buttons[1]?.getAttribute("aria-label")).toBe("Hindi");
  });

  test("test_player_language_switch_keeps_relative_position_and_playing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(VTT))),
    );
    const m = mount({ src: "a.mp3", tracks: TRACKS });
    const langs: string[] = [];
    m.el.addEventListener("as-language", (e) =>
      langs.push((e as CustomEvent<{ lang: string }>).detail.lang),
    );
    m.q(".play").click();
    m.audio.currentTime = 40;
    keydown(m, "l", ".wave");
    expect(m.audio.getAttribute("src")).toBe("a-hi.mp3");
    expect(m.root.querySelectorAll(".lang button")[1]?.getAttribute("aria-checked")).toBe("true");
    Object.defineProperty(m.audio, "duration", { value: 105, configurable: true });
    m.fire("loadedmetadata");
    expect(m.audio.currentTime).toBeCloseTo(42);
    expect(m.play).toHaveBeenCalledTimes(2);
    expect(langs).toEqual(["hi"]);
    expect(m.q(".cap").lang).toBe("hi");
    await flush();
    keydown(m, "l", ".wave");
    expect(m.audio.getAttribute("src")).toBe("a.mp3");
  });

  test("test_player_language_switch_restarts_when_durations_differ", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(VTT))),
    );
    const m = mount({ src: "a.mp3", tracks: TRACKS });
    m.audio.currentTime = 40;
    m.root.querySelectorAll<HTMLElement>(".lang button")[1]?.click();
    Object.defineProperty(m.audio, "duration", { value: 200, configurable: true });
    m.fire("loadedmetadata");
    expect(m.audio.currentTime).toBe(0);
    expect(m.play).not.toHaveBeenCalled();
  });
});

describe("storage and media session", () => {
  test("test_player_remembers_position_per_src", () => {
    vi.useFakeTimers();
    window.localStorage.setItem("as:pos:a.mp3", "30");
    const m = mount({ src: "a.mp3" });
    m.fire("loadedmetadata");
    expect(m.audio.currentTime).toBe(30);
    m.audio.currentTime = 44;
    vi.advanceTimersByTime(1500);
    m.fire("timeupdate");
    expect(window.localStorage.getItem("as:pos:a.mp3")).toBe("44");
    m.fire("ended");
    expect(window.localStorage.getItem("as:pos:a.mp3")).toBeNull();
  });

  test("regression_player_resume_when_metadata_loaded_before_upgrade", () => {
    // A cached file can fire loadedmetadata before the element upgrades (seen as an e2e flake).
    window.localStorage.setItem("as:pos:b.mp3", "30");
    const proto = HTMLAudioElement.prototype;
    Object.defineProperty(proto, "readyState", { get: () => 1, configurable: true });
    try {
      const m = mount({ src: "b.mp3" });
      expect(m.audio.currentTime).toBe(30);
    } finally {
      Reflect.deleteProperty(proto, "readyState");
    }
  });

  test("test_player_localstorage_blocked_still_works", () => {
    const boom = (): never => {
      throw new DOMException("blocked", "SecurityError");
    };
    vi.spyOn(MemStorage.prototype, "getItem").mockImplementation(boom);
    vi.spyOn(MemStorage.prototype, "setItem").mockImplementation(boom);
    vi.spyOn(MemStorage.prototype, "removeItem").mockImplementation(boom);
    const m = mount({ src: "a.mp3" });
    m.q(".play").click();
    m.audio.currentTime = 5;
    m.q(".play").click();
    m.fire("ended");
    expect(m.el.state).toBe("ended");
    vi.restoreAllMocks();
  });

  test("test_player_media_session_metadata_set", async () => {
    class FakeMetadata {
      constructor(public init: { title: string; artist: string }) {}
    }
    const session = { metadata: null as unknown, setActionHandler: vi.fn() };
    vi.stubGlobal("MediaMetadata", FakeMetadata);
    Object.defineProperty(navigator, "mediaSession", { value: session, configurable: true });
    const m = mount({ src: "a.mp3", label: "Letter", artist: "Dad" });
    m.q(".play").click();
    await flush();
    expect((session.metadata as FakeMetadata).init).toEqual({ title: "Letter", artist: "Dad" });
    expect(session.setActionHandler).toHaveBeenCalledWith("play", expect.any(Function));
    const calls = session.setActionHandler.mock.calls as [string, () => void][];
    m.audio.currentTime = 10;
    calls.find((c) => c[0] === "seekforward")?.[1]();
    expect(m.audio.currentTime).toBe(15);
    calls.find((c) => c[0] === "seekbackward")?.[1]();
    calls.find((c) => c[0] === "pause")?.[1]();
    expect(m.el.state).toBe("paused");
    calls.find((c) => c[0] === "play")?.[1]();
    Reflect.deleteProperty(navigator, "mediaSession");
  });
});

describe("format helpers and network", () => {
  test("test_player_time_format", () => {
    expect(formatTime(252)).toBe("4:12");
    expect(formatTime(Number.NaN)).toBe("--:--");
    expect(spokenTime(80)).toBe("1 minute 20 seconds");
    expect(spokenTime(1)).toBe("1 second");
    expect(spokenTime(120)).toBe("2 minutes");
  });

  test("test_player_no_external_network_requests", async () => {
    const fetchSpy = vi.fn(() => Promise.resolve(new Response(VTT)));
    vi.stubGlobal("fetch", fetchSpy);
    mount({ src: "a.mp3", captions: "a.vtt" });
    await flush();
    expect(fetchSpy.mock.calls.map((c) => (c as unknown[])[0])).toEqual(["a.vtt"]);
    const dir = join(import.meta.dirname, "../src");
    for (const f of readdirSync(dir)) {
      const text = readFileSync(join(dir, f), "utf8");
      expect(text, f).not.toMatch(/https?:\/\//);
      expect(text, f).not.toMatch(/XMLHttpRequest|sendBeacon|WebSocket/);
    }
  });

  test("test_player_no_autoplay_on_connect", () => {
    const m = mount({ src: "a.mp3" });
    expect(m.play).not.toHaveBeenCalled();
    expect(m.audio.hasAttribute("autoplay")).toBe(false);
  });

  test("test_player_debug_attribute_logs_state_transitions", () => {
    const dbg = vi.spyOn(console, "debug").mockImplementation(() => undefined);
    const m = mount({ src: "a.mp3", debug: "" });
    m.q(".play").click();
    expect(dbg).toHaveBeenCalled();
    dbg.mockRestore();
  });

  test("test_player_disconnect_saves_position_and_cleans_up", () => {
    const m = mount({ src: "a.mp3" });
    m.audio.currentTime = 12;
    m.el.remove();
    expect(window.localStorage.getItem("as:pos:a.mp3")).toBe("12");
  });
});
