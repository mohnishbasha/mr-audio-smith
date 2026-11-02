import { JOB_LABEL, type Job } from "../state";

export function RenderQueue({
  jobs,
  indexOf,
  onClear,
}: {
  jobs: Job[];
  indexOf: (chunkId: string) => number;
  onClear: () => void;
}) {
  const finished = jobs.some((j) => j.status === "rendered" || j.status === "failed");
  return (
    <section aria-labelledby="queue-h" class="panel">
      <h2 id="queue-h">Render queue</h2>
      {jobs.length === 0 ? (
        <p>Queue is empty.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Target</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td>Chunk {String(indexOf(j.chunkId)).padStart(2, "0")}</td>
                <td>
                  <span class={`pill pill-job-${j.status}`}>{JOB_LABEL[j.status]}</span>
                  {j.error !== "" && <span class="muted"> {j.error}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {finished && (
        <button type="button" class="btn" onClick={onClear}>
          Clear finished
        </button>
      )}
    </section>
  );
}
