/**
 * steps/transcript.ts — 전사 + 타임코드. 명세: 설계/단계상세.md 「2. transcript」
 *
 * 두 번 부른다:
 *   ① payload.asr 가 없으면 → 지시. do[] 로 오디오 추출(argv), jobs_kind:"transcribe" 로 Groq 호출.
 *      키는 auth 로 "GROQ_API_KEY 환경변수" 위치만 알려준다 — 서버는 키를 보관하지 않는다.
 *   ② payload.asr(verbose_json) 가 있으면 → 검사. 발화 0건이면 hard_fail(status error) + 수리 지침.
 *      발화 단위로 정리한 transcript.json 을 write_files 로 쓰게 하고 metrics 를 뱉는다. next_step=brief
 *
 * 설정값(제공자·모델·오디오 추출·파일 상한)은 전부 스타일/영화롱폼/규격.json 「전사」에서 온다.
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";

interface TranscribeSpec {
  제공자: "groq" | "speechmatics";
  설정?: { type?: string; transcription_config?: Record<string, unknown> };
  모델: string;
  엔드포인트: string;
  키_환경변수: string;
  응답형식: string;
  타임스탬프단위: string;
  온도: number;
  오디오추출: { 샘플레이트_hz: number; 채널: number; 코덱: string; 비트레이트: string; 확장자: string };
  파일상한_mb: number;
  분할전사: string;
  환청규칙: { 최소길이_s: number; 최대단어: number };
  늘어난발화_규칙: { 트리거_단어당_s: number; 트리거_여유_s: number; 무음_최소_s: number };
  무음스캔: { 필터: string; noise_dB: number; d_s: number };
}
const T = (spec as unknown as { 전사: TranscribeSpec })["전사"];

function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}

/** whisper verbose_json 에서 우리가 읽는 칸 */
interface AsrSegment { id?: number; start?: number; end?: number; text?: string; no_speech_prob?: number }
interface AsrRaw { language?: string; duration?: number; text?: string; segments?: AsrSegment[];
  /** Speechmatics json-v2 */ results?: { type?: string; start_time?: number; end_time?: number; attaches_to?: string; alternatives?: { content?: string }[] }[];
  job?: { duration?: number; id?: string } }

const r3 = (x: number) => Math.round(x * 1000) / 1000;

/** Groq 는 언어를 이름("English")으로 돌려준다. source.lang(코드 "en")과 비교하려고 코드로 맞춘다 */
const LANG_NAME_TO_CODE: Record<string, string> = {
  english: "en", korean: "ko", japanese: "ja", chinese: "zh", french: "fr", spanish: "es", german: "de",
  italian: "it", portuguese: "pt", russian: "ru", hindi: "hi", arabic: "ar", thai: "th", vietnamese: "vi", indonesian: "id",
};
function langCode(x: string | undefined): string | undefined {
  if (!x) return undefined;
  const k = x.trim().toLowerCase();
  return LANG_NAME_TO_CODE[k] ?? k;
}

/** payload.audio_bytes — ffprobe json_stdout({format:{size}}) 또는 숫자 */
function readBytes(x: unknown): number | null {
  if (typeof x === "number") return x;
  const size = (x as { format?: { size?: string | number } } | undefined)?.format?.size;
  return size === undefined ? null : Number(size);
}

export const transcript: StepHandler = {
  name: "transcript",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; lang?: string; title?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number } | undefined;

    if (!workdir || !source?.path || typeof ps?.duration_s !== "number") {
      return reject(
        "transcript", preset,
        "payload 에 carry 값(source·workdir·probe_summary)이 없다",
        "probe 응답의 source·workdir·probe_summary 를 payload 에 그대로 실어 transcript 를 다시 부르라.",
      );
    }
    const durationS = ps.duration_s;
    const audioPath = join(workdir, "transcript", `audio.${T.오디오추출.확장자}`);
    const rawPath = join(workdir, "transcript", "asr_raw.json");
    const outPath = join(workdir, "transcript", "transcript.json");

    // ── ① 지시 ──────────────────────────────────────────────────────────
    if (payload.asr === undefined) {
      const isSM = T.제공자 === "speechmatics";
      // Speechmatics(1순위) = 단어 단위 시각. 배치 v2: data_file + config 를 제출하고 폴링해서 json-v2 를 받는다.
      // Groq(폴백 2순위) = 세그먼트 단위. 규격 「전사.폴백_사다리」
      const smConfig = JSON.stringify({ ...(T.설정 ?? { type: "transcription" }), transcription_config: { ...((T.설정 ?? {}).transcription_config ?? {}), ...(source.lang ? { language: source.lang } : {}) } });
      const multipart: Record<string, string> = isSM
        ? { data_file: `@${audioPath}`, config: smConfig }
        : {
            file: `@${audioPath}`,
            model: T.모델,
            response_format: T.응답형식,
            "timestamp_granularities[]": T.타임스탬프단위,
            temperature: String(T.온도),
            ...(source.lang ? { language: source.lang } : {}),
          };

      return base("transcript", preset, {
        status: "execute",
        next_step: "transcript",
        message: `전사 지시: 오디오를 ${T.오디오추출.샘플레이트_hz}Hz 모노 ${T.오디오추출.확장자} 로 뽑고 Groq ${T.모델} 에 보내라. 결과(verbose_json)를 payload.asr 에 실어 transcript 를 다시 부르라.`,
        instructions: [
          `① do[] 의 extract_audio 를 그대로 실행해 ${audioPath} 를 만든다.`,
          `② do[] 의 audio_size 로 크기를 잰다. ${T.파일상한_mb}MB(규격.json 전사.파일상한_mb)를 넘으면 여기서 멈추고 사람에게 보고한다 — 장편 분할 전사는 미정이다.`,
          `③ jobs 의 transcribe 를 그대로 보낸다(배치면 batch 의 제출→폴링→받기 순서로). 키는 auth 대로 환경변수 ${T.키_환경변수} 에서 읽어 헤더에 붙인다. 키 값을 화면·파일·payload 에 쓰지 않는다. 응답 JSON 을 out 경로에 저장한다.`,
          "④ measure 대로 응답 JSON 을 payload.asr 에, 크기 JSON 을 payload.audio_bytes 에, silence_scan 의 stderr 전문을 payload.silences_raw 에 넣고, carry 값과 함께 transcript 를 다시 부른다.",
        ],
        then_call_with: [
          "step: 'transcript'",
          "payload: { workdir, source, probe_summary, asr: <Groq verbose_json 응답>, audio_bytes: <audio_size 의 JSON>, silences_raw: <silence_scan stderr> }",
        ],
        do: [
          {
            name: "extract_audio",
            argv: [
              "ffmpeg", "-y", "-v", "error",
              "-i", source.path,
              "-map", "0:a:0", "-vn",
              "-ar", String(T.오디오추출.샘플레이트_hz),
              "-ac", String(T.오디오추출.채널),
              "-c:a", T.오디오추출.코덱,
              "-b:a", T.오디오추출.비트레이트,
              audioPath,
            ],
            note: "첫 오디오 트랙만. 전사용 저용량 — 규격.json 전사.오디오추출",
          },
          {
            name: "audio_size",
            argv: ["ffprobe", "-v", "error", "-print_format", "json", "-show_entries", "format=size,duration", audioPath],
            note: "업로드 상한 확인용",
          },
          {
            name: "silence_scan",
            argv: ["ffmpeg", "-v", "info", "-nostats", "-i", audioPath, "-af", `${T.무음스캔.필터},silencedetect=noise=${T.무음스캔.noise_dB}dB:d=${T.무음스캔.d_s}`, "-f", "null", "-"],
            note: "오디오 전체 무음 구간 실측 (stderr 에 silence_start/end). 늘어난 발화 끝·나레 배치 틈·무음 컷이 이 실측을 쓴다",
          },
        ],
        jobs_kind: "transcribe",
        jobs: [
          {
            name: "asr",
            provider: T.제공자,
            model: T.모델,
            request: { method: "POST", url: T.엔드포인트, multipart },
            ...(isSM ? { batch: { submit_url: T.엔드포인트, status_url: `${T.엔드포인트}/{id}`, transcript_url: `${T.엔드포인트}/{id}/transcript?format=json-v2`, poll_s: 10, timeout_s: 1800 } } : {}),
            auth: {
              env: T.키_환경변수,
              header: `Authorization: Bearer <${T.키_환경변수} 값>`,
              note: "서버는 키를 보관하지 않는다. runner 가 로컬 환경변수에서 읽어 붙인다.",
            },
            out: rawPath,
            note: isSM
              ? "Speechmatics batch v2 — 제출 후 상태가 done 이 되면 json-v2 를 받는다. results[] 에 start_time·end_time·alternatives[0].content (단어 단위)"
              : "verbose_json — segments[] 에 start·end·text (폴백: 단어 시각 없음)",
          },
        ],
        measure: [
          { as: "asr", from: "job:asr", unit: "json_stdout" },
          { as: "audio_bytes", from: "job:audio_size", unit: "json_stdout" },
          { as: "silences_raw", from: "job:silence_scan", unit: "stderr" },
        ],
        carry: ["source", "workdir", "probe_summary"],
        source, workdir, probe_summary: ps,
        limits: { upload_max_mb: T.파일상한_mb, split_transcription: T.분할전사 },
      });
    }

    // ── ② 결과 검사 ──────────────────────────────────────────────────────
    const raw = payload.asr as AsrRaw;
    // Speechmatics(1순위) json-v2 → 단어 목록 + 발화(문장) 로 접는다. 단어 시각이 자막 시작·끝의 근거가 된다.
    const smWords: { w: string; s: number; e: number }[] = Array.isArray(raw?.results)
      ? raw.results.filter((r) => (r.type ?? "word") === "word" && typeof r.start_time === "number").map((r) => ({ w: String(r.alternatives?.[0]?.content ?? ""), s: r3(r.start_time as number), e: r3(r.end_time ?? r.start_time as number) })).filter((w) => w.w)
      : [];
    if (smWords.length && !Array.isArray(raw.segments)) {
      // 문장 끝 부호(. ? !)나 큰 쉼(≥0.6s)에서 발화를 끊는다 — 시각은 언제나 단어 실측
      const punct = Array.isArray(raw.results) ? raw.results.filter((r) => r.type === "punctuation") : [];
      const endsAfter = new Set(punct.filter((p2) => /[.?!]/.test(String(p2.alternatives?.[0]?.content ?? ""))).map((p2) => r3(p2.start_time ?? 0)));
      const segs: AsrSegment[] = [];
      let cur: { s: number; e: number; ws: string[] } | null = null;
      for (let i = 0; i < smWords.length; i++) {
        const w = smWords[i];
        if (!cur) cur = { s: w.s, e: w.e, ws: [w.w] };
        else { cur.ws.push(w.w); cur.e = w.e; }
        const nxt = smWords[i + 1];
        const gap = nxt ? nxt.s - w.e : Infinity;
        const sentenceEnd = [...endsAfter].some((t) => Math.abs(t - w.e) < 0.06);
        if (!nxt || sentenceEnd || gap >= 0.6) { segs.push({ start: cur.s, end: cur.e, text: cur.ws.join(" ") }); cur = null; }
      }
      raw.segments = segs;
    }
    if (typeof raw !== "object" || raw === null || !Array.isArray(raw.segments)) {
      return reject(
        "transcript", preset,
        "payload.asr 가 verbose_json 모양이 아니다 (segments[] 필요)",
        `response_format 이 ${T.응답형식} 인지 확인하고, ${rawPath} 의 JSON 전체를 payload.asr 에 실어 다시 부르라. 응답이 {error:…} 면 그 메시지를 사람에게 보여주고 멈춘다 (키·한도·파일 크기 문제일 수 있다).`,
      );
    }
    // 규칙 (단계상세.md 2. transcript): 발화 시작이 원본 길이 이후면 제거하고 경고 기록.
    //   근거: Full Time whisper 끝부분 환청 실측 ("Thank you." 925.9→955.9s, 2026-08-15)
    // 원본 길이를 넘는 끝 타임코드는 길이에 맞춰 자른다.
    // 무음 실측 (silence_scan stderr) → [[start,end],…]. 없으면 빈 배열 + 경고 (늘어난 발화 끝은 못 자른다)
    const silences: [number, number][] = [];
    {
      const txt = typeof payload.silences_raw === "string" ? payload.silences_raw : "";
      let cur: number | null = null;
      for (const m of txt.matchAll(/silence_(start|end): ([\d.]+)/g)) {
        if (m[1] === "start") cur = Number(m[2]);
        else if (cur !== null) { silences.push([r3(cur), r3(Number(m[2]))]); cur = null; }
      }
      if (cur !== null) silences.push([r3(cur), r3(durationS)]);
    }
    // 규칙 ⓐ 환청 (규격.json 전사.환청규칙): 길이 ≥ 최소길이_s 이면서 단어 ≤ 최대단어 → 제거+경고.
    //   근거: Full Time 실측 — 무음 구간에서 정확히 30.0s "Thank you."/"The End"/"I'm sorry." 10개 (단계상세.md 2. transcript)
    let clamped = 0;
    const stretched: { start: number; end: number; text: string; cut_to: number }[] = [];
    const droppedAfterEnd: { start: number; end: number; text: string }[] = [];
    const droppedHallucination: { start: number; end: number; text: string }[] = [];
    const H = T.환청규칙;
    const utterances = raw.segments
      .filter((s) => typeof s.start === "number" && typeof s.end === "number" && (s.text ?? "").trim().length > 0 && s.end > s.start)
      .filter((s) => {
        const dur = (s.end as number) - (s.start as number);
        const words = (s.text ?? "").trim().split(/\s+/).filter(Boolean).length;
        if (dur >= H.최소길이_s && words <= H.최대단어) { droppedHallucination.push({ start: s.start as number, end: s.end as number, text: (s.text ?? "").trim() }); return false; }
        return true;
      })
      .filter((s) => {
        if ((s.start as number) >= durationS) { droppedAfterEnd.push({ start: s.start as number, end: s.end as number, text: (s.text ?? "").trim() }); return false; }
        return true;
      })
      .map((s, i) => {
        let end = s.end as number;
        if (end > durationS) { end = durationS; clamped++; }
        // 규칙 ⓒ 늘어난 발화 (규격 전사.늘어난발화_규칙): 끝을 **실측**으로 — 원래 끝 앞의 꼬리 무음(silence_scan)을 벗겨 '마지막 소리의 끝'으로 자른다.
        //   시작은 믿는다. 첫 무음에서 자르지 않는다(여러 마디가 한 세그먼트로 합쳐진 발화를 망친다). 무음 실측이 없으면 자르지 않는다.
        //   단어 수 기준(트리거)은 '자른 목록'을 경고에 실을 때 수상한 것만 골라 보여주는 용도다.
        if (silences.length) {
          const st = s.start as number, orig = end;
          let guard = 0;
          while (guard++ < 50) {
            const tail = silences.find(([a, b]) => a < end && b >= end - 0.05 && a > st + 0.3 && b - a >= T.늘어난발화_규칙.무음_최소_s);
            if (!tail) break;
            end = tail[0];
          }
          if (orig - end > 0.2) {
            const words = (s.text ?? "").trim().split(/\s+/).filter(Boolean).length;
            const suspicious = orig - st > words * T.늘어난발화_규칙.트리거_단어당_s + T.늘어난발화_규칙.트리거_여유_s;
            stretched.push({ start: st, end: orig, text: (s.text ?? "").trim() + (suspicious ? "" : " (경미)"), cut_to: r3(end) });
          }
        }
        return { i, start: r3(s.start as number), end: r3(end), text: (s.text ?? "").trim() };
      })
      .filter((u) => u.end > u.start);

    if (utterances.length === 0) {
      return reject(
        "transcript", preset,
        "hard_fail: 발화가 0건이다 — 대사·나레이션 근거가 없어 다음 단계로 갈 수 없다",
        `① ${audioPath} 를 직접 들어 소리가 있는지 확인하라 (무음이면 원본 오디오 트랙 문제 → probe 부터 다시). ` +
          `② 소리는 있는데 0건이면 language 값(${source.lang ?? "미지정"})이 원어와 맞는지 확인하고, 틀리면 source.lang 을 고쳐 start 부터 다시. ` +
          `③ 그래도 0건이면 ${rawPath} 의 text·segments 를 사람에게 보여주고 멈춘다.`,
      );
    }

    const speechS = r3(utterances.reduce((a, u) => a + (u.end - u.start), 0));
    const silenceRatio = durationS > 0 ? r3(Math.max(0, 1 - speechS / durationS)) : null;
    const lastEnd = utterances[utterances.length - 1].end;
    const warnings: string[] = [];
    if (droppedHallucination.length > 0) {
      const dropS = r3(droppedHallucination.reduce((a, d) => a + (d.end - d.start), 0));
      warnings.push(`환청 규칙(길이 ≥${H.최소길이_s}s · 단어 ≤${H.최대단어})으로 세그먼트 ${droppedHallucination.length}건(${dropS}s)을 제거했다: ${droppedHallucination.map((d) => `${r3(d.start)}→${r3(d.end)}s "${d.text.slice(0, 20)}"`).join(", ")}`);
    }
    if (droppedAfterEnd.length > 0) {
      warnings.push(`원본 길이(${durationS}s) 이후에 시작하는 발화 ${droppedAfterEnd.length}건을 제거했다 (whisper 끝부분 환청 규칙): ${droppedAfterEnd.map((d) => `${d.start}→${d.end}s "${d.text.slice(0, 20)}"`).join(", ")}`);
    }
    if (silences.length === 0) warnings.push("무음 실측(silence_scan)이 없다 — 늘어난 발화 끝을 자르지 못했고 subtitle 이 틈·컷을 실측 없이 계산한다. ① 의 silence_scan 을 실행해 payload.silences_raw 를 넣어라.");
    if (stretched.length > 0) warnings.push(`발화 ${stretched.length}건의 꼬리 무음을 실측대로 벗겼다 (규격 전사.늘어난발화_규칙 — 끝 = 마지막 소리의 끝): ${stretched.slice(0, 6).map((x) => `${r3(x.start)}→${r3(x.end)}s→${x.cut_to}s "${x.text.slice(0, 18)}"`).join(", ")}${stretched.length > 6 ? " …" : ""}`);
    if (clamped > 0) warnings.push(`원본 길이(${durationS}s)를 넘는 발화 ${clamped}건의 끝을 길이에 맞춰 잘랐다 (whisper 끝부분 특성. 마지막 발화 본문이 "Thank you." 류면 환청일 수 있다 — 사람이 확인).`);
    if (durationS > 0 && lastEnd < durationS * 0.5) {
      warnings.push(`마지막 발화 끝(${lastEnd}s)이 원본 길이의 절반 이하다 — 전사가 중간에 끊겼을 수 있다 (파일 상한·분할 전사 미정).`);
    }
    if (raw.language && source.lang && langCode(raw.language) !== langCode(source.lang)) {
      warnings.push(`Groq 감지 언어(${raw.language})가 source.lang(${source.lang})과 다르다.`);
    }

    const transcriptDoc = {
      source: source.path,
      title: source.title ?? null,
      lang: source.lang ?? langCode(raw.language) ?? null,
      asr: { provider: T.제공자, model: T.모델, raw: rawPath, timestamp_unit: smWords.length ? "word" : "segment", words_measured: smWords.length },
      words: smWords,
      duration_s: durationS,
      utterance_count: utterances.length,
      speech_s: speechS,
      silences,
      silence_scan: T.무음스캔,
      warnings,
      utterances,
    };

    return base("transcript", preset, {
      status: "execute",
      next_step: "brief",
      message: `전사 통과: 발화 ${utterances.length}건 · 발화 ${speechS}s / 원본 ${durationS}s · 무음 비율 ${silenceRatio}. write_files 를 쓰고 brief 로 넘어가라.`,
      instructions: [
        `① write_files 의 내용을 그대로 ${outPath} 에 쓴다.`,
        "② metrics 를 사람에게 한 줄로 보여준다.",
        "③ carry 의 값(source·workdir·probe_summary·transcript_path)을 payload 에 그대로 실어 next_step 을 부른다. 전사 본문은 payload 에 싣지 않는다 (brief 는 파일 경로로 읽는다).",
        "④ brief 는 아직 스텁이다 — judge 모델·조각 크기 결정 대기 (단계상세.md 미정 표).",
      ],
      then_call_with: ["step: 'brief'", "payload: { workdir, source, probe_summary, transcript_path }"],
      jobs_kind: null,
      jobs: [],
      write_files: [{ path: outPath, content: transcriptDoc, note: "발화 단위 + 시작·끝 타임코드. brief 의 입력" }],
      measure: [],
      metrics: {
        utterance_count: utterances.length,
        speech_s: speechS,
        silence_ratio: silenceRatio,
        dropped_hallucination: droppedHallucination.length,
        dropped_hallucination_s: r3(droppedHallucination.reduce((a, d) => a + (d.end - d.start), 0)),
        stretched_cut: stretched.length,
        silences_measured: silences.length,
        dropped_after_end: droppedAfterEnd.length,
        clamped_end: clamped,
        audio_bytes: readBytes(payload.audio_bytes),
      },
      carry: ["source", "workdir", "probe_summary", "transcript_path"],
      source, workdir, probe_summary: ps, transcript_path: outPath,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
