import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { useMedia } from "../hooks";
import type { Track } from "../types";

declare module "preact" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "audio-smith-player": JSX.IntrinsicElements["div"] & {
        src: string;
        captions?: string;
        peaks?: string;
        label?: string;
      };
    }
  }
}

export const PLAYER_SCRIPT = "/player/audio-smith-player.js";
export type PlayerState = "loading" | "ready" | "missing";

let playerLoad: Promise<boolean> | null = null;

/** Load the built player once. Resolves false when the script is missing. */
export function loadPlayer(): Promise<boolean> {
  if (customElements.get("audio-smith-player")) return Promise.resolve(true);
  playerLoad ??= new Promise<boolean>((resolve) => {
    const s = document.createElement("script");
    s.type = "module";
    s.src = PLAYER_SCRIPT;
    s.onload = () => {
      resolve(true);
    };
    s.onerror = () => {
      playerLoad = null;
      resolve(false);
    };
    document.head.append(s);
  });
  return playerLoad;
}

interface Props {
  track: Track | null;
  busy: boolean;
  onMaster: () => void;
}

export function MasterPreview({ track, busy, onMaster }: Props) {
  const [player, setPlayer] = useState<PlayerState>("loading");
  const audio = useMedia(track?.url ?? null);
  const captions = useMedia(track?.captions_url ?? null);
  useEffect(() => {
    let live = true;
    void loadPlayer().then((ok) => {
      if (live) setPlayer(ok ? "ready" : "missing");
    });
    return () => {
      live = false;
    };
  }, []);

  let body: JSX.Element;
  if (!track) {
    body = <p>Master not built yet. Build it from the selected takes.</p>;
  } else if (audio.error !== null) {
    body = <p role="alert">{audio.error}</p>;
  } else if (audio.src === null) {
    body = <p role="status">Loading master audio</p>;
  } else {
    const peaks = track.peaks.join(",");
    body = (
      <>
        <audio-smith-player
          src={audio.src}
          label="Listen to the master"
          {...(captions.src === null ? {} : { captions: captions.src })}
          {...(peaks === "" ? {} : { peaks })}
        >
          <audio controls src={audio.src} aria-label="Master audio" />
        </audio-smith-player>
        <p class="muted" role="status">
          {player === "missing"
            ? "Full player not available. Using the basic audio control."
            : player === "loading"
              ? "Loading player"
              : "Full player loaded."}
        </p>
        <dl class="facts">
          <dt>Duration</dt>
          <dd>{track.duration_s.toFixed(1)} s</dd>
          <dt>Loudness</dt>
          <dd>{track.loudness_lufs.toFixed(1)} LUFS (target -16)</dd>
        </dl>
      </>
    );
  }
  return (
    <section aria-labelledby="master-h" class="panel">
      <h2 id="master-h">Master preview</h2>
      {body}
      <button type="button" class="btn btn-primary" onClick={onMaster} disabled={busy}>
        {busy ? "Building master" : track ? "Rebuild master" : "Build master"}
      </button>
    </section>
  );
}
