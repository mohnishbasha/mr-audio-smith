export function MarkerChip({
  marker,
  onInsert,
}: {
  marker: string;
  onInsert: (m: string) => void;
}) {
  return (
    <button
      type="button"
      class="chip mono"
      aria-label={`Insert ${marker}`}
      onClick={() => {
        onInsert(marker);
      }}
    >
      {marker}
    </button>
  );
}
