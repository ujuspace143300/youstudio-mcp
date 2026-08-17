/**
 * steps/voice.ts — 나레이션 TTS. 명세: 설계/단계상세.md 「6. voice」
 *
 * 두 번 부른다:
 *   ① payload.voice_bytes 가 없으면 → 지시. jobs_kind:"synthesize" — 블록마다 ElevenLabs 호출 1건 (pcm 원시), auth 는 env 위치만.
 *      post[] 로 pcm → wav 감싸기(ffmpeg). measure 는 응답 바이트 수 → 길이 = 바이트 ÷ (샘플레이트 × 2).
 *      규격 「음성.보이스_ID」가 비어 있으면 여기서 반려 — 샘플을 듣고 정하라.
 *   ② payload.voice_bytes 가 있으면 → 검사. 빠졌거나 0 바이트면 hard_fail + 수리 지침.
 *      블록별 실측 길이 · 총 길이 · 실측 자당초 → voice/voice.json. script 의 나레 시간점유를 실측으로 재계산해 추정과 비교하고,
 *      빈 위치를 채울 예산(초·자)을 낸다. 실측 자당초는 우리실측.json 에 기록하라고 record_to_ours 로 돌려준다 (저장소 파일은 runner 가 쓴다).
 *
 * measure-never-predict: 실측 길이가 타임라인 슬롯을 정한다. 추정(규격 나레이션.자당초_추정)은 여기서 끝난다.
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import answer from "../../../스타일/영화롱폼/정답지.json";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";
import type { SynthesizeJob, ArgvJob, MeasureRule } from "../schema.js";

interface VoiceSpec {
  제공자: "elevenlabs"; 모델: string; 엔드포인트: string; 키_환경변수: string;
  보이스_ID: string | null; 보이스_이름: string | null; 보이스_후보: { id: string; 이름: string; 메모: string }[];
  출력형식: string; 샘플레이트_hz: number; voice_settings: Record<string, unknown>; 요청_최대자수: number;
}
const V = (spec as unknown as { 음성: VoiceSpec })["음성"];
const VS = ((spec as unknown as { 음성: { 무음스캔?: { noise_dB: number; d_s: number } } })["음성"].무음스캔) ?? { noise_dB: -40, d_s: 0.2 };
const VW = (spec as unknown as { 음성: { 단어실측: { 제공자: string; 모델: string; 엔드포인트: string; 키_환경변수: string; 언어: string; 유사도_최소: number; 정렬_유사도_최소: number; 이어붙임_무음_s: number; 설정: Record<string, unknown> } } })["음성"]["단어실측"];
const VC = (spec as unknown as { 음성: { 문구대조: { 제공자: "groq"; 모델: string; 엔드포인트: string; 키_환경변수: string; 언어: string; 유사도_최소: number } } })["음성"]["문구대조"];
const N = (spec as unknown as { 나레이션: { 자당초_추정: number } })["나레이션"];
const A = (answer as unknown as { 대본: { 나레_시간점유: { min: number; max: number } } })["대본"];

function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}
const r3 = (x: number) => Math.round(x * 1000) / 1000;
const pad2 = (n: number) => String(n).padStart(2, "0");

interface ScriptBlock { n: number; pos: { kind: string; seg?: number; bridge?: number }; text: string; lines?: string[] | null; intent?: string; chars: number; est_s?: number }
interface ScriptDoc { blocks?: ScriptBlock[]; metrics?: { dialogue_s?: number; total_chars?: number; nar_est_s?: number; nar_share_est?: number }; warnings?: string[] }

/** 문구 대조용 정규화 — 공백·문장부호를 지운다(ASR 은 마침표·띄어쓰기를 다르게 쓴다) */
function normText(t: string): string {
  return (t ?? "").replace(/[^0-9A-Za-z\uac00-\ud7a3]/g, "");
}
/** 유사도 = 2×최장공통부분수열 ÷ (길이 합). 1 = 같음 */
export function textSim(a: string, b: string): number {
  const x = normText(a), y = normText(b);
  if (!x.length || !y.length) return 0;
  const dp: number[] = new Array(y.length + 1).fill(0);
  for (let i = 1; i <= x.length; i++) {
    let prev = 0;
    for (let j = 1; j <= y.length; j++) {
      const tmp = dp[j];
      dp[j] = x[i - 1] === y[j - 1] ? prev + 1 : Math.max(dp[j], dp[j - 1]);
      prev = tmp;
    }
  }
  return Math.round((2 * dp[y.length] / (x.length + y.length)) * 1000) / 1000;
}

export const voice: StepHandler = {
  name: "voice",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; title?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number } | undefined;
    const script = payload.script as ScriptDoc | undefined;
    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !script || !Array.isArray(script.blocks) || script.blocks.length === 0) {
      return reject(
        "voice", preset,
        "payload 에 carry 값(source·workdir·probe_summary) 또는 script(블록)가 없다",
        "script 응답의 carry 값과 함께 payload.script 에 script/script.json 의 내용을 실어 voice 를 다시 부르라.",
      );
    }
    const blocks = script.blocks;
    const voiceDir = join(workdir, "voice");
    const bytesPerSec = V.샘플레이트_hz * 2; // 16bit 모노
    const bname = (n: number) => `b${pad2(n)}`;

    // ── ① 지시 ──────────────────────────────────────────────────────────
    if (payload.voice_ts === undefined) {
      if (!V.보이스_ID) {
        return reject(
          "voice", preset,
          "규격 음성.보이스_ID 가 비어 있다 — 보이스를 아직 정하지 않았다",
          `voice/samples/ 의 샘플을 듣고 규격.json 음성.보이스_ID·보이스_이름 을 채워라 (후보: ${V.보이스_후보.map((c) => `${c.이름}=${c.id}`).join(" · ")}). 규격은 서버 번들에 실리므로 고친 뒤 서버를 다시 띄우고 voice 를 다시 부르라.`,
        );
      }
      const tooLong = blocks.filter((b) => (b.text ?? "").length > V.요청_최대자수);
      if (tooLong.length) return reject("voice", preset, `블록 ${tooLong.map((b) => b.n).join(",")} 의 본문이 요청 최대 ${V.요청_최대자수}자를 넘는다`, "script 로 돌아가 블록을 나누라.");
      // with-timestamps: 글자별 시작·끝 초를 함께 받는다 (subtitle 큐 실측용 — 결정 E 2026-08-16)
      const url = V.엔드포인트.replace("{voice_id}", V.보이스_ID) + `/with-timestamps?output_format=${V.출력형식}`;
      const auth = { env: V.키_환경변수, header: `xi-api-key: <${V.키_환경변수} 값>`, note: "ElevenLabs. 서버는 키를 보관하지 않는다 — runner 가 로컬 환경변수에서 읽어 헤더에 붙인다." };
      const jobs: SynthesizeJob[] = blocks.map((b) => ({
        name: bname(b.n), provider: "elevenlabs", model: V.모델, voice_id: V.보이스_ID!,
        request: { method: "POST", url, headers: { "Content-Type": "application/json", Accept: "application/json" }, body: { text: b.text, model_id: V.모델, voice_settings: V.voice_settings } },
        auth, out: join(voiceDir, `${bname(b.n)}.pcm`),
        note: `블록 ${b.n} (${b.chars}자) — ${b.pos.kind}${b.pos.kind === "bridge" ? ` bridge#${b.pos.bridge}` : ` seg#${b.pos.seg}`}`,
      }));
      const post: ArgvJob[] = blocks.map((b) => ({
        name: `wrap_${bname(b.n)}`,
        argv: ["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", String(V.샘플레이트_hz), "-ac", "1", "-i", join(voiceDir, `${bname(b.n)}.pcm`), join(voiceDir, `${bname(b.n)}.wav`)],
        note: "pcm(16bit 모노) → wav 감싸기. 인코딩 없음 — 길이 그대로",
      }));
      for (const b of blocks) post.push({
        name: `silence_${bname(b.n)}`,
        argv: ["ffmpeg", "-v", "info", "-nostats", "-i", join(voiceDir, `${bname(b.n)}.wav`), "-af", `silencedetect=noise=${VS.noise_dB}dB:d=${VS.d_s}`, "-f", "null", "-"],
        note: "발성 구간 실측(stderr 의 silence_start/end) — subtitle 이 자막 큐를 발성 안으로 클램프한다",
      });
      const measure: MeasureRule[] = blocks.map((b) => ({ as: `voice_ts.${bname(b.n)}`, from: `job:${bname(b.n)}`, unit: "tts_timestamps" }));
      // 발성 구간 실측 — 문자 정렬(chars_t)은 문장 사이 쉼을 글자에 붙여 늘린다(2026-08-17 진단). subtitle 이 이 실측으로 큐를 클램프한다
      for (const b of blocks) measure.push({ as: `speech_raw.${bname(b.n)}`, from: `post:silence_${bname(b.n)}`, unit: "stderr" });
      const totalChars = blocks.reduce((a, b) => a + (b.chars ?? b.text.length), 0);
      return base("voice", preset, {
        status: "execute",
        next_step: "voice",
        message: `TTS 지시: ${blocks.length}블록 · ${totalChars}자 → ${V.제공자}/${V.모델} 보이스 ${V.보이스_이름 ?? V.보이스_ID} (with-timestamps). 각 응답의 {audio_bytes, alignment} 를 payload.voice_ts 에 실어 voice 를 다시 부르라.`,
        instructions: [
          `① jobs 의 synthesize 를 블록 순서대로 보낸다. 키는 auth 대로 환경변수 ${V.키_환경변수} 에서 읽어 헤더 xi-api-key 에 붙인다. 응답은 JSON — audio_base64 를 디코드한 원시 pcm 을 out 경로에 저장한다. HTTP 200 이 아니면 그 블록은 실패다 — 본문의 detail 을 사람에게 보여주고 나머지는 계속한다.`,
          "② post[] 의 ffmpeg 를 그대로 실행한다 (pcm → wav, 그다음 wav 마다 무음 스캔).",
          "③ measure(tts_timestamps) 대로 payload.voice_ts.bNN = {audio_bytes, alignment} 를 넣는다 (실패한 블록은 {audio_bytes:0}).",
          "④ carry 값(script 포함)과 함께 voice 를 다시 부른다.",
        ],
        then_call_with: ["step: 'voice'", "payload: { …carry, script, voice_ts: { b01: {audio_bytes, alignment}, b02: … } }"],
        jobs_kind: "synthesize", jobs, post, measure,
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "script"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, script,
        plan: { provider: V.제공자, model: V.모델, voice: V.보이스_이름 ?? V.보이스_ID, blocks: blocks.length, chars: totalChars, output_format: V.출력형식, sample_rate_hz: V.샘플레이트_hz },
      });
    }

    // ── ② 결과 검사 ──────────────────────────────────────────────────────
    const vb = payload.voice_ts as Record<string, { audio_bytes?: number; alignment?: { characters?: string[]; character_start_times_seconds?: number[]; character_end_times_seconds?: number[] } } | number>;
    if (typeof vb !== "object" || vb === null) return reject("voice", preset, "payload.voice_ts 가 객체가 아니다", "① 의 measure 대로 {b01: {audio_bytes, alignment}, …} 를 실어 다시 부르라.");
    const failed: string[] = [];
    const per = blocks.map((b) => {
      const raw = vb[bname(b.n)];
      const bytes = typeof raw === "number" ? raw : Number((raw as { audio_bytes?: number } | undefined)?.audio_bytes ?? 0);
      if (!Number.isFinite(bytes) || bytes <= 0) failed.push(`블록 ${b.n}(${bname(b.n)})`);
      const dur = r3(bytes / bytesPerSec);
      const chars = b.chars ?? b.text.replace(/\s+/g, " ").trim().length;
      const al = typeof raw === "object" && raw ? raw.alignment : undefined;
      // 글자별 시각 (subtitle 이 큐를 실측으로 자른다). 없으면 null — subtitle 이 글자 비례로 대신한다
      const chars_t = al && Array.isArray(al.characters) && Array.isArray(al.character_start_times_seconds) && Array.isArray(al.character_end_times_seconds)
        ? al.characters.map((c, i) => ({ c, s: r3(al.character_start_times_seconds![i]), e: r3(al.character_end_times_seconds![i]) }))
        : null;
      return { n: b.n, pos: b.pos, text: b.text, lines: b.lines ?? null, chars, bytes, dur_s: dur, sec_per_char: chars > 0 ? r3(dur / chars) : null, est_s: b.est_s ?? r3(chars * N.자당초_추정), wav: join(voiceDir, `${bname(b.n)}.wav`), chars_t, speech: null as [number, number][] | null };
    });
    // 발성 구간 실측 파싱 (payload.speech_raw = {b01: "<ffmpeg stderr>", …}). 없으면 null — subtitle 이 chars_t 만 쓴다(경고)
    const sraw = (payload.speech_raw ?? null) as Record<string, string> | null;
    const speechOf = (n: number, dur: number): [number, number][] | null => {
      const txt = sraw?.[bname(n)];
      if (typeof txt !== "string" || !txt) return null;
      const sil: [number, number][] = [];
      let st: number | null = null;
      for (const line of txt.split(/\r?\n/)) {
        const a = /silence_start:\s*(-?[\d.]+)/.exec(line); if (a) st = Math.max(0, Number(a[1]));
        const b = /silence_end:\s*([\d.]+)/.exec(line);
        if (b && st !== null) { sil.push([r3(st), r3(Number(b[1]))]); st = null; }
      }
      if (st !== null) sil.push([r3(st), r3(dur)]);
      const sp: [number, number][] = []; let cur = 0;
      for (const [a, b] of sil.sort((x, y) => x[0] - y[0])) { if (a > cur + 0.001) sp.push([r3(cur), r3(a)]); cur = Math.max(cur, b); }
      if (dur > cur + 0.001) sp.push([r3(cur), r3(dur)]);
      return sp.length ? sp : null;
    };
    const withTs = per.filter((p) => p.chars_t).length;
    if (failed.length > 0) {
      return reject(
        "voice", preset,
        `hard_fail: 합성 실패 ${failed.length}건 — ${failed.join(", ")}`,
        `① 실패 블록의 HTTP 응답 detail 을 본다: 401 → 키(${V.키_환경변수}) 확인 · 402/quota → 잔여 문자 수 확인(/v1/user/subscription) · 400 voice_not_fine_tuned → 다른 보이스(규격 음성.보이스_후보) · 5xx → 잠시 뒤 재시도. ② 같은 jobs 중 실패한 것만 다시 보내고 payload.voice_bytes 를 채워 다시 부르라. 0 바이트 파일을 그대로 두고 넘어가지 않는다.`,
      );
    }
    for (const p2 of per) p2.speech = speechOf(p2.n, p2.dur_s);
    const withSpeech = per.filter((p2) => p2.speech).length;
    const speechS = r3(per.reduce((a, p2) => a + (p2.speech ?? []).reduce((x, [u, v]) => x + (v - u), 0), 0));
    const totalS = r3(per.reduce((a, p) => a + p.dur_s, 0));
    const totalChars = per.reduce((a, p) => a + p.chars, 0);
    const spc = r3(totalS / totalChars);
    const estTotal = r3(per.reduce((a, p) => a + p.est_s, 0));
    const dlgS = script.metrics?.dialogue_s ?? 0;
    const shareMeasured = dlgS > 0 ? r3(totalS / (totalS + dlgS)) : null;
    const shareEst = script.metrics?.nar_share_est ?? null;
    const hi = A.나레_시간점유.max, lo = A.나레_시간점유.min;
    const narMax = r3(dlgS * hi / (1 - hi)), narMin = r3(dlgS * lo / (1 - lo));
    const headroomS = r3(narMax - totalS);
    const headroomChars = Math.round(headroomS / spc);
    const sharePass = shareMeasured === null ? null : shareMeasured >= lo && shareMeasured <= hi;
    const warnings: string[] = [];
    if (withSpeech < per.length) warnings.push(`발성 구간 실측이 ${per.length - withSpeech}블록 없다 — subtitle 이 문자 정렬만 쓰게 되어 자막이 쉼 위에 뜰 수 있다(payload.speech_raw 확인).`);
    if (sharePass === false) warnings.push(`실측 나레 시간점유 ${shareMeasured} 가 대역 ${lo}~${hi} 밖 — ${shareMeasured! < lo ? `나레 ${r3(narMin - totalS)}s(≈${Math.round((narMin - totalS) / spc)}자)가 더 필요하다. script 로 돌아가 빈 위치를 채워라.` : `나레 ${r3(totalS - narMax)}s 를 덜어내라.`}`);
    const slowest = [...per].sort((a, b) => (b.sec_per_char ?? 0) - (a.sec_per_char ?? 0))[0];
    const fastest = [...per].sort((a, b) => (a.sec_per_char ?? 9) - (b.sec_per_char ?? 9))[0];

    const voiceDoc = {
      source: source.path, title: source.title ?? null,
      tts: { provider: V.제공자, model: V.모델, voice_id: V.보이스_ID, voice_name: V.보이스_이름, output_format: V.출력형식, sample_rate_hz: V.샘플레이트_hz, voice_settings: V.voice_settings },
      metrics: { block_count: per.length, blocks_with_timestamps: withTs, blocks_with_speech: withSpeech, speech_s: speechS, silence_in_wav_s: r3(totalS - speechS), total_s: totalS, total_chars: totalChars, sec_per_char_measured: spc, sec_per_char_est: N.자당초_추정, est_total_s: estTotal, est_error_ratio: r3(estTotal / totalS), dialogue_s: dlgS, nar_share_measured: shareMeasured, nar_share_est: shareEst, headroom_s: headroomS, headroom_chars: headroomChars, slowest_block: { n: slowest.n, sec_per_char: slowest.sec_per_char }, fastest_block: { n: fastest.n, sec_per_char: fastest.sec_per_char } },
      warnings,
      blocks: per,
    };
    const today = new Date().toISOString().slice(0, 10); // 서버(UTC) 날짜 — 로컬과 하루 어긋날 수 있다. runner 가 기록할 때 로컬 날짜로 고쳐도 된다
    const recordToOurs = { tts: { 자당초: { value: spc, unit: "s/자(공백 1칸 정규화)", measure: `ElevenLabs ${V.모델} 보이스 ${V.보이스_이름 ?? V.보이스_ID} · ${per.length}블록 ${totalChars}자 → 실측 ${totalS}s (pcm 바이트 ÷ ${bytesPerSec})`, n: per.length, date: today, src: `${source.title ?? source.path} voice/voice.json` }, 블록당초: { value: r3(totalS / per.length), unit: "s/블록", measure: "같은 실측", n: per.length, date: today, src: "voice/voice.json" } } };

    // ── ③ 단어 실측 국면 (2026-08-18) — 나레도 **단어 단위 실측**으로 (HARNESS 강제 규칙) ──
    //   wav 27개를 사이 무음 1.0s 로 이어 붙여 **한 번** 전사한다(27콜 아님). 얻은 단어 시각으로
    //   자막 큐를 놓고(subtitle), 같은 전사로 문구 일치도 판정한다 — Groq 27콜을 대체한다.
    //   근거·설계: 설계/진단일지.md 22절. 글자 타임스탬프(chars_t)는 폴백으로만 남는다.
    const gapS = VW.이어붙임_무음_s;
    const concatPath = join(voiceDir, "nar_concat.wav");
    const offsets: { n: number; off: number }[] = [];
    {
      let cum = 0;
      for (const p2 of per) { offsets.push({ n: p2.n, off: r3(cum) }); cum = r3(cum + p2.dur_s + gapS); }
    }
    const concatTotal = r3(offsets.length ? offsets[offsets.length - 1].off + (per[per.length - 1].dur_s ?? 0) : 0);
    const asrIn = (payload.asr_nar ?? null) as { results?: { type?: string; start_time?: number; end_time?: number; alternatives?: { content?: string }[] }[] } | null;
    if (!asrIn) {
      const inputs: string[] = [];
      const filters: string[] = [];
      per.forEach((p2, i) => {
        inputs.push("-i", p2.wav);
        const ms = Math.round((offsets[i]?.off ?? 0) * 1000);
        filters.push(`[${i}]adelay=${ms}|${ms}[a${i}]`);
      });
      const fc = `${filters.join(";")};${per.map((_, i) => `[a${i}]`).join("")}amix=inputs=${per.length}:normalize=0:dropout_transition=0,apad=whole_dur=${concatTotal}[out]`;
      return base("voice", preset, {
        status: "execute",
        next_step: "voice",
        message: `TTS 합성·길이 검사 통과 (${per.length}블록 · ${totalS}s). 이제 **단어 실측**: wav 를 사이 ${gapS}s 무음으로 이어 붙여(${concatTotal}s) 한 번 전사한다 — 자막 큐를 단어에 맞추고 문구 일치도 같은 전사로 본다.`,
        instructions: [
          `① do[] 의 ffmpeg 를 실행해 ${concatPath} 를 만든다 (블록 ${per.length}개를 ${gapS}s 무음 간격으로 이어 붙인 것 — 합성이 아니라 이어 붙이기다).`,
          "② jobs 의 Speechmatics 배치 전사 1건을 실행한다(제출 → 폴링 → json-v2).",
          "③ measure 대로 응답 JSON 을 payload.asr_nar 에 담고, carry 값과 voice_ts·speech_raw 를 그대로 다시 실어 voice 를 한 번 더 부른다.",
        ],
        then_call_with: ["step: 'voice'", "payload: { …carry, voice_ts, speech_raw, asr_nar }"],
        do: [{ name: "nar_concat", argv: ["ffmpeg", "-y", "-v", "error", ...inputs, "-filter_complex", fc, "-map", "[out]", "-ar", String(V.샘플레이트_hz), "-ac", "1", "-c:a", "pcm_s16le", "-t", String(concatTotal), concatPath], note: `나레 ${per.length}블록을 ${gapS}s 무음 간격으로 이어 붙인다(전사 1콜용). 오프셋 표는 응답 offsets 에 있다` }],
        jobs_kind: "transcribe",
        jobs: [{
          name: "asr_nar",
          provider: VW.제공자 as "speechmatics",
          model: VW.모델,
          request: { method: "POST" as const, url: VW.엔드포인트, multipart: { data_file: `@${concatPath}`, config: JSON.stringify(VW.설정) } },
          batch: { submit_url: VW.엔드포인트, status_url: `${VW.엔드포인트}/{id}`, transcript_url: `${VW.엔드포인트}/{id}/transcript?format=json-v2`, poll_s: 5, timeout_s: 900 },
          auth: { env: VW.키_환경변수, header: `Authorization: Bearer <${VW.키_환경변수} 값>`, note: "서버는 키를 보관하지 않는다. runner 가 로컬 환경변수에서 읽어 붙인다." },
          out: join(voiceDir, "asr_nar.json"),
          note: "나레 전체를 한 번에 — results[] 의 start_time·end_time 이 우리가 쓸 단어 시각이다(이어붙임 좌표)",
        }],
        measure: [{ as: "asr_nar", from: "job:asr_nar", unit: "json_stdout" as const }],
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "script"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, script,
        metrics: { block_count: per.length, total_s: totalS, blocks_with_speech: withSpeech, concat_total_s: concatTotal, concat_gap_s: gapS },
        offsets,
      });
    }
    // ── 단어 → 블록 배정 (이어붙임 좌표 − 오프셋 = 블록 안 초) ──────────────────
    const smWords = (asrIn.results ?? [])
      .filter((r) => (r.type ?? "word") === "word" && typeof r.start_time === "number")
      .map((r) => ({ w: String(r.alternatives?.[0]?.content ?? "").trim(), s: r.start_time as number, e: (r.end_time ?? r.start_time) as number }))
      .filter((w) => w.w.length > 0);
    const blockWords = new Map<number, { w: string; s: number; e: number }[]>();
    for (const { n, off } of offsets) {
      const p2 = per.find((x) => x.n === n)!;
      const lo = off - 0.15, hi = off + p2.dur_s + 0.15;                 // 블록 창(이어붙임 좌표) — 무음 간격이 있어 겹치지 않는다
      // 단어 시각을 **블록 경계로 조인다** — ASR 은 마지막 단어의 끝을 이어붙임 무음까지 늘려 잡는다(실측 22/27블록 +0.5~1.0s).
      //   무음은 우리가 넣은 것이므로 단어가 그 안까지 이어질 수 없다. 시작은 그대로 믿고 끝만 자른다.
      blockWords.set(n, smWords.filter((w) => w.s >= lo && w.s < hi).map((w) => {
        const s0 = Math.max(0, r3(w.s - off));
        return { w: w.w, s: s0, e: Math.max(s0 + 0.02, Math.min(r3(w.e - off), p2.dur_s)) };
      }));
    }
    const simMin = VC.유사도_최소;
    const simRows = per.map((p2) => {
      const heard = (blockWords.get(p2.n) ?? []).map((w) => w.w).join(" ");   // 같은 전사로 판정 — Groq 27콜을 대체한다
      return { n: p2.n, wav: bname(p2.n), sim: textSim(p2.text, heard), text: p2.text, heard, words: (blockWords.get(p2.n) ?? []).length };
    });
    const simBad = simRows.filter((r) => r.sim < simMin);
    const simMinSeen = simRows.length ? Math.min(...simRows.map((r) => r.sim)) : 0;
    if (simBad.length) {
      return reject(
        "voice", preset,
        `hard_fail: G-나레문구일치 — 자막 문구와 실제 발화가 다른 블록 ${simBad.length}건 (유사도 < ${simMin})\n` +
          simBad.slice(0, 8).map((r) => `  · 블록 ${r.n}(${r.wav}) 유사 ${r.sim} — 문구 「${r.text.slice(0, 26)}」 / 들리는 말 「${r.heard.slice(0, 26)}」`).join("\n"),
        `① 어긋난 블록의 wav 를 **재사용 없이 새로 합성**한다(러너 캐시를 끄거나 비운다). ② 러너 캐시는 직전 실행본만 쓰고 (문구+파일 해시) 쌍이 맞을 때만 재사용한다 — 대본이 바뀌면 캐시를 통째로 버린다. ③ 다시 합성한 뒤 ①~③ 국면을 처음부터 돌린다. 자막·타임라인은 이 검사를 통과한 voice.json 으로만 만든다.`,
      );
    }
    voiceDoc.metrics = { ...voiceDoc.metrics, text_match_min: simMinSeen, text_match_blocks: simRows.length } as typeof voiceDoc.metrics;
    (voiceDoc as { blocks: { n: number; heard?: string; text_sim?: number; words?: { w: string; s: number; e: number }[] }[] }).blocks.forEach((b2) => {
      const row = simRows.find((r) => r.n === b2.n);
      if (row) { b2.heard = row.heard; b2.text_sim = row.sim; }
      b2.words = blockWords.get(b2.n) ?? [];        // **자막 큐를 여기에 맞춘다**(블록 안 초)
    });
    // 검산: 블록마다 단어가 있고, 마지막 단어 끝이 wav 길이를 넘지 않는가 (이어붙임 환산이 맞는지)
    const wordsBad = per.filter((p2) => {
      const ws = blockWords.get(p2.n) ?? [];
      return ws.length === 0 || ws[0].s > p2.dur_s * 0.5;                      // 단어가 없거나, 첫 단어가 블록 후반에서 시작(환산이 어긋난 신호)
    }).map((p2) => `블록 ${p2.n}(단어 ${(blockWords.get(p2.n) ?? []).length}개, 끝 ${(blockWords.get(p2.n) ?? []).slice(-1)[0]?.e ?? "-"}s / wav ${p2.dur_s}s)`);
    if (wordsBad.length) warnings.push(`단어 실측 검산 불통 ${wordsBad.length}건 — ${wordsBad.slice(0, 5).join(" · ")}. 자막 단계가 그 블록만 글자 타임스탬프(chars_t)로 폴백한다(줄↔단어 정렬 유사도로 한 번 더 걸러진다).`);
    voiceDoc.metrics = { ...voiceDoc.metrics, words_total: smWords.length, words_blocks: per.filter((p2) => (blockWords.get(p2.n) ?? []).length > 0).length, concat_total_s: concatTotal, concat_gap_s: gapS } as typeof voiceDoc.metrics;
    const gates = [{ id: "G-나레문구일치", pass: true, hard: true, detail: `${simRows.length}블록 전부 문구 일치 — 최저 유사도 ${simMinSeen} (기준 ${simMin}) · 단어 실측 ${smWords.length}개(블록당 평균 ${r3(smWords.length / Math.max(1, simRows.length))}) · 판정 재료 = Speechmatics 1콜`, fix: "어긋나면 그 블록을 재사용 없이 재합성하고 러너 캐시를 비운다" }];

    return base("voice", preset, {
      status: "execute",
      next_step: "subtitle",
      gates,
      message: `TTS 통과(문구 일치 ${simRows.length}/${simRows.length}, 최저 유사도 ${simMinSeen}): ${per.length}블록 · 실측 ${totalS}s (추정 ${estTotal}s, 추정/실측 ${r3(estTotal / totalS)}) · 실측 ${spc}s/자 (추정 ${N.자당초_추정}) · 나레 시간점유 실측 ${shareMeasured} (추정 ${shareEst}) · 빈 위치 채울 여유 ${headroomS}s ≈ ${headroomChars}자. write_files 를 쓰고 subtitle 로 넘어가라.`,
      instructions: [
        `① write_files 의 내용을 그대로 ${join(voiceDir, "voice.json")} 에 쓴다.`,
        "② record_to_ours 의 값을 저장소의 스타일/영화롱폼/우리실측.json 「tts」에 그대로 넣는다 (기존 값이 있으면 덮어쓴다 — 결과는 매번 갱신). 규격 나레이션.자당초_추정 은 다음 판부터 이 실측으로 바꾼다.",
        "③ metrics 를 사람에게 보여준다 — 추정과 실측이 얼마나 달랐는지, 빈 위치(구간·브리지)를 채울 예산이 얼마인지.",
        "④ carry 의 값을 payload 에 그대로 실어 next_step 을 부른다. subtitle 은 아직 스텁이다.",
      ],
      then_call_with: ["step: 'subtitle'", "payload: { workdir, source, probe_summary, transcript_path, brief_path, selection_path, script_path, voice_path }"],
      jobs_kind: null, jobs: [], measure: [],
      write_files: [{ path: join(voiceDir, "voice.json"), content: voiceDoc, note: "블록별 실측 길이. subtitle 의 입력 — 실측이 슬롯을 정한다" }],
      metrics: voiceDoc.metrics,
      record_to_ours: recordToOurs,
      carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path"],
      source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: join(voiceDir, "voice.json"),
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
