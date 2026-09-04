/**
 * steps/린박스/voice.ts — lb_voice: 나레 TTS(★Typecast 유료) + 정규화 + 나레 낱말 시각(★Speechmatics 1건). 세 번 부른다.
 *
 * 볼케이노 대응: stitch_narr 응답(jobs_kind synthesize · raw 캐시 · steps 2단계 · measure wav_secs) 을 그대로 베낀다(설계 5.6.1) + narr_align.py(규격 §8 9).
 *   ① wav 결과 없음 → N 블록마다 Typecast 요청 본문을 짓고(이나 tc_62686be9… · normal · tempo 1.2 · ssfm-v30 — 볼트 drv2 VOICE 훅과 같다),
 *      raw 는 cache/tts/<키>.raw.wav (있으면 건너뜀 → 재과금 없음), post 로 ffmpeg 정규화 2단계(narr_norm/nNN.wav 1ch · blocks/nNN.wav 2ch),
 *      measure 로 블록마다 길이를 재 온다. ★유료 — 글자 수로 비용을 말하고 승인 뒤 실행.
 *   ② wav 길이 있음·narr_words 없음 → 검사(빠진 블록·너무 짧음) → narr_align.py 지시(★Speechmatics 1건 · 나레 전부를 무음 1초로 이어 한 번만).
 *   ③ narr_words 있음 → 검사(N 블록마다 낱말) → next_step=lb_blocks.
 * ★배속은 TTS 본문 audio_tempo 1.2 한 번뿐이다 — 키트 speed_narr.py 는 안 돌린다(두 번 걸면 안 된다, 맥 사슬도 안 돈다).
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import type { SynthesizeJob } from "../../schema.js";
import { CARRY_KEYS, RUNNER_DIR, join, ours, r3, readCarry, spec, str } from "./lib.js";

type NBlock = ["N", string, [number, number][]];
const NAR = (spec as unknown as { narration: { engine: string; voice: string; voice_id: string; tempo: number; emotion_preset: string; model?: string } }).narration;
const O = ours as unknown as { tts: { chars_per_sec: number } };
const ENDPOINT = "https://api.typecast.ai/v1/text-to-speech";
/** 볼케이노 stitch_narr 후처리 2단계 — 그대로 (설계 5.6.1 ③) */
const NORM1 = "loudnorm=I=-23.0:TP=-3:LRA=9";
const NORM2 = "silenceremove=start_periods=1:start_threshold=-38dB:start_silence=0.1:stop_periods=-1:stop_threshold=-38dB:stop_duration=0.20:stop_silence=0.02,loudnorm=I=-23:TP=-3:LRA=9";

/** 결정적 16자 hex 키 — 같은 문장·같은 목소리는 같은 raw 를 쓴다(재과금 없음). FNV-1a 64비트 */
export function ttsKey(s: string): string {
  let h1 = 0xcbf29ce4, h2 = 0x84222325; // 64비트를 32비트 둘로
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 ^ (c * 31 + 7), 0x01000193) >>> 0;
  }
  return h1.toString(16).padStart(8, "0") + h2.toString(16).padStart(8, "0");
}

function nBlocks(payload: Record<string, unknown>): { index: number; text: string }[] {
  const a = payload.authored as { BLOCKS?: unknown[] } | undefined;
  const B = Array.isArray(a?.BLOCKS) ? a!.BLOCKS! : [];
  return B.map((b, i) => (Array.isArray(b) && b[0] === "N" ? { index: i, text: String((b as NBlock)[1] ?? "").trim() } : null)).filter((x): x is { index: number; text: string } => x !== null);
}
const nn = (i: number) => `n${String(i).padStart(2, "0")}`;

export const lbVoice: StepHandler = {
  name: "lb_voice",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_voice", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_script 응답의 carry 값을 payload 에 그대로 실어 lb_voice 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    const N = nBlocks(payload);
    if (!N.length) {
      return reject("lb_voice", preset, "payload.authored 에 나레(N) 블록이 없다", "lb_script 응답의 carry(authored 포함)를 그대로 실어 다시 부르라. 나레가 정말 없는 편이면 이 프리셋(린박스)이 아니다 — 나레 15~19장이 채널 규격이다.");
    }
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, scene_count: payload.scene_count ?? null, 대사: payload.대사, 편정보: payload.편정보, authored: payload.authored,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "scene_count", "대사", "편정보", "authored"];
    const secKey = (i: number) => `${nn(i)}_secs`;

    // ── ③ narr_words 검사 ───────────────────────────────────────────────
    if (payload.narr_words !== undefined) {
      const nw = (typeof payload.narr_words === "object" && payload.narr_words !== null ? payload.narr_words : {}) as Record<string, unknown[]>;
      const missing = N.filter((b) => !Array.isArray(nw[String(b.index)]) || !(nw[String(b.index)] as unknown[]).length).map((b) => b.index);
      if (missing.length) {
        return reject("lb_voice", preset, `narr_words.json 에 낱말이 없는 나레 블록: ${missing.join(", ")}`, "narr_align.py 로그(narr_log)를 보라 — Speechmatics 키(~/.volcano/.env 의 SPEECHMATICS_API_KEY)가 없거나 blocks/nNN.wav 가 비었을 수 있다. 고친 뒤 payload.narr_words 를 빼고 lb_voice 를 다시 부르라.");
      }
      const wordCount = N.reduce((a, b) => a + (nw[String(b.index)] as unknown[]).length, 0);
      return base("lb_voice", preset, {
        status: "execute",
        next_step: "lb_blocks",
        message: `나레 ${N.length}블록 · 낱말 시각 ${wordCount}개 확인. lb_blocks(얼굴·재프레이밍·블록 굽기·서버 ass 상당)로.`,
        instructions: ["① carry 의 값(… wav_secs·narr_words)을 payload 에 그대로 실어 lb_blocks 를 부른다."],
        then_call_with: ["step: 'lb_blocks'", "payload: { …carry, wav_secs, narr_words }"],
        jobs_kind: null,
        jobs: [],
        measure: [],
        metrics: { n_blocks: N.length, narr_words: wordCount },
        carry: [...carryKeys, "wav_secs", "narr_words"],
        ...common,
        wav_secs: payload.wav_secs,
        narr_words: payload.narr_words,
      });
    }

    // ── ② wav 검사 → narr_align 지시 ─────────────────────────────────────
    const gotSecs = N.map((b) => [b.index, payload[secKey(b.index)]] as const).filter(([, v]) => typeof v === "number");
    if (gotSecs.length) {
      if (!repo) return reject("lb_voice", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
      const wavSecs: Record<string, number> = {};
      const bad: string[] = [];
      for (const b of N) {
        const v = payload[secKey(b.index)];
        if (typeof v !== "number" || !Number.isFinite(v)) { bad.push(`블록 ${b.index}(${nn(b.index)}) 길이를 못 쟀다`); continue; }
        if (v < 0.3) bad.push(`블록 ${b.index} 나레가 ${r3(v)}초 — 너무 짧다(응답이 비었거나 잘렸다)`);
        wavSecs[String(b.index)] = r3(v);
      }
      if (bad.length) return reject("lb_voice", preset, `나레 wav 가 맞지 않다 (${bad.length}건)`, bad.join(" · ") + " — cache/tts/<키>.raw.wav 를 지우고 lb_voice 를 다시 부르면 그 블록만 다시 합성한다.");
      const total = r3(Object.values(wavSecs).reduce((a, v) => a + v, 0));
      const chars = N.reduce((a, b) => a + b.text.replace(/\s/g, "").length, 0);
      const cps = total ? r3(chars / total) : 0;
      const warnings: string[] = [];
      if (cps && (cps < 8 || cps > 12.5)) warnings.push(`실측 ${cps}자/초 — 우리실측 ${O.tts.chars_per_sec}자/초와 다르다. 목소리·배속이 규격(이나 · tempo 1.2)과 같은지 확인.`);
      return base("lb_voice", preset, {
        status: "execute",
        next_step: "lb_voice",
        message: `나레 ${N.length}블록 합성 확인 — 총 ${total}초 · ${chars}자 (${cps}자/초). ★유료 — 나레 낱말 시각을 재려고 Speechmatics 1건(나레 전부 ${total}초 + 무음 ${N.length}초)을 보낸다. 승인 뒤 jobs 를 돌리라.`,
        instructions: [
          `① ★유료 API 단계다 — Speechmatics 배치 1건(약 ${r3((total + N.length) / 60)}분 분량). 승인받은 뒤 실행.`,
          `② jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 실행한다. narr_align.py 가 blocks/nNN.wav 를 무음 1초로 이어 한 번만 보내고 낱말을 블록으로 되돌려 narr_words.json 을 쓴다(토막마다 부르면 최소 과금이 N번 붙는다). ★키는 ~/.volcano/.env 의 SPEECHMATICS_API_KEY 에서 읽는다(narr_align.py 는 keys/ 자리를 안 본다).`,
          "③ measure 대로 payload.narr_words(narr_words.json)·payload.narr_log 를 실어 lb_voice 를 다시 부른다.",
        ],
        then_call_with: ["step: 'lb_voice'", "payload: { …carry, wav_secs, narr_words: <narr_words.json>, narr_log: <stdout> }"],
        jobs_kind: "argv",
        jobs_cwd: carry.ep_dir,
        jobs: [
          { name: "narr_align", argv: ["python", join(repo, RUNNER_DIR, "도구", "narr_align.py")], out: join(carry.ep_dir, "_narr_align_log.txt"), note: "★유료 Speechmatics 1건 — 나레 낱말 시각 → narr_words.json (--reuse 면 재과금 없음)." },
          { name: "read_narr_words", argv: ["python", "-c", "import io;print(io.open('narr_words.json',encoding='utf-8').read())"], note: "narr_words.json 을 표준출력으로 — measure 가 payload.narr_words 로 싣는다." },
        ],
        measure: [
          { as: "narr_words", from: "job:read_narr_words", unit: "json_stdout" },
          { as: "narr_log", from: "job:narr_align", unit: "stdout" },
        ],
        metrics: { n_blocks: N.length, narr_total_s: total, narr_chars: chars, chars_per_sec: cps },
        carry: [...carryKeys, "wav_secs"],
        ...common,
        wav_secs: wavSecs,
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ① TTS 지시 (★Typecast) ──────────────────────────────────────────
    const voiceSig = `${NAR.voice_id}|${NAR.emotion_preset}|None|${NAR.tempo}`;
    const chars = N.reduce((a, b) => a + b.text.replace(/\s/g, "").length, 0);
    const digits = N.filter((b) => /[0-9]/.test(b.text)).map((b) => b.index);
    const warnings: string[] = [];
    if (digits.length) warnings.push(`나레 블록 ${digits.join(", ")} 에 숫자가 있다 — 볼케이노 서버가 하던 «숫자·단위 한글 발음 바꾸기»는 여기 없다. 대본에서 한글로 적어라(«3만 자» → «삼만 자»).`);
    const jobs = N.map((b) => {
      const key = ttsKey(`${b.text}|${voiceSig}`);
      const raw = join(carry.ep_dir, "cache", "tts", `${key}.raw.wav`);
      const norm = join(carry.ep_dir, "narr_norm", `${nn(b.index)}.wav`);
      const out = join(carry.ep_dir, "blocks", `${nn(b.index)}.wav`);
      return {
        name: nn(b.index),
        provider: "typecast",
        model: NAR.model ?? "ssfm-v30",
        voice_id: NAR.voice_id,
        request: {
          method: "POST",
          url: ENDPOINT,
          headers: { "Content-Type": "application/json" },
          body: {
            voice_id: NAR.voice_id, text: b.text, model: NAR.model ?? "ssfm-v30", language: "KOR",
            prompt: { emotion_type: "preset", emotion_preset: NAR.emotion_preset },
            output: { volume: 100, audio_pitch: 0, audio_tempo: NAR.tempo, audio_format: "wav" },
          },
        },
        auth: { env: "TYPECAST_API_KEY", header: "X-API-KEY", note: "본인 Typecast 키 — ~/.volcano/keys/typecast 파일 또는 TYPECAST_API_KEY 환경변수에서 읽어 X-API-KEY 헤더에. 서버는 키를 갖고 있지 않고 받지도 않는다." },
        out: raw,
        skip_if: { path: raw, key, min_bytes: 2000 },
        post_steps: [
          { argv: ["ffmpeg", "-y", "-i", raw, "-af", NORM1, "-ar", "48000", "-ac", "1", norm], out: norm },
          { argv: ["ffmpeg", "-y", "-i", norm, "-af", NORM2, "-ar", "48000", "-ac", "2", out], out },
        ],
        final_out: out,
        note: `블록 ${b.index} 「${b.text}」 ${b.text.replace(/\s/g, "").length}자 — raw 캐시(${key})가 있으면 요청을 안 보낸다.`,
      } as unknown as SynthesizeJob;
    });
    const post = N.flatMap((b) => {
      const key = ttsKey(`${b.text}|${voiceSig}`);
      const raw = join(carry.ep_dir, "cache", "tts", `${key}.raw.wav`);
      const norm = join(carry.ep_dir, "narr_norm", `${nn(b.index)}.wav`);
      const out = join(carry.ep_dir, "blocks", `${nn(b.index)}.wav`);
      return [
        { name: `${nn(b.index)}_norm`, argv: ["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", NORM1, "-ar", "48000", "-ac", "1", norm], note: "정규화 ① 1ch(narr_norm — 프리미어 A2 나레 트랙이 문다). 볼케이노 stitch_narr steps[0]" },
        { name: `${nn(b.index)}_block`, argv: ["ffmpeg", "-y", "-v", "error", "-i", norm, "-af", NORM2, "-ar", "48000", "-ac", "2", out], note: "정규화 ② 앞뒤 무음 걷고 2ch(blocks/nNN.wav — N 블록 굽기의 입력). 볼케이노 stitch_narr steps[1]" },
      ];
    });
    return base("lb_voice", preset, {
      status: "execute",
      next_step: "lb_voice",
      message: `★유료 단계 — 나레 ${N.length}블록 · ${chars}자를 Typecast(이나 ${NAR.voice_id} · ${NAR.emotion_preset} · ${NAR.tempo}배속 · ${NAR.model ?? "ssfm-v30"})로 합성한다. 같은 문장은 raw 캐시로 재과금이 없다. 실행 전에 비용(글자 수 ${chars}자 · Typecast 요금제 — 무료 월 3만 자)을 보고하고 승인받으라.`,
      instructions: [
        `① ★유료 API 단계다 — 나레 ${chars}자(Typecast 본인 키·본인 계정). 승인받은 뒤 jobs 를 돌린다. 429·403 이면 새 키를 만들어 이어 돌리지 마라 — 계정 정지 사유다. 잠시 뒤 같은 키로.`,
        `② jobs(synthesize)는 편 폴더 ${carry.ep_dir} 를 cwd 로: raw(out)가 이미 있고 ${2000}바이트를 넘으면(skip_if) 요청하지 않는다. 받은 응답(wav)은 .part 로 받아 검사 뒤 raw 로 옮긴다. 응답이 2000바이트 이하면 실패다.`,
        "③ post 의 ffmpeg 두 단계를 블록마다 순서대로 돌린다(정규화 ① narr_norm/nNN.wav 1ch → ② blocks/nNN.wav 2ch, 앞뒤 무음 제거). ★후처리는 캐시가 있어도 언제나 다시 돈다.",
        "④ measure 대로 블록마다 blocks/nNN.wav 길이(초)를 payload.nNN_secs 에 실어 lb_voice 를 **다시** 부른다.",
      ],
      then_call_with: ["step: 'lb_voice'", `payload: { …carry, ${N.map((b) => secKey(b.index)).join(", ")} }`],
      jobs_kind: "synthesize",
      jobs_cwd: carry.ep_dir,
      jobs,
      post,
      measure: N.map((b) => ({ as: secKey(b.index), from: `job:${nn(b.index)}_block`, unit: "seconds" as const })),
      metrics: { n_blocks: N.length, narr_chars: chars, est_narr_s: r3(chars / O.tts.chars_per_sec), voice_id: NAR.voice_id, tempo: NAR.tempo },
      carry: carryKeys,
      ...common,
      retry_policy: { retry: 4, retry_status: [500, 502, 503, 504], backoff_s: [2, 4, 8, 16], stop_on: [429, 403, 401] },
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
