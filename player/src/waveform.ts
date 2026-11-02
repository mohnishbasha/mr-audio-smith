/** The 28-bar breathing waveform (DESIGN.md section 5). */
export const BAR_COUNT = 28;

/** Parse the `peaks` attribute. Returns null when missing or malformed (flat bar fallback). */
export function parsePeaks(raw: string | null): number[] | null {
  if (raw === null) return null;
  const parts = raw.split(",");
  if (parts.length !== BAR_COUNT) return null;
  const out: number[] = [];
  for (const part of parts) {
    const text = part.trim();
    if (!/^\d{1,3}$/.test(text)) return null;
    const n = Number(text);
    if (n > 100) return null;
    out.push(n);
  }
  return out;
}

/** Bar height in px: 8 + (value / 100) * 24. */
export function barHeight(value: number): number {
  return 8 + (value / 100) * 24;
}

export interface Waveform {
  readonly el: HTMLElement;
  setPeaks(peaks: number[] | null): void;
  update(progress: number, playing: boolean): void;
}

export function createWaveform(): Waveform {
  const el = document.createElement("div");
  el.className = "wave";
  let bars: HTMLElement[] = [];
  let fill: HTMLElement | null = null;

  const setPeaks = (peaks: number[] | null): void => {
    el.textContent = "";
    bars = [];
    fill = null;
    if (peaks === null) {
      const flat = document.createElement("span");
      flat.className = "flat";
      fill = document.createElement("span");
      fill.className = "fill";
      flat.append(fill);
      el.append(flat);
      return;
    }
    for (const value of peaks) {
      const bar = document.createElement("span");
      bar.className = "bar";
      bar.style.height = `calc(${barHeight(value)}px * var(--_scale, 1))`;
      bars.push(bar);
      el.append(bar);
    }
  };

  const update = (progress: number, playing: boolean): void => {
    const p = Math.min(1, Math.max(0, Number.isFinite(progress) ? progress : 0));
    el.toggleAttribute("data-playing", playing);
    if (fill) fill.style.width = `${p * 100}%`;
    const head = p >= 1 ? -1 : Math.min(BAR_COUNT - 1, Math.floor(p * BAR_COUNT));
    bars.forEach((bar, i) => {
      bar.classList.toggle("on", p >= 1 || i < head);
      bar.classList.toggle("head", i === head);
    });
  };

  setPeaks(null);
  return { el, setPeaks, update };
}
