import { useCallback, useEffect, useMemo, useReducer, useState } from "preact/hooks";
import type { Api } from "./api";
import { ProjectList } from "./components/ProjectList";
import { ProjectView } from "./components/ProjectView";
import { Toasts } from "./components/Toast";
import { StudioContext } from "./ctx";
import { initialToasts, toastReducer, type ToastKind } from "./state";

export function slugFromHash(hash: string): string | null {
  const m = /^#\/p\/(.+)$/.exec(hash);
  return m?.[1] ? decodeURIComponent(m[1]) : null;
}

export function App({ api }: { api: Api | null }) {
  const [toasts, dispatch] = useReducer(toastReducer, initialToasts);
  const [slug, setSlug] = useState(() => slugFromHash(location.hash));
  useEffect(() => {
    const on = (): void => {
      setSlug(slugFromHash(location.hash));
    };
    window.addEventListener("hashchange", on);
    return () => {
      window.removeEventListener("hashchange", on);
    };
  }, []);
  const notify = useCallback((kind: ToastKind, message: string) => {
    dispatch({ type: "add", kind, message });
  }, []);
  const dismiss = useCallback((id: number) => {
    dispatch({ type: "dismiss", id });
  }, []);
  const studio = useMemo(() => (api ? { api, notify } : null), [api, notify]);

  return (
    <>
      <header class="topbar">
        <span class="brand">mr-audio-smith Studio</span>
      </header>
      <main>
        {studio ? (
          <StudioContext.Provider value={studio}>
            {slug === null ? (
              <ProjectList
                onOpen={(s) => {
                  location.hash = `#/p/${encodeURIComponent(s)}`;
                }}
              />
            ) : (
              <ProjectView
                key={slug}
                slug={slug}
                onBack={() => {
                  location.hash = "";
                }}
              />
            )}
          </StudioContext.Provider>
        ) : (
          <p role="alert">
            No session token. Open the link printed by mr-audio-smith studio, including its ?token=
            value.
          </p>
        )}
      </main>
      <Toasts items={toasts.items} onDismiss={dismiss} />
    </>
  );
}
