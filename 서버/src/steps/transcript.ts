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
  제공자: "groq";
  모델: string;
  엔드포인트: string;
  키_환경변수: string;
  응답형식: string;
  타임스탬프단위: string;
  온도: number;
  오디오추출: { 샘플레이트_hz: number; 채널: number; 코덱: string; 비트레이트: string; 확장자: string };
  파일상한_mb: number;
  분할전사: string;
}
const T = (spec as unknown as { 전사: TranscribeSpec })["전사"];

function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}

/** whisper verbose_json 에서 우리가 읽는 칸 */
interface AsrSegment { id?: number; start?: number; end?: number; text?: string; no_speech_prob?: number }
interface AsrRaw { language?: string; duration?: number; text?: string; segments?: AsrSegment[] }

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
      const multipart: Record<string, string> = {
        file: `@${audioPath}`,
        model: T.모델,
        response_format: T.응답형식,
        "timestamp_granularities[]": T.타임스탬프단위,
        temperature: String(T.온도),
      };
      if (source.lang) multipart.language = source.lang;

      return base("transcript", preset, {
        status: "execute",
        next_step: "transcript",
        message: `전사 지시: 오디오를 ${T.오디오추출.샘플레이트_hz}Hz 모노 ${T.오디오추출.확장자} 로 뽑고 Groq ${T.모델} 에 보내라. 결과(verbose_json)를 payload.asr 에 실어 transcript 를 다시 부르라.`,
        instructions: [
          `① do[] 의 extract_audio 를 그대로 실행해 ${audioPath} 를 만든다.`,
          `② do[] 의 audio_size 로 크기를 잰다. ${T.파일상한_mb}MB(규격.json 전사.파일상한_mb)를 넘으면 여기서 멈추고 사람에게 보고한다 — 장편 분할 전사는 미정이다.`,
          `③ jobs 의 transcribe 를 그대로 보낸다. 키는 auth 대로 환경변수 ${T.키_환경변수} 에서 읽어 헤더에 붙인다. 키 값을 화면·파일·payload 에 쓰지 않는다. 응답 JSON 을 out 경로에 저장한다.`,
          "④ measure 대로 응답 JSON 을 payload.asr 에, 크기 JSON 을 payload.audio_bytes 에 넣고, carry 값과 함께 transcript 를 다시 부른다.",
        ],
        then_call_with: [
          "step: 'transcript'",
          "payload: { workdir, source, probe_summary, asr: <Groq verbose_json 응답>, audio_bytes: <audio_size 의 JSON> }",
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
        ],
        jobs_kind: "transcribe",
        jobs: [
          {
            name: "groq_asr",
            provider: T.제공자,
            model: T.모델,
            request: { method: "POST", url: T.엔드포인트, multipart },
            auth: {
              env: T.키_환경변수,
              header: `Authorization: Bearer <${T.키_환경변수} 값>`,
              note: "서버는 키를 보관하지 않는다. runner 가 로컬 환경변수에서 읽어 붙인다.",
            },
            out: rawPath,
            note: "verbose_json — segments[] 에 start·end·text",
          },
        ],
        measure: [
          { as: "asr", from: "job:groq_asr", unit: "json_stdout" },
          { as: "audio_bytes", from: "job:audio_size", unit: "json_stdout" },
        ],
        carry: ["source", "workdir", "probe_summary"],
        source, workdir, probe_summary: ps,
        limits: { upload_max_mb: T.파일상한_mb, split_transcription: T.분할전사 },
      });
    }

    // ── ② 결과 검사 ──────────────────────────────────────────────────────
    const raw = payload.asr as AsrRaw;
    if (typeof raw !== "object" || raw === null || !Array.isArray(raw.segments)) {
      return reject(
        "transcript", preset,
        "payload.asr 가 verbose_json 모양이 아니다 (segments[] 필요)",
        `response_format 이 ${T.응답형식} 인지 확인하고, ${rawPath} 의 JSON 전체를 payload.asr 에 실어 다시 부르라. 응답이 {error:…} 면 그 메시지를 사람에게 보여주고 멈춘다 (키·한도·파일 크기 문제일 수 있다).`,
      );
    }
    // 원본 길이를 넘는 타임코드는 길이에 맞춰 자른다 (whisper 는 파일 끝에서 end 를 넘겨 찍기도 한다)
    let clamped = 0;
    const utterances = raw.segments
      .filter((s) => typeof s.start === "number" && typeof s.end === "number" && (s.text ?? "").trim().length > 0 && s.end > s.start && s.start < durationS)
      .map((s, i) => {
        let end = s.end as number;
        if (end > durationS) { end = durationS; clamped++; }
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
      asr: { provider: T.제공자, model: T.모델, raw: rawPath },
      duration_s: durationS,
      utterance_count: utterances.length,
      speech_s: speechS,
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
        audio_bytes: readBytes(payload.audio_bytes),
      },
      carry: ["source", "workdir", "probe_summary", "transcript_path"],
      source, workdir, probe_summary: ps, transcript_path: outPath,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
