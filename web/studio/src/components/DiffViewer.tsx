export function lineKind(line: string): "add" | "del" | "hunk" | "ctx" {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "ctx";
}

export function DiffViewer({ diff, changed }: { diff: string; changed: boolean }) {
  if (!changed || diff.trim() === "") return <p>No changes. The file already matches.</p>;
  return (
    <pre class="diff mono" aria-label="Dry-run diff" tabIndex={0}>
      {diff.split("\n").map((line, i) => (
        <span key={i} class={`diff-${lineKind(line)}`}>
          {line}
          {"\n"}
        </span>
      ))}
    </pre>
  );
}
