import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";

export interface Call {
  method: string;
  path: string;
  auth: string | null;
  body: unknown;
}

export type Handler = (
  call: Call,
) => { status?: number; body?: unknown; problem?: boolean } | Error;

/** A mocked fetch server: routes by "METHOD /path" to handlers, recording calls. */
export function mockServer(routes: Record<string, Handler | Handler[]>): {
  fetch: (input: string, init?: RequestInit) => Promise<Response>;
  calls: Call[];
} {
  const calls: Call[] = [];
  const counters = new Map<string, number>();
  const fetchFn = (input: string, init?: RequestInit): Promise<Response> => {
    const url = new URL(input);
    const method = init?.method ?? "GET";
    const headers = new Headers(init?.headers);
    const call: Call = {
      method,
      path: url.pathname,
      auth: headers.get("authorization"),
      body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined,
    };
    calls.push(call);
    const key = `${method} ${url.pathname}`;
    const entry = routes[key];
    if (entry === undefined) return Promise.resolve(new Response("not found", { status: 404 }));
    let handler: Handler;
    if (Array.isArray(entry)) {
      const n = counters.get(key) ?? 0;
      counters.set(key, n + 1);
      const picked = entry[Math.min(n, entry.length - 1)];
      if (picked === undefined) return Promise.resolve(new Response("empty", { status: 500 }));
      handler = picked;
    } else {
      handler = entry;
    }
    const out = handler(call);
    if (out instanceof Error) return Promise.reject(out);
    const status = out.status ?? 200;
    const type = out.problem === true ? "application/problem+json" : "application/json";
    const text = out.body === undefined ? "" : JSON.stringify(out.body);
    return Promise.resolve(new Response(text, { status, headers: { "content-type": type } }));
  };
  return { fetch: fetchFn, calls };
}

export interface FakePi {
  api: ExtensionAPI;
  tools: Map<
    string,
    {
      name: string;
      description: string;
      parameters: unknown;
      execute: (...a: never[]) => Promise<unknown>;
    }
  >;
  commands: Map<
    string,
    { description?: string; handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }
  >;
  events: Map<string, (event: unknown, ctx: unknown) => unknown>;
  sent: { customType: string; content: unknown; display: boolean }[];
}

export function fakePi(): FakePi {
  const fake: FakePi = {
    api: undefined as unknown as ExtensionAPI,
    tools: new Map(),
    commands: new Map(),
    events: new Map(),
    sent: [],
  };
  const api = {
    registerTool: (t: FakePi["tools"] extends Map<string, infer V> ? V : never) =>
      fake.tools.set(t.name, t),
    registerCommand: (
      name: string,
      o: FakePi["commands"] extends Map<string, infer V> ? V : never,
    ) => fake.commands.set(name, o),
    on: (name: string, h: (event: unknown, ctx: unknown) => unknown) => {
      fake.events.set(name, h);
      return () => undefined;
    },
    sendMessage: (m: FakePi["sent"][number]) => fake.sent.push(m),
  };
  fake.api = api as unknown as ExtensionAPI;
  return fake;
}

export function fakeCtx(): {
  ctx: ExtensionCommandContext;
  notes: { msg: string; type: string | undefined }[];
} {
  const notes: { msg: string; type: string | undefined }[] = [];
  const ctx = {
    signal: undefined,
    ui: { notify: (msg: string, type?: string) => notes.push({ msg, type }) },
  };
  return { ctx: ctx as unknown as ExtensionCommandContext, notes };
}
