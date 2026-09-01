/**
 * steps/스케치코미디/lib.ts — 스케치코미디 파이프라인 공용: 규격 3파일·편.json 타입·경로·argv 단계 공장.
 *
 * 러너는 저장소 `서버/runner/스케치코미디/` 의 파이썬이고, jobs 는 그 폴더에서 실행한다.
 * config.json 은 규격조립.py 가 작업 폴더에 생성한다(정본은 스타일 3파일).
 */
import spec from "../../../../스타일/스케치코미디/규격.json";
import answer from "../../../../스타일/스케치코미디/정답지.json";
import ours from "../../../../스타일/스케치코미디/우리실측.json";
import { base } from "../../response.js";
import type { Step, StepResponse } from "../../schema.js";
import type { StepContext, StepHandler } from "../types.js";

export { spec, answer, ours };

export const PRESET = "스케치코미디" as const;
/** jobs 실행 위치 — 지시문에 반드시 적는다 (python -m s2pipe.* 가 여기서만 돈다) */
export const RUNNER_DIR = "서버/runner/스케치코미디";
export const RUNNER_NOTE =
  `이 단계의 jobs 는 저장소의 ${RUNNER_DIR} 폴더에서 실행한다 (파이썬은 러너 venv — 맥 ~/.volcano/venv/bin/python · 윈도우 ~/.volcano/venv/Scripts/python.exe, 없으면 python).`;

/** 경로 이어붙이기 — 클라이언트 OS 를 모르므로 '/' 로 잇는다 */
export function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}

export function configPath(workdir: string): string {
  return join(workdir, "config.json");
}

// ── 편.json (plan 이 만드는 프로젝트 파일) ────────────────────────────────
export interface Segment {
  t0: number;
  t1: number;
  what?: string;
  punch?: number;
  phase?: number;
  keep?: boolean;
  narration?: string;
}
export interface Sub {
  t: number;
  text?: string;
  kind?: string;
}
export interface Project {
  slug?: string;
  source?: { url?: string; id?: string; dur?: number; fps?: number };
  title?: string | string[];
  title_candidates?: (string | string[])[];
  hashtag?: string;
  hooks?: unknown[];
  segments?: Segment[];
  subs?: Sub[];
  comments?: unknown[];
  credit?: { channel?: string; title?: string };
  /** 절대 지침(정답지 G-결말) — 이 편이 무엇으로 끝나는지. type: 반전|결론 */
  ending?: { type?: string; desc?: string };
}

export function isProject(x: unknown): x is Project {
  return typeof x === "object" && x !== null && !Array.isArray(x) && "segments" in (x as object);
}

/** payload 에서 문자열 칸을 안전하게 꺼낸다 */
export function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === "string" ? v.trim() : "";
}

/**
 * argv 한 벌짜리 단계 공장 — sk_cut·sk_subs·sk_asr·sk_sync·sk_render 처럼
 * 「러너 명령 하나 실행 → 다음 단계」 모양이 같은 단계를 찍어낸다.
 * workdir·project_path 가 없으면 고치는 법과 함께 반려한다.
 */
export function argvStep(opts: {
  name: Step;
  /** argv 조립 — (project_path, config_path, payload) */
  argv(project: string, config: string, payload: Record<string, unknown>): string[];
  jobName: string;
  jobNote: string;
  /** 단계 지시 (RUNNER_NOTE·carry 지시는 공장이 붙인다) */
  instructions(payload: Record<string, unknown>): string[];
  message(payload: Record<string, unknown>): string;
  thenCallWith?: string[];
  over?(payload: Record<string, unknown>): Partial<StepResponse>;
}): StepHandler {
  return {
    name: opts.name,
    run({ preset, payload }: StepContext): StepResponse {
      const workdir = str(payload, "workdir");
      const projectPath = str(payload, "project_path");
      if (!workdir || !projectPath) {
        return base(opts.name, preset, {
          status: "error",
          next_step: opts.name,
          message: "payload 에 workdir·project_path 가 없다 — carry 값을 그대로 실어 다시 부르라.",
          instructions: ["직전 단계 응답의 carry 값(workdir·project_path 등)을 payload 에 그대로 실어 이 단계를 다시 부르라."],
        });
      }
      const extra = opts.over?.(payload) ?? {};
      return base(opts.name, preset, {
        status: "execute",
        message: opts.message(payload),
        instructions: [
          `① ${RUNNER_NOTE}`,
          ...opts.instructions(payload).map((s, i) => `${"②③④⑤⑥"[i] ?? "•"} ${s}`),
        ],
        then_call_with: opts.thenCallWith ?? ["payload: { workdir, project_path, ... (carry 그대로) }"],
        jobs_kind: "argv",
        jobs: [
          {
            name: opts.jobName,
            argv: opts.argv(projectPath, configPath(workdir), payload),
            note: opts.jobNote,
          },
        ],
        measure: [],
        carry: ["workdir", "project_path", "source"],
        workdir,
        project_path: projectPath,
        source: payload.source,
        ...extra,
      });
    },
  };
}
