import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Build the player when player/dist is missing so `make e2e` works from a clean checkout. */
export default function globalSetup(): void {
  const player = fileURLToPath(new URL("../../player", import.meta.url));
  if (existsSync(`${player}/dist/audio-smith-player.js`)) return;
  execFileSync("npm", ["ci"], { cwd: player, stdio: "inherit" });
  execFileSync("npm", ["run", "build"], { cwd: player, stdio: "inherit" });
}
