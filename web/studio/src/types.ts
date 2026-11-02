export type ChunkStatus = "cached" | "stale" | "rendering" | "failed";

export interface Take {
  take: number;
  seed: number;
  similarity: number | null;
  duration_ms: number;
  url: string;
}

export interface Chunk {
  id: string;
  text: string;
  verbatim: boolean;
  status: ChunkStatus;
  selected_take: number | null;
  takes: Take[];
}

export interface Track {
  url: string;
  captions_url: string;
  duration_s: number;
  loudness_lufs: number;
  peaks: number[];
}

export interface ProjectSummary {
  slug: string;
  title: string;
  updated_at: string;
  has_manifest: boolean;
  approved: boolean;
}

export interface Project {
  slug: string;
  title: string;
  source: string;
  profile: string;
  lang: string;
  chunks: Chunk[];
  track: Track | null;
  approved: boolean;
  warnings: string[];
}

export interface ScriptChunk {
  id: string;
  text: string;
  verbatim: boolean;
}

export interface SaveResult {
  ok: boolean;
  errors: string[];
  warnings: string[];
  stale: string[];
}

export interface InjectResult {
  diff: string;
  changed: boolean;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  hint: string;
}
