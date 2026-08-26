/**
 * steps/setup.ts — 준비 확인.
 *
 * 하는 일:
 *   1) ffmpeg / ffprobe 가 깔려 있는지 확인하라고 지시한다 (jobs_kind: "argv")
 *   2) 작업 폴더 구조를 알려주고 만들라고 지시한다 (번호 대신 단계 이름 — 확장 계획 3번)
 *   3) 스타일/영화롱폼/규격.json 을 응답에 실어 "규격은 서버가 내려준다"를 증명한다
 */
import { styleOf } from "../styles.js";
import { base } from "../response.js";
import type { StepHandler } from "./types.js";

/** 작업 폴더 하위 이름 — 단계 이름 그대로. 스타일마다 달라도 어긋나지 않는다 */
export const WORK_DIRS = ["probe", "transcript", "brief", "clips", "script", "voice", "subtitle", "render"] as const;

export const setup: StepHandler = {
  name: "setup",
  run({ preset }) {
    const { spec, from } = styleOf(preset);
    return base("setup", preset, {
      status: "execute",
      next_step: "start",
      message: "준비 확인. 아래 명령을 그대로 실행하고, 작업 폴더를 만든 뒤 start 를 부르라.",
      instructions: [
        "① jobs 의 두 명령을 그대로 실행한다. 둘 중 하나라도 실패하면 여기서 멈추고 ffmpeg 를 설치한다 (윈도우: winget install Gyan.FFmpeg · macOS: brew install ffmpeg).",
        "② 작업 폴더 루트를 하나 정한다 (예: 바탕화면/youstudio_work/<영화슬러그>). 그 아래에 workdir_layout.dirs 의 하위 폴더를 전부 만든다.",
        "③ spec 은 이 스타일의 설정값이다. 여기 실려 온 그대로 쓰고, 클라이언트 쪽에서 값을 지어내지 않는다.",
        "④ 끝나면 start 를 부른다 — source 에 영화 파일 경로, payload.workdir 에 ②의 루트 절대경로.",
      ],
      then_call_with: [
        "step: 'start'",
        "source: { kind: 'local_video', path: '<영화 파일 절대경로>', title: '<제목 (연도)>', lang: '<원어>' }",
        "payload: { workdir: '<작업 폴더 루트 절대경로>', tools: <measure 결과> }",
      ],
      jobs_kind: "argv",
      jobs: [
        { name: "check_ffmpeg", argv: ["ffmpeg", "-version"], note: "설치 확인. 첫 줄에 버전이 찍힌다" },
        { name: "check_ffprobe", argv: ["ffprobe", "-version"], note: "설치 확인. 첫 줄에 버전이 찍힌다" },
      ],
      measure: [
        { as: "tools.ffmpeg", from: "job:check_ffmpeg", unit: "stdout_first_line" },
        { as: "tools.ffprobe", from: "job:check_ffprobe", unit: "stdout_first_line" },
      ],
      carry: [],
      workdir_layout: {
        note: "루트는 클라이언트가 정한다. 하위 폴더 이름은 단계 이름이다.",
        dirs: [...WORK_DIRS],
      },
      spec: {
        _from: from,
        ...spec,
      },
    });
  },
};
