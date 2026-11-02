import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { AudioSmithClient, resolveConfig, type ClientConfig } from "./client.ts";
import { registerCommands } from "./commands.ts";
import { createTools, type PollingOptions } from "./tools.ts";

export const CONTEXT_MESSAGE_TYPE = "mr-audio-smith-context";

export interface ExtensionOptions {
  config?: Partial<ClientConfig>;
  fetch?: (input: string, init?: RequestInit) => Promise<Response>;
  polling?: PollingOptions;
}

/** Build the context text; returns undefined when nothing is available. */
export async function buildContext(client: AudioSmithClient): Promise<string | undefined> {
  try {
    const [voices, profiles] = await Promise.all([client.listVoices(), client.listProfiles()]);
    const v = voices.map((x) => `${x.id}${x.cloned ? " (cloned)" : ""}`).join(", ") || "none";
    const p = profiles.map((x) => x.id).join(", ") || "none";
    return (
      "mr-audio-smith is available for narrating pages (tool mr_audio_smith_narrate).\n" +
      `Voices: ${v}\nProfiles: ${p}\n` +
      "Cloning needs a voice registered on the server with a consent record."
    );
  } catch {
    return undefined; // fail soft: the server may simply be down
  }
}

export function createExtension(options: ExtensionOptions = {}): (pi: ExtensionAPI) => void {
  return (pi) => {
    const config = resolveConfig(process.env, options.config);
    const client = new AudioSmithClient(config, options.fetch);
    for (const tool of createTools(client, options.polling)) pi.registerTool(tool);
    registerCommands(pi, client, options.polling);
    pi.on("session_start", async () => {
      const content = await buildContext(client);
      if (content === undefined) return;
      pi.sendMessage(
        { customType: CONTEXT_MESSAGE_TYPE, content, display: false },
        { triggerTurn: false },
      );
    });
  };
}

export default createExtension();
