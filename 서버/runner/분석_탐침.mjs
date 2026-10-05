// runner: 제미나이 **유튜브 URL 영상 입력** 탐침 (분석 단계 (b) 자동화 가능 여부 실측)
//   재는 것: agy(기본) / EvoLink(사람이 --backend 로 고를 때만) 의 generateContent 가 file_data.file_uri 에
//   유튜브 URL 을 받아 **영상을 실제로 보고** 답하는가. 프롬프트는 짧게(첫 장면 한 줄 묘사).
//   키는 **환경변수·키 파일에서만** 읽는다(서버 무보관). 응답 원문은 잘라서 찍고 파일로 남긴다.
//   ★2026-09-26 사장님 결정 ④ — 순정 구글 키(GEMINI_API_KEY) 길은 막혔다(--backend google 은 멈춘다).
//     EvoLink 는 판정 길이 아니라 사람이 일부러 고른 계측일 때만 — 보낼 때마다 gemini_route.jsonl 에 «fallback» 한 줄
//     (EvoLink 로 곧장 나간 호출이 기록에 안 남던 구멍 — 볼트 제미나이점검_20260926 점검_계획 3장 구멍 4).
//   agy 쪽은 judge_run.py 를 지난다(judge_run.mjs) — agy_gemini 다리를 곧장 부르면 agy 가 막혔을 때 EvoLink 로
//     안 갔는데도 «fallback» 한 줄이 남았다(2026-09-26 검증 — fallback 줄 수 = EvoLink 로 보낸 수 규약이 깨짐,
//     둘다 는 한 번 보내고 두 줄). judge_run 은 그 줄을 맡아 두었다가 «agy_fail_stop» 으로 적는다(영상이라 멈춤 · 돈 0).
// 사용: node 서버/runner/분석_탐침.mjs [--url <youtube>] [--backend agy|evolink|둘다]  (둘다 = agy + evolink)
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { judgeRun } from "./judge_run.mjs"; // 2026-09-26 — agy 도 같이 잰다(규칙은 judge_run.py 한 곳)

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL_ = arg("--url", "https://www.youtube.com/watch?v=snhH6I5XlFQ");
const BACKEND = arg("--backend", "agy"); // 2026-09-26 기본을 agy 로 — EvoLink 는 --backend 로 부를 때만
const MODEL = arg("--model", "gemini-3.5-flash");
const OUT = arg("--out", "C:/Users/user/Desktop/youstudio_work/분석/_탐침");
if (BACKEND === "google") {
  console.error("★--backend google(순정 구글 키) 길은 막혔다 — 사장님 결정 ④ 2026-09-26. agy 또는 evolink(사람이 고른 계측)만.");
  process.exit(2);
}
if (!["agy", "evolink", "둘다"].includes(BACKEND)) {
  console.error(`★모르는 --backend ${BACKEND} — agy · evolink · 둘다 중 하나`);
  process.exit(2);
}

const key = (env) => {
  if (process.env[env]) return process.env[env].trim();
  if (process.platform === "win32") {
    try { const v = execFileSync("powershell", ["-NoProfile", "-Command", `[Environment]::GetEnvironmentVariable('${env}','User')`], { encoding: "utf8" }).trim(); if (v) return v; } catch { /* 없으면 파일 */ }
  }
  try { return fs.readFileSync(path.join(os.homedir(), ".volcano", "keys", env.replace(/_API_KEY$/, "").toLowerCase()), "utf8").trim(); } catch { return ""; }
};
/** gemini_route.jsonl 에 한 줄 — agy_gemini.py 규약 {t, caller, route, sec, model, reason} */
const 기록 = (route, sec, reason) => {
  try {
    const f = path.join(os.homedir(), ".volcano", "logs", "gemini_route.jsonl");
    fs.mkdirSync(path.dirname(f), { recursive: true });
    const t = new Date(); const p2 = (n) => String(n).padStart(2, "0");
    const ts = `${t.getFullYear()}-${p2(t.getMonth() + 1)}-${p2(t.getDate())} ${p2(t.getHours())}:${p2(t.getMinutes())}:${p2(t.getSeconds())}`;
    fs.appendFileSync(f, JSON.stringify({ t: ts, caller: "분석_탐침", route, sec: Math.round(sec * 10) / 10, model: MODEL, reason: reason.slice(0, 300) }) + "\n", "utf8");
  } catch { /* 기록 실패는 계측을 막지 않는다 */ }
};
const 프롬프트 = "이 영상의 첫 장면을 한 줄로 묘사해라. 영상을 볼 수 없으면 '영상을 볼 수 없음' 이라고만 답해라.";

const 본문 = {
  // EvoLink 실측(2026-08-18): fileData 는 받지만 **mimeType 이 비면 400** — 유튜브 URL 에도 붙여 준다
  contents: [{ role: "user", parts: [{ file_data: { mime_type: arg("--mime", "video/mp4"), file_uri: URL_ } }, { text: 프롬프트 }] }],
  generationConfig: { temperature: 0, maxOutputTokens: 256, thinkingConfig: { thinkingBudget: 0 } },
};

async function 탐침(이름, url, headers) {
  const t0 = Date.now();
  let status = 0, text = "";
  try {
    const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(본문) });
    status = r.status;
    text = await r.text();
  } catch (e) {
    text = `요청 실패: ${e.message}`;
  }
  const 초 = ((Date.now() - t0) / 1000).toFixed(1);
  let 답 = null, 사용 = null;
  try {
    const j = JSON.parse(text);
    답 = (j?.candidates?.[0]?.content?.parts ?? []).map((p) => p.text).filter(Boolean).join("").trim();
    사용 = j?.usageMetadata ?? null;
  } catch { /* 원문 그대로 본다 */ }
  console.log(`\n── ${이름} · HTTP ${status} · ${초}s`);
  console.log("응답 원문(앞 600자):", text.slice(0, 600).replace(/\s+/g, " "));
  if (답) console.log("답:", 답);
  if (사용) console.log("토큰:", JSON.stringify(사용));
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(`${OUT}/탐침_${이름}.json`, JSON.stringify({ 이름, url: URL_, model: MODEL, status, 초: Number(초), 답, usage: 사용, 원문: text.slice(0, 4000) }, null, 1), "utf8");
  return { 이름, status, 초: Number(초), 답, 사용, ok: status === 200 && !!답 && !/영상을 볼 수 없음/.test(답) };
}

const 결과 = [];
if (BACKEND === "agy" || BACKEND === "둘다") {
  const t0 = Date.now();
  // 일감 모양으로 judge_run 에 — agy 먼저, 막히면 유튜브 영상이라 멈춤(종료 3 · EvoLink 로 안 감). request.url 은 안 준다(비상 길 없음).
  const 임시 = fs.mkdtempSync(path.join(os.tmpdir(), "탐침_agy_"));
  let r = null, 멈춤 = "";
  try {
    const j = judgeRun({ name: "분석_탐침", model: MODEL, request: { body: 본문 }, out: path.join(임시, "resp.json") }, { limitMin: 5, caller: "분석_탐침" });
    r = j.code === 0 ? j.resp : null;
    if (j.code !== 0) 멈춤 = `judge_run 종료코드 ${j.code} — ${j.why}`;
  } finally {
    fs.rmSync(임시, { recursive: true, force: true });
  }
  const 답 = r ? r.candidates[0].content.parts.map((p) => p.text ?? "").join("").trim() : null;
  const 초 = Number(((Date.now() - t0) / 1000).toFixed(1));
  console.log(`
── agy · ${r ? "성공" : `실패(${멈춤})`} · ${초}s`);
  if (답) console.log("답:", 답);
  결과.push({ 이름: "agy", status: r ? 200 : 0, 초, 답, 사용: r?.usageMetadata ?? null, ok: !!답 && !/영상을 볼 수 없음/.test(답) });
}
if (BACKEND === "evolink" || BACKEND === "둘다") {
  console.log("★경고: EvoLink 유료 호출 — 사람이 --backend 로 고른 계측이다(판정 길 아님, 사장님 규칙 2026-09-26). gemini_route.jsonl 에 fallback 한 줄로 남긴다.");
  const k = key("EVOLINK_API_KEY");
  // 2026-10-05 사장님 «에보링크 사용하지 않도록 막아 … 그때 내가 판단해줄께» — 사람이 고른 계측도 허락 없이는 안 보낸다
  if (process.env.YOUSTUDIO_EVOLINK_APPROVED !== "1") console.log("★EvoLink 는 사장님 허락 때만(YOUSTUDIO_EVOLINK_APPROVED=1) — 건너뜀");
  else if (!k) console.log("EVOLINK_API_KEY 없음 — 건너뜀");
  else {
    const r = await 탐침("evolink", `https://api.evolink.ai/v1beta/models/${MODEL}:generateContent`, { authorization: `Bearer ${k}`, "user-agent": "youstudio-mcp/0.8 (analysis probe)" });
    기록("fallback", r.초, `사람이 --backend ${BACKEND} 로 고른 계측(유튜브 URL) → EvoLink HTTP ${r.status}`);
    결과.push(r);
  }
}
console.log("\n판정:", JSON.stringify(결과.map((r) => [r.이름, r.status, r.ok ? "유튜브 URL 입력 됨" : "안 됨"]), null, 0));
