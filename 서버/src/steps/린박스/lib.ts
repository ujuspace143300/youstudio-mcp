/**
 * steps/린박스/lib.ts — 린박스 파이프라인 공용: 규격 3파일·경로·payload 읽기·편 폴더 규약.
 *
 * 프리셋 3호 (설계/프리셋_린박스.md · 5.6.1 「입력 6개의 꼴」). 앞 7단계(lb_probe~lb_blocks)는
 * 볼케이노 서버 산출물을 그대로 «베낀다» — 응답 틀(do/jobs/measure/carry)은 볼케이노 문법이다.
 *
 * 편 폴더 규약(볼케이노 키트 그대로): <workdir>/소재/ · <workdir>/작업/<EP>/ · <workdir>/완성/<EP>/
 *   workdir = 드라마 폴더 루트(setup 이 만들라고 한 곳). EP 는 "EP01" 같은 편 이름.
 */
import spec from "../../../../스타일/린박스/규격.json";
import answer from "../../../../스타일/린박스/정답지.json";
import ours from "../../../../스타일/린박스/우리실측.json";

export { spec, answer, ours };

export const PRESET = "린박스" as const;
/** 키트 도구가 반입될 자리 — lb_cut 부터 여기 파이썬을 부른다 (아직 반입 전이면 지시문이 그렇게 말한다) */
export const RUNNER_DIR = "서버/runner/린박스";
export const RUNNER_NOTE = `이 단계의 러너 명령은 저장소의 ${RUNNER_DIR} 폴더 도구를 부른다 (파이썬은 러너 venv — 맥 ~/.volcano/venv/bin/python · 윈도우 ~/.volcano/venv/Scripts/python.exe, 없으면 python).`;

/** 경로 이어붙이기 — 클라이언트 OS 를 모르므로 '/' 로 잇는다 (윈도우도 '/' 를 받는다) */
export function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}

/** payload 에서 문자열 칸을 안전하게 꺼낸다 */
export function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === "string" ? v.trim() : "";
}

/** payload 에서 숫자 칸을 안전하게 꺼낸다 (문자열 숫자도 받는다). 없으면 null */
export function num(payload: Record<string, unknown>, key: string): number | null {
  const v = payload[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

/** 편 이름 규약 — EP01 · EP19 (대문자 EP + 숫자). 볼케이노 키트의 폴더 이름과 같다 */
export function isEpName(x: string): boolean {
  return /^EP\d{1,3}$/.test(x);
}

/** 작업/<EP> 편 폴더 */
export function epDir(workdir: string, ep: string): string {
  return join(workdir, "작업", ep);
}

/** "24000/1001" → 23.976 (소수 3자리). 못 읽으면 null */
export function parseFps(rate: string | undefined): number | null {
  if (!rate) return null;
  const [n, d] = rate.split("/").map(Number);
  if (!Number.isFinite(n) || n <= 0) return null;
  const den = d === undefined ? 1 : d;
  if (!Number.isFinite(den) || den <= 0) return null;
  return Math.round((n / den) * 1000) / 1000;
}

export const r3 = (x: number): number => Math.round(x * 1000) / 1000;

/** 이 단계들이 payload 로 이어 나르는 값 — start 가 정하고 lb_* 가 그대로 실어 보낸다 */
export interface LbCarry {
  workdir: string;
  ep: string;
  ep_dir: string;
  start_s: number;
  end_s: number;
}

/** carry 값을 payload 에서 읽는다. 하나라도 없으면 null (부르는 쪽이 반려한다) */
export function readCarry(payload: Record<string, unknown>): LbCarry | null {
  const workdir = str(payload, "workdir");
  const ep = str(payload, "ep");
  const start_s = num(payload, "start_s");
  const end_s = num(payload, "end_s");
  if (!workdir || !isEpName(ep) || start_s === null || end_s === null) return null;
  return { workdir, ep, ep_dir: str(payload, "ep_dir") || epDir(workdir, ep), start_s, end_s };
}

export const CARRY_KEYS = ["source", "workdir", "ep", "ep_dir", "start_s", "end_s"] as const;
