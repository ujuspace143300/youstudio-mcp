/**
 * steps/select.ts — 쓸 구간 확정. 명세: 설계/단계상세.md 「4. select」(두 겹 판정 보강판)
 *
 * 두 번 부른다:
 *   ① payload.visual 가 없으면 → 지시. do[] 로 무음 구간 프레임(5s 간격)·결말 클립(15s)을 ffmpeg 로 뽑고,
 *      jobs_kind:"judge"(Google 순정 Gemini, auth env GEMINI_API_KEY) 로 무음 구간마다 프레임 판정 1콜 + 결말 클립 판정 1콜.
 *      프레임은 {"@inline_file"} 표식, 클립은 {"@file_uri"} 표식(Files API) 파트로 넣는다 — runner 가 실제 미디어로 바꾼다.
 *   ② payload.visual 가 있으면 → 검사·계산. 후보(brief 사건 + 시각 장면) → 우선순위 채움 → 창·병합 → 역할 → 게이트 → selection.json
 *
 * 설정값은 규격.json 「구간선택」「판정.영상」, 게이트 대역은 정답지.json 「구간선택」에서 온다.
 * 사람이 잰 소재 사실(크레딧 시작·무음 구간·시각 결말)은 <workdir>/facts.json → payload.facts 로 받는다.
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import answer from "../../../스타일/영화롱폼/정답지.json";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";
import type { JudgeJob, ArgvJob } from "../schema.js";

interface SelectSpec {
  목표길이: { 장편_기준_s: number; 장편_목표_s: number; 그외_목표_s: number };
  구간창_s: { min: number; max: number };
  총량계수: number;
  인접병합_간격_s: number;
  크레딧_이후_제외: boolean;
  시각판정: { 경계용_프레임_간격_s: number; 정서결말용_클립길이_s: number; 프레임_가로_px: number; 클립_가로_px: number };
  역할규칙: { 원본대사_최소중요도: number; 나레이션덮기_최대중요도: number; 무음장면_역할: string };
  결말포함: boolean;
  흡수규칙: { 흡수_최소중요도: number };
  결말_통째: boolean;
  브리지_최소_s: number;
}
interface ProviderSpec { 엔드포인트: string; 키_환경변수: string; 인증헤더: string; 파일업로드: string | null }
interface VideoJudgeSpec {
  backend: "evolink" | "google"; 모델: string;
  제공자: { evolink: ProviderSpec; google: ProviderSpec };
  클립전달: "inline" | "files_api"; 인라인_상한_mb: number;
  온도: number; thinkingBudget: number; maxOutputTokens: number; responseMimeType: string;
}
interface Band { min?: number; max?: number; value?: number; 출처: string; 적용: string }
interface SelectAnswer {
  "G-밀도": { 블록당_초: Band; 분당_블록수_환산: Band };
  "G-반복": { 컷_반복_비율_max: Band; 소스_점프_비율_max: Band; 인접_60s초과_점프_비율: Band };
}
const S = (spec as unknown as { 구간선택: SelectSpec })["구간선택"];
const V = (spec as unknown as { 판정: { 영상: VideoJudgeSpec } })["판정"]["영상"];
/** 규격 판정.영상.backend 가 가리키는 제공자 설정 (evolink 기본, google 스위치) */
const P: ProviderSpec = V.제공자[V.backend];
const A = (answer as unknown as { 구간선택: SelectAnswer })["구간선택"];

function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}
const r1 = (x: number) => Math.round(x * 10) / 10;
const r3 = (x: number) => Math.round(x * 1000) / 1000;

/** 목표 길이 — 규격.json 구간선택.목표길이 (가족 공식) */
export function targetLength(durationS: number): number {
  return durationS > S.목표길이.장편_기준_s ? S.목표길이.장편_목표_s : S.목표길이.그외_목표_s;
}

// ── 입력 모양 ────────────────────────────────────────────────────────────
interface Facts {
  credits_start_s?: number;
  ending_visual_only?: { start_s: number; end_s: number; note?: string };
  silent_visual_stretches?: { start_s: number; end_s: number; note?: string }[];
}
interface BriefEvent { n: number; start: number; end: number; summary: string; importance: number; spoiler?: boolean }
interface BriefDoc { events?: BriefEvent[] }
interface Scene { start: number; end: number; what: string; importance: number; people?: string; visual_facts?: string }
interface Beat { start: number; end: number; what: string; emotion?: string; importance: number; is_ending_beat?: boolean }
interface Visual { silent?: { scenes?: Scene[] }[]; ending?: { beats?: Beat[]; ending_summary?: string } | null }

// ── 판정 프롬프트 ────────────────────────────────────────────────────────
function framePrompt(title: string | null, a: number, b: number, note: string | undefined, interval: number): string {
  return [
    `너는 영화 편집자다. 아래는 영화 ${title ? `「${title}」` : ""}의 **대사가 없는 구간** ${a}~${b}초를 ${interval}초 간격으로 뽑은 프레임이다. 각 이미지 앞의 [t=…s] 가 그 프레임의 원본 시각이다.${note ? ` 사람이 적어 둔 메모: "${note}".` : ""}`,
    "프레임만 보고 이 구간에서 무슨 일이 벌어지는지 **장면(scene) 단위**로 나눠라. 밖의 지식으로 채우지 말고 보이는 것만 써라.",
    "규칙:",
    `· start·end 는 프레임의 t 값을 쓰되 ${a} 이상 ${b} 이하. 장면끼리 겹치지 않게, 시간순으로, 구간 전체를 덮어라 (아무 일도 없으면 그 자체가 한 장면 — "그대로 서 있음").`,
    "· what 은 **한국어** 한 문장(60자 이내): 누가·어디서·무엇을. people 은 보이는 인물(짧게). visual_facts 는 나중에 대본에 쓸 시각적 사실(옷차림 변화·시간대·소품 등, 없으면 빈 문자열).",
    "· importance 는 1~5 정수. 5=이야기가 바뀌는 시각적 사실(인물 변화·반전), 3=분위기·시간 경과, 1=반복·정지.",
    "· 프레임에 없는 사건을 상상하지 마라. 확실하지 않으면 what 에 '(불명확)' 을 붙여라.",
    "## 출력 — JSON 객체 하나만",
    '{"scenes":[{"start":<초>,"end":<초>,"what":"…","people":"…","visual_facts":"…","importance":<정수>}]}',
  ].join("\n");
}
function clipPrompt(title: string | null, a: number, b: number, note: string | undefined, clips: { start: number; end: number }[]): string {
  return [
    `너는 영화 편집자다. 아래는 영화 ${title ? `「${title}」` : ""}의 **결말부** ${a}~${b}초를 잘라 낸 클립 ${clips.length}개(영상+소리)다. 각 클립 앞의 텍스트가 그 클립의 원본 시각 범위다.${note ? ` 사람이 적어 둔 메모: "${note}".` : ""}`,
    "클립을 보고 들으며 결말이 어떻게 진행되는지 **감정 비트(beat) 단위**로 나눠라. 움직임·표정·소리(음악·효과음)로 알 수 있는 것을 써라. 밖의 지식으로 채우지 마라.",
    "규칙:",
    `· start·end 는 원본 시각(초). 클립 범위 안에서 정하고 ${a} 이상 ${b} 이하. 비트끼리 겹치지 않게, 시간순으로.`,
    "· what 은 **한국어** 한 문장(60자 이내). emotion 은 그 비트의 정서(짧게: 쓸쓸함·해방감·충격 등). is_ending_beat 는 이야기가 실제로 끝나는 비트면 true.",
    "· importance 는 1~5 정수. 5=결말의 핵심(무슨 일이 일어났는지 결정하는 순간), 1=여운·풍경.",
    "· 화면이 검게 되는 구간(블랙)은 그대로 '블랙' 비트로 적어라. 넘어짐·쓰러짐처럼 뜻이 갈리는 동작은 보이는 대로 적고 해석은 '(해석: …)' 로 구분하라.",
    "· ending_summary 는 결말 전체를 한국어 두 문장으로.",
    "## 출력 — JSON 객체 하나만",
    '{"ending_summary":"…","beats":[{"start":<초>,"end":<초>,"what":"…","emotion":"…","importance":<정수>,"is_ending_beat":<true|false>}]}',
  ].join("\n");
}
const SCENE_SCHEMA = {
  type: "OBJECT",
  properties: { scenes: { type: "ARRAY", items: { type: "OBJECT", properties: {
    start: { type: "NUMBER" }, end: { type: "NUMBER" }, what: { type: "STRING" }, people: { type: "STRING" }, visual_facts: { type: "STRING" }, importance: { type: "INTEGER" },
  }, required: ["start", "end", "what", "people", "visual_facts", "importance"] } } },
  required: ["scenes"],
};
const BEAT_SCHEMA = {
  type: "OBJECT",
  properties: { ending_summary: { type: "STRING" }, beats: { type: "ARRAY", items: { type: "OBJECT", properties: {
    start: { type: "NUMBER" }, end: { type: "NUMBER" }, what: { type: "STRING" }, emotion: { type: "STRING" }, importance: { type: "INTEGER" }, is_ending_beat: { type: "BOOLEAN" },
  }, required: ["start", "end", "what", "emotion", "importance", "is_ending_beat"] } } },
  required: ["ending_summary", "beats"],
};
function genConfig(schema: unknown) {
  return { temperature: V.온도, thinkingConfig: { thinkingBudget: V.thinkingBudget }, maxOutputTokens: V.maxOutputTokens, responseMimeType: V.responseMimeType, responseSchema: schema };
}

// ── 후보·선택 ────────────────────────────────────────────────────────────
interface Candidate { in: number; out: number; importance: number; kind: "dialogue" | "visual" | "ending"; src: string; why: string }
interface Segment { in: number; out: number; role: string; src: string[]; why: string; importance: number; kind: Candidate["kind"] }

export const select: StepHandler = {
  name: "select",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; title?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number } | undefined;
    const briefDoc = payload.brief as BriefDoc | undefined;
    const facts = (payload.facts ?? {}) as Facts;
    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !briefDoc || !Array.isArray(briefDoc.events)) {
      return reject(
        "select", preset,
        "payload 에 carry 값(source·workdir·probe_summary) 또는 brief(사건 목록)가 없다",
        "brief 응답의 carry 값과 함께 payload.brief 에 brief.json 의 내용, payload.facts 에 <workdir>/facts.json 의 내용(없으면 {}), payload.utterance_spans 에 transcript.json 의 [start,end] 배열을 실어 select 를 다시 부르라.",
      );
    }
    const durationS = ps.duration_s;
    const title = source.title ?? null;
    const creditsStart = typeof facts.credits_start_s === "number" ? facts.credits_start_s : null;
    const usableEnd = S.크레딧_이후_제외 && creditsStart !== null ? creditsStart : durationS;
    const stretches = (facts.silent_visual_stretches ?? []).filter((x) => x && typeof x.start_s === "number" && typeof x.end_s === "number" && x.end_s > x.start_s);
    const ending = facts.ending_visual_only && typeof facts.ending_visual_only.start_s === "number" ? facts.ending_visual_only : null;
    const target = targetLength(durationS);
    const budget = r3(target * S.총량계수);
    const clipsDir = join(workdir, "clips");
    const warnings: string[] = [];
    if (creditsStart === null) warnings.push("facts.json 에 credits_start_s 가 없다 — 크레딧 제외를 못 한다. 사람이 재서 적어라 (blackdetect + 프레임 스윕).");
    if (stretches.length === 0) warnings.push("facts.json 에 silent_visual_stretches 가 없다 — 무음 구간 시각 판정을 건너뛴다. 대사 없는 긴 구간이 있으면 반드시 적어라 (단계상세.md select).");

    // ── ① 지시 ──────────────────────────────────────────────────────────
    if (payload.visual === undefined) {
      const url = P.엔드포인트.replace("{model}", V.모델);
      const doJobs: ArgvJob[] = [];
      const jobs: JudgeJob[] = [];
      const useFilesApi = V.클립전달 === "files_api";
      if (useFilesApi && !P.파일업로드) {
        return reject("select", preset, `규격 판정.영상.클립전달=files_api 인데 backend=${V.backend} 에는 Files API 가 없다`, "규격.json 판정.영상.backend 를 google 로 바꾸거나 클립전달 을 inline 으로 바꿔라 (인라인 상한 안이면 inline 이 기본).");
      }
      const auth = { env: P.키_환경변수, header: P.인증헤더.replace("<키>", `<${P.키_환경변수} 값>`), note: `${V.backend}. 서버는 키를 보관하지 않는다 — runner 가 로컬 환경변수에서 읽어 헤더에 붙인다.${useFilesApi ? " Files API 업로드도 같은 키." : ""}` };
      const measure: { as: string; from: string; unit: "gemini_json_text" }[] = [];

      // (a) 무음 구간 프레임 판정 — 구간마다 1콜
      const iv = S.시각판정.경계용_프레임_간격_s;
      stretches.forEach((st, k) => {
        const a = r1(st.start_s), b = r1(Math.min(st.end_s, usableEnd));
        if (b - a < iv) return;
        const dir = join(clipsDir, `frames_silent_${k}`);
        const n = Math.max(1, Math.ceil((b - a) / iv)); // ffmpeg fps=1/iv 가 내는 장수 (0, iv, 2iv … < 길이)
        doJobs.push({
          name: `frames_silent_${k}`,
          argv: ["ffmpeg", "-y", "-v", "error", "-ss", String(a), "-to", String(b), "-i", source.path!, "-vf", `fps=1/${iv},scale=${S.시각판정.프레임_가로_px}:-2`, "-q:v", "3", "-pix_fmt", "yuvj420p", "-strict", "unofficial", join(dir, "f_%03d.jpg")],
          note: `${a}~${b}s 를 ${iv}s 간격으로 ${n}장. f_001 = ${a}s, f_002 = ${a + iv}s …`,
        });
        const parts: unknown[] = [{ text: framePrompt(title, a, b, st.note, iv) }];
        for (let i = 0; i < n; i++) {
          const t = r1(a + i * iv);
          parts.push({ text: `[t=${t}s]` });
          parts.push({ "@inline_file": { path: join(dir, `f_${String(i + 1).padStart(3, "0")}.jpg`), mime: "image/jpeg" } });
        }
        jobs.push({
          name: `judge_silent_${k}`, provider: V.backend, model: V.모델,
          request: { method: "POST", url, headers: { "Content-Type": "application/json" }, body: { contents: [{ role: "user", parts }], generationConfig: genConfig(SCENE_SCHEMA) } },
          inputs: [], media: { kind: "@inline_file", count: n, note: "프레임 jpg 를 base64 inline_data 로" },
          auth, out: join(clipsDir, "judge", `silent_${k}.json`),
          note: `무음 구간 ${a}~${b}s 프레임 ${n}장 → 장면 목록 (경계용)`,
        });
        measure.push({ as: `visual.silent.${k}`, from: `job:judge_silent_${k}`, unit: "gemini_json_text" });
      });

      // (b) 결말 클립 판정 — 1콜 (Files API)
      if (ending) {
        const a = r1(ending.start_s), b = r1(Math.min(ending.end_s, usableEnd));
        const L = S.시각판정.정서결말용_클립길이_s;
        const clips: { start: number; end: number; path: string }[] = [];
        for (let t = a, i = 0; t < b - 1; t += L, i++) {
          const e = r1(Math.min(t + L, b));
          const path = join(clipsDir, "ending", `clip_${String(i + 1).padStart(2, "0")}.mp4`);
          clips.push({ start: r1(t), end: e, path });
          doJobs.push({
            name: `clip_ending_${i + 1}`,
            argv: ["ffmpeg", "-y", "-v", "error", "-ss", String(r1(t)), "-to", String(e), "-i", source.path!, "-vf", `scale=${S.시각판정.클립_가로_px}:-2`, "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", path],
            note: `결말 클립 ${r1(t)}~${e}s (영상+소리)`,
          });
        }
        const parts: unknown[] = [{ text: clipPrompt(title, a, b, ending.note, clips) }];
        for (const c of clips) {
          parts.push({ text: `클립 ${c.start}~${c.end}s:` });
          parts.push(useFilesApi ? { "@file_uri": { path: c.path, mime: "video/mp4" } } : { "@inline_file": { path: c.path, mime: "video/mp4" } });
        }
        jobs.push({
          name: "judge_ending", provider: V.backend, model: V.모델,
          request: { method: "POST", url, headers: { "Content-Type": "application/json" }, body: { contents: [{ role: "user", parts }], generationConfig: genConfig(BEAT_SCHEMA) } },
          inputs: [],
          media: useFilesApi
            ? { kind: "@file_uri", count: clips.length, note: `Files API(${P.파일업로드}) 업로드 → state ACTIVE 대기 → file_data` }
            : { kind: "@inline_file", count: clips.length, note: `클립 mp4 를 base64 inline_data 로 (요청 합계 ≤ ${V.인라인_상한_mb}MB — 넘으면 규격 판정.영상 을 google + files_api 로)` },
          auth, out: join(clipsDir, "judge", "ending.json"),
          note: `결말 ${a}~${b}s 클립 ${clips.length}개(각 ≤${L}s, 영상+소리) → 감정 비트 (정서·결말용)`,
        });
        measure.push({ as: "visual.ending", from: "job:judge_ending", unit: "gemini_json_text" });
      }

      return base("select", preset, {
        status: "execute",
        next_step: "select",
        message: `시각 판정 지시: 무음 구간 ${stretches.length}개 프레임 판정 + 결말 클립 판정 ${ending ? 1 : 0}콜 (${V.backend}/${V.모델}, 클립 ${V.클립전달}). 결과를 payload.visual 에 실어 select 를 다시 부르라. 목표 ${target}s · 예산 ${budget}s · 크레딧 ${creditsStart ?? "미상"}s 이후 제외.`,
        instructions: [
          "① do[] 의 ffmpeg 를 순서대로 그대로 실행한다 (프레임 폴더·클립 파일이 생긴다).",
          `② jobs 의 judge 를 그대로 보낸다. 파트 안의 {"@inline_file"} 은 파일을 base64 로 읽어 inline_data 로 바꾼다${useFilesApi ? `, {"@file_uri"} 는 Files API(${P.파일업로드})에 올려 state 가 ACTIVE 가 된 뒤 file_data 로 바꾼다` : ""}. 키는 auth 대로 환경변수 ${P.키_환경변수} 에서 읽어 헤더(${P.인증헤더.split(":")[0]})에 붙인다. 키 값을 화면·파일·payload 에 쓰지 않는다. 응답 JSON 은 out 경로에 저장한다.`,
          "③ measure 대로 각 응답의 candidates[0].content.parts[].text 를 JSON 으로 파싱해 payload.visual.silent[k] / payload.visual.ending 에 넣는다. finishReason 이 STOP 이 아니면 멈추고 보고한다.",
          "④ carry 값(source·workdir·probe_summary·transcript_path·brief_path·brief·facts·utterance_spans)과 함께 select 를 다시 부른다.",
        ],
        then_call_with: ["step: 'select'", "payload: { …carry, visual: { silent: [<장면 JSON>…], ending: <비트 JSON> | null } }"],
        do: doJobs,
        jobs_kind: "judge",
        jobs,
        measure,
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "brief", "facts", "utterance_spans"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, brief: briefDoc, facts, utterance_spans: payload.utterance_spans ?? [],
        plan: { backend: V.backend, model: V.모델, clip_transfer: V.클립전달, target_s: target, budget_s: budget, usable_end_s: usableEnd, silent_stretches: stretches.length, ending_clips: ending ? Math.ceil((Math.min(ending.end_s, usableEnd) - ending.start_s) / S.시각판정.정서결말용_클립길이_s) : 0 },
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ② 결과 검사·계산 ────────────────────────────────────────────────
    const visual = payload.visual as Visual;
    if (typeof visual !== "object" || visual === null) {
      return reject("select", preset, "payload.visual 가 객체가 아니다", "① 의 measure 대로 {silent:[…], ending:{…}} 를 payload.visual 에 실어 다시 부르라.");
    }
    const silentResults = Array.isArray(visual.silent) ? visual.silent : [];
    if (stretches.length > 0 && silentResults.length < stretches.length) {
      return reject(
        "select", preset,
        `hard_fail: 무음 구간 판정 결과가 부족하다 (${silentResults.length}/${stretches.length})`,
        "무음 구간은 반드시 시각 판정 대상이다 (단계상세.md select). ① 의 judge_silent_* 를 전부 보내고 payload.visual.silent[k] 를 채워 다시 부르라. 판정 파일이 없으면 진행하지 않는다.",
      );
    }
    if (ending && (!visual.ending || !Array.isArray(visual.ending.beats))) {
      return reject("select", preset, "hard_fail: 결말 클립 판정 결과(visual.ending.beats)가 없다", "① 의 judge_ending 을 보내고 payload.visual.ending 을 채워 다시 부르라. 결말은 후보 우선 대상이라 없이는 진행하지 않는다.");
    }

    // 후보 만들기
    const cands: Candidate[] = [];
    const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
    for (const e of briefDoc.events) {
      if (typeof e.start !== "number" || typeof e.end !== "number") continue;
      const out = Math.min(e.end, usableEnd);
      if (out <= e.start) continue;
      cands.push({ in: e.start, out, importance: e.importance, kind: "dialogue", src: `brief#${e.n}`, why: e.summary });
    }
    const visualDoc: { silent: { stretch: Facts["silent_visual_stretches"] extends (infer T)[] | undefined ? T : never; scenes: Scene[] }[]; ending: Visual["ending"] } = { silent: [], ending: visual.ending ?? null };
    stretches.forEach((st, k) => {
      const res = silentResults[k];
      let scenes = (res?.scenes ?? []).filter((sc) => typeof sc.start === "number" && typeof sc.end === "number" && sc.end > sc.start)
        .map((sc) => ({ ...sc, start: r1(clamp(sc.start, st.start_s, usableEnd)), end: r1(clamp(sc.end, st.start_s, usableEnd)), importance: Number.isInteger(sc.importance) ? clamp(sc.importance, 1, 5) : 2 }))
        .filter((sc) => sc.end > sc.start);
      if (scenes.length === 0) {
        warnings.push(`무음 구간 ${k}(${st.start_s}~${st.end_s}s) 판정이 장면 0건이다 — 구간 전체를 시각몽타주 후보(중요도 2)로 둔다. 판정을 다시 보내 보라.`);
        scenes = [{ start: st.start_s, end: Math.min(st.end_s, usableEnd), what: st.note ?? "(판정 없음) 무음 구간", importance: 2 }];
      }
      visualDoc.silent.push({ stretch: st, scenes });
      scenes.forEach((sc, i) => cands.push({ in: sc.start, out: sc.end, importance: sc.importance, kind: "visual", src: `visual:silent_${k}#${i + 1}`, why: sc.what }));
    });
    if (ending && visual.ending) {
      const beats = (visual.ending.beats ?? []).filter((b) => typeof b.start === "number" && typeof b.end === "number" && b.end > b.start)
        .map((b) => ({ ...b, start: r1(clamp(b.start, ending.start_s, usableEnd)), end: r1(clamp(b.end, ending.start_s, usableEnd)), importance: Number.isInteger(b.importance) ? clamp(b.importance, 1, 5) : 3 }))
        .filter((b) => b.end > b.start);
      const endIn = ending.start_s, endOut = Math.min(ending.end_s, usableEnd);
      if (beats.length === 0) {
        warnings.push("결말 클립 판정이 비트 0건이다 — 결말 구간 전체를 후보(중요도 5)로 둔다.");
        cands.push({ in: endIn, out: endOut, importance: 5, kind: "ending", src: "visual:ending(통째)", why: ending.note ?? "시각적 결말" });
      } else if (S.결말_통째 && endOut - endIn <= S.구간창_s.max) {
        // 규격 구간선택.결말_통째 — 비트가 클립 경계에서 조각나지 않도록 결말은 한 후보로 (비트는 visual.json 에 남는다)
        const imp = Math.max(...beats.map((b) => b.importance));
        const why = (visual.ending.ending_summary ?? "").trim() || beats.map((b) => b.what).join(" / ");
        cands.push({ in: endIn, out: endOut, importance: imp, kind: "ending", src: "visual:ending(통째)", why });
      } else {
        if (S.결말_통째) warnings.push(`결말 구간 ${r1(endOut - endIn)}s 가 창 최대 ${S.구간창_s.max}s 를 넘어 통째로 못 잡는다 — 비트 단위로 되돌린다.`);
        beats.forEach((b, i) => cands.push({ in: b.start, out: b.end, importance: b.importance, kind: "ending", src: `visual:ending#${i + 1}`, why: b.what }));
      }
    }
    // 결말 후보는 서로 인접하면 먼저 붙인다 (15s 클립 경계에서 잘게 쪼개지는 것 방지)
    // → 채움 단계에서 병합되므로 여기선 우선순위만.
    const rank = (c: Candidate) => (S.결말포함 && c.kind === "ending" ? 100 : 0) + c.importance;
    cands.sort((a, b) => rank(b) - rank(a) || a.in - b.in);

    // 우선순위 채움
    const W = S.구간창_s;
    const chosen: Segment[] = [];
    let total = 0;
    const roleOf = (c: Candidate) => c.kind === "dialogue"
      ? (c.importance >= S.역할규칙.원본대사_최소중요도 ? "원본대사" : "나레이션덮기")
      : S.역할규칙.무음장면_역할;
    const absorbMin = S.흡수규칙.흡수_최소중요도;
    let absorbed = 0;
    /** 규격 구간선택.흡수규칙 — 창 최소보다 짧은 ★≥N 후보는 인접(겹치거나 병합 간격 안) 선택 구간을 늘려 흡수한다 */
    const tryAbsorb = (c: Candidate): boolean => {
      const gap = S.인접병합_간격_s;
      const host = chosen.find((s) => s.out >= c.in - gap && s.in <= c.out + gap);
      if (!host) return false;
      let nin = Math.min(host.in, c.in), nout = Math.max(host.out, c.out);
      for (const o of chosen) { if (o === host) continue; if (o.out <= host.in && o.out > nin) nin = o.out; if (o.in >= host.out && o.in < nout) nout = o.in; }
      nin = Math.max(0, nin); nout = Math.min(usableEnd, nout);
      const extra = (nout - nin) - (host.out - host.in);
      if (extra > 0) {
        const remain = budget - total;
        if (remain <= 0) return false;
        if (extra > remain) { // 예산만큼만 — 뒤쪽부터 줄인다
          let over = extra - remain;
          const cutTail = Math.min(over, nout - host.out); nout -= cutTail; over -= cutTail;
          if (over > 0) nin += Math.min(over, host.in - nin);
        }
        total += (nout - nin) - (host.out - host.in);
      }
      host.in = r1(nin); host.out = r1(nout);
      host.src.push(c.src); host.why = `${host.why} / ${c.why}`; host.importance = Math.max(host.importance, c.importance);
      absorbed++;
      return true;
    };
    for (const c of cands) {
      let a = c.in, b = c.out;
      // 창: 짧으면 — ★≥흡수 기준이면 먼저 인접 구간에 흡수를 시도, 아니면 늘린다. 길면 자른다
      if (b - a < W.min) {
        if (c.importance >= absorbMin && tryAbsorb(c)) continue;
        const need = W.min - (b - a); a = Math.max(0, a - need / 2); b = Math.min(usableEnd, a + W.min); a = Math.max(0, b - W.min);
      }
      if (b - a > W.max) b = a + W.max;
      // 이미 고른 것과 겹치면 겹치지 않는 가장 큰 조각만
      const pieces: [number, number][] = [[a, b]];
      for (const s of chosen) {
        for (let i = pieces.length - 1; i >= 0; i--) {
          const [pa, pb] = pieces[i];
          if (s.out <= pa || s.in >= pb) continue;
          pieces.splice(i, 1);
          if (s.in > pa) pieces.push([pa, s.in]);
          if (s.out < pb) pieces.push([s.out, pb]);
        }
      }
      if (pieces.length === 0) { if (c.importance >= absorbMin) tryAbsorb(c); continue; }
      pieces.sort((x, y) => (y[1] - y[0]) - (x[1] - x[0]));
      let [pa, pb] = pieces[0];
      if (pb - pa < W.min) { if (c.importance >= absorbMin) tryAbsorb(c); continue; }
      const remain = budget - total;
      if (remain < W.min) break;
      if (pb - pa > remain) pb = pa + remain;
      chosen.push({ in: r1(pa), out: r1(pb), role: roleOf(c), src: [c.src], why: c.why, importance: c.importance, kind: c.kind });
      total += pb - pa;
    }
    chosen.sort((x, y) => x.in - y.in);
    // 인접 병합 (같은 역할, 간격 ≤ 규격)
    const merged: Segment[] = [];
    for (const s of chosen) {
      const last = merged[merged.length - 1];
      if (last && s.in - last.out <= S.인접병합_간격_s && last.role === s.role) {
        last.out = Math.max(last.out, s.out); last.src.push(...s.src); last.why = `${last.why} / ${s.why}`; last.importance = Math.max(last.importance, s.importance);
      } else merged.push({ ...s, src: [...s.src] });
    }
    // 병합 뒤 창 최대 초과분은 자르지 않는다 (같은 이야기 흐름) — 경고만
    merged.forEach((s) => { if (s.out - s.in > W.max) warnings.push(`병합 뒤 구간 ${s.in}~${s.out}s 가 창 최대 ${W.max}s 를 넘는다 (${r1(s.out - s.in)}s). 규격 구간선택.인접병합_간격_s 를 줄이면 나뉜다.`); });

    if (merged.length === 0) {
      return reject("select", preset, "hard_fail: 확정된 구간이 0개다", "brief 사건과 시각 판정 장면이 전부 창 최소 길이보다 짧거나 크레딧 이후다. 규격.json 구간선택.구간창_s.min 을 낮추거나 facts.json 의 credits_start_s 를 확인하라.");
    }

    // ── 지표 (산출물에서 독립 계산) ──────────────────────────────────────
    const totalS = r3(merged.reduce((a, s) => a + (s.out - s.in), 0));
    const count = merged.length;
    const avg = r3(totalS / count);
    const ratio = r3(totalS / durationS);
    const spans = (payload.utterance_spans as [number, number][] | undefined) ?? [];
    let uttIn = 0;
    for (const [us, ue] of spans) if (merged.some((s) => us < s.out && ue > s.in)) uttIn++;
    const blocksPerMin = spans.length ? r3(uttIn / (totalS / 60)) : null;
    // 최대 미선택 스트레치 (크레딧 제외)
    let gapBest = { start: 0, end: 0, len: 0 };
    let cursor = 0;
    for (const s of merged) { if (s.in - cursor > gapBest.len) gapBest = { start: r1(cursor), end: r1(s.in), len: r1(s.in - cursor) }; cursor = Math.max(cursor, s.out); }
    if (usableEnd - cursor > gapBest.len) gapBest = { start: r1(cursor), end: r1(usableEnd), len: r1(usableEnd - cursor) };
    // 나레이션 브리지 후보 — 선택되지 않은 원본 구간 ≥ 규격 브리지_최소_s (크레딧 제외)
    const bridges: { start: number; end: number; len_s: number; events: { n: number; summary: string; importance: number }[]; note: string }[] = [];
    {
      let cur = 0;
      const gaps: [number, number][] = [];
      for (const s of merged) { if (s.in - cur >= S.브리지_최소_s) gaps.push([cur, s.in]); cur = Math.max(cur, s.out); }
      if (usableEnd - cur >= S.브리지_최소_s) gaps.push([cur, usableEnd]);
      for (const [ga, gb] of gaps) {
        const evs = briefDoc.events.filter((e) => e.start < gb - 0.1 && e.end > ga + 0.1).map((e) => ({ n: e.n, summary: e.summary, importance: e.importance }));
        bridges.push({ start: r1(ga), end: r1(gb), len_s: r1(gb - ga), events: evs, note: "나레이션 브리지 후보 — 선택되지 않은 구간. script 가 앞뒤를 잇는 나레로 덮는다" });
      }
    }
    // 반복(겹침) 비율 — 병합 뒤라 0 이어야 정상
    let overlapS = 0;
    for (let i = 1; i < merged.length; i++) overlapS += Math.max(0, merged[i - 1].out - merged[i].in);
    const overlapRatio = r3(overlapS / totalS);
    // 인접 점프
    let jump05 = 0, jump60 = 0;
    for (let i = 1; i < merged.length; i++) { const g = merged[i].in - merged[i - 1].out; if (g > 0.5) jump05++; if (g > 60) jump60++; }
    const pairs = Math.max(1, merged.length - 1);
    const jump05Ratio = r3(jump05 / pairs), jump60Ratio = r3(jump60 / pairs);
    const byRole: Record<string, { count: number; s: number }> = {};
    for (const s of merged) { byRole[s.role] ??= { count: 0, s: 0 }; byRole[s.role].count++; byRole[s.role].s = r3(byRole[s.role].s + (s.out - s.in)); }

    // ── 게이트 ─────────────────────────────────────────────────────────
    const gates: { id: string; pass: boolean | null; hard: boolean; detail: string; fix?: string }[] = [];
    const g16 = A["G-반복"].컷_반복_비율_max;
    const g16pass = overlapRatio <= (g16.value ?? 0.05);
    gates.push({ id: "G-반복(G16 컷 반복)", pass: g16pass, hard: true, detail: `겹침 ${overlapRatio} ≤ ${g16.value} (${g16.출처})`, fix: g16pass ? undefined : `선택 구간끼리 겹친다. 규격.json 구간선택.인접병합_간격_s 를 늘려 붙이거나 구간창_s.max 를 줄여라.` });
    // G13 소스 점프·G63 60s 초과 점프는 select 게이트에서 뺐다 — 최종 컷 단위 측정, 이후 단계(render 예정) 대상 (정답지.json 구간선택.G-반복 적용 표시). 지표로만 남긴다.
    const g25 = A["G-밀도"].분당_블록수_환산;
    gates.push({ id: "G-밀도(G25 분당 블록 대용치, soft)", pass: blocksPerMin === null ? null : blocksPerMin >= (g25.min ?? 0) && blocksPerMin <= (g25.max ?? 999), hard: false, detail: blocksPerMin === null ? "utterance_spans 없음 — 미판정" : `선택 구간 안 발화 ${uttIn}건 / ${r1(totalS / 60)}분 = ${blocksPerMin}/분 (대역 ${g25.min}~${g25.max}, ${g25.적용})` });
    const lenPass = totalS >= target * 0.8;
    gates.push({ id: "분량(G18 계열, soft)", pass: lenPass, hard: false, detail: `총 ${totalS}s / 목표 ${target}s (${r3(totalS / target)}). 참고 G18 ≥80% — 판정 안 함(길이는 내용이 정한다)` });
    const hardFail = gates.filter((g) => g.hard && g.pass === false);
    for (const g of gates) if (g.pass === false && !g.hard) warnings.push(`[soft] ${g.id}: ${g.detail}`);
    if (!lenPass) warnings.push(`총 길이가 목표의 80% 미만이다 — 후보가 모자란다. 규격.json 구간선택.목표길이 를 낮추거나(단편은 CASE C 검토) brief 사건 수 목표를 올려라.`);

    const selectionDoc = {
      source: source.path, title, duration_s: durationS, usable_end_s: usableEnd, credits_start_s: creditsStart,
      target_s: target, budget_s: budget,
      role_rule: S.역할규칙, window_s: S.구간창_s,
      metrics: { count, total_s: totalS, avg_len_s: avg, ratio_vs_source: ratio, blocks_per_min_proxy: blocksPerMin, max_unselected_stretch: gapBest, bridge_count: bridges.length, absorbed_candidates: absorbed, by_role: byRole, overlap_ratio: overlapRatio, jump_gt_0_5s_ratio: jump05Ratio, jump_gt_60s_ratio: jump60Ratio },
      gates,
      warnings,
      narration_bridges: bridges,
      segments: merged.map((s, i) => ({ i: i + 1, in: s.in, out: s.out, len_s: r1(s.out - s.in), role: s.role, importance: s.importance, kind: s.kind, src: s.src, why: s.why })),
    };

    if (hardFail.length > 0) {
      return reject(
        "select", preset,
        `게이트 불통 — ${hardFail.map((g) => `${g.id}: ${g.detail}`).join(" / ")}`,
        hardFail.map((g) => g.fix ?? "").join(" ") + " 규격을 고친 뒤 select ② 를 같은 payload 로 다시 부르라 (판정 재호출 불필요).",
      );
    }

    return base("select", preset, {
      status: "execute",
      next_step: "script",
      message: `구간 확정: ${count}개 · ${totalS}s (목표 ${target}s, 원본 대비 ${ratio}) · 평균 ${avg}s · 최대 미선택 ${gapBest.start}~${gapBest.end}s(${gapBest.len}s). 게이트 hard 통과. write_files 를 쓰고 script 로 넘어가라.`,
      instructions: [
        `① write_files 의 내용을 그대로 쓴다 — ${join(clipsDir, "visual.json")}(판정 정리), ${join(clipsDir, "selection.json")}(확정 구간).`,
        "② metrics 와 gates 를 사람에게 보여준다. 구간 목록은 시간순 표(시간·길이·역할·근거)로.",
        "③ carry 의 값을 payload 에 그대로 실어 next_step 을 부른다.",
        "④ script 는 아직 스텁이다 — 나레이션 지침(스타일/영화롱폼/나레이션.md) 확정 대기.",
      ],
      then_call_with: ["step: 'script'", "payload: { workdir, source, probe_summary, transcript_path, brief_path, selection_path }"],
      jobs_kind: null, jobs: [], measure: [],
      write_files: [
        { path: join(clipsDir, "visual.json"), content: visualDoc as unknown as Record<string, unknown>, note: "시각 판정 정리 (무음 구간 장면 + 결말 비트)" },
        { path: join(clipsDir, "selection.json"), content: selectionDoc, note: "확정 구간. script 의 입력" },
      ],
      metrics: selectionDoc.metrics,
      gates,
      carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path"],
      source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: join(clipsDir, "selection.json"),
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
