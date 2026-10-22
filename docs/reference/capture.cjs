// Screenshot the login page at several viewports without starting a server.
// Usage: node capture.cjs --base <dir> --entry <path> --tag <name>
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

const argv = {};
for (let i = 2; i < process.argv.length; i += 2) {
  argv[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
}
const BASE = path.resolve(argv.base || ".");
const ENTRY = argv.entry || "/index.html";
const TAG = argv.tag || "shot";
const OUT = path.resolve(argv.out || "shots");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
  ".map": "application/json",
};

// Fonts are remote in the shipped app; a customer intranet cannot reach them.
const BLOCKED = /fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net|unpkg\.com|googleapis\.com/;

const VIEWS = [
  { w: 1440, h: 900 },
  { w: 1920, h: 1080 },
  { w: 3440, h: 1440 },
  { w: 1280, h: 720 },
  { w: 768, h: 1024 },
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const report = [];
  for (const v of VIEWS) {
    const context = await browser.newContext({
      viewport: { width: v.w, height: v.h },
      deviceScaleFactor: 1,
    });
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (BLOCKED.test(url.hostname)) return route.abort();
      if (url.pathname.startsWith("/api/")) {
        return route.fulfill({
          status: 401,
          contentType: "application/json",
          body: '{"detail":"not authenticated"}',
        });
      }
      const rel = decodeURIComponent(url.pathname).replace(/^\/+/, "");
      const file = path.join(BASE, rel || ENTRY.replace(/^\/+/, ""));
      const abs = path.resolve(file);
      if (!abs.startsWith(BASE) || !fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
        return route.fulfill({ status: 404, contentType: "text/plain", body: "not found" });
      }
      await route.fulfill({
        status: 200,
        contentType: MIME[path.extname(abs).toLowerCase()] || "application/octet-stream",
        body: fs.readFileSync(abs),
      });
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 160)));
    await page.goto("http://local.test" + ENTRY, { waitUntil: "load" });
    await page.waitForTimeout(1200);
    const name = `${TAG}-${v.w}x${v.h}.png`;
    await page.screenshot({ path: path.join(OUT, name) });
    const fonts = await page.evaluate(() => {
      const el = document.querySelector("h1, h2, .card h2, .pitch h1");
      return el ? getComputedStyle(el).fontFamily : "n/a";
    });
    report.push({ view: name, errors: [...new Set(errors)], font: fonts.slice(0, 60) });
    await context.close();
  }
  await browser.close();
  console.log(JSON.stringify(report, null, 2));
})();
