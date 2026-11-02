import { useEffect } from "preact/hooks";
import type { ToastItem } from "../state";

const AUTO_DISMISS_MS = 5000;

function ToastView({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  useEffect(() => {
    if (item.kind === "error") return;
    const t = setTimeout(() => {
      onDismiss(item.id);
    }, AUTO_DISMISS_MS);
    return () => {
      clearTimeout(t);
    };
  }, [item, onDismiss]);
  return (
    <div class={`toast toast-${item.kind}`} role={item.kind === "error" ? "alert" : "status"}>
      <span>{item.message}</span>
      <button
        type="button"
        class="btn btn-quiet"
        onClick={() => {
          onDismiss(item.id);
        }}
      >
        Dismiss
      </button>
    </div>
  );
}

export function Toasts({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div class="toasts">
      {items.map((t) => (
        <ToastView key={t.id} item={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
