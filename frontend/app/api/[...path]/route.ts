/**
 * Forwards /api/* to the API at request time.
 *
 * The page only ever talks to its own origin, so the API's port is plain runtime
 * configuration: the launcher sets API_URL when it starts this server, and nothing about
 * the port is compiled into the build. A rewrite in next.config would not do, because
 * Next evaluates rewrites at build time and stores them in the build manifest.
 *
 * Bodies stream through in both directions, so a PDF upload is not buffered here and a
 * figure image is not either.
 */

const API = process.env.API_URL ?? "http://127.0.0.1:8000";

// Hop-by-hop headers belong to each connection, not to the message. Expect is in the list
// because curl sends "100-continue" on a large upload and Node's fetch refuses to forward it.
const DROP = new Set([
  "host", "connection", "keep-alive", "transfer-encoding", "content-length", "expect",
]);

async function proxy(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const target = API + url.pathname + url.search;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!DROP.has(key.toLowerCase())) headers.set(key, value);
  });

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch when the body is a stream.
      ...(hasBody ? { duplex: "half" as const } : {}),
      cache: "no-store",
      redirect: "manual",
    });
  } catch (err) {
    const cause = err instanceof Error ? (err.cause instanceof Error ? err.cause.message : err.message) : String(err);
    const down = /ECONNREFUSED/.test(cause);
    return Response.json(
      {
        detail: down
          ? "The API is not running. Start Paper in Five again, or see logs/api.log."
          : `The web app could not forward this request to the API: ${cause}`,
      },
      { status: 502 },
    );
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!DROP.has(key.toLowerCase())) out.set(key, value);
  });
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE, proxy as PATCH, proxy as HEAD };

// A build takes minutes, and the proxy has to wait for it.
export const maxDuration = 1200;
export const dynamic = "force-dynamic";
