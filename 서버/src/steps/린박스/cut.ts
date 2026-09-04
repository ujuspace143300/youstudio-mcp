/**
 * steps/린박스/cut.ts — lb_cut: 구간 절단 + 손대지 않은 사본 + 절단본 재기 + 장면전환 표.
 *
 * 볼케이노 키트 대응: 한편.py 준비 ②(구간 자르기·구간_원본 사본) · 장면컷.py(scene_cuts.txt).
 * 규칙:
 *   · 절단은 `-i` 뒤 `-ss/-to` + 재인코딩, `-c copy` 금지 (볼트 카드 프리셋/린박스.md 2절 · 규격 source.segment_cut)
 *   · 손대지 않은 원본 구간을 `구간_원본.mp4` 로 남긴다 (규격.md §84) — 스트림 복사라 바이트가 같다
 *   · 절단본의 start_time 이 0.1초 넘으면 옛 컷 표를 못 쓴다 (§78) — 새로 잰 표만 쓴다 (lb_transcript 가 검사)
 *   · 컷 표는 ffmpeg select 로 만들지 않는다 (§71) — 장면컷.py 가 세 가지(화소차·히스토그램·이웃 대비)로 잰다
 * jobs 는 편 폴더를 cwd 로 실행한다(jobs_cwd) — 장면컷.py 가 scene_cuts.txt 를 cwd 에 쓴다.
 * 유료 없음.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, readCarry, str } from "./lib.js";

export const lbCut: StepHandler = {
  name: "lb_cut",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_cut", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_probe 응답의 carry 값을 payload 에 그대로 실어 lb_cut 을 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) {
      return reject("lb_cut", preset, "payload.repo(저장소 루트 절대경로)가 없다", "youstudio-mcp 저장소 루트의 절대경로(예: /Users/<나>/Desktop/youstudio-mcp)를 payload.repo 에 실어 lb_cut 을 다시 부르라 — 러너 도구(서버/runner/린박스/도구/)를 그 밑에서 찾는다.");
    }
    const ps = payload.probe_summary as { fps_fraction?: string | null } | undefined;
    const cut = join(carry.ep_dir, "구간.mp4");
    const keep = join(carry.ep_dir, "구간_원본.mp4");
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const spanS = Math.round((carry.end_s - carry.start_s) * 1000) / 1000;

    return base("lb_cut", preset, {
      status: "execute",
      next_step: "lb_transcript",
      message: `구간 ${carry.start_s}~${carry.end_s}초(${spanS}초)를 잘라 ${cut} 으로 굽고, 원본 사본·절단본 재기·장면전환 표까지 네 명령을 편 폴더에서 차례로 실행하라.`,
      instructions: [
        `① jobs 는 편 폴더 ${carry.ep_dir} 를 현재 폴더(cwd)로 두고 순서대로 실행한다 (jobs_cwd). 한 글자도 고치지 않는다.`,
        "② cut: `-i` 뒤에 `-ss/-to` 를 두고 재인코딩한다 — `-c copy` 로 자르면 키프레임 때문에 소리와 그림이 어긋난다(볼트 카드 «구간 절단»). 소재 프레임률은 그대로 간다(`-r` 없음 · 규격 §82).",
        "③ keep: 구간.mp4 를 스트림 복사로 `구간_원본.mp4` 에 남긴다 — 손대지 않은 원본 구간(§84). 프리미어 V1 이 이걸 문다.",
        "④ cut_probe · scene_cuts: measure 대로 payload.cut_probe(ffprobe JSON) · payload.scene_cuts_log(장면컷.py 표준출력 전문)에 넣는다. 장면컷.py 가 편 폴더에 scene_cuts.txt 를 쓴다(있으면 scene_cuts.bak 으로 물려 둔다).",
        "⑤ carry 의 값(source·workdir·ep·ep_dir·start_s·end_s·repo·probe_summary)을 payload 에 그대로 실어 lb_transcript 를 부른다 — ★유료(Speechmatics) 단계라 그 응답이 먼저 비용을 묻는다.",
      ],
      then_call_with: [
        "step: 'lb_transcript'",
        "payload: { source, workdir, ep, ep_dir, start_s, end_s, repo, probe_summary, cut_probe: <ffprobe JSON>, scene_cuts_log: <stdout> }",
      ],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        {
          name: "cut",
          argv: [
            "ffmpeg", "-y", "-v", "error", "-i", source.path,
            "-ss", String(carry.start_s), "-to", String(carry.end_s),
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2",
            cut,
          ],
          note: `구간 절단 — -i 뒤 -ss/-to + 재인코딩(crf 16 · aac 320k). 소재 ${ps?.fps_fraction ?? "?"} 프레임률 그대로.`,
        },
        {
          name: "keep",
          argv: ["ffmpeg", "-y", "-v", "error", "-i", cut, "-c", "copy", keep],
          note: "손대지 않은 원본 구간 사본(§84) — 스트림 복사라 구간.mp4 와 같은 그림·소리.",
        },
        {
          name: "cut_probe",
          argv: ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", cut],
          out: join(carry.ep_dir, "_cut_probe.json"),
          note: "절단본의 길이·start_time·fps. lb_transcript 가 «구간 길이 ≈ 요청 길이 · start_time ≤ 0.1» 을 검사한다(§78).",
        },
        {
          name: "scene_cuts",
          argv: ["python", tool("장면컷.py"), cut, "--쓰기"],
          out: join(carry.ep_dir, "_scene_cuts_log.txt"),
          note: "장면전환 표 scene_cuts.txt (화소차+히스토그램+이웃 대비 · §71 ffmpeg select 금지). 표준출력에 「찾은 장면전환 N개 (x개/분)」 가 찍힌다.",
        },
      ],
      measure: [
        { as: "cut_probe", from: "job:cut_probe", unit: "json_stdout" },
        { as: "scene_cuts_log", from: "job:scene_cuts", unit: "stdout" },
      ],
      carry: [...CARRY_KEYS, "repo", "probe_summary"],
      source,
      workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo,
      probe_summary: payload.probe_summary,
      cut_path: cut,
      keep_path: keep,
    });
  },
};
