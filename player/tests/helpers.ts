import { vi, type Mock } from "vitest";
import "../src/index";
import type { AudioSmithPlayer } from "../src/player";

export interface Mounted {
  el: AudioSmithPlayer;
  audio: HTMLAudioElement;
  play: Mock;
  root: ShadowRoot;
  q: (sel: string) => HTMLElement;
  fire: (type: string) => void;
}

/** Mount a player with a light DOM <audio> and a stubbed media API (no network, no media decode). */
export function mount(attrs: Record<string, string> = {}, withAudio = true): Mounted {
  document.body.innerHTML = "";
  const el = document.createElement("audio-smith-player") as AudioSmithPlayer;
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (withAudio) {
    const a = document.createElement("audio");
    a.setAttribute("controls", "");
    if (attrs["src"]) a.setAttribute("src", attrs["src"]);
    el.append(a);
  }
  const audio = el.querySelector("audio") ?? document.createElement("audio");
  const play = vi.fn(() => {
    Object.defineProperty(audio, "paused", { value: false, configurable: true });
    audio.dispatchEvent(new Event("play"));
    audio.dispatchEvent(new Event("playing"));
    return Promise.resolve();
  });
  const pause = vi.fn(() => {
    Object.defineProperty(audio, "paused", { value: true, configurable: true });
    audio.dispatchEvent(new Event("pause"));
  });
  Object.defineProperty(audio, "play", { value: play, configurable: true });
  Object.defineProperty(audio, "pause", { value: pause, configurable: true });
  Object.defineProperty(audio, "load", { value: vi.fn(), configurable: true });
  Object.defineProperty(audio, "paused", { value: true, configurable: true });
  Object.defineProperty(audio, "duration", { value: 100, configurable: true });
  document.body.append(el);
  const root = el.shadowRoot as ShadowRoot;
  return {
    el,
    audio,
    play,
    root,
    q: (sel) => root.querySelector(sel) as HTMLElement,
    fire: (t) => audio.dispatchEvent(new Event(t)),
  };
}

export async function flush(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
}
