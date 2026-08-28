/**
 * steps/start.ts — 소재를 받고 probe 를 지시한다.
 *
 * 하는 일:
 *   1) source(local_video) 와 payload.workdir 를 검사한다 — 없으면 고치는 법과 함께 반려
 *   2) probe 용 ffprobe 명령을 서버가 조립해 jobs_kind:"argv" 로 내려보낸다
 *      (runner 는 이 argv 를 한 글자도 고치지 않는다 — 판단은 서버에 있다)
 *   3) 결과를 payload.probe 로 재서 다음 단계(probe)에 가져오라고 measure 를 건다
 */
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";

/** 경로 이어붙이기 — 클라이언트 OS 를 모르므로 '/' 로 잇는다 (윈도우도 '/' 를 받는다) */
function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}

export const start: StepHandler = {
  name: "start",
  run({ preset, source, payload }) {
    if (!source || source.kind !== "local_video") {
      return reject("start", preset, "source 가 없거나 로컬 영상이 아니다", "source: { kind: 'local_video', path: '<영화 파일 절대경로>' } 를 실어 start 를 다시 부르라. (영화롱폼은 로컬 파일만 받는다 — 유튜브 소재는 스케치코미디 프리셋)");
    }
    const workdir = typeof payload.workdir === "string" ? payload.workdir.trim() : "";
    if (!workdir) {
      return reject("start", preset, "payload.workdir 가 없다", "setup 의 ②에서 만든 작업 폴더 루트 절대경로를 payload.workdir 에 실어 start 를 다시 부르라.");
    }

    const probeOut = join(workdir, "probe", "probe.json");
    return base("start", preset, {
      status: "execute",
      next_step: "probe",
      message: `소재 접수: ${source.path}. 아래 ffprobe 를 그대로 실행하고 결과를 payload.probe 로 실어 probe 를 부르라.`,
      instructions: [
        "① jobs 의 ffprobe 명령을 그대로 실행한다. 표준출력(JSON)을 out 경로에 저장한다.",
        "② measure 대로 그 JSON 을 payload.probe 에 넣는다.",
        "③ carry 의 값(source, workdir)을 payload 에 그대로 실어 next_step 을 부른다.",
      ],
      then_call_with: [
        "step: 'probe'",
        "payload: { workdir, source, probe: <ffprobe JSON> }",
      ],
      jobs_kind: "argv",
      jobs: [
        {
          name: "probe",
          argv: [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            source.path,
          ],
          out: probeOut,
          note: "길이·fps·해상도·코덱·오디오 채널. probe 단계의 입력이다.",
        },
      ],
      measure: [{ as: "probe", from: "job:probe", unit: "json_stdout" }],
      carry: ["source", "workdir"],
      source,
      workdir,
    });
  },
};
