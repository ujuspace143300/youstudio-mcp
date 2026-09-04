/**
 * index.ts — Cloudflare Worker 진입점.
 *
 * 들어온 HTTP 요청을 MCP 핸들러에 넘긴다. 그게 전부다.
 * `/health` 는 살아 있는지 보는 용도. 나머지 경로는 전부 MCP.
 *
 * 인증 — 두 길 (설계 `설계/인증_이메일허가제.md`):
 *   ① 발급 대장(LICENSES KV 가 바인딩돼 있으면): 이메일 허가제. Authorization: Bearer <토큰>
 *      + X-Youstudio-Device <기기지문> 을 대장과 대조한다. 지인 배포는 이 길.
 *   ② 단일 토큰 폴백(KV 없고 YOUSTUDIO_TOKEN 만 있으면): 지금까지의 방식. 로컬 dev·스모크용.
 *   ③ 둘 다 없으면 검사 안 함(로컬 dev). 배포본에는 KV 를 반드시 붙인다 — 공개 URL 이다.
 */
import { createMcpHandler } from "@modelcontextprotocol/server";
import { buildServer } from "./server.js";
import { decideAuth, presetsInBody, readCreds, type License } from "./auth.js";

interface Env {
  YOUSTUDIO_TOKEN?: string;
  LICENSES?: KVNamespace;
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({
        ok: true,
        server: "youstudio-mcp",
        auth: env.LICENSES ? "license" : Boolean((env.YOUSTUDIO_TOKEN ?? "").trim()) ? "token" : "none",
      });
    }

    // ① 발급 대장이 붙어 있으면 이메일 허가제로 판정
    if (env.LICENSES) {
      const { token, device } = readCreds(request);
      if (!token) return deny(-32001, "인증 실패 — Authorization: Bearer <토큰> 헤더가 필요하다.");
      let license: License | null = null;
      try {
        license = await env.LICENSES.get<License>(token, "json");
      } catch {
        license = null;
      }
      // 프리셋별 권한(6번째 검사) — body 의 tools/call arguments.preset 을 꺼내 넘긴다. body 는 복제본에서 읽는다(원본은 handler 가 읽는다).
      let presets: string[] = [];
      try {
        presets = presetsInBody(await request.clone().json());
      } catch {
        presets = [];
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
      return handler.fetch(request);
    }

    // ② 폴백: 단일 토큰(로컬 dev·스모크)
    if (!tokenOk(request, env)) {
      return deny(-32001, "인증 실패 — Authorization: Bearer <YOUSTUDIO_TOKEN> 헤더가 필요하다.");
    }
    return handler.fetch(request);
  },
} satisfies ExportedHandler<Env>;
