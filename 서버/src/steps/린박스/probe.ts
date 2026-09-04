/**
 * steps/린박스/probe.ts — lb_probe: 소재 확인(코덱·길이·프레임률·레터박스·start_time) + 구간이 소재 안인지.
 *
 * 볼케이노 키트 대응: 영상읽기.py · 소재재기.py · 레터박스재기.py · 한편.py 준비의 «소재 크기 → WIN» · «프레임률» 파일(규격 §82).
 * 하는 일:
 *   1) start 가 재 온 payload.probe(ffprobe JSON)·payload.cropdetect_raw(ffmpeg stderr)를 읽는다 (jobs 없음)
 *   2) 영상·오디오 트랙 없음 / 길이 못 읽음 / 구간이 소재 밖 → 반려 + 수리 지침
 *   3) write_files 로 편 폴더에 «프레임률» 파일을 쓴다 — 소재 프레임률 분수 그대로(절대 지침 §82)
 *   4) metrics 와 probe_summary(레터박스·WIN 포함)를 carry 에 담고 next_step=lb_cut
 * 유료 없음.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, join, parseFps, r3, readCarry, spec } from "./lib.js";

interface FfStream {
  codec_type?: string;
  codec_name?: string;
  width?: number;
  height?: number;
  r_frame_rate?: string;
  avg_frame_rate?: string;
  duration?: string;
  start_time?: string;
  channels?: number;
  sample_rate?: string;
  tags?: { language?: string };
}
interface FfProbe {
  streams?: FfStream[];
  format?: { duration?: string; size?: string; start_time?: string };
}
function isProbe(x: unknown): x is FfProbe {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

/** ffmpeg cropdetect 로그의 마지막 crop=W:H:X:Y */
export function parseCrop(raw: unknown): { w: number; h: number; x: number; y: number } | null {
  if (typeof raw !== "string") return null;
  const all = [...raw.matchAll(/crop=(\d+):(\d+):(\d+):(\d+)/g)];
  if (!all.length) return null;
  const m = all[all.length - 1];
  return { w: Number(m[1]), h: Number(m[2]), x: Number(m[3]), y: Number(m[4]) };
}

const VB = (spec as { layout: { video_box: { w: number; h: number } } }).layout.video_box;

export const lbProbe: StepHandler = {
  name: "lb_probe",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_probe", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "start 응답의 carry 값을 payload 에 그대로 실어 lb_probe 를 다시 부르라.");
    }
    const raw = payload.probe;
    if (!isProbe(raw) || !Array.isArray(raw.streams) || !raw.format) {
      return reject("lb_probe", preset, "payload.probe 가 없거나 ffprobe JSON 모양이 아니다 (streams·format 필요)", "start 가 지시한 ffprobe 를 다시 실행해 그 JSON 전체를 payload.probe 에 실어 lb_probe 를 다시 부르라.");
    }
    const video = raw.streams.find((s) => s.codec_type === "video");
    const audios = raw.streams.filter((s) => s.codec_type === "audio");
    const durationS = Number(raw.format.duration ?? video?.duration ?? NaN);
    if (!video) {
      return reject("lb_probe", preset, "영상 트랙이 없다", "source.path 가 드라마 영상 파일인지 확인하라. 소리만 있는 파일이면 영상 원본으로 바꿔 start 부터 다시 부르라.");
    }
    if (!Number.isFinite(durationS) || durationS <= 0) {
      return reject("lb_probe", preset, "길이(format.duration)를 읽을 수 없다", "파일이 깨졌거나 아직 쓰는 중일 수 있다. `ffprobe -v error -show_format <파일>` 로 duration 이 나오는지 확인하고 start 부터 다시 부르라.");
    }
    if (audios.length === 0) {
      return reject("lb_probe", preset, "hard_fail: 오디오 트랙이 없다 — 전사(lb_transcript)와 원음 대사를 쓸 수 없다", "원본에 소리가 있는지 확인하라. 오디오가 별도 파일이면 `ffmpeg -i <영상> -i <오디오> -c copy -map 0:v -map 1:a <새파일.mp4>` 로 합친 뒤 start 부터 다시. 무성 영상이면 린박스로는 만들 수 없다.");
    }
    if (carry.end_s > durationS + 0.5) {
      return reject("lb_probe", preset, `구간 끝 ${carry.end_s}초가 소재 길이 ${r3(durationS)}초를 넘는다`, "payload.end_s 를 소재 길이 안으로 줄여 start 부터 다시 부르라 (구간오프셋을 잘못 셌을 수 있다 — 편정보.json «구간오프셋» 은 소재 파일 기준 초다).");
    }

    const fpsFraction = video.avg_frame_rate && video.avg_frame_rate !== "0/0" ? video.avg_frame_rate : video.r_frame_rate ?? null;
    const fps = parseFps(fpsFraction ?? undefined);
    const width = video.width ?? null;
    const height = video.height ?? null;
    const startTime = Number(video.start_time ?? raw.format.start_time ?? 0) || 0;
    const a0 = audios[0];

    // 레터박스 — cropdetect 마지막 줄. 없으면 «못 쟀다» 로 두고 경고(막지 않는다 — lb_cut 이 다시 잰다)
    const crop = parseCrop(payload.cropdetect_raw);
    const letterbox = crop && height
      ? { top: crop.y, bottom: Math.max(0, height - (crop.y + crop.h)), left: crop.x, right: width ? Math.max(0, width - (crop.x + crop.w)) : null, content_h: crop.h, content_w: crop.w }
      : null;
    // 재프레이밍 창 폭 — 규격 layout.reframe.win_formula: round(소재높이 × 1080/1020). 레터박스를 걷어낸 높이로 센다
    const contentH = letterbox ? letterbox.content_h : height;
    const win = contentH ? Math.round((contentH * VB.w) / VB.h) : null;

    const warnings: string[] = [];
    if (!fpsFraction || fps === null) warnings.push("프레임률을 읽지 못했다 — «프레임률» 파일을 못 쓴다. 규격 §82(소재와 같은 프레임률) 를 lb_cut 전에 사람이 확인하라.");
    if (!letterbox) warnings.push("cropdetect 결과가 없어 레터박스를 못 쟀다 — lb_cut 이 구간.mp4 로 다시 잰다.");
    if (startTime > 0.1) warnings.push(`소재 스트림 start_time 이 ${r3(startTime)}초다 — 절단 뒤 옛 컷 표를 쓰면 그만큼 어긋난다(규격.md §78). lb_cut 이 새로 잰다.`);
    if (audios.length > 1) warnings.push(`오디오 트랙이 ${audios.length}개다. 첫 트랙(${a0.tags?.language ?? "언어 미상"})을 쓴다.`);

    const spanS = r3(carry.end_s - carry.start_s);
    const summary = {
      duration_s: r3(durationS),
      width, height,
      fps, fps_fraction: fpsFraction,
      start_time_s: r3(startTime),
      video_codec: video.codec_name ?? null,
      audio_codec: a0.codec_name ?? null,
      audio_channels: a0.channels ?? null,
      audio_sample_rate: a0.sample_rate ? Number(a0.sample_rate) : null,
      letterbox,
      win,
      span_s: spanS,
    };

    const fpsFile = join(carry.ep_dir, "프레임률");
    return base("lb_probe", preset, {
      status: "execute",
      next_step: "lb_cut",
      message: `소재 확인 통과: ${summary.duration_s}s · ${width}x${height} · ${fpsFraction ?? "?"}(${fps ?? "?"}fps) · 레터박스 ${letterbox ? `위 ${letterbox.top} 아래 ${letterbox.bottom}` : "미측정"} · 창 폭 WIN ${win ?? "?"} · 구간 ${spanS}초. 프레임률 파일을 쓰고 lb_cut 으로.`,
      instructions: [
        "① write_files 대로 편 폴더에 «프레임률» 파일을 쓴다 — 소재 프레임률 분수 그대로(규격 §82 절대 지침: 완성본·블록·prproj 가 소재와 같은 프레임률).",
        "② metrics 는 이 단계가 잰 숫자다. 사람에게 한 줄로 보여준다.",
        "③ carry 의 값(source·workdir·ep·ep_dir·start_s·end_s·probe_summary)을 payload 에 그대로 실어 lb_cut 을 부른다.",
      ],
      then_call_with: ["step: 'lb_cut'", "payload: { source, workdir, ep, ep_dir, start_s, end_s, probe_summary }"],
      jobs_kind: null,
      jobs: [],
      ...(fpsFraction ? { write_files: [{ path: fpsFile, content: fpsFraction, note: "소재 프레임률 분수. 볼케이노 키트 한편.py 굽기가 쓰던 파일 — drv2 프레임률 훅·make_xml set_fps 가 읽는다." }] } : {}),
      measure: [],
      metrics: {
        duration_s: summary.duration_s, width, height, fps, fps_fraction: fpsFraction,
        start_time_s: summary.start_time_s,
        letterbox_top: letterbox?.top ?? null, letterbox_bottom: letterbox?.bottom ?? null,
        win, span_s: spanS, audio_tracks: audios.length,
      },
      carry: [...CARRY_KEYS, "probe_summary"],
      source,
      workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      probe_summary: summary,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
