/**
 * schema.ts — 도구 입력 모양(zod)과 서버 응답 모양(TypeScript 타입).
 *
 * 입력은 zod 로 검사한다(MCP SDK 가 tools/list 에 JSON Schema 로도 내보낸다).
 * 응답은 볼케이노 문법을 따른다 — 설계/참고_runner.md 1-2 참조.
 */
import { z } from "zod";

// ── 단계 이름 ────────────────────────────────────────────────────────────
// 단계 순서(상태 기계)는 프리셋마다 다르다 — styles.ts 등록표의 steps 가 정본이다.
// 여기의 STEP_ORDER 는 입력 검사용 「모든 프리셋 단계의 합집합」일 뿐, 순서 판정에 쓰지 않는다.
import { ALL_STEPS, PRESETS, DEFAULT_PRESET, type Preset, type StyleStep } from "./styles.js";
export const STEP_ORDER = ALL_STEPS;
export type Step = StyleStep;
export { PRESETS };
export type { Preset };

// ── 소재 ────────────────────────────────────────────────────────────────
// 영화롱폼 = 로컬 영상 파일 · 스케치코미디 = 유튜브 롱폼 URL.
export const SourceSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("local_video"),
    path: z.string().min(1).describe("영화 원본 파일의 절대경로"),
    title: z.string().optional().describe("영화 제목 (개봉연도) — 예: '영화 제목 (2024)'"),
    lang: z.string().optional().describe("원어 코드 — 예: en, ko, ja"),
  }),
  z.object({
    kind: z.literal("youtube"),
    url: z.string().min(1).describe("유튜브 롱폼 URL (스케치코미디 소재)"),
    slug: z.string().optional().describe("편 이름 — 한 소재 두 편이면 <id>_A · <id>_B"),
    focus_sec: z.number().optional().describe("B 편 전용 — 다른 웃음 클러스터의 초 지점 (댓글 타임스탬프 참고)"),
  }),
]);
export type Source = z.infer<typeof SourceSchema>;

// ── 도구 입력 ────────────────────────────────────────────────────────────
export const ToolInputSchema = z.object({
  step: z.enum(STEP_ORDER).describe(
    "맨 처음은 'setup'(준비 확인). 준비가 끝났으면 'start' 로 소재를 준다. 이후는 서버가 next_step 으로 지시한 값을 그대로.",
  ),
  preset: z.enum(PRESETS).default(DEFAULT_PRESET).describe("채널 규격 이름 (스타일/<이름>/ 폴더)"),
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

/** 외부 전사 호출 한 건. 키 값은 절대 담지 않는다 — auth 는 "어디서 읽어라"만 */
export interface TranscribeJob {
  name: string;
  provider: "groq" | "speechmatics";
  /** 비동기 배치 API 인가 (speechmatics: 제출 → 폴링 → 받기). runner 가 이 절차를 밟는다 */
  batch?: { submit_url: string; status_url: string; transcript_url: string; poll_s: number; timeout_s: number };
  model: string;
  /** HTTP 요청 명세. runner 는 이대로 보낸다 */
  request: {
    method: "POST";
    url: string;
    /** multipart/form-data 필드. 값이 "@<경로>" 면 파일 업로드 */
    multipart: Record<string, string>;
  };
  /** 키 위치. env 이름만 — 서버는 키를 보관하지 않는다 */
  auth: { env: string; header: string; note: string };
  /** 응답 본문(JSON)을 이 파일에 그대로 저장 */
  out: string;
  note?: string;
}

/** 외부 모델 판정 한 건 (jobs_kind:"judge"). 프롬프트·바디는 서버가 조립하고, 큰 입력(전사 등)은 inputs 로 파일 치환만 지시한다 */
export interface JudgeJob {
  name: string;
  provider: "evolink" | "google";
  model: string;
  /** HTTP 요청 명세. runner 는 inputs 치환 뒤 이대로 보낸다 */
  request: {
    method: "POST";
    url: string;
    headers: Record<string, string>;
    /** JSON 바디. 문자열 안의 placeholder 를 inputs 로 치환한다 */
    body: Record<string, unknown>;
  };
  /** 파일 내용을 바디의 placeholder 자리에 문자열로 넣는다 (payload 에 본문을 싣지 않기 위함) */
  inputs: { placeholder: string; path: string; note?: string }[];
  /**
   * 미디어 표식 파트 — body.contents[].parts[] 안에 아래 모양이 있으면 runner 가 실제 파트로 바꾼다.
   *   {"@inline_file": {path, mime}} → {inline_data: {mime_type, data: <base64>}}          (프레임 jpg 등 작은 파일)
   *   {"@file_uri":    {path, mime}} → Files API 업로드 → {file_data: {mime_type, file_uri}} (영상 클립. Google 순정 전용, state ACTIVE 까지 대기)
   * 이 칸은 안내용 — 어떤 표식을 몇 개 썼는지. 판단은 파트 자체가 한다.
   */
  media?: { kind: "@inline_file" | "@file_uri"; count: number; note?: string };
  /** 키 위치. env 이름만 — 서버는 키를 보관하지 않는다 */
  auth: { env: string; header: string; note: string };
  /** 응답 본문(JSON)을 이 파일에 그대로 저장 */
  out: string;
  note?: string;
}

/** TTS 합성 한 건 (jobs_kind:"synthesize"). 키 값은 절대 담지 않는다 */
export interface SynthesizeJob {
  name: string;
  /** elevenlabs = 영화롱폼 · typecast = 린박스(볼케이노 stitch_narr 꼴 — X-API-KEY, wav 응답) */
  provider: "elevenlabs" | "typecast";
  model: string;
  voice_id: string;
  request: { method: "POST"; url: string; headers: Record<string, string>; body: Record<string, unknown> };
  auth: { env: string; header: string; note: string };
  /** 응답 본문(바이너리)을 이 파일에 그대로 저장 */
  out: string;
  note?: string;
}

export type Job = ArgvJob | TranscribeJob | JudgeJob | SynthesizeJob;

/** 서버가 내용을 정하고 runner 가 파일로 쓴다 (볼케이노 write_files) */
export interface WriteFile {
  path: string;
  /** 문자열이면 그대로, 객체면 JSON(들여쓰기 2)으로 쓴다 */
  content: string | Record<string, unknown>;
  note?: string;
}

export interface MeasureRule {
  /** payload 의 어느 칸에 넣을지 */
  as: string;
  /** 어디서 재는지 — `job:<name>` */
  from: string;
  /**
   * 어떻게 읽는지.
   * stderr = 명령의 표준오류 전문(문자열). ffmpeg 필터 로그(silencedetect)처럼 stderr 로만 나오는 측정값용
   * bytes = 응답 본문의 바이트 수 (숫자). 바이너리 응답(TTS pcm)의 길이 계산용
   * tts_timestamps = ElevenLabs with-timestamps 응답(JSON). runner 는 audio_base64 를 디코드해 out 파일(pcm)로 저장하고,
   *   payload 에는 {audio_bytes: <디코드된 바이트 수>, alignment: {characters[], character_start_times_seconds[], character_end_times_seconds[]}} 만 넣는다 (base64 는 싣지 않는다)
   * gemini_json_text = 응답의 candidates[0].content.parts[].text 를 이어 붙여 JSON.parse 한 것.
   *   finishReason 이 STOP 이 아니면(MAX_TOKENS 등) 잘린 것 — 여기서 멈추고 오류로 보고한다 (참고_runner.md 「EvoLink 호출 규약」)
   */
  unit: "json_stdout" | "stdout" | "stdout_first_line" | "stderr" | "seconds" | "gemini_json_text" | "bytes" | "tts_timestamps";
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
  /** jobs 앞에 실행하는 준비용 로컬 명령(argv). 볼케이노 do[] 와 이름은 같지만 순서는 앞 — 우리 argv 는 전사·판정의 입력을 만든다 (설계/단계상세.md 「응답 칸」) */
  do?: ArgvJob[];
  /** 기계 일감 묶음. 종류는 jobs_kind 가 선언한다 (모양으로 추측하지 않는다) */
  jobs: Job[];
  jobs_kind: JobsKind | null;
  /** jobs 뒤에 실행하는 로컬 명령(argv) — 예: 받은 pcm 을 wav 로 감싸기. do → jobs → post → write_files → measure 순 */
  post?: ArgvJob[];
  /** 서버가 정한 내용을 runner 가 파일로 쓴다. jobs 뒤, measure 앞 */
  write_files?: WriteFile[];
  /** runner 에게 주는 측정 규칙 — 무엇을 재서 payload 어느 칸에 넣을지 (볼케이노 문법) */
  measure: MeasureRule[];
  /**
   * 이 단계가 뱉는 숫자 (HARNESS 4장 관측 가능성). 서버가 계산한 결과이지 지시가 아니다.
   * metrics 는 나중에 우리실측.json 에 쌓이는 원천이다 — 게이트는 이 숫자를 정답지 대역과 비교한다.
   */
  metrics: Record<string, unknown>;
  /** 이 응답의 값 중 다음 호출 payload 에 그대로 실어 보낼 키 */
  carry: string[];
  /** 화면에 그대로 찍을 안내 · 경고 */
  message?: string;
  warnings?: string[];
  /** 그 외 단계별 데이터 (spec, workdir 등). carry 로 지목되면 payload 로 돌아온다 */
  [extra: string]: unknown;
}
