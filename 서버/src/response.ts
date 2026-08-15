/**
 * response.ts — 응답을 만드는 작은 도우미.
 *
 * 모든 단계가 같은 칸을 가진 JSON 을 돌려주게 한다 (빠뜨리는 칸이 없도록).
 */
import { STEP_ORDER, type Preset, type Step, type StepResponse } from "./schema.js";

/** 이 단계의 다음 단계 이름. 마지막이면 null */
export function nextOf(step: Step): Step | null {
  const i = STEP_ORDER.indexOf(step);
  return i >= 0 && i + 1 < STEP_ORDER.length ? STEP_ORDER[i + 1] : null;
}

/** 빈 껍데기 응답. 필요한 칸만 덮어써서 쓴다 */
export function base(step: Step, preset: Preset, over: Partial<StepResponse> = {}): StepResponse {
  return {
    status: "execute",
    step,
    preset,
    next_step: nextOf(step),
    then_call_with: [],
    instructions: [],
    need_input: null,
    jobs: [],
    jobs_kind: null,
    measure: [],
    metrics: {},
    carry: [],
    ...over,
  };
}

/** 아직 안 만든 단계가 돌려주는 응답 */
export function notImplemented(step: Step, preset: Preset): StepResponse {
  return base(step, preset, {
    status: "not_implemented",
    next_step: null,
    message: `'${step}' 단계는 아직 구현 안 됨. 설계/단계상세.md 참조.`,
    instructions: ["여기서 멈춘다. 이 단계의 지시는 설계/단계상세.md 의 명세대로 만든다."],
  });
}

/** 입력이 잘못됐을 때 — 메시지에 고치는 법을 담는다 (HARNESS 5장) */
export function reject(step: Step, preset: Preset, why: string, fix: string): StepResponse {
  return base(step, preset, {
    status: "error",
    next_step: step,
    message: `${why} — ${fix}`,
    instructions: [fix],
  });
}
