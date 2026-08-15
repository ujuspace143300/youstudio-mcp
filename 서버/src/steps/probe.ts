/**
 * steps/probe.ts — 원본 확인. 명세: 설계/단계상세.md 「1. probe」
 *
 * 하는 일:
 *   1) start 가 만들어 둔 probe/probe.json 내용을 payload.probe 로 받는다 (jobs 없음 — argv 는 start 가 실행)
 *   2) 오디오 트랙이 없으면 hard_fail = status "error" 반려 + 수리 지침
 *   3) metrics 로 길이(초)·해상도·fps·오디오 유무를 뱉는다 (HARNESS 4장)
 *   4) carry 에 다음 단계가 쓸 값(source·workdir·probe_summary)을 담고 next_step=transcript
 */
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";

// ffprobe -print_format json 출력에서 우리가 읽는 칸만
interface FfStream {
  codec_type?: string;
  codec_name?: string;
  width?: number;
  height?: number;
  r_frame_rate?: string;
  avg_frame_rate?: string;
  duration?: string;
  channels?: number;
  sample_rate?: string;
  channel_layout?: string;
  tags?: { language?: string };
}
interface FfProbe {
  streams?: FfStream[];
  format?: { duration?: string; size?: string; bit_rate?: string; format_name?: string };
}

/** "24000/1001" → 23.976 (소수 3자리). 못 읽으면 null */
export function parseFps(rate: string | undefined): number | null {
  if (!rate) return null;
  const [n, d] = rate.split("/").map(Number);
  if (!Number.isFinite(n) || n <= 0) return null;
  const den = d === undefined ? 1 : d;
  if (!Number.isFinite(den) || den <= 0) return null;
  return Math.round((n / den) * 1000) / 1000;
}

function isProbe(x: unknown): x is FfProbe {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

export const probe: StepHandler = {
  name: "probe",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source;
    const raw = payload.probe;

    if (!isProbe(raw) || !Array.isArray(raw.streams) || !raw.format) {
      return reject(
        "probe", preset,
        "payload.probe 가 없거나 ffprobe JSON 모양이 아니다 (streams·format 필요)",
        "start 가 지시한 ffprobe 를 다시 실행해 <workdir>/probe/probe.json 을 만들고, 그 JSON 전체를 payload.probe 에 실어 probe 를 다시 부르라.",
      );
    }
    if (!workdir || !source) {
      return reject(
        "probe", preset,
        "payload 에 carry 값(source·workdir)이 없다",
        "start 응답의 source 와 workdir 를 payload 에 그대로 실어 probe 를 다시 부르라.",
      );
    }

    const video = raw.streams.find((s) => s.codec_type === "video");
    const audios = raw.streams.filter((s) => s.codec_type === "audio");
    const durationS = Number(raw.format.duration ?? video?.duration ?? NaN);

    if (!video) {
      return reject(
        "probe", preset,
        "영상 트랙이 없다",
        "source.path 가 영화 원본 영상 파일인지 확인하라. 소리만 있는 파일이면 영상 원본으로 바꿔 start 부터 다시 부르라.",
      );
    }
    if (!Number.isFinite(durationS) || durationS <= 0) {
      return reject(
        "probe", preset,
        "길이(format.duration)를 읽을 수 없다",
        "파일이 깨졌거나 아직 쓰는 중일 수 있다. `ffprobe -v error -show_format <파일>` 로 duration 이 나오는지 확인하고, 안 나오면 원본을 다시 받아 start 부터 다시 부르라.",
      );
    }
    // hard_fail: 오디오 트랙 없음 (단계상세.md 1. probe)
    if (audios.length === 0) {
      return reject(
        "probe", preset,
        "hard_fail: 오디오 트랙이 없다 — 전사(transcript)와 대사 사용이 불가능하다",
        "① 원본에 소리가 원래 있는지 확인하라 (`ffprobe -v error -select_streams a -show_streams <파일>`). " +
          "② 오디오가 별도 파일이면 `ffmpeg -i <영상> -i <오디오> -c copy -map 0:v -map 1:a <새파일.mp4>` 로 합친 뒤, 그 파일로 start 부터 다시 부르라. " +
          "③ 정말 무성 영상이면 이 스타일(영화롱폼)로는 만들 수 없다 — 다른 소재를 고르라.",
      );
    }

    const a0 = audios[0];
    const fps = parseFps(video.avg_frame_rate) ?? parseFps(video.r_frame_rate);
    const summary = {
      duration_s: Math.round(durationS * 1000) / 1000,
      width: video.width ?? null,
      height: video.height ?? null,
      fps,
      fps_fraction: video.avg_frame_rate ?? video.r_frame_rate ?? null,
      video_codec: video.codec_name ?? null,
      audio: true,
      audio_tracks: audios.length,
      audio_codec: a0.codec_name ?? null,
      audio_channels: a0.channels ?? null,
      audio_sample_rate: a0.sample_rate ? Number(a0.sample_rate) : null,
      audio_lang: a0.tags?.language ?? null,
    };

    const warnings: string[] = [];
    if (fps === null) warnings.push("fps 를 읽지 못했다 (avg_frame_rate/r_frame_rate 없음). transcript 는 진행 가능하나 subtitle 단계 전에 확인 필요.");
    if (audios.length > 1) warnings.push(`오디오 트랙이 ${audios.length}개다. 첫 트랙(${a0.tags?.language ?? "언어 미상"})을 쓴다. 다른 트랙을 쓰려면 원본을 바꿔 start 부터 다시.`);

    return base("probe", preset, {
      status: "execute",
      next_step: "transcript",
      message: `원본 확인 통과: ${summary.duration_s}s · ${summary.width}x${summary.height} · ${fps ?? "?"}fps · 오디오 ${audios.length}트랙. transcript 로 넘어가라.`,
      instructions: [
        "① metrics 는 이 단계가 잰 숫자다. 사람에게 한 줄로 보여준다.",
        "② carry 의 값(source·workdir·probe_summary)을 payload 에 그대로 실어 next_step 을 부른다.",
        "③ transcript 는 아직 스텁이다 — ASR 제공자 결정 대기 (규격.json 에 미정. Groq whisper-large-v3-turbo 권장). 결정이 나기 전엔 transcript 가 not_implemented 를 돌려준다.",
      ],
      then_call_with: [
        "step: 'transcript'",
        "payload: { workdir, source, probe_summary }",
      ],
      jobs_kind: null,
      jobs: [],
      measure: [],
      metrics: {
        duration_s: summary.duration_s,
        width: summary.width,
        height: summary.height,
        fps,
        audio: summary.audio,
        audio_tracks: summary.audio_tracks,
      },
      carry: ["source", "workdir", "probe_summary"],
      source,
      workdir,
      probe_summary: summary,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
