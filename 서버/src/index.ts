/**
 * index.ts — Cloudflare Worker 진입점.
 *
 * 들어온 HTTP 요청을 MCP 핸들러에 넘긴다. 그게 전부다.
 * `/health` 는 살아 있는지 보는 용도. 나머지 경로는 전부 MCP.
 */
import { createMcpHandler } from "@modelcontextprotocol/server";
import { buildServer } from "./server.js";

const handler = createMcpHandler(() => buildServer(), { legacy: "stateless" });

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({ ok: true, server: "youstudio-mcp" });
    }
    return handler.fetch(request);
  },
} satisfies ExportedHandler;
