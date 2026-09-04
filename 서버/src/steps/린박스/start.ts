/**
 * steps/린박스/start.ts — 소재(드라마 로컬 영상)·드라마 폴더·편 이름·구간을 접수하고 lb_probe 재기를 지시한다.
 *
 * 볼케이노 키트의 `한편.py 준비 <편폴더> --소재 <드라마.mp4> --시작 s --끝 e` 첫 줄에 해당한다.
 * 하는 일:
 *   1) source(local_video) · payload.workdir(드라마 폴더 루트) · payload.ep("EP01") · payload.start_s/end_s(구간 초) 검사
 *   2) jobs_kind:"argv" 로 두 명령을 내려보낸다 — ffprobe(JSON) · 구간 한가운데 cropdetect(레터박스 실측, stderr)
 *      (runner 는 argv 를 한 글자도 고치지 않는다 — 판단은 lb_probe 가 한다)
 *   3) measure 로 결과를 payload.probe · payload.cropdetect_raw 에 실어 lb_probe 로 오게 한다
 * 유료 없음.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, epDir, isEpName, join, num, str } from "./lib.js";

export const lbStart: StepHandler = {
  name: "start",
  run({ preset, source, payload }) {
    if (!source || source.kind !== "local_video") {
      return reject(
        "start", preset,
        "source 가 없거나 로컬 영상이 아니다",
        "source: { kind: 'local_video', path: '<드라마 영상 절대경로>', title: '<작품명>', lang: 'ko' } 를 실어 start 를 다시 부르라. 린박스는 화이트리스트 드라마 파일만 받는다(규격 source.whitelist_only).",
      );
    }
    const workdir = str(payload, "workdir");
    if (!workdir) {
      return reject("start", preset, "payload.workdir 가 없다", "setup 의 ②에서 만든 드라마 폴더 루트(소재/·작업/·완성/ 의 부모) 절대경로를 payload.workdir 에 실어 start 를 다시 부르라.");
    }
    const ep = str(payload, "ep");
    if (!isEpName(ep)) {
      return reject("start", preset, `payload.ep 가 없거나 꼴이 아니다 (${ep || "빈값"})`, "편 이름을 'EP01' 처럼 대문자 EP + 숫자로 payload.ep 에 실어 start 를 다시 부르라 (볼케이노 키트의 작업/EPnn 폴더 이름과 같다).");
    }
    const start_s = num(payload, "start_s");
    const end_s = num(payload, "end_s");
    if (start_s === null || end_s === null || start_s < 0 || end_s <= start_s) {
      return reject("start", preset, "payload.start_s / end_s(구간 초)가 없거나 end 가 start 보다 크지 않다", "소재에서 쓸 대목의 시작·끝 초를 payload.start_s · payload.end_s 에 숫자로 실어 start 를 다시 부르라 (예: 1495, 1635). 대목은 한 통으로(규격 edit.whole_scene) — 결말까지.");
    }
    const spanS = end_s - start_s;
    const ep_dir = epDir(workdir, ep);
    // 저장소 루트 — lb_cut 부터 러너 도구(서버/runner/린박스/도구/)를 절대경로로 부르려면 필요하다. 여기서 받아 두면 carry 로 이어 간다
    const repo = str(payload, "repo");
    const probeOut = join(ep_dir, "_probe.json");
    const mid = Math.round(((start_s + end_s) / 2) * 1000) / 1000;

    return base("start", preset, {
      status: "execute",
      next_step: "lb_probe",
      message: `소재 접수: ${source.path} · ${ep} · 구간 ${start_s}~${end_s}초(${Math.round(spanS)}초). 편 폴더를 만들고 아래 두 명령을 그대로 실행한 뒤 lb_probe 를 부르라.`,
      instructions: [
        `① 편 폴더 ${ep_dir} 를 만든다 (드라마 폴더 아래 작업/${ep}). 이미 있으면 그대로 둔다 — 안의 파일을 지우지 않는다.`,
        "② jobs 의 두 명령을 그대로 실행한다. probe 는 표준출력(JSON)을 out 에 저장하고, cropdetect 는 표준오류(ffmpeg 로그)를 통째로 payload.cropdetect_raw 에 넣는다 (measure 대로).",
        "③ carry 의 값(source·workdir·ep·ep_dir·start_s·end_s·repo)을 payload 에 그대로 실어 lb_probe 를 부른다." + (repo ? "" : " ★payload.repo(youstudio-mcp 저장소 루트 절대경로)를 아직 안 실었다 — lb_cut 부터 러너 도구를 거기서 찾으므로 다음 호출부터 실어라."),
      ],
      then_call_with: [
        "step: 'lb_probe'",
        "payload: { source, workdir, ep, ep_dir, start_s, end_s, probe: <ffprobe JSON>, cropdetect_raw: <ffmpeg stderr 전문> }",
      ],
      jobs_kind: "argv",
      jobs: [
        {
          name: "probe",
          argv: ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", source.path],
          out: probeOut,
          note: "길이·fps(분수)·해상도·코덱·오디오·start_time. lb_probe 의 입력이다.",
        },
        {
          name: "cropdetect",
          argv: [
            "ffmpeg", "-hide_banner", "-nostats", "-ss", String(mid), "-t", "3", "-i", source.path,
            "-vf", "cropdetect=24:16:0", "-an", "-f", "null", "-",
          ],
          note: `구간 한가운데(${mid}초) 3초로 레터박스를 잰다 — 마지막 'crop=W:H:X:Y' 줄이 답이다(규격 source.letterbox_crop · 규격.md §2). 결과는 stderr 로만 나온다.`,
        },
      ],
      measure: [
        { as: "probe", from: "job:probe", unit: "json_stdout" },
        { as: "cropdetect_raw", from: "job:cropdetect", unit: "stderr" },
      ],
      carry: [...CARRY_KEYS, ...(repo ? ["repo"] : [])],
      source,
      workdir,
      ep,
      ep_dir,
      start_s,
      end_s,
      ...(repo ? { repo } : {}),
    });
  },
};
