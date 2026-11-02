// Tiny static server for the e2e suite. Serves the repo root and supports HTTP Range
// requests, which Chromium needs for seeking in audio.
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const PORT = Number(process.env.E2E_PORT ?? 4173);
const TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mp3": "audio/mpeg",
    ".vtt": "text/vtt; charset=utf-8",
    ".json": "application/json",
};

createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    let path = normalize(join(ROOT, decodeURIComponent(url.pathname)));
    if (!path.startsWith(ROOT)) {
        res.writeHead(403).end();
        return;
    }
    if (url.pathname.startsWith("/fixtures/"))
        path = join(ROOT, "tests/e2e", url.pathname);
    let stat;
    try {
        stat = statSync(path);
    } catch {
        res.writeHead(404).end("not found");
        return;
    }
    if (!stat.isFile()) {
        res.writeHead(404).end("not found");
        return;
    }
    const headers = {
        "Content-Type": TYPES[extname(path)] ?? "application/octet-stream",
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
    };
    const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
    if (range) {
        const start = range[1] === "" ? 0 : Number(range[1]);
        const end =
            range[2] === ""
                ? stat.size - 1
                : Math.min(Number(range[2]), stat.size - 1);
        res.writeHead(206, {
            ...headers,
            "Content-Range": `bytes ${start}-${end}/${stat.size}`,
            "Content-Length": end - start + 1,
        });
        createReadStream(path, { start, end }).pipe(res);
        return;
    }
    res.writeHead(200, { ...headers, "Content-Length": stat.size });
    if (req.method === "HEAD") res.end();
    else createReadStream(path).pipe(res);
}).listen(PORT, "127.0.0.1");
