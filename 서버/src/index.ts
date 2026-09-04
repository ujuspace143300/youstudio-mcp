/**
 * index.ts — Cloudflare Worker 진입점.
 *
 * 들어온 HTTP 요청을 MCP 핸들러에 넘긴다. `/health` 는 살아 있는지 보는 용도.
 * `/asset/<프리셋>/<경로>` 는 자산 다운로드(길 C — 토큰 있는 사람만 · 이식원칙 ⑥ · 2026-09-04).
 * 나머지 경로는 전부 MCP.
 *
 * 인증 — 두 길 (설계 `설계/인증_이메일허가제.md`):
 *   ① 발급 대장(LICENSES KV 가 바인딩돼 있으면): 이메일 허가제. Authorization: Bearer <토큰>
 *      + X-Youstudio-Device <기기지문> 을 대장과 대조한다(+ 프리셋별 권한). 지인 배포는 이 길.
 *   ② 단일 토큰 폴백(KV 없고 YOUSTUDIO_TOKEN 만 있으면): 지금까지의 방식. 로컬 dev·스모크용.
 *   ③ 둘 다 없으면 검사 안 함(로컬 dev). 배포본에는 KV 를 반드시 붙인다 — 공개 URL 이다.
 *
 * 자산 — Workers Static Assets(wrangler.jsonc assets: 저장소 자산/ 을 배포 때 그대로 올린다 · run_worker_first 라
 *   이 워커를 거치지 않고는 못 받는다). 목록은 배포 전 `도구/자산목록.mjs` 가 자산/<프리셋>/_목록.json 으로 만든다.
 */
import { createMcpHandler } from "@modelcontextprotocol/server";
import { buildServer } from "./server.js";
import { decideAuth, presetsInBody, readCreds, type License } from "./auth.js";

interface Env {
  YOUSTUDIO_TOKEN?: string;
  LICENSES?: KVNamespace;
  /** Workers Static Assets — 저장소 자산/ (wrangler.jsonc assets.binding) */
  ASSETS?: Fetcher;
}

const handler = createMcpHandler(() => buildServer(), { legacy: "stateless" });

/** 폴백 단일 토큰 검사(구방식). 길이+값 상수시간 비교. */
function tokenOk(request: Request, env: Env): boolean {
  const want = (env.YOUSTUDIO_TOKEN ?? "").trim();
  if (!want) return true;
  const got = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "").trim();
  return got.length === want.length && got === want;
}

function deny(code: number, message: string): Response {
  return Response.json(
    { jsonrpc: "2.0", error: { code, message }, id: null },
    { status: 401 },
  );
}

/**
 * 인증 — 통과면 null, 아니면 거부 응답. presets 는 이 요청이 지목한 프리셋(들) — MCP 는 body 에서, 자산은 경로에서.
 * 대장 검사(KV) → 단일 토큰 폴백 → 없음 순서는 위 머리말 그대로.
 */
async function authorize(request: Request, env: Env, presets: string[]): Promise<Response | null> {
  if (env.LICENSES) {
    const { token, device } = readCreds(request);
    if (!token) return deny(-32001, "인증 실패 — Authorization: Bearer <토큰> 헤더가 필요하다.");
    let license: License | null = null;
    try {
      license = await env.LICENSES.get<License>(token, "json");
    } catch {
      license = null;
    }
    let decision = decideAuth(license, device, Date.now(), presets[0] ?? null);
    for (const p of presets.slice(1)) {
      if (!decision.ok) break;
      const d2 = decideAuth(license, device, Date.now(), p);
      if (!d2.ok) decision = d2;
    }
    if (!decision.ok) return deny(decision.code, decision.message);
    // 기기가 새로 등록됐으면 대장에 다시 쓴다(빈 자리 채움)
    if (decision.changed) {
      try {
        await env.LICENSES.put(token, JSON.stringify(decision.license));
      } catch {
        // 저장 실패해도 이번 요청은 통과시킨다 — 다음 요청에서 다시 등록 시도된다
      }
    }
    return null;
  }
  if (!tokenOk(request, env)) {
    return deny(-32001, "인증 실패 — Authorization: Bearer <YOUSTUDIO_TOKEN> 헤더가 필요하다.");
  }
  return null;
}

/** /asset/<프리셋>/<경로> → 자산 파일. 프리셋 권한은 authorize 가 봤다. 경로는 자산/<프리셋>/ 아래로만(.. 금지). */
async function serveAsset(request: Request, env: Env, url: URL): Promise<Response> {
  const rest = url.pathname.slice("/asset/".length);
  const parts = rest.split("/").map((s) => { try { return decodeURIComponent(s); } catch { return s; } });
  const preset = parts[0] ?? "";
  const rel = parts.slice(1);
  if (!preset || !rel.length || parts.some((p) => p === "" || p === "." || p === ".." || p.includes("\\"))) {
    return Response.json({ error: "경로가 틀렸다 — /asset/<프리셋>/<파일 경로> (예: /asset/린박스/_목록.json)" }, { status: 400 });
  }
  if (!env.ASSETS) {
    return Response.json({ error: "이 서버에는 자산 바인딩(ASSETS)이 없다 — wrangler.jsonc assets 를 보라." }, { status: 503 });
  }
  const assetUrl = new URL(request.url);
  assetUrl.pathname = "/" + [preset, ...rel].map((s) => encodeURIComponent(s)).join("/");
  assetUrl.search = "";
  const r = await env.ASSETS.fetch(new Request(assetUrl.toString(), { method: "GET" }));
  if (r.status === 404) {
    return Response.json({ error: `자산이 없다: ${preset}/${rel.join("/")} — /asset/${preset}/_목록.json 을 보라.` }, { status: 404 });
  }
  const h = new Headers(r.headers);
  h.set("cache-control", "private, no-store"); // 토큰 있는 사람에게만 — 중간 캐시 금지
  h.set("x-youstudio-asset", `${preset}/${rel.join("/")}`);
  return new Response(r.body, { status: r.status, headers: h });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({
        ok: true,
        server: "youstudio-mcp",
        auth: env.LICENSES ? "license" : Boolean((env.YOUSTUDIO_TOKEN ?? "").trim()) ? "token" : "none",
        assets: Boolean(env.ASSETS),
      });
    }

    // 자산 다운로드 — 프리셋은 경로에서. 인증(대장·기기·프리셋 권한)을 MCP 와 똑같이 태운다.
    if (url.pathname.startsWith("/asset/")) {
      if (request.method !== "GET" && request.method !== "HEAD") return Response.json({ error: "GET 만" }, { status: 405 });
      const preset = (() => { try { return decodeURIComponent(url.pathname.slice("/asset/".length).split("/")[0] ?? ""); } catch { return ""; } })();
      const denied = await authorize(request, env, preset ? [preset] : []);
      if (denied) return denied;
      return serveAsset(request, env, url);
    }

    // MCP — 프리셋별 권한(6번째 검사)은 body 의 tools/call arguments.preset 을 꺼내 넘긴다. body 는 복제본에서 읽는다(원본은 handler 가 읽는다).
    let presets: string[] = [];
    if (env.LICENSES) {
      try {
        presets = presetsInBody(await request.clone().json());
      } catch {
        presets = [];
      }
    }
    const denied = await authorize(request, env, presets);
    if (denied) return denied;
    return handler.fetch(request);
  },
} satisfies ExportedHandler<Env>;
