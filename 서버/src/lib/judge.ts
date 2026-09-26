/**
 * lib/judge.ts — judge 일감(jobs_kind:"judge")을 받는 쪽이 지킬 규칙을 **한 곳에서** 낸다 (2026-09-26 사장님 결정 ②④).
 *
 * 왜: 예전 지시는 원시 request(EvoLink 주소·키 자리)를 주고 «그대로 보낸다» 였다. 받는 쪽(세션·실행기)마다
 *   «agy 먼저» 규칙이 빠져 영화롱폼 judge 가 EvoLink 로 곧장 갔다(볼트 제안/스크립트/제미나이점검_20260926
 *   점검_계획 표 ② · 클래스 3). 이제 judge 일감은 전부 저장소의 서버/runner/judge_run.py 하나를 지난다 —
 *   agy(구독) 먼저 · 막히면 글만 EvoLink 비상 길 · 영상·소리·그림은 멈춤 · 순정 구글 길은 거절.
 *   request 는 그 비상 길의 재료로 일감에 남긴다(보내는 것은 judge_run 만).
 * 지시문은 여기서만 만든다 — brief·select·subtitle 이 같은 글을 쓴다(규칙은 최종 관문 하나 — 2026-09-03 «14자 규칙을
 *   복원 경로가 우회» 사건). 배포 순서의 틈(반박 25): 서버가 먼저 바뀌고 PC 저장소가 옛 판이면 judge_run.py 가 없다 —
 *   그때는 멈추고 git pull 하라고 지시에 적는다(원시 request 를 손으로 보내 대신하지 않게).
 */
import type { JudgeJob } from "../schema.js";

export const JUDGE_RUN_PY = "서버/runner/judge_run.py";
const 번호 = "①②③④⑤⑥⑦⑧⑨⑩";

function dirOf(p: string): string {
  const i = p.lastIndexOf("/");
  return i > 0 ? p.slice(0, i) : ".";
}

/** 일감에 job_file(세션이 일감 객체를 저장할 자리)과 run(저장소 루트에서 그대로 실행할 argv)을 붙인다 */
export function viaJudgeRun(job: Omit<JudgeJob, "job_file" | "run">): JudgeJob {
  const jobFile = `${dirOf(job.out)}/${job.name}.job.json`;
  return { ...job, job_file: jobFile, run: ["python", JUDGE_RUN_PY, "--job", jobFile, "--out", job.out] };
}

/** judge 일감 처리 지시 4줄 — start 번호(①=1)부터 매긴다. 단계는 이 뒤에 measure·carry 줄을 잇는다 */
export function judgeRunInstructions(start = 1): string[] {
  const n = (i: number) => 번호[start - 1 + i] ?? `(${start + i})`;
  return [
    `${n(0)} jobs 의 judge 일감마다 일감 객체 전체(JSON)를 그 일감의 job_file 경로에 그대로 쓴다 — Write 도구로(셸 echo·heredoc 금지 · 한글 이스케이프 금지). request 를 직접 보내지 않는다(curl·fetch·손 스크립트 금지) — request 는 judge_run 의 EvoLink 비상 길 재료다.`,
    `${n(1)} **저장소 루트에서** 일감의 run 을 그대로 실행한다: python ${JUDGE_RUN_PY} --job <job_file> --out <out> (맥은 python3). judge_run 이 agy(구독) 먼저 → 막히면 사장님 규칙(2026-09-26)대로: 글만 보내는 판정은 EvoLink 비상 길 한 번 · 영상·소리·그림이 든 판정은 멈춤 · 순정 구글 길(GEMINI_API_KEY·Files API)은 거절. inputs 치환·키 읽기도 judge_run 이 한다 — 전사 본문·키 값을 화면·파일·payload 에 옮겨 적지 않는다.`,
    `${n(2)} 종료코드 0 = out 에 generateContent 응답 모양이 있다. 3 = 멈춤(agy 실패인데 영상·소리·그림 판정 · 모르는 본문 모양 · agy 없음 · EvoLink 키 없음) — 표준오류 문구를 사람에게 그대로 보이고 여쭙는다. 2 = 일감 잘못·막힌 길 · 4 = EvoLink 비상 길도 실패 — 멈추고 보고한다. 어느 경우든 EvoLink·구글로 손수 보내 우회하지 않는다.`,
    `${n(3)} ${JUDGE_RUN_PY} 가 없으면(옛 저장소) 멈추고 저장소를 git pull 한 뒤 다시 한다 — 원시 request 를 손으로 보내 대신하지 않는다.`,
  ];
}

/** 메시지용 — 이 판정이 어느 길로 가는지 한 토막 */
export function judgeRoute(hasMedia: boolean, backend: string, model: string): string {
  return hasMedia
    ? "judge_run.py — agy 먼저 · 영상·그림 판정이라 막히면 멈춤"
    : `judge_run.py — agy 먼저 · 막히면 ${backend}/${model} 비상 길`;
}
