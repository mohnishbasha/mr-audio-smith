import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { AudioSmithClient } from "./client.ts";
import { describeError, formatProgress, runNarrate, type PollingOptions } from "./tools.ts";

export interface NarrateCommandArgs {
  source: string;
  profile?: string;
  voice?: string;
}

/** Parse `<url> [profile] [voice]`; returns undefined when the URL is missing. */
export function parseNarrateArgs(args: string): NarrateCommandArgs | undefined {
  const [source, profile, voice] = args.trim().split(/\s+/);
  if (source === undefined || source === "") return undefined;
  const out: NarrateCommandArgs = { source };
  if (profile !== undefined) out.profile = profile;
  if (voice !== undefined) out.voice = voice;
  return out;
}

export function registerCommands(
  pi: Pick<ExtensionAPI, "registerCommand">,
  client: AudioSmithClient,
  polling: PollingOptions = {},
): void {
  pi.registerCommand("narrate", {
    description: "Narrate a page: /narrate <url> [profile] [voice]",
    async handler(args: string, ctx: ExtensionCommandContext) {
      const parsed = parseNarrateArgs(args);
      if (parsed === undefined) {
        ctx.ui.notify("usage: /narrate <url> [profile] [voice]", "warning");
        return;
      }
      let last = "";
      try {
        const run = await runNarrate(client, parsed, {
          signal: ctx.signal,
          ...polling,
          onProgress: (job) => {
            const line = formatProgress(job);
            if (line !== last) {
              last = line;
              ctx.ui.notify(line, "info");
            }
          },
        });
        ctx.ui.notify(run.summary, "info");
      } catch (err) {
        ctx.ui.notify(`narrate failed: ${describeError(err)}`, "error");
      }
    },
  });

  pi.registerCommand("voices", {
    description: "List voices and profiles on the mr-audio-smith server",
    async handler(_args: string, ctx: ExtensionCommandContext) {
      try {
        const [voices, profiles] = await Promise.all([client.listVoices(), client.listProfiles()]);
        const v = voices.map((x) => `${x.id}${x.cloned ? " (cloned)" : ""}`).join(", ") || "none";
        const p = profiles.map((x) => x.id).join(", ") || "none";
        ctx.ui.notify(`voices: ${v}\nprofiles: ${p}`, "info");
      } catch (err) {
        ctx.ui.notify(`voices unavailable: ${describeError(err)}`, "error");
      }
    },
  });

  pi.registerCommand("audio-status", {
    description: "Show mr-audio-smith server status, or a job: /audio-status [job_id]",
    async handler(args: string, ctx: ExtensionCommandContext) {
      const id = args.trim();
      try {
        if (id !== "") {
          const job = await client.getJob(id);
          ctx.ui.notify(`job ${job.job_id} is ${job.status}; ${formatProgress(job)}`, "info");
          return;
        }
        const s = await client.serverStatus();
        ctx.ui.notify(
          `server ${client.baseUrl}: healthy ${String(s.healthy)}, ready ${String(s.ready)} (${s.detail})`,
          "info",
        );
      } catch (err) {
        ctx.ui.notify(`status unavailable: ${describeError(err)}`, "error");
      }
    },
  });
}
