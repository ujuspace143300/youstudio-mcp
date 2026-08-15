/**
 * steps/_stub.ts — 아직 안 만든 단계의 자리표.
 * 단계 이름만 받아 "아직 구현 안 됨" 응답을 돌려주는 처리기를 만든다.
 * 실제로 만들 때는 이 파일을 고치지 말고 steps/<이름>.ts 를 새로 만들어 index.ts 에 등록한다.
 */
import { notImplemented } from "../response.js";
import type { Step } from "../schema.js";
import type { StepHandler } from "./types.js";

export function stub(name: Step): StepHandler {
  return { name, run: ({ preset }) => notImplemented(name, preset) };
}
