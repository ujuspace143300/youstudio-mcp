/**
 * steps/types.ts — 단계 처리기 하나의 모양.
 * "기능 하나 = 처리기 하나": 단계마다 파일 하나가 이 모양을 export 한다.
 */
import type { Preset, Source, Step, StepResponse } from "../schema.js";

export interface StepContext {
  step: Step;
  preset: Preset;
  source?: Source;
  payload: Record<string, unknown>;
}

export interface StepHandler {
  name: Step;
  run(ctx: StepContext): StepResponse | Promise<StepResponse>;
}
