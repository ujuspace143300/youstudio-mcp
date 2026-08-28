/**
 * styles.ts — 프리셋(스타일) 등록표. 프리셋 하나 = `스타일/<이름>/` 폴더 하나.
 *
 * Workers 는 파일시스템이 없어 정적 import 로 번들한다. 새 프리셋을 추가하려면:
 *   1) `스타일/<이름>/` 에 규격.json · 정답지.json · 지침 md 를 둔다 (영화롱폼을 본뜬다)
 *   2) 아래 STYLES 에 항목 하나 추가한다 — spec·answer·guideMd·from 에 더해
 *      steps(단계 순서 = 상태 기계)·workDirs(작업 폴더 하위 이름)를 적는다
 *   3) `서버/src/steps/` 에 그 프리셋의 단계 처리기를 만들고 steps/index.ts 의
 *      PIPELINES 에 등록한다 (다른 프리셋과 단계가 겹치면 처리기를 공유해도 된다)
 *   4) `npm run typecheck && npm test` 통과 → `npx wrangler deploy`
 * 단계 이름 목록(STEP_ORDER)·프리셋 목록(PRESETS)은 여기서 파생된다 — schema.ts 는 손대지 않는다.
 *
 * ※ 파이프라인 등록표 전환 (2026-08-28, 프리셋 2호 스케치코미디 선행 작업):
 *    프리셋마다 steps 가 다르다 — next_step 과 단계 유효성은 그 프리셋의 steps 로 판정한다.
 *    영화롱폼 단계 처리기(brief~export)가 영화롱폼 상수를 모듈 수준에서 import 하는 것은
 *    그대로 둔다 — 그 처리기들은 영화롱폼 파이프라인에서만 불리므로 다른 프리셋과 섞이지
 *    않는다. 다른 프리셋이 그 단계를 「공유」하려는 순간에 상수 → styleOf(preset) 전환을 한다.
 */
import 영화롱폼_규격 from "../../스타일/영화롱폼/규격.json";
import 영화롱폼_정답지 from "../../스타일/영화롱폼/정답지.json";
import 영화롱폼_나레이션 from "../../스타일/영화롱폼/나레이션.md";

export interface Style {
  /** 우리가 정한 설정값 (스타일/<이름>/규격.json) */
  spec: Record<string, unknown>;
  /** 게이트 합격 대역 (정답지.json) */
  answer: Record<string, unknown>;
  /** 집필 지침 전문 (나레이션.md 등) */
  guideMd: string;
  /** 응답 spec._from 에 찍는 출처 */
  from: string;
  /** 이 프리셋의 단계 순서 — 곧 상태 기계. next_step 은 이 배열의 "다음 칸"이다 */
  steps: readonly string[];
  /** setup 이 만들라고 안내하는 작업 폴더 하위 이름 (단계 이름 그대로) */
  workDirs: readonly string[];
}

export const STYLES = {
  영화롱폼: {
    spec: 영화롱폼_규격 as Record<string, unknown>,
    answer: 영화롱폼_정답지 as Record<string, unknown>,
    guideMd: 영화롱폼_나레이션,
    from: "스타일/영화롱폼/규격.json (서버 번들에 포함 — 배포본에도 실려 간다)",
    steps: ["setup", "start", "probe", "transcript", "brief", "select", "script", "voice", "subtitle", "export"],
    workDirs: ["probe", "transcript", "brief", "clips", "script", "voice", "subtitle", "render"],
  },
} as const satisfies Record<string, Style>;

export const PRESETS = Object.keys(STYLES) as [keyof typeof STYLES, ...(keyof typeof STYLES)[]];
export type Preset = keyof typeof STYLES;
export const DEFAULT_PRESET: Preset = "영화롱폼";

/** 모든 프리셋의 단계 이름 (등장 순서 유지·중복 제거) — schema 의 enum 이 여기서 나온다 */
export type StyleStep = (typeof STYLES)[Preset]["steps"][number];
export const ALL_STEPS = [...new Set(Object.values(STYLES).flatMap((s) => s.steps))] as [
  StyleStep,
  ...StyleStep[],
];

export function styleOf(preset: Preset): Style {
  return STYLES[preset];
}
