// .mjs 실행기용 — 서버 judge 일감은 전부 같은 폴더 judge_run.py 하나를 지난다 (2026-09-26 사장님 결정 ②④).
//   agy(구독) 먼저 → 막히면 멈춤(글만이어도 · 2026-10-05 사장님 — 허락 YOUSTUDIO_EVOLINK_APPROVED=1 일 때만 글만 EvoLink 한 번) · 영상·소리·그림은 멈춤 · 순정 구글(Files API·GEMINI_API_KEY) 길은 거절.
//   규칙은 judge_run.py 한 곳에만 있다 — 여기서 EvoLink·구글을 직접 부르지 않는다.
//   const { code, resp } = judgeRun(job);   // code 0 이면 resp = generateContent 응답 모양 · 3 멈춤 · 2 일감 잘못·막힌 길 · 4 비상 길 실패
//   judgeRun(job, { limitMin: 5, caller: "분석_탐침" })   // caller = gemini_route.jsonl 에 남길 이름 (없으면 judge_run/<일감 이름>)
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PY = process.platform === "win32" ? "python" : "python3";
export const JUDGE_RUN_PY = path.join(HERE, "judge_run.py");

export const 종료코드_뜻 = { 0: "답 받음", 2: "일감이 잘못됐거나 막힌 길(순정)", 3: "멈춤 — 사람에게 여쭙기(agy 실패 — 글 판정도 · agy 없음 · 모르는 본문 모양)", 4: "EvoLink 비상 길도 실패" };

export function judgeRun(job, { out = job.out, limitMin, caller } = {}) {
  if (!fs.existsSync(JUDGE_RUN_PY)) return { code: 2, resp: null, why: "judge_run.py 가 없다 — 저장소를 git pull 하라" };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "judgejob_"));
  try {
    const jobF = path.join(dir, "job.json");
    fs.writeFileSync(jobF, JSON.stringify(job), "utf8");
    const argv = [JUDGE_RUN_PY, "--job", jobF, "--out", out, ...(limitMin ? ["--limit", String(limitMin)] : []), ...(caller ? ["--caller", caller] : [])];
    const r = spawnSync(PY, argv, { encoding: "utf8", stdio: ["ignore", "inherit", "inherit"] });
    const code = r.status ?? 1;
    if (code !== 0) return { code, resp: null, why: 종료코드_뜻[code] ?? (r.error?.message || "알 수 없는 실패") };
    return { code, resp: JSON.parse(fs.readFileSync(out, "utf8")), why: "" };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
