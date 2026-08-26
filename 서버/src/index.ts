/**
 * index.ts — Cloudflare Worker 진입점.
 *
 * 들어온 HTTP 요청을 MCP 핸들러에 넘긴다. 그게 전부다.
 * `/health` 는 살아 있는지 보는 용도. 나머지 경로는 전부 MCP.
 *
 * 인증: 시크릿 YOUSTUDIO_TOKEN 이 설정돼 있으면 `Authorization: Bearer <토큰>` 이 맞아야 한다.
 *   설정: `npx wrangler secret put YOUSTUDIO_TOKEN`  (로컬 dev 는 서버/.dev.vars 에 YOUSTUDIO_TOKEN=... — gitignore 됨)
 *   미설정이면 검사하지 않는다 (로컬 dev · 스모크 테스트용). 배포본에는 반드시 넣는다 — 공개 URL 이다.
 */
import { createMcpHandler } from "@modelcontextprotocol/server";
import { buildServer } from "./server.js";

interface Env {
  YOUSTUDIO_TOKEN?: string;
}

const handler = createMcpHandler(() => buildServer(), { legacy: "stateless" });

function authorized(request: Request, env: Env): boolean {
  const want = (env.YOUSTUDIO_TOKEN ?? "").trim();
  if (!want) return true;
  const got = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "").trim();
  return got.length === want.length && got === want;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({ ok: true, server: "youstudio-mcp", auth: Boolean((env.YOUSTUDIO_TOKEN ?? "").trim()) });
    }
    if (!authorized(request, env)) {
      return Response.json(
        { jsonrpc: "2.0", error: { code: -32001, message: "인증 실패 — Authorization: Bearer <YOUSTUDIO_TOKEN> 헤더가 필요하다" }, id: null },
        { status: 401 },
      );
    }
    return handler.fetch(request);
  },
} satisfies ExportedHandler<Env>;
