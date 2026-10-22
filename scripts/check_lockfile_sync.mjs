// G5 lockfile gate, deterministic and offline: does package-lock.json still satisfy every
// DIRECT dependency range declared in package.json?
//
// Why not just call `npm ci`: on this machine `npm ci` also fails because of transitive
// platform-optional deps (`@emnapi/*`) that resolve differently per OS, so the gate would be
// red for reasons nobody caused. A declared-range drift (the postcss-html class, which really
// does break `frontend/Dockerfile` -> `RUN npm ci`) is caught here without touching the network.
import fs from "node:fs";
import path from "node:path";

const feDir = path.resolve(process.argv[2] || ".");
const pkg = JSON.parse(fs.readFileSync(path.join(feDir, "package.json"), "utf8"));
const lock = JSON.parse(fs.readFileSync(path.join(feDir, "package-lock.json"), "utf8"));

const declared = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
const locked = {};
for (const [key, entry] of Object.entries(lock.packages || {})) {
  const m = key.match(/^node_modules\/((?:@[^/]+\/)?[^/]+)$/);
  if (m && entry.version) locked[m[1]] = entry.version;
}

const parse = (v) => (String(v).match(/(\d+)\.(\d+)\.(\d+)/) || []).slice(1).map(Number);
const cmp = (a, b) => (a[0] - b[0]) || (a[1] - b[1]) || (a[2] - b[2]);

const bad = [];
for (const [name, range] of Object.entries(declared)) {
  const have = locked[name];
  if (!have) { bad.push(`${name}: declared ${range}, absent from lockfile`); continue; }
  if (range === "*" || range === "latest" || /^[>=<~^]?\d/.test(range) === false) continue;
  if (/^https?:|^file:|^link:|^workspace:/.test(range)) continue;
  const want = parse(range);
  const got = parse(have);
  if (!want.length || !got.length) { continue; }
  let ok;
  if (range.startsWith("^")) ok = got[0] === want[0] && cmp(got, want) >= 0;
  else if (range.startsWith("~")) ok = got[0] === want[0] && got[1] === want[1] && cmp(got, want) >= 0;
  else ok = cmp(got, want) === 0;
  if (!ok) bad.push(`${name}: lock file's ${have} does not satisfy ${range}`);
}

if (bad.length) {
  console.log(`LOCKFILE OUT OF SYNC (${bad.length} direct dep(s)) -- \`npm ci\` in frontend/Dockerfile will fail:`);
  for (const line of bad) console.log("  - " + line);
  process.exit(2);
}
console.log(`lockfile ok: all ${Object.keys(declared).length} direct deps are satisfied by package-lock.json`);
