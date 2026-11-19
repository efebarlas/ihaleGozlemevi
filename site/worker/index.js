// İhale Gözlemevi Worker: static core pages from the ASSETS binding, bulk pages from D1 (binding PAGES).
// The bulk path classifier mirrors src/ihale/sitegen/d1.py (_BULK); keep both in sync.
// Unlisted site: every response carries X-Robots-Tag: noindex, nofollow.

const BULK = [
  /^\/ihale\/[^/]+\/$/,
  /^\/idare\/(?!liste\/)[^/]+\/(?:\d+\/)?$/,
  /^\/yuklenici\/(?!liste\/)[^/]+\/(?:\d+\/)?$/,
  /^\/gun\/[^/]+\/\d+\/$/,
];

const isBulk = (path) => BULK.some((r) => r.test(path));

function withRobots(headers) {
  headers.set("X-Robots-Tag", "noindex, nofollow");
  return headers;
}

async function notFound(request, env) {
  // /404.html may be redirected to /404 by the asset layer; follow it internally.
  const url = new URL(request.url);
  let res = await env.ASSETS.fetch(new Request(new URL("/404.html", url), { redirect: "follow" }));
  const headers = withRobots(new Headers(res.headers));
  headers.set("content-type", "text/html; charset=utf-8");
  headers.set("cache-control", "public, max-age=60");
  return new Response(request.method === "HEAD" ? null : res.body, { status: 404, headers });
}

function unavailable(request) {
  const body = "<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\"><meta name=\"robots\" content=\"noindex, nofollow\">"
    + "<title>Geçici olarak ulaşılamıyor</title></head><body><h1>Bu sayfa şu anda yüklenemiyor</h1>"
    + "<p>Biraz sonra tekrar deneyin. <a href=\"/\">Bugün sayfası</a> etkilenmez.</p></body></html>";
  const headers = withRobots(new Headers({ "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "retry-after": "60" }));
  return new Response(request.method === "HEAD" ? null : body, { status: 503, headers });
}

// Pages are stored gzip-compressed (table pg: one BLOB row per page, more parts only for very large pages). The parts
// are slices of ONE gzip stream, so they are concatenated before decompressing.
async function loadPage(env, path) {
  const { results } = await env.PAGES.prepare("SELECT gz FROM pg WHERE path = ?1 ORDER BY part").bind(path).all();
  if (!results || results.length === 0) return null;
  const parts = results.map((r) => new Uint8Array(r.gz));   // D1 hands BLOBs over as number[] or ArrayBuffer
  const bytes = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let off = 0;
  for (const p of parts) { bytes.set(p, off); off += p.length; }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).text();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (method !== "GET" && method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405, headers: withRobots(new Headers({ Allow: "GET, HEAD" })) });
    }

    if (!path.endsWith("/") && isBulk(path + "/")) {
      url.pathname = path + "/";
      return new Response(null, { status: 308, headers: withRobots(new Headers({ Location: url.toString() })) });
    }

    if (isBulk(path)) {
      let html;
      try {
        html = await loadPage(env, path);
      } catch (e) {
        // D1 unavailable: only bulk pages fail; core pages never touch D1.
        return unavailable(request);
      }
      if (html === null) return notFound(request, env);
      const headers = withRobots(new Headers({
        "content-type": "text/html; charset=utf-8",
        "cache-control": "public, max-age=300",
      }));
      return new Response(method === "HEAD" ? null : html, { status: 200, headers });
    }

    const res = await env.ASSETS.fetch(request);
    if (res.status === 404) return notFound(request, env);
    const headers = withRobots(new Headers(res.headers));
    const ct = headers.get("content-type") || "";
    if (/^text\/html/i.test(ct) && !/charset/i.test(ct)) headers.set("content-type", "text/html; charset=utf-8");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  },
};
