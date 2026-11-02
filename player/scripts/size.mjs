import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const LIMIT = 12 * 1024;
const file = new URL("../dist/audio-smith-player.js", import.meta.url);
const size = gzipSync(readFileSync(file), { level: 9 }).length;
process.stdout.write(`audio-smith-player.js gzipped: ${size} bytes (limit ${LIMIT})\n`);
if (size > LIMIT) {
    process.stderr.write("Bundle exceeds the 12 KB gzipped budget (NFR-011).\n");
    process.exit(1);
}
