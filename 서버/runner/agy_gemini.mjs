// .mjs 실행기용 다리 — 제미나이는 agy(구독) 먼저, 막히면 null 을 돌려줘 부른 쪽이 EvoLink 로 간다.
//   실제 일은 같은 폴더 agy_gemini.py 가 한다(한 벌만 둔다). 2026-09-26 사장님 지시.
//   const resp = agyGenerate(body, "run_brief");   // generateContent 응답 모양 또는 null
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PY = process.platform === "win32" ? "python" : "python3";

export class AgyStop extends Error {}

export function agyGenerate(body, caller, limitMin = 10) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "agyreq_"));
  try {
    const inF = path.join(dir, "body.json"), outF = path.join(dir, "resp.json");
    fs.writeFileSync(inF, typeof body === "string" ? body : JSON.stringify(body), "utf8");
    const r = spawnSync(PY, [path.join(HERE, "agy_gemini.py"), "--body", inF, "--out", outF, "--caller", caller, "--limit", String(limitMin)],
      { encoding: "utf8", stdio: ["ignore", "inherit", "inherit"], timeout: (limitMin * 60 + 180) * 1000 });
    // 3 = 영상·소리 판정이 agy 로 끝내 안 됨 — EvoLink 로 넘기지 않고 멈춘다(2026-09-26 사장님 결정 2번)
    if (r.status === 3) throw new AgyStop("agy 실패 · 영상·소리 판정 — EvoLink 금지라 멈춤 (" + caller + ")");
    if (r.status !== 0 || !fs.existsSync(outF)) return null;
    return JSON.parse(fs.readFileSync(outF, "utf8"));
  } catch (e) {
    if (e instanceof AgyStop) throw e;               // 멈춤은 삼키지 않는다
    console.error("agy 다리 실패:", e.message);
    return null;
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
