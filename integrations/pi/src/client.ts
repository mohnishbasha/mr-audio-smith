/** Typed REST client for the mr-audio-smith server (ARCHITECTURE 6.3). */

export const DEFAULT_SERVER_URL = "http://127.0.0.1:8765";

export interface ClientConfig {
  baseUrl: string;
  token?: string;
}

export interface Env {
  [key: string]: string | undefined;
}

export interface JobRequest {
  source: string;
  profile?: string;
  voice?: string;
  backend?: string;
  langs?: string[];
}

export interface Progress {
  stage_pct: number;
  chunk?: number | null;
  chunks_total?: number | null;
}

export interface JobView {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  stage: string | null;
  progress: Progress;
  created_at: string;
  error: Record<string, unknown> | null;
}

export interface Track {
  lang: string;
  kind: string;
  file: string;
  duration_s: number;
}

export interface Manifest {
  title: string;
  source: string;
  voice_id: string;
  tracks: Track[];
  warnings: string[];
}

export interface VoiceSummary {
  id: string;
  display_name: string;
  backends: string[];
  cloned: boolean;
}

export interface ProfileSummary {
  id: string;
  version: string;
  description: string;
}

export interface BackendSummary {
  id: string;
  available: boolean;
  languages: string[];
  cloning: boolean;
  license: string;
}

export interface ServerStatus {
  healthy: boolean;
  ready: boolean;
  detail: string;
}

/** Resolve configuration from the environment, with explicit overrides winning. */
export function resolveConfig(env: Env, overrides: Partial<ClientConfig> = {}): ClientConfig {
  const baseUrl = overrides.baseUrl ?? env["AUDIO_SMITH_SERVER_URL"] ?? DEFAULT_SERVER_URL;
  const token = overrides.token ?? env["AUDIO_SMITH_SERVER_TOKEN"];
  const config: ClientConfig = { baseUrl: baseUrl.replace(/\/+$/, "") };
  if (token !== undefined && token !== "") config.token = token;
  return config;
}

/** An error response (problem+json) or a transport failure, rendered readably. */
export class AudioSmithError extends Error {
  readonly code: string;
  readonly status: number;
  readonly hint: string | undefined;

  constructor(code: string, status: number, detail: string, hint?: string) {
    super(hint === undefined || hint === "" ? detail : `${detail} (hint: ${hint})`);
    this.name = "AudioSmithError";
    this.code = code;
    this.status = status;
    this.hint = hint;
  }
}

export interface WaitOptions {
  signal?: AbortSignal | undefined;
  onProgress?: ((job: JobView) => void) | undefined;
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
}

type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

export function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted === true) {
      reject(new AudioSmithError("aborted", 0, "request aborted"));
      return;
    }
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(new AudioSmithError("aborted", 0, "request aborted"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export class AudioSmithClient {
  private readonly config: ClientConfig;
  private readonly fetchFn: FetchFn;

  constructor(config: ClientConfig, fetchFn?: FetchFn) {
    this.config = config;
    this.fetchFn = fetchFn ?? ((input, init) => fetch(input, init));
  }

  get baseUrl(): string {
    return this.config.baseUrl;
  }

  private async request(
    method: string,
    path: string,
    opts: { body?: unknown; signal?: AbortSignal | undefined } = {},
  ): Promise<unknown> {
    const headers: Record<string, string> = {
      accept: "application/json, application/problem+json",
    };
    if (this.config.token !== undefined) headers["authorization"] = `Bearer ${this.config.token}`;
    const init: RequestInit = { method, headers };
    if (opts.body !== undefined) {
      headers["content-type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    if (opts.signal !== undefined) init.signal = opts.signal;
    let res: Response;
    try {
      res = await this.fetchFn(`${this.config.baseUrl}${path}`, init);
    } catch (err) {
      if (opts.signal?.aborted === true) throw new AudioSmithError("aborted", 0, "request aborted");
      const reason = err instanceof Error ? err.message : String(err);
      throw new AudioSmithError(
        "unreachable",
        0,
        `cannot reach the mr-audio-smith server at ${this.config.baseUrl}: ${reason}`,
        "start it with `mr-audio-smith serve` or set AUDIO_SMITH_SERVER_URL",
      );
    }
    const text = await res.text();
    let data: unknown;
    try {
      data = text === "" ? null : (JSON.parse(text) as unknown);
    } catch {
      data = null;
    }
    if (!res.ok) throw this.toError(res.status, data, text);
    return data;
  }

  private toError(status: number, data: unknown, text: string): AudioSmithError {
    if (isRecord(data)) {
      const code = str(data["code"]) ?? str(data["title"]) ?? `http_${String(status)}`;
      const detail = str(data["detail"]) ?? `server returned HTTP ${String(status)}`;
      return new AudioSmithError(code, status, `${code}: ${detail}`, str(data["hint"]));
    }
    if (status === 401 || status === 403) {
      return new AudioSmithError(
        "unauthorized",
        status,
        "the server rejected the token",
        "set AUDIO_SMITH_SERVER_TOKEN",
      );
    }
    const snippet = text.slice(0, 200);
    return new AudioSmithError(
      `http_${String(status)}`,
      status,
      `server returned HTTP ${String(status)} ${snippet}`.trim(),
    );
  }

  async submitJob(req: JobRequest, signal?: AbortSignal): Promise<string> {
    const data = await this.request("POST", "/v1/jobs", { body: req, signal });
    const id = isRecord(data) ? str(data["job_id"]) : undefined;
    if (id === undefined)
      throw new AudioSmithError("bad_response", 0, "server did not return a job_id");
    return id;
  }

  async getJob(id: string, signal?: AbortSignal): Promise<JobView> {
    const data = await this.request("GET", `/v1/jobs/${encodeURIComponent(id)}`, { signal });
    if (!isRecord(data) || str(data["status"]) === undefined) {
      throw new AudioSmithError("bad_response", 0, "malformed job status");
    }
    return data as unknown as JobView;
  }

  async getManifest(id: string, signal?: AbortSignal): Promise<Manifest> {
    const data = await this.request("GET", `/v1/jobs/${encodeURIComponent(id)}/manifest`, {
      signal,
    });
    if (!isRecord(data) || !Array.isArray(data["tracks"])) {
      throw new AudioSmithError("bad_response", 0, "malformed manifest");
    }
    return {
      title: str(data["title"]) ?? "",
      source: str(data["source"]) ?? "",
      voice_id: str(data["voice_id"]) ?? "",
      tracks: data["tracks"] as Track[],
      warnings: Array.isArray(data["warnings"]) ? (data["warnings"] as string[]) : [],
    };
  }

  private async list<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const data = await this.request("GET", path, { signal });
    if (!Array.isArray(data))
      throw new AudioSmithError("bad_response", 0, `malformed response from ${path}`);
    return data as T[];
  }

  listVoices(signal?: AbortSignal): Promise<VoiceSummary[]> {
    return this.list<VoiceSummary>("/v1/voices", signal);
  }

  listProfiles(signal?: AbortSignal): Promise<ProfileSummary[]> {
    return this.list<ProfileSummary>("/v1/profiles", signal);
  }

  listBackends(signal?: AbortSignal): Promise<BackendSummary[]> {
    return this.list<BackendSummary>("/v1/backends", signal);
  }

  async serverStatus(signal?: AbortSignal): Promise<ServerStatus> {
    await this.request("GET", "/healthz", { signal });
    try {
      await this.request("GET", "/readyz", { signal });
      return { healthy: true, ready: true, detail: "ready" };
    } catch (err) {
      if (err instanceof AudioSmithError && err.code !== "aborted") {
        return { healthy: true, ready: false, detail: err.message };
      }
      throw err;
    }
  }

  /** Poll a job until it is done or failed; reports every poll to `onProgress`. */
  async waitForJob(id: string, opts: WaitOptions = {}): Promise<JobView> {
    const sleep = opts.sleep ?? defaultSleep;
    const interval = opts.intervalMs ?? 1000;
    const deadline =
      opts.timeoutMs === undefined ? Number.POSITIVE_INFINITY : Date.now() + opts.timeoutMs;
    for (;;) {
      if (opts.signal?.aborted === true) throw new AudioSmithError("aborted", 0, "request aborted");
      const job = await this.getJob(id, opts.signal);
      opts.onProgress?.(job);
      if (job.status === "done") return job;
      if (job.status === "failed") {
        const err = job.error ?? {};
        const code = str(err["code"]) ?? "job_failed";
        const detail = str(err["detail"]) ?? str(err["message"]) ?? "the job failed";
        throw new AudioSmithError(code, 0, `${code}: ${detail}`, str(err["hint"]));
      }
      if (Date.now() >= deadline) {
        throw new AudioSmithError(
          "timeout",
          0,
          `job ${id} did not finish in time`,
          "check status later",
        );
      }
      await sleep(interval, opts.signal);
    }
  }
}
