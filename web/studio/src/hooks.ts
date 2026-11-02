import { useEffect, useState } from "preact/hooks";
import { useStudio } from "./ctx";

export interface Media {
  src: string | null;
  error: string | null;
}

/** Load a protected media file (token header) as an object URL. */
export function useMedia(url: string | null): Media {
  const { api } = useStudio();
  const [media, setMedia] = useState<Media>({ src: null, error: null });
  useEffect(() => {
    if (url === null) {
      setMedia({ src: null, error: null });
      return;
    }
    let live = true;
    setMedia({ src: null, error: null });
    api.mediaUrl(url).then(
      (src) => {
        if (live) setMedia({ src, error: null });
      },
      () => {
        if (live) setMedia({ src: null, error: "Could not load the audio." });
      },
    );
    return () => {
      live = false;
    };
  }, [api, url]);
  return media;
}
