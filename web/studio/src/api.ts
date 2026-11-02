import type {
  InjectResult,
  Problem,
  Project,
  ProjectSummary,
  SaveResult,
  ScriptChunk,
  Take,
  Track,
} from "./types";

export const TOKEN_HEADER = "X-Studio-Token";

export class ApiError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail === "" ? problem.title : problem.detail);
    this.name = "ApiError";
    this.problem = problem;
  }

  /** Human text for toasts: detail plus hint when the server sent one. */
  describe(): string {
    return this.problem.hint === "" ? this.message : `${this.message} ${this.problem.hint}`;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Turn a failed response into a Problem, accepting RFC 9457 bodies and falling back to status text. */
export async function readProblem(res: Response): Promise<Problem> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const rec = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
  const title = str(rec["title"]);
  return {
    type: str(rec["type"]) || "about:blank",
    title: title === "" ? `Request failed (${String(res.status)})` : title,
    status: typeof rec["status"] === "number" ? rec["status"] : res.status,
    detail: str(rec["detail"]),
    hint: str(rec["hint"]),
  };
}

export interface Api {
  projects(): Promise<ProjectSummary[]>;
  project(slug: string): Promise<Project>;
  saveScript(slug: string, chunks: ScriptChunk[]): Promise<SaveResult>;
  render(slug: string, chunkId: string, seed?: number): Promise<Take>;
  select(slug: string, chunkId: string, take: number): Promise<void>;
  master(slug: string): Promise<Track>;
  approve(slug: string): Promise<void>;
  inject(slug: string, path: string, selector: string, dryRun: boolean): Promise<InjectResult>;
  /** Fetch a protected media file with the token and return an object URL for native elements. */
  mediaUrl(url: string): Promise<string>;
}

export function createApi(token: string, fetchFn: FetchLike = (i, init) => fetch(i, init)): Api {
  const blobs = new Map<string, Promise<string>>();

  async function send(method: string, path: string, body?: unknown): Promise<Response> {
    const headers: Record<string, string> = { [TOKEN_HEADER]: token };
    const init: RequestInit = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    let res: Response;
    try {
      res = await fetchFn(path, init);
    } catch {
      throw new ApiError({
        type: "about:blank",
        title: "Network error",
        status: 0,
        detail: "Could not reach the Studio server.",
        hint: "Check that mr-audio-smith studio is still running.",
      });
    }
    if (!res.ok) throw new ApiError(await readProblem(res));
    return res;
  }

  async function json<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await send(method, path, body);
    return (await res.json()) as T;
  }

  const base = (slug: string): string => `/api/projects/${encodeURIComponent(slug)}`;

  return {
    projects: () => json<ProjectSummary[]>("GET", "/api/projects"),
    project: (slug) => json<Project>("GET", base(slug)),
    saveScript: (slug, chunks) => json<SaveResult>("PUT", `${base(slug)}/script`, { chunks }),
    render: (slug, chunkId, seed) =>
      json<Take>(
        "POST",
        `${base(slug)}/chunks/${encodeURIComponent(chunkId)}/render`,
        seed === undefined ? {} : { seed },
      ),
    select: async (slug, chunkId, take) => {
      await send("POST", `${base(slug)}/chunks/${encodeURIComponent(chunkId)}/select`, { take });
    },
    master: (slug) => json<Track>("POST", `${base(slug)}/master`),
    approve: async (slug) => {
      await send("POST", `${base(slug)}/approve`);
    },
    inject: (slug, path, selector, dryRun) =>
      json<InjectResult>("POST", `${base(slug)}/inject`, {
        path,
        ...(selector === "" ? {} : { selector }),
        dry_run: dryRun,
      }),
    mediaUrl: (url) => {
      const hit = blobs.get(url);
      if (hit) return hit;
      const pending = send("GET", url)
        .then((res) => res.blob())
        .then((blob) => URL.createObjectURL(blob));
      blobs.set(url, pending);
      pending.catch(() => blobs.delete(url));
      return pending;
    },
  };
}
