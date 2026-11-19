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

async function loadPage(env, path) {
  const { results } = await env.PAGES.prepare("SELECT html FROM pages WHERE path = ?1 ORDER BY part").bind(path).all();
  if (!results || results.length === 0) return null;
  return results.map((r) => r.html).join("");
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
