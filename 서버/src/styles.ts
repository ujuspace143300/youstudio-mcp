/**
 * styles.ts — 프리셋(스타일) 등록표. 프리셋 하나 = `스타일/<이름>/` 폴더 하나.
 *
 * Workers 는 파일시스템이 없어 정적 import 로 번들한다. 새 프리셋을 추가하려면:
 *   1) `스타일/<이름>/` 에 규격.json · 정답지.json · 나레이션.md 를 둔다 (영화롱폼을 본뜬다)
 *   2) 아래 STYLES 에 한 줄 추가한다
 *   3) `npm run typecheck && npm test` 통과 → `npx wrangler deploy`
 * 이름 목록(PRESETS)은 여기서 파생되므로 schema.ts 는 손대지 않는다.
 *
 * ※ 2026-08-26 현재 setup 만 프리셋별로 규격을 고른다. 나머지 단계는 아직 영화롱폼 상수를
 *    모듈 수준에서 굳혀 쓴다 — 두 번째 프리셋이 실제로 생길 때 그 사례로 단계별 전환을 한다.
 */
import 영화롱폼_규격 from "../../스타일/영화롱폼/규격.json";
import 영화롱폼_정답지 from "../../스타일/영화롱폼/정답지.json";
import 영화롱폼_나레이션 from "../../스타일/영화롱폼/나레이션.md";

export interface Style {
  /** 우리가 정한 설정값 (스타일/<이름>/규격.json) */
  spec: Record<string, unknown>;
  /** 게이트 합격 대역 (정답지.json) */
  answer: Record<string, unknown>;
  /** 집필 지침 전문 (나레이션.md) */
  guideMd: string;
  /** 응답 spec._from 에 찍는 출처 */
  from: string;
}

export const STYLES = {
  영화롱폼: {
    spec: 영화롱폼_규격 as Record<string, unknown>,
    answer: 영화롱폼_정답지 as Record<string, unknown>,
    guideMd: 영화롱폼_나레이션,
    from: "스타일/영화롱폼/규격.json (서버 번들에 포함 — 배포본에도 실려 간다)",
  },
} as const satisfies Record<string, Style>;

export const PRESETS = Object.keys(STYLES) as [keyof typeof STYLES, ...(keyof typeof STYLES)[]];
export type Preset = keyof typeof STYLES;
export const DEFAULT_PRESET: Preset = "영화롱폼";

export function styleOf(preset: Preset): Style {
  return STYLES[preset];
}
