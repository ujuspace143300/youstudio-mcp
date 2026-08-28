/**
 * steps/스케치코미디/start.ts — 소재(유튜브 URL) 접수 + 작업 폴더에 config 생성 지시.
 *
 * 영화롱폼의 start(로컬 파일 → probe)와 완전히 다르다 — 이 프리셋은 유튜브 롱폼을
 * 받아 sk_plan(다운로드+5-Phase 계획)으로 간다. config.json 은 규격조립.py 가
 * 작업 폴더에 생성한다(정본은 스타일 3파일 — 손으로 만들지 않는다).
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { RUNNER_NOTE, str } from "./lib.js";

export const skStart: StepHandler = {
  name: "start",
  run({ preset, source, payload }) {
    if (!source || source.kind !== "youtube") {
      return reject(
        "start",
        preset,
        "source 가 없거나 유튜브 소재가 아니다",
        "source: { kind: 'youtube', url: '<롱폼 URL>' } 를 실어 start 를 다시 부르라. 한 소재 두 편(A/B)이면 slug: '<id>_A' — B 편은 나중에 slug: '<id>_B', focus_sec: <다른 웃음 대목의 초> 로 처음부터 다시.",
      );
    }
    const workdir = str(payload, "workdir");
    if (!workdir) {
      return reject(
        "start",
        preset,
        "payload.workdir 가 없다",
        "setup 의 ②에서 만든 작업 폴더 루트 절대경로를 payload.workdir 에 실어 start 를 다시 부르라.",
      );
    }

    return base("start", preset, {
      status: "execute",
      next_step: "sk_plan",
      message: `소재 접수: ${source.url}${source.slug ? ` (편: ${source.slug})` : ""}. config 를 생성하고 sk_plan 을 부르라.`,
      instructions: [
        `① ${RUNNER_NOTE}`,
        "② jobs 의 규격조립.py 를 그대로 실행한다 — 작업 폴더에 config.json 이 생성된다(정본은 스타일/스케치코미디/ 3파일. 손으로 만들거나 고치지 않는다).",
        "③ carry 의 값(source·workdir)을 payload 에 그대로 실어 sk_plan 을 부른다.",
      ],
      then_call_with: ["step: 'sk_plan'", "payload: { workdir, source }"],
      jobs_kind: "argv",
      jobs: [
        {
          name: "make_config",
          argv: ["python", "규격조립.py", "--workdir", workdir],
          note: "스타일 3파일 → 러너용 config.json 생성. 「생성:」과 「되읽기 확인:」 두 줄이 찍혀야 성공이다.",
        },
      ],
      measure: [{ as: "config_gen", from: "job:make_config", unit: "stdout_first_line" }],
      carry: ["source", "workdir"],
      source,
      workdir,
    });
  },
};
