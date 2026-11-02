import { AudioSmithPlayer } from "./player";

export { AudioSmithPlayer } from "./player";

export function defineAudioSmithPlayer(): void {
  if (!customElements.get("audio-smith-player")) {
    customElements.define("audio-smith-player", AudioSmithPlayer);
  }
}

defineAudioSmithPlayer();
