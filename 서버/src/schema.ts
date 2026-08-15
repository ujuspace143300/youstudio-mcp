/**
 * schema.ts — 도구 입력 모양(zod)과 서버 응답 모양(TypeScript 타입).
 *
 * 입력은 zod 로 검사한다(MCP SDK 가 tools/list 에 JSON Schema 로도 내보낸다).
 * 응답은 볼케이노 문법을 따른다 — 설계/참고_runner.md 1-2 참조.
 */
import { z } from "zod";

// ── 단계 이름과 순서 ─────────────────────────────────────────────────────
// 순서가 곧 상태 기계다. next_step 은 이 배열의 "다음 칸"이다.
export const STEP_ORDER = [
  "setup",
  "start",
  "probe",
  "transcript",
  "brief",
  "select",
  "script",
  "voice",
  "subtitle",
  "export",
] as const;
export type Step = (typeof STEP_ORDER)[number];

export const PRESETS = ["영화롱폼"] as const;
export type Preset = (typeof PRESETS)[number];

// ── 소재 ────────────────────────────────────────────────────────────────
// 영화롱폼은 로컬 영상 파일만 받는다. 종류가 늘면 여기 discriminated union 으로 추가한다.
export const SourceSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("local_video"),
    path: z.string().min(1).describe("영화 원본 파일의 절대경로"),
    title: z.string().optional().describe("영화 제목 (개봉연도) — 예: '영화 제목 (2024)'"),
    lang: z.string().optional().describe("원어 코드 — 예: en, ko, ja"),
  }),
]);
export type Source = z.infer<typeof SourceSchema>;

// ── 도구 입력 ────────────────────────────────────────────────────────────
export const ToolInputSchema = z.object({
  step: z.enum(STEP_ORDER).describe(
    "맨 처음은 'setup'(준비 확인). 준비가 끝났으면 'start' 로 소재를 준다. 이후는 서버가 next_step 으로 지시한 값을 그대로.",
  ),
  preset: z.enum(PRESETS).default("영화롱폼").describe("채널 규격 이름"),
  source: SourceSchema.optional().describe("소재. start 에서 한 번만 준다."),
  payload: z.record(z.string(), z.unknown()).optional().describe(
    "직전 단계에서 서버가 요청한 자료 (measure 결과, carry 값, 사람이 채운 값).",
  ),
});
export type ToolInput = z.infer<typeof ToolInputSchema>;

// ── 서버 응답 (볼케이노 문법) ─────────────────────────────────────────────
export type JobsKind = "argv" | "transcribe" | "synthesize" | "judge" | "generate_images" | "fetch_images";

export interface ArgvJob {
  /** 일감 이름. measure 가 `job:<name>` 으로 참조한다 */
  name: string;
  /** 실행할 명령줄. runner 는 한 글자도 고치지 않는다 */
  argv: string[];
  /** 표준출력을 이 파일에 그대로 저장한다(선언된 출력 — runner 가 부모 폴더를 먼저 만든다) */
  out?: string;
  /** 실패해도 건너뛸 수 있는가 */
  optional?: boolean;
  /** 사람이 읽을 메모 */
  note?: string;
}

export interface MeasureRule {
  /** payload 의 어느 칸에 넣을지 */
  as: string;
  /** 어디서 재는지 — `job:<name>` */
  from: string;
  /** 어떻게 읽는지 */
  unit: "json_stdout" | "stdout" | "stdout_first_line" | "seconds";
}

export interface StepResponse {
  /** execute = 기계가 할 일이 있다 · need_input = 사람(모델)이 채울 차례 · done = 끝 · not_implemented = 아직 없음 · error = 반려 */
  status: "execute" | "need_input" | "done" | "not_implemented" | "error";
  step: Step;
  preset: Preset;
  /** 다음에 부를 step. null 이면 종료 */
  next_step: Step | null;
  /** 다음 호출 때 무엇을 실어 보내야 하는지 — 사람이 읽는 안내문 */
  then_call_with: string[];
  /** 이 단계에서 runner/모델이 따라야 할 지시. 순서대로 그대로 실행한다 */
  instructions: string[];
  /** status=need_input 일 때 무엇이 왜 필요한지 */
  need_input: { keys: string[]; why: string } | null;
  /** 기계 일감 묶음. 종류는 jobs_kind 가 선언한다 (모양으로 추측하지 않는다) */
  jobs: ArgvJob[];
  jobs_kind: JobsKind | null;
  /** 무엇을 재서 payload 어느 칸에 넣을지 */
  measure: MeasureRule[];
  /** 이 응답의 값 중 다음 호출 payload 에 그대로 실어 보낼 키 */
  carry: string[];
  /** 화면에 그대로 찍을 안내 · 경고 */
  message?: string;
  warnings?: string[];
  /** 그 외 단계별 데이터 (spec, workdir 등). carry 로 지목되면 payload 로 돌아온다 */
  [extra: string]: unknown;
}
