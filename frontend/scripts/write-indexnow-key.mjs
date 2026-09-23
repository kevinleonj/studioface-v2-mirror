// Task 95b. Writes public/<key>.txt containing only the IndexNow key, before every
// `npm run build` (npm runs "prebuild" first; so does the Docker image's build).
//
// The key is public by design - IndexNow checks ownership by fetching this very file
// from the site root - so it lives in frontend/src/content/indexnow.json, not in Secret
// Manager. Plain node, no dependency. The generated file is gitignored: indexnow.json is
// the one place the key is written by hand.
import { readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = join(dirname(fileURLToPath(import.meta.url)), "..");
const { key } = JSON.parse(readFileSync(join(frontend, "src/content/indexnow.json"), "utf8"));

// indexnow.org: 8 to 128 characters of a-z, A-Z, 0-9 and "-" (docs/verified.md).
if (typeof key !== "string" || !/^[A-Za-z0-9-]{8,128}$/.test(key)) {
  console.error("indexnow.json: key missing or malformed");
  process.exit(1);
}

const pub = join(frontend, "public");
// A rotated key must not leave the old one answering: remove any earlier key file.
for (const name of readdirSync(pub)) {
  if (/^[A-Za-z0-9-]{8,128}\.txt$/.test(name) && name !== `${key}.txt`) {
    rmSync(join(pub, name));
  }
}
writeFileSync(join(pub, `${key}.txt`), key);
console.log(`indexnow: wrote public/${key}.txt`);
