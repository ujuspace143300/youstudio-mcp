/**
 * steps/스케치코미디/plan.ts — sk_plan: 원본 다운로드(yt-dlp) + 5-Phase 계획.
 *
 * 러너 s2pipe.plan 이 원본을 받고, 모델(EvoLink 우선·무료 한도)이 조각·나레이션·
 * 제목 후보 5개·후킹 대사 3개·댓글 선택까지 만들어 projects/<슬러그>.json 으로 저장한다.
 * ★한 소재에서 두 편 — B 편은 start 부터 slug=<id>_B · focus_sec 으로 다시 온다.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { configPath, RUNNER_NOTE, str } from "./lib.js";

export const skPlan: StepHandler = {
  name: "sk_plan",
  run({ preset, payload }) {
    const workdir = str(payload, "workdir");
    const source = payload.source as { url?: string; slug?: string; focus_sec?: number } | undefined;
    if (!workdir || !source?.url) {
      return reject(
        "sk_plan",
        preset,
        "payload 에 carry 값(source.url·workdir)이 없다",
        "start 응답의 source 와 workdir 를 payload 에 그대로 실어 sk_plan 을 다시 부르라.",
      );
    }
    const argv = ["python", "-m", "s2pipe.plan", source.url, "--config", configPath(workdir)];
    if (source.slug) argv.push("--slug", source.slug);
    if (typeof source.focus_sec === "number") argv.push("--focus", String(source.focus_sec));

    return base("sk_plan", preset, {
      status: "execute",
      next_step: "sk_check",
      message: "계획을 만들라 — 다운로드는 공짜, 모델 판정은 EvoLink 무료 한도다. 결과 편.json 은 사람이 검토한다.",
      instructions: [
        `① ${RUNNER_NOTE}`,
        "② jobs 의 plan 을 그대로 실행한다. yt-dlp 다운로드(공짜) + 모델 판정(EvoLink 무료 한도, 18MB 초과 미디어만 순정 Gemini). ★yt-dlp 가 낡으면 미디어만 403 이 난다 — 메타데이터는 멀쩡해서 헷갈린다. 그러면 yt-dlp --update-to nightly.",
        "③ 출력 끝에 저장된 projects/<슬러그>.json 경로가 찍힌다. 그 파일을 **한 글자도 고치지 말고** JSON 그대로 payload.project 에 싣고, 경로를 payload.project_path 에 넣어 sk_check 를 부른다.",
        "④ 편.json 은 사람이 훑는다 — 특히 조각의 what(무슨 대목인지)이 실제 영상과 맞는지. 판정은 sk_check(서버)가 한다.",
      ],
      then_call_with: ["step: 'sk_check'", "payload: { workdir, source, project_path, project: <편.json 전체> }"],
      jobs_kind: "argv",
      jobs: [
        {
          name: "plan",
          argv,
          note: "원본 받기 + 5-Phase 계획. ★모델은 Phase 라벨만 얹고 시간순으로 두려 한다 — (phase,t0) 정렬은 plan 코드가 보장한다.",
        },
      ],
      measure: [],
      carry: ["source", "workdir"],
      source,
      workdir,
    });
  },
};
