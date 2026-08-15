/**
 * steps/brief.ts — 전사 전문을 읽고 사건 목록. 명세: 설계/단계상세.md 「3. brief」
 *
 * 두 번 부른다:
 *   ① payload.brief 가 없으면 → 지시. jobs_kind:"judge". 서버가 프롬프트·바디를 조립하고
 *      전사는 inputs 로 "transcript.json 파일 내용을 이 자리에 넣어라"만 지시한다 (전사 본문은 payload 에 안 실림 — 컨텍스트 보호).
 *      키는 auth 로 "EVOLINK_API_KEY 환경변수" 위치만. 원본 응답은 brief/brief_raw.json.
 *   ② payload.brief(모델 JSON) 가 있으면 → 검사. 사건 0건 / 타임코드 범위 밖이면 반려 + 수리 지침.
 *      통과하면 정리한 brief.json 을 write_files 로 쓰게 하고 metrics 를 뱉는다. next_step=select
 *
 * 설정값(backend·모델·온도·사건 수 목표)은 전부 스타일/영화롱폼/규격.json 「판정」에서 온다.
 * 호출 규약: 설계/참고_runner.md 「EvoLink 호출 규약」.
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";

interface JudgeSpec {
  텍스트: {
    backend: "evolink" | "google"; 모델: string; 엔드포인트: string; 키_환경변수: string;
    온도: number; thinkingBudget: number; maxOutputTokens: number; responseMimeType: string;
  };
  brief: { 사건_평균길이_목표_s: number; 사건수_최소: number; 사건수_최대: number; 중요도_범위: [number, number]; 타임코드_허용오차_s: number };
}
const J = (spec as unknown as { 판정: JudgeSpec })["판정"];

function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}
const r3 = (x: number) => Math.round(x * 1000) / 1000;

const PLACEHOLDER = "{{TRANSCRIPT_JSON}}";

/** 사건 수 목표 — 원본 길이 / 목표 평균 길이, 최소·최대로 자른다 (규격.json 판정.brief) */
export function targetEventCount(durationS: number): number {
  const n = Math.round(durationS / J.brief.사건_평균길이_목표_s);
  return Math.min(J.brief.사건수_최대, Math.max(J.brief.사건수_최소, n));
}

function buildPrompt(title: string | null, durationS: number, target: number): string {
  const [lo, hi] = J.brief.중요도_범위;
  return [
    `너는 영화 분석가다. 아래는 영화 ${title ? `「${title}」` : "한 편"}의 **전사 전체**다 (JSON. utterances[] 의 start·end 는 초, text 는 발화). 원본 길이는 ${durationS}초다.`,
    "이것만 보고 줄거리를 **사건 단위**로 재구성하라. 밖의 지식으로 채우지 말고, 여기 있는 것만 써라. 확실하지 않으면 단정하지 마라.",
    "",
    "규칙:",
    `· 사건은 시간순으로, 처음(0초)부터 마지막 발화까지 **빠짐없이** 덮어라. 앞쪽만 촘촘히 쓰고 중간에서 끊지 마라.`,
    `· 사건 수는 ${target}개 내외. 길이를 균등하게 맞추지 마라 — 사건이 짧으면 짧게, 길면 길게.`,
    `· start·end 는 utterances 의 start·end 초 값을 그대로 옮겨 적어라. 0 이상 ${durationS} 이하여야 한다. 사건끼리 겹치지 않게 하라.`,
    `· summary 는 **한국어** 한 문장(60자 이내). 누가 무엇을 했는지. 인물 이름이 대사에 나오면 그 이름을 한글로 옮겨 쓰고(성은 뺀다), 안 나오면 대사에서 드러나는 지칭을 써라.`,
    `· importance 는 ${lo}~${hi} 정수. ${hi}=이야기가 꺾이는 결정적 사건, ${lo}=있어도 없어도 되는 잔가지.`,
    "· spoiler 는 결말·핵심 반전·생사·승패를 드러내는 사건이면 true.",
    "",
    "## 출력 — JSON 객체 하나만 (설명 문장·코드펜스 금지)",
    '{"logline":"<한 문장 줄거리, 40자 이내>","events":[{"n":1,"start":<초>,"end":<초>,"summary":"<한국어 한 문장>","importance":<정수>,"spoiler":<true|false>}]}',
    "",
    "## 전사",
    PLACEHOLDER,
  ].join("\n");
}

/**
 * 출력 스키마 (Gemini structured output — generationConfig.responseSchema).
 * 근거: 첫 실호출(Full Time, 2026-08-15)에서 모델이 summary 를 전사의 키 이름을 흉내 내 "text"/"address" 로 바꿔 냈다.
 * 프롬프트 문장만으로는 키가 흔들린다 — 스키마로 고정한다. 값의 범위(0~길이, 1~5)는 서버가 ② 에서 검사한다.
 */
function responseSchema() {
  const [lo, hi] = J.brief.중요도_범위;
  return {
    type: "OBJECT",
    properties: {
      logline: { type: "STRING", description: "한 문장 줄거리, 40자 이내" },
      events: {
        type: "ARRAY",
        items: {
          type: "OBJECT",
          properties: {
            n: { type: "INTEGER", description: "순번 1부터" },
            start: { type: "NUMBER", description: "시작 초" },
            end: { type: "NUMBER", description: "끝 초" },
            summary: { type: "STRING", description: "한국어 한 문장 60자 이내" },
            importance: { type: "INTEGER", description: `${lo}~${hi}` },
            spoiler: { type: "BOOLEAN" },
          },
          required: ["n", "start", "end", "summary", "importance", "spoiler"],
        },
      },
    },
    required: ["logline", "events"],
  };
}

interface RawEvent { n?: number; start?: number; end?: number; summary?: string; importance?: number; spoiler?: boolean }
interface RawBrief { logline?: string; events?: RawEvent[] }

export const brief: StepHandler = {
  name: "brief",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; lang?: string; title?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number } | undefined;
    const transcriptPath = typeof payload.transcript_path === "string" ? payload.transcript_path : "";

    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !transcriptPath) {
      return reject(
        "brief", preset,
        "payload 에 carry 값(source·workdir·probe_summary·transcript_path)이 없다",
        "transcript 응답의 source·workdir·probe_summary·transcript_path 를 payload 에 그대로 실어 brief 를 다시 부르라.",
      );
    }
    const durationS = ps.duration_s;
    const rawPath = join(workdir, "brief", "brief_raw.json");
    const outPath = join(workdir, "brief", "brief.json");
    const T = J.텍스트;
    const target = targetEventCount(durationS);

    // ── ① 지시 ──────────────────────────────────────────────────────────
    if (payload.brief === undefined) {
      const url = T.엔드포인트.replace("{model}", T.모델);
      const body = {
        contents: [{ role: "user", parts: [{ text: buildPrompt(source.title ?? null, durationS, target) }] }],
        generationConfig: {
          temperature: T.온도,
          thinkingConfig: { thinkingBudget: T.thinkingBudget },
          maxOutputTokens: T.maxOutputTokens,
          responseMimeType: T.responseMimeType,
          responseSchema: responseSchema(),
        },
      };
      return base("brief", preset, {
        status: "execute",
        next_step: "brief",
        message: `판정 지시: transcript.json 을 ${T.backend}/${T.모델} 에 보내 사건 ${target}개 내외를 받아라. 결과 JSON 을 payload.brief 에 실어 brief 를 다시 부르라.`,
        instructions: [
          `① jobs 의 judge 를 그대로 보낸다. 먼저 inputs 대로 ${transcriptPath} 파일 내용을 바디의 ${PLACEHOLDER} 자리에 문자열로 넣는다. 전사 본문을 payload 나 대화에 옮겨 적지 않는다.`,
          `② 키는 auth 대로 환경변수 ${T.키_환경변수} 에서 읽어 헤더에 붙인다. 키 값을 화면·파일·payload 에 쓰지 않는다. 응답 JSON 을 out 경로에 저장한다.`,
          "③ measure 대로 응답의 candidates[0].content.parts[].text 를 이어 붙여 JSON 으로 파싱해 payload.brief 에 넣는다. finishReason 이 STOP 이 아니면(MAX_TOKENS 등) 잘린 것이다 — 멈추고 사람에게 보고한다. 응답이 {error:…} 면 그 메시지를 보여주고 멈춘다.",
          "④ carry 값과 함께 brief 를 다시 부른다.",
        ],
        then_call_with: [
          "step: 'brief'",
          "payload: { workdir, source, probe_summary, transcript_path, brief: <모델이 낸 JSON 객체> }",
        ],
        jobs_kind: "judge",
        jobs: [
          {
            name: "brief_judge",
            provider: T.backend,
            model: T.모델,
            request: { method: "POST", url, headers: { "Content-Type": "application/json" }, body },
            inputs: [{ placeholder: PLACEHOLDER, path: transcriptPath, note: "transcript.json 전체를 문자열로 치환. 전사는 파일→요청으로만 흐른다" }],
            auth: {
              env: T.키_환경변수,
              header: `Authorization: Bearer <${T.키_환경변수} 값>`,
              note: "서버는 키를 보관하지 않는다. runner 가 로컬 환경변수에서 읽어 붙인다.",
            },
            out: rawPath,
            note: "Google-Native v1beta generateContent. JSON 강제 · thinkingBudget 0 · maxOutputTokens 명시 (참고_runner.md 「EvoLink 호출 규약」)",
          },
        ],
        measure: [{ as: "brief", from: "job:brief_judge", unit: "gemini_json_text" }],
        carry: ["source", "workdir", "probe_summary", "transcript_path"],
        source, workdir, probe_summary: ps, transcript_path: transcriptPath,
        target_event_count: target,
      });
    }

    // ── ② 결과 검사 ──────────────────────────────────────────────────────
    const raw = payload.brief as RawBrief;
    if (typeof raw !== "object" || raw === null || !Array.isArray(raw.events)) {
      return reject(
        "brief", preset,
        "payload.brief 가 {logline, events[]} 모양이 아니다",
        `${rawPath} 의 candidates[0].content.parts[].text 를 JSON 으로 파싱한 객체를 payload.brief 에 실어 다시 부르라. 파싱이 안 되면(잘림·코드펜스) 판정을 다시 보내라 — 같은 jobs 를 한 번 더 실행.`,
      );
    }
    if (raw.events.length === 0) {
      return reject(
        "brief", preset,
        "hard_fail: 사건이 0건이다",
        `① ${rawPath} 를 열어 모델이 무엇을 돌려줬는지 본다 (거절·빈 응답·형식 오류). ② transcript.json 의 발화가 실제 대사인지 확인한다 (환청·노래 가사만이면 소재 문제). ③ 같은 judge 를 한 번 더 보낸다. 그래도 0건이면 사람에게 보고하고 멈춘다.`,
      );
    }

    const [lo, hi] = J.brief.중요도_범위;
    const tol = J.brief.타임코드_허용오차_s;
    const bad: string[] = [];
    const events = raw.events.map((e, idx) => {
      const n = idx + 1;
      const start = Number(e.start), endRaw = Number(e.end);
      const summary = String(e.summary ?? "").trim();
      const imp = Number(e.importance);
      if (!Number.isFinite(start) || !Number.isFinite(endRaw)) bad.push(`사건 ${n}: start/end 가 숫자가 아니다 (${e.start}, ${e.end})`);
      else {
        if (start < 0) bad.push(`사건 ${n}: start ${start} < 0`);
        if (endRaw > durationS + tol) bad.push(`사건 ${n}: end ${endRaw} > 원본 길이 ${durationS} (+허용오차 ${tol})`);
        if (start >= durationS) bad.push(`사건 ${n}: start ${start} ≥ 원본 길이 ${durationS}`);
        if (endRaw <= start) bad.push(`사건 ${n}: end ${endRaw} ≤ start ${start}`);
      }
      if (!summary) bad.push(`사건 ${n}: summary 가 비었다`);
      if (!Number.isInteger(imp) || imp < lo || imp > hi) bad.push(`사건 ${n}: importance ${e.importance} 가 ${lo}~${hi} 정수가 아니다`);
      const end = Math.min(endRaw, durationS);
      return { n, start: r3(start), end: r3(end), summary, importance: imp, spoiler: e.spoiler === true };
    });

    if (bad.length > 0) {
      return reject(
        "brief", preset,
        `판정 결과가 범위 밖이다 — ${bad.length}건: ${bad.slice(0, 5).join(" / ")}${bad.length > 5 ? " / …" : ""}`,
        `사건의 start·end 는 0~${durationS}초, importance 는 ${lo}~${hi} 정수, summary 는 비면 안 된다. 같은 jobs 의 judge 를 한 번 더 보내라 (프롬프트에 원본 길이가 이미 명시돼 있다 — 온도 ${T.온도} 라 재시도로 대개 잡힌다). 두 번 연속 실패면 규격.json 판정.텍스트.온도 를 낮추거나 모델을 바꾸고 사람에게 보고하라.`,
      );
    }

    events.sort((a, b) => a.start - b.start);
    events.forEach((e, i) => { e.n = i + 1; });

    // 지표 — 산출물에서 독립 계산
    const count = events.length;
    const avgLen = r3(events.reduce((a, e) => a + (e.end - e.start), 0) / count);
    // 커버리지 = 사건 구간의 합집합 길이 / 원본 길이
    let covered = 0, curS = -1, curE = -1;
    for (const e of events) {
      if (e.start > curE) { if (curE > curS) covered += curE - curS; curS = e.start; curE = e.end; }
      else if (e.end > curE) curE = e.end;
    }
    if (curE > curS) covered += curE - curS;
    const coverage = r3(covered / durationS);
    let overlaps = 0, maxGap = 0;
    for (let i = 1; i < events.length; i++) {
      if (events[i].start < events[i - 1].end) overlaps++;
      maxGap = Math.max(maxGap, events[i].start - events[i - 1].end);
    }
    maxGap = r3(Math.max(maxGap, events[0].start, durationS - events[events.length - 1].end));

    const warnings: string[] = [];
    if (count < J.brief.사건수_최소) warnings.push(`사건 ${count}건 — 목표 하한 ${J.brief.사건수_최소} 미만. select 에서 고를 폭이 좁을 수 있다.`);
    if (count > J.brief.사건수_최대) warnings.push(`사건 ${count}건 — 목표 상한 ${J.brief.사건수_최대} 초과.`);
    if (overlaps > 0) warnings.push(`사건끼리 겹치는 곳 ${overlaps}건.`);
    if (coverage < 0.8) warnings.push(`커버리지 ${coverage} — 사건이 덮지 않는 시간이 20% 넘는다 (가장 긴 빈틈 ${maxGap}s). 대사 없는 구간이 많은 영화면 정상일 수 있다.`);

    const briefDoc = {
      source: source.path,
      title: source.title ?? null,
      judge: { provider: T.backend, model: T.모델, raw: rawPath, transcript: transcriptPath },
      duration_s: durationS,
      logline: String(raw.logline ?? "").trim() || null,
      event_count: count,
      avg_event_len_s: avgLen,
      coverage,
      warnings,
      events,
    };

    return base("brief", preset, {
      status: "execute",
      next_step: "select",
      message: `사건 목록 통과: ${count}건 · 평균 ${avgLen}s · 커버리지 ${coverage}. write_files 를 쓰고 select 로 넘어가라.`,
      instructions: [
        `① write_files 의 내용을 그대로 ${outPath} 에 쓴다.`,
        "② metrics 를 사람에게 한 줄로 보여준다. 사건 목록(n·start~end·importance·summary)은 사람이 볼 수 있게 표로 보여준다.",
        "③ carry 의 값(source·workdir·probe_summary·transcript_path·brief_path)을 payload 에 그대로 실어 next_step 을 부른다.",
        "④ select 는 아직 스텁이다 — 영상 판정용 구글 순정 키·조각 크기 결정 대기 (단계상세.md 미정 표).",
      ],
      then_call_with: ["step: 'select'", "payload: { workdir, source, probe_summary, transcript_path, brief_path }"],
      jobs_kind: null,
      jobs: [],
      write_files: [{ path: outPath, content: briefDoc, note: "사건 목록. select 의 입력" }],
      measure: [],
      metrics: { event_count: count, avg_event_len_s: avgLen, coverage, overlaps, max_gap_s: maxGap, target_event_count: target },
      carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path"],
      source, workdir, probe_summary: ps, transcript_path: transcriptPath, brief_path: outPath,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
