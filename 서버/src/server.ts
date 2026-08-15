/**
 * server.ts — MCP 서버 정의. 도구는 youstudio_video 하나뿐이다.
 *
 * 요청마다 새 McpServer 를 만든다(createMcpHandler 의 per-request 모델).
 * 상태는 서버에 두지 않는다 — 어제 것이 오늘 이어지는 곳은 클라이언트의 작업 폴더다 (HARNESS 6장 ④).
 */
import { McpServer } from "@modelcontextprotocol/server";
import { HANDLERS } from "./steps/index.js";
import { ToolInputSchema, type StepResponse } from "./schema.js";

export const SERVER_INFO = { name: "youstudio-mcp", version: "0.1.0" } as const;

/** 서버 수준 지시문 — 클라이언트(클로드)가 initialize 때 받는다 */
export const INSTRUCTIONS =
  "이 서버가 돌려주는 지시를 순서대로 그대로 실행하라. 임의로 해석하거나 개선하지 마라.";

export function buildServer(): McpServer {
  const server = new McpServer(SERVER_INFO, { instructions: INSTRUCTIONS });

  server.registerTool(
    "youstudio_video",
    {
      title: "영화 롱폼 리캡 제작",
      description:
        "영화 원본 한 편으로 롱폼 리캡을 만든다. 서버가 돌려주는 next_step 의 지시를 순서대로 그대로 실행하라. 지시를 임의로 해석하거나 개선하지 마라.",
      inputSchema: ToolInputSchema,
    },
    async (input) => {
      const { step, preset, source, payload } = input;
      const handler = HANDLERS[step];
      const res: StepResponse = await handler.run({ step, preset, source, payload: payload ?? {} });
      return {
        // 사람이 읽을 요약 한 줄 + 기계가 읽을 전체 JSON
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        structuredContent: res as unknown as Record<string, unknown>,
        isError: res.status === "error",
      };
    },
  );

  return server;
}
