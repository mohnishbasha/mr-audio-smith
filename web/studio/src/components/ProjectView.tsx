import { useCallback, useEffect, useReducer, useRef, useState } from "preact/hooks";
import { errorText, useStudio } from "../ctx";
import {
  countChunks,
  initialQueue,
  initialView,
  nextJob,
  pillStatus,
  queueReducer,
  textOf,
  viewReducer,
} from "../state";
import { validateChunkText } from "../validate";
import { ApprovePanel } from "./ApprovePanel";
import { ChunkEditor } from "./ChunkEditor";
import { ChunkList } from "./ChunkList";
import { MasterPreview } from "./MasterPreview";
import { RenderQueue } from "./RenderQueue";
import { TakeCompare } from "./TakeCompare";

export function ProjectView({ slug, onBack }: { slug: string; onBack: () => void }) {
  const { api, notify } = useStudio();
  const [view, dispatch] = useReducer(viewReducer, initialView);
  const [queue, qDispatch] = useReducer(queueReducer, initialQueue);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [keeping, setKeeping] = useState(false);
  const [mastering, setMastering] = useState(false);
  const started = useRef(new Set<number>());

  const reload = useCallback(async (): Promise<void> => {
    try {
      dispatch({ type: "loaded", project: await api.project(slug) });
      setLoadError(null);
    } catch (err) {
      setLoadError(errorText(err));
    }
  }, [api, slug]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Sequential render queue: one job at a time.
  useEffect(() => {
    const job = nextJob(queue);
    if (!job || started.current.has(job.id)) return;
    started.current.add(job.id);
    qDispatch({ type: "start", id: job.id });
    dispatch({ type: "chunk-status", id: job.chunkId, status: "rendering" });
    api.render(slug, job.chunkId).then(
      (take) => {
        dispatch({ type: "take-added", id: job.chunkId, take });
        qDispatch({ type: "done", id: job.id });
        notify("success", `Rendered take ${String(take.take)}.`);
      },
      (err: unknown) => {
        dispatch({ type: "chunk-status", id: job.chunkId, status: "failed" });
        qDispatch({ type: "fail", id: job.id, error: errorText(err) });
        notify("error", `Render failed. ${errorText(err)}`);
      },
    );
  }, [queue, api, slug, notify]);

  const project = view.project;
  if (loadError !== null) {
    return (
      <section>
        <p role="alert">Could not load the project. {loadError}</p>
        <button type="button" class="btn" onClick={onBack}>
          Back to projects
        </button>
      </section>
    );
  }
  if (!project) return <p role="status">Loading project</p>;

  const counts = countChunks(view);
  const selected = project.chunks.find((c) => c.id === view.selectedId) ?? null;
  const indexOf = (id: string): number => project.chunks.findIndex((c) => c.id === id) + 1;
  const invalid = project.chunks.some((c) => validateChunkText(textOf(view, c)).length > 0);

  async function save(): Promise<void> {
    if (!project) return;
    setSaving(true);
    try {
      const res = await api.saveScript(
        slug,
        project.chunks.map((c) => ({ id: c.id, text: textOf(view, c), verbatim: c.verbatim })),
      );
      if (!res.ok) {
        setServerErrors(res.errors);
        notify("error", `Script not saved. ${res.errors.join(" ")}`);
        return;
      }
      setServerErrors([]);
      await reload();
      notify(
        "success",
        res.stale.length === 0
          ? "Script saved. No chunks changed."
          : `Script saved. ${String(res.stale.length)} chunk(s) are stale.`,
      );
    } catch (err) {
      notify("error", errorText(err));
    } finally {
      setSaving(false);
    }
  }

  async function keep(chunkId: string, take: number): Promise<void> {
    setKeeping(true);
    try {
      await api.select(slug, chunkId, take);
      dispatch({ type: "take-kept", id: chunkId, take });
      notify("success", `Kept take ${String(take)}.`);
    } catch (err) {
      notify("error", errorText(err));
    } finally {
      setKeeping(false);
    }
  }

  async function master(): Promise<void> {
    setMastering(true);
    try {
      dispatch({ type: "track", track: await api.master(slug) });
      notify("success", "Master built from the kept takes.");
    } catch (err) {
      notify("error", errorText(err));
    } finally {
      setMastering(false);
    }
  }

  async function approve(): Promise<void> {
    try {
      await api.approve(slug);
      dispatch({ type: "approved" });
      notify("success", "Approved. The manifest is marked approved.");
    } catch (err) {
      notify("error", errorText(err));
    }
  }

  const queuedNow = (id: string): boolean =>
    queue.jobs.some((j) => j.chunkId === id && (j.status === "queued" || j.status === "rendering"));
  const staleIds = project.chunks
    .filter((c) => c.status === "stale" && !(c.id in view.drafts))
    .map((c) => c.id);

  return (
    <div class="project">
      <div class="project-head">
        <button type="button" class="btn btn-quiet" onClick={onBack}>
          All projects
        </button>
        <h1>{project.title}</h1>
        {project.approved && <span class="pill pill-approved">Approved</span>}
        <div class="row">
          <button
            type="button"
            class="btn btn-primary"
            disabled={saving || counts.drafts === 0 || invalid}
            onClick={() => void save()}
          >
            {saving ? "Saving" : "Save script"}
          </button>
          <button
            type="button"
            class="btn"
            disabled={staleIds.length === 0}
            onClick={() => {
              staleIds.forEach((id) => {
                qDispatch({ type: "enqueue", chunkId: id });
              });
            }}
          >
            Render stale chunks
          </button>
        </div>
      </div>
      {project.warnings.length > 0 && (
        <ul class="warnings" aria-label="Warnings">
          {project.warnings.map((w) => (
            <li key={w}>Warning: {w}</li>
          ))}
        </ul>
      )}
      <p class="statusbar" role="status">
        Chunks: {counts.total}. Stale: {counts.stale}. Failed: {counts.failed}. Unsaved:{" "}
        {counts.drafts}.
      </p>
      <div class="cols">
        <ChunkList
          view={view}
          onSelect={(id) => {
            dispatch({ type: "select", id });
          }}
          onFilter={(filter) => {
            dispatch({ type: "filter", filter });
          }}
        />
        <div class="stack">
          {selected ? (
            <>
              <ChunkEditor
                key={selected.id}
                chunk={selected}
                index={indexOf(selected.id)}
                text={textOf(view, selected)}
                status={pillStatus(view, selected)}
                serverErrors={serverErrors}
                onChange={(text) => {
                  dispatch({ type: "edit", id: selected.id, text });
                }}
                onRender={() => {
                  if (selected.id in view.drafts) {
                    notify("info", "Save the script before rendering.");
                    return;
                  }
                  qDispatch({ type: "enqueue", chunkId: selected.id });
                }}
              />
              <TakeCompare
                chunk={selected}
                busy={keeping}
                rendering={queuedNow(selected.id)}
                onKeep={(take) => void keep(selected.id, take)}
                onRerender={() => {
                  qDispatch({ type: "enqueue", chunkId: selected.id });
                }}
              />
            </>
          ) : (
            <p>Select a chunk to edit.</p>
          )}
        </div>
      </div>
      <RenderQueue
        jobs={queue.jobs}
        indexOf={indexOf}
        onClear={() => {
          qDispatch({ type: "clear" });
        }}
      />
      <MasterPreview track={project.track} busy={mastering} onMaster={() => void master()} />
      <ApprovePanel
        slug={slug}
        counts={counts}
        hasTrack={project.track !== null}
        approved={project.approved}
        onApprove={approve}
      />
    </div>
  );
}
