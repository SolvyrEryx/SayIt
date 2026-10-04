// Zero-dependency static preview server for the exported site in out/.
// Usage: npm run build && npm run preview   (http://localhost:4173)
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, resolve, sep } from "node:path";

const ROOT = resolve(process.cwd(), "out");
const PORT = Number(process.env.PORT) || 4173;

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".json": "application/json",
  ".txt": "text/plain; charset=utf-8",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".webmanifest": "application/manifest+json",
};

async function isFile(path) {
  try {
    const info = await stat(path);
    return info.isFile();
  } catch {
    return false;
  }
}

function cacheControl(pathname, type) {
  // Release data must never be stale (§64): the manifest (and HTML) always
  // revalidates; hashed build assets are immutable.
  if (pathname.startsWith("/_next/static/")) return "public, max-age=31536000, immutable";
  if (type.startsWith("text/html") || type === "application/json") return "no-cache";
  return "no-cache";
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", "http://localhost");
    let pathname = decodeURIComponent(url.pathname);

    // Resolve inside ROOT only — reject any traversal attempt.
    const resolved = resolve(join(ROOT, "." + pathname));
    if (resolved !== ROOT && !resolved.startsWith(ROOT + sep)) {
      res.writeHead(403, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
      res.end("Forbidden");
      return;
    }

    // Static export uses trailingSlash: /design serves /design/index.html.
    if (pathname.endsWith("/")) {
      const data = await readFile(join(resolved, "index.html"));
      res.writeHead(200, {
        "Content-Type": MIME_TYPES[".html"],
        "Cache-Control": cacheControl(pathname, MIME_TYPES[".html"]),
      });
      res.end(data);
      return;
    }

    if (await isFile(resolved)) {
      const ext = extname(resolved).toLowerCase();
      const type = MIME_TYPES[ext] ?? "application/octet-stream";
      const data = await readFile(resolved);
      res.writeHead(200, {
        "Content-Type": type,
        "Cache-Control": cacheControl(pathname, type),
      });
      res.end(data);
      return;
    }

    res.writeHead(308, { Location: pathname + "/" });
    res.end();
  } catch {
    // 404s (e.g. a not-yet-published release manifest) must not be cached,
    // so the page picks up the file the moment it appears.
    res.writeHead(404, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
    res.end("Not found");
  }
});

server.listen(PORT, () => {
  console.log(`Serving ${ROOT} at http://localhost:${PORT}`);
});
