// runner: 제미나이 **유튜브 URL 영상 입력** 탐침 (분석 단계 (b) 자동화 가능 여부 실측)
//   재는 것: EvoLink(1순위) / 구글 순정(2순위) 의 generateContent 가 file_data.file_uri 에
//   유튜브 URL 을 받아 **영상을 실제로 보고** 답하는가. 프롬프트는 짧게(첫 장면 한 줄 묘사).
//   키는 **환경변수에서만** 읽는다(서버 무보관). 응답 원문은 잘라서 찍고 파일로 남긴다.
// 사용: node 서버/runner/분석_탐침.mjs [--url <youtube>] [--backend evolink|google|둘다]
import fs from "node:fs";
import { execFileSync } from "node:child_process";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL_ = arg("--url", "https://www.youtube.com/watch?v=snhH6I5XlFQ");
const BACKEND = arg("--backend", "둘다");
const MODEL = arg("--model", "gemini-3.5-flash");
const OUT = arg("--out", "C:/Users/user/Desktop/youstudio_work/분석/_탐침");

const key = (env) => process.env[env] || execFileSync("powershell", ["-NoProfile", "-Command", `[Environment]::GetEnvironmentVariable('${env}','User')`], { encoding: "utf8" }).trim();
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
if (BACKEND === "evolink" || BACKEND === "둘다") {
  const k = key("EVOLINK_API_KEY");
  if (!k) console.log("EVOLINK_API_KEY 없음 — 건너뜀");
  else 결과.push(await 탐침("evolink", `https://api.evolink.ai/v1beta/models/${MODEL}:generateContent`, { authorization: `Bearer ${k}` }));
}
if (BACKEND === "google" || BACKEND === "둘다") {
  const k = key("GEMINI_API_KEY");
  if (!k) console.log("GEMINI_API_KEY 없음 — 건너뜀");
  else 결과.push(await 탐침("google", `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, { "x-goog-api-key": k }));
}
console.log("\n판정:", JSON.stringify(결과.map((r) => [r.이름, r.status, r.ok ? "유튜브 URL 입력 됨" : "안 됨"]), null, 0));
