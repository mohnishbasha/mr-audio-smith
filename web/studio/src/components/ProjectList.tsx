import { useEffect, useState } from "preact/hooks";
import { errorText, useStudio } from "../ctx";
import type { ProjectSummary } from "../types";

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; items: ProjectSummary[] };

export function ProjectList({ onOpen }: { onOpen: (slug: string) => void }) {
  const { api } = useStudio();
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  useEffect(() => {
    let live = true;
    api.projects().then(
      (items) => {
        if (live) setLoad({ kind: "ok", items });
      },
      (err: unknown) => {
        if (live) setLoad({ kind: "error", message: errorText(err) });
      },
    );
    return () => {
      live = false;
    };
  }, [api]);

  return (
    <section aria-labelledby="projects-h">
      <h1 id="projects-h">Projects</h1>
      {load.kind === "loading" && <p role="status">Loading projects</p>}
      {load.kind === "error" && <p role="alert">Could not load projects. {load.message}</p>}
      {load.kind === "ok" && load.items.length === 0 && (
        <p>No projects yet. Run mr-audio-smith narrate &lt;url&gt;</p>
      )}
      {load.kind === "ok" && load.items.length > 0 && (
        <ul class="project-list">
          {load.items.map((p) => (
            <li key={p.slug}>
              <button
                type="button"
                class="btn project-open"
                onClick={() => {
                  onOpen(p.slug);
                }}
              >
                <strong>{p.title}</strong>
                <span class="muted">{p.slug}</span>
                <span class={`pill ${p.approved ? "pill-approved" : "pill-draft"}`}>
                  {p.approved ? "Approved" : "Not approved"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
