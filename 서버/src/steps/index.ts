/**
 * steps/index.ts — 단계 처리기 등록표.
 * 새 단계를 구현하면 여기 한 줄만 바꾼다 (stub → 실제 처리기).
 */
import { STEP_ORDER, type Step } from "../schema.js";
import { setup } from "./setup.js";
import { start } from "./start.js";
import { probe } from "./probe.js";
import { stub } from "./_stub.js";
import type { StepHandler } from "./types.js";

const IMPLEMENTED: Partial<Record<Step, StepHandler>> = {
  setup,
  start,
  probe,
};

export const HANDLERS: Record<Step, StepHandler> = Object.fromEntries(
  STEP_ORDER.map((s) => [s, IMPLEMENTED[s] ?? stub(s)]),
) as Record<Step, StepHandler>;
