import { useState } from "preact/hooks";
import { errorText, useStudio } from "../ctx";
import type { Counts } from "../state";
import type { InjectResult } from "../types";
import { DiffViewer } from "./DiffViewer";

interface Props {
  slug: string;
  counts: Counts;
  hasTrack: boolean;
  approved: boolean;
  onApprove: () => Promise<void>;
}

export function ApprovePanel({ slug, counts, hasTrack, approved, onApprove }: Props) {
  const { api, notify } = useStudio();
  const [ack, setAck] = useState(false);
  const [approving, setApproving] = useState(false);
  const [path, setPath] = useState("");
  const [selector, setSelector] = useState("");
  const [preview, setPreview] = useState<InjectResult | null>(null);
  const [injecting, setInjecting] = useState(false);

  const checks = [
    {
      ok: counts.stale === 0 && counts.drafts === 0,
      text: `${String(counts.stale)} stale, ${String(counts.drafts)} unsaved`,
    },
    { ok: counts.failed === 0, text: `${String(counts.failed)} failed` },
    { ok: hasTrack, text: hasTrack ? "Master built" : "Master not built" },
  ];
  const ready = checks.every((c) => c.ok);

  async function approve(): Promise<void> {
    setApproving(true);
    try {
      await onApprove();
    } finally {
      setApproving(false);
    }
  }

  async function run(dry: boolean): Promise<void> {
    setInjecting(true);
    try {
      const res = await api.inject(slug, path.trim(), selector.trim(), dry);
      if (dry) setPreview(res);
      else {
        setPreview(null);
        notify(
          "success",
          res.changed ? `Injected the player into ${path}.` : "No changes were needed.",
        );
      }
    } catch (err) {
      notify("error", errorText(err));
    } finally {
      setInjecting(false);
    }
  }

  return (
    <section aria-labelledby="approve-h" class="panel">
      <h2 id="approve-h">Approve and publish</h2>
      <ul class="checks" aria-label="Approval checks">
        {checks.map((c) => (
          <li key={c.text}>
            <span class={`pill ${c.ok ? "pill-ok" : "pill-blocked"}`}>
              {c.ok ? "OK" : "Blocked"}
            </span>{" "}
            {c.text}
          </li>
        ))}
      </ul>
      {approved ? (
        <p>
          <span class="pill pill-approved">Approved</span> This narration is approved.
        </p>
      ) : (
        <>
          <label class="check">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => {
                setAck(e.currentTarget.checked);
              }}
            />
            <span>I have listened to this narration and approve it.</span>
          </label>
          <button
            type="button"
            class="btn btn-primary"
            disabled={!ready || !ack || approving}
            onClick={() => void approve()}
          >
            {approving ? "Approving" : "Approve"}
          </button>
        </>
      )}

      <h3>Inject the player into a page</h3>
      <form
        class="inject"
        onSubmit={(e) => {
          e.preventDefault();
          void run(true);
        }}
      >
        <label class="field">
          <span>Page path</span>
          <input
            type="text"
            value={path}
            required
            onInput={(e) => {
              setPath(e.currentTarget.value);
              setPreview(null);
            }}
          />
        </label>
        <label class="field">
          <span>Selector (optional)</span>
          <input
            type="text"
            value={selector}
            onInput={(e) => {
              setSelector(e.currentTarget.value);
              setPreview(null);
            }}
          />
        </label>
        <div class="row">
          <button type="submit" class="btn" disabled={injecting || path.trim() === ""}>
            Preview diff
          </button>
          <button
            type="button"
            class="btn btn-primary"
            disabled={injecting || preview === null || !preview.changed}
            onClick={() => void run(false)}
          >
            Apply
          </button>
        </div>
      </form>
      {preview && <DiffViewer diff={preview.diff} changed={preview.changed} />}
    </section>
  );
}
