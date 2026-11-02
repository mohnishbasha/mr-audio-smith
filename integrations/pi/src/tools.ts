import type { AgentToolResult, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import type { Static } from "typebox";
import {
  AudioSmithClient,
  AudioSmithError,
  type JobRequest,
  type JobView,
  type Manifest,
} from "./client.ts";

const CONSENT_NOTE =
  "Voice cloning needs a voice already registered on the server with a consent record; " +
  "unregistered voices are refused.";

const REF = "^[A-Za-z0-9][A-Za-z0-9._@-]{0,79}$";

export const NarrateParams = Type.Object({
  source: Type.String({
    minLength: 1,
    maxLength: 2048,
    description: "URL, or a path the server can read, of the page or document to narrate",
  }),
  profile: Type.Optional(Type.String({ pattern: REF, description: "Narration profile id" })),
  voice: Type.Optional(
    Type.String({ pattern: REF, description: "Registered voice id (cloned voices need consent)" }),
  ),
  backend: Type.Optional(Type.String({ pattern: REF, description: "TTS backend id" })),
  langs: Type.Optional(
    Type.Array(Type.String({ pattern: "^[a-z]{2,3}$" }), {
      maxItems: 16,
      description: 'Language codes for extra tracks, for example ["es"]',
    }),
  ),
});
export const EmptyParams = Type.Object({});
export const StatusParams = Type.Object({
  job_id: Type.Optional(
    Type.String({ minLength: 1, description: "Job id; omit to check server health" }),
  ),
});

export type NarrateArgs = Static<typeof NarrateParams>;
export type StatusArgs = Static<typeof StatusParams>;

export interface ProgressDetails {
  job_id?: string;
  stage?: string | null;
  percent?: number;
  chunk?: number;
  chunks_total?: number;
}

function text(body: string, details: ProgressDetails = {}): AgentToolResult<ProgressDetails> {
  return { content: [{ type: "text", text: body }], details };
}

export function formatProgress(job: JobView): string {
  const stage = job.stage ?? job.status;
  const pct = Math.round(
    job.progress.stage_pct <= 1 ? job.progress.stage_pct * 100 : job.progress.stage_pct,
  );
  const { chunk, chunks_total: total } = job.progress;
  const chunks =
    typeof chunk === "number" && typeof total === "number"
      ? `, chunk ${String(chunk)} of ${String(total)}`
      : "";
  return `${stage}: ${String(pct)}%${chunks}`;
}

function progressDetails(job: JobView): ProgressDetails {
  const d: ProgressDetails = {
    job_id: job.job_id,
    stage: job.stage,
    percent: Math.round(
      job.progress.stage_pct <= 1 ? job.progress.stage_pct * 100 : job.progress.stage_pct,
    ),
  };
  if (typeof job.progress.chunk === "number") d.chunk = job.progress.chunk;
  if (typeof job.progress.chunks_total === "number") d.chunks_total = job.progress.chunks_total;
  return d;
}

export function summarizeManifest(jobId: string, m: Manifest): string {
  const lines = [`Narration complete (job ${jobId}): ${m.title || m.source}`];
  for (const t of m.tracks) {
    lines.push(`- ${t.lang} ${t.kind}: ${t.file} (${t.duration_s.toFixed(1)} s)`);
  }
  if (m.warnings.length > 0) {
    lines.push("Warnings:", ...m.warnings.map((w) => `- ${w}`));
  }
  return lines.join("\n");
}

export interface NarrateRun {
  jobId: string;
  manifest: Manifest;
  summary: string;
}

/** Submit a narration job, report progress, and return the manifest summary. */
export async function runNarrate(
  client: AudioSmithClient,
  args: NarrateArgs,
  opts: {
    signal?: AbortSignal | undefined;
    onProgress?: ((job: JobView) => void) | undefined;
    intervalMs?: number;
    sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  } = {},
): Promise<NarrateRun> {
  const req: JobRequest = { source: args.source };
  if (args.profile !== undefined) req.profile = args.profile;
  if (args.voice !== undefined) req.voice = args.voice;
  if (args.backend !== undefined) req.backend = args.backend;
  if (args.langs !== undefined) req.langs = args.langs;
  const jobId = await client.submitJob(req, opts.signal);
  const wait: Parameters<AudioSmithClient["waitForJob"]>[1] = {
    signal: opts.signal,
    onProgress: opts.onProgress,
  };
  if (opts.intervalMs !== undefined) wait.intervalMs = opts.intervalMs;
  if (opts.sleep !== undefined) wait.sleep = opts.sleep;
  await client.waitForJob(jobId, wait);
  const manifest = await client.getManifest(jobId, opts.signal);
  return { jobId, manifest, summary: summarizeManifest(jobId, manifest) };
}

function describeError(err: unknown): string {
  return err instanceof AudioSmithError
    ? err.message
    : err instanceof Error
      ? err.message
      : String(err);
}

export interface PollingOptions {
  intervalMs?: number;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
}

export function createTools(
  client: AudioSmithClient,
  polling: PollingOptions = {},
): ToolDefinition[] {
  const narrate: ToolDefinition<typeof NarrateParams, ProgressDetails> = {
    name: "mr_audio_smith_narrate",
    label: "Narrate",
    description:
      "Narrate a web page or document into audio tracks with captions using the mr-audio-smith server. " +
      "Long running: streams stage, percent and chunk progress, then returns the tracks with durations and warnings. " +
      CONSENT_NOTE,
    promptSnippet: "mr_audio_smith_narrate: turn a URL into narrated audio tracks",
    parameters: NarrateParams,
    async execute(_id, params, signal, onUpdate) {
      const run = await runNarrate(client, params, {
        signal,
        ...polling,
        onProgress: (job) => {
          onUpdate?.(text(formatProgress(job), progressDetails(job)));
        },
      });
      return text(run.summary, { job_id: run.jobId });
    },
  };

  const listVoices: ToolDefinition<typeof EmptyParams, ProgressDetails> = {
    name: "mr_audio_smith_list_voices",
    label: "List voices",
    description: `List voices registered on the server. ${CONSENT_NOTE}`,
    parameters: EmptyParams,
    async execute(_id, _params, signal) {
      const voices = await client.listVoices(signal);
      if (voices.length === 0) return text("No voices registered.");
      return text(
        voices
          .map(
            (v) =>
              `- ${v.id} (${v.display_name}) backends: ${v.backends.join(", ")}${v.cloned ? " [cloned]" : ""}`,
          )
          .join("\n"),
      );
    },
  };

  const listProfiles: ToolDefinition<typeof EmptyParams, ProgressDetails> = {
    name: "mr_audio_smith_list_profiles",
    label: "List profiles",
    description: "List narration profiles available on the server.",
    parameters: EmptyParams,
    async execute(_id, _params, signal) {
      const profiles = await client.listProfiles(signal);
      if (profiles.length === 0) return text("No profiles available.");
      return text(profiles.map((p) => `- ${p.id}@${p.version}: ${p.description}`).join("\n"));
    },
  };

  const listBackends: ToolDefinition<typeof EmptyParams, ProgressDetails> = {
    name: "mr_audio_smith_list_backends",
    label: "List backends",
    description: "List TTS backends with availability, languages, cloning support and license.",
    parameters: EmptyParams,
    async execute(_id, _params, signal) {
      const backends = await client.listBackends(signal);
      if (backends.length === 0) return text("No backends available.");
      return text(
        backends
          .map(
            (b) =>
              `- ${b.id}: ${b.available ? "available" : "unavailable"}, languages ${b.languages.join(", ")}, ` +
              `cloning ${b.cloning ? "yes" : "no"}, license ${b.license}`,
          )
          .join("\n"),
      );
    },
  };

  const status: ToolDefinition<typeof StatusParams, ProgressDetails> = {
    name: "mr_audio_smith_status",
    label: "Status",
    description:
      "Report a narration job's status (pass job_id) or, without job_id, the server's health and readiness.",
    parameters: StatusParams,
    async execute(_id, params, signal) {
      if (params.job_id !== undefined) {
        const job = await client.getJob(params.job_id, signal);
        const err = job.error === null ? "" : `\nerror: ${JSON.stringify(job.error)}`;
        return text(
          `job ${job.job_id} is ${job.status}; ${formatProgress(job)}${err}`,
          progressDetails(job),
        );
      }
      const s = await client.serverStatus(signal);
      return text(`server healthy: ${String(s.healthy)}; ready: ${String(s.ready)} (${s.detail})`);
    },
  };

  return [narrate, listVoices, listProfiles, listBackends, status] as unknown as ToolDefinition[];
}

export { describeError };
