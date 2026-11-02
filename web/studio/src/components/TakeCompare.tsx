import { useMedia } from "../hooks";
import type { Chunk, Take } from "../types";

export const LOW_SIMILARITY = 0.75;

function TakeCard({
  label,
  take,
  kept,
  busy,
  onKeep,
}: {
  label: string;
  take: Take;
  kept: boolean;
  busy: boolean;
  onKeep: () => void;
}) {
  const media = useMedia(take.url);
  const low = take.similarity !== null && take.similarity < LOW_SIMILARITY;
  return (
    <section class={`take${kept ? " kept" : ""}`} aria-label={`Take ${label}`}>
      <h3>
        Take {label} {kept && <span class="pill pill-approved">Kept</span>}
      </h3>
      {media.src === null && media.error === null && <p role="status">Loading audio</p>}
      {media.error !== null && <p role="alert">{media.error}</p>}
      {media.src !== null && <audio controls src={media.src} aria-label={`Play take ${label}`} />}
      <dl class="facts">
        <dt>Similarity</dt>
        <dd>{take.similarity === null ? "not scored" : take.similarity.toFixed(2)}</dd>
        <dt>Duration</dt>
        <dd>{(take.duration_ms / 1000).toFixed(1)} s</dd>
        <dt>Seed</dt>
        <dd>{take.seed}</dd>
      </dl>
      {low && <p class="note">Low similarity. Below the {LOW_SIMILARITY.toFixed(2)} threshold.</p>}
      <button type="button" class="btn" disabled={kept || busy} onClick={onKeep}>
        {kept ? "Kept" : "Keep this take"}
      </button>
    </section>
  );
}

interface Props {
  chunk: Chunk;
  busy: boolean;
  rendering: boolean;
  onKeep: (take: number) => void;
  onRerender: () => void;
}

export function TakeCompare({ chunk, busy, rendering, onKeep, onRerender }: Props) {
  const takes = [...chunk.takes].sort((a, b) => a.take - b.take);
  return (
    <section aria-labelledby="takes-h" class="panel">
      <h2 id="takes-h">Takes</h2>
      {takes.length === 0 && <p>No takes yet. Render a take to hear this chunk.</p>}
      {takes.length === 1 && <p class="muted">One take. Render another to compare.</p>}
      <div class="takes">
        {takes.map((t, i) => (
          <TakeCard
            key={t.take}
            label={String.fromCharCode(65 + i)}
            take={t}
            kept={chunk.selected_take === t.take}
            busy={busy}
            onKeep={() => {
              onKeep(t.take);
            }}
          />
        ))}
      </div>
      {takes.length > 0 && (
        <button type="button" class="btn" onClick={onRerender} disabled={rendering}>
          Re-render with new seed
        </button>
      )}
    </section>
  );
}
