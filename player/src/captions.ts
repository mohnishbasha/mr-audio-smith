/** WebVTT parsing and cue lookup for the CaptionLine. */
export interface Cue {
  start: number;
  end: number;
  text: string;
}

const TIME = /(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})/;

function toSeconds(text: string): number | null {
  const m = TIME.exec(text);
  if (!m) return null;
  const [, h, min, sec, ms] = m;
  return (
    Number(h ?? 0) * 3600 +
    Number(min) * 60 +
    Number(sec) +
    Number((ms ?? "0").padEnd(3, "0")) / 1000
  );
}

export function parseVtt(source: string): Cue[] {
  const cues: Cue[] = [];
  for (const block of source.replace(/\r\n?/g, "\n").split(/\n{2,}/)) {
    const lines = block.split("\n");
    const at = lines.findIndex((l) => l.includes("-->"));
    const timing = lines[at];
    if (at < 0 || timing === undefined) continue;
    const [a, b] = timing.split("-->");
    const start = toSeconds(a ?? "");
    const end = toSeconds(b ?? "");
    if (start === null || end === null) continue;
    const text = lines
      .slice(at + 1)
      .join(" ")
      .replace(/<[^>]*>/g, "")
      .replace(/\s+/g, " ")
      .trim();
    cues.push({ start, end, text });
  }
  return cues;
}

/** Index of the cue active at time t, or -1. */
export function activeCueIndex(cues: readonly Cue[], t: number): number {
  return cues.findIndex((c) => t >= c.start && t < c.end);
}

export async function fetchCues(url: string): Promise<Cue[]> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`captions ${res.status}`);
  return parseVtt(await res.text());
}
