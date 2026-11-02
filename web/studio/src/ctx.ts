import { createContext } from "preact";
import { useContext } from "preact/hooks";
import type { Api } from "./api";
import { ApiError } from "./api";
import type { ToastKind } from "./state";

export interface Studio {
  api: Api;
  notify: (kind: ToastKind, message: string) => void;
}

export const StudioContext = createContext<Studio | null>(null);

export function useStudio(): Studio {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("StudioContext is missing");
  return ctx;
}

export function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.describe();
  return err instanceof Error ? err.message : "Something went wrong.";
}
