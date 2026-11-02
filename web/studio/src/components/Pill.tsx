import { PILL_LABEL, type PillStatus } from "../state";

export function Pill({ status }: { status: PillStatus }) {
  return <span class={`pill pill-${status}`}>{PILL_LABEL[status]}</span>;
}
