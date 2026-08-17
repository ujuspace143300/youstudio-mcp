// runner 역할: brief ① 지시 받기 → judge job 실행(inputs 치환·auth env·out 저장) → measure(gemini_json_text) → brief ② → write_files
import fs from "node:fs";
import { execFileSync } from "node:child_process";
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const carry = {
  workdir: W,
  source: { kind: "local_video", path: "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4", title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" },
  transcript_path: W + "/transcript/transcript.json",
};
let id = 0;
async function call(step, payload) {
  const body = { jsonrpc: "2.0", id: ++id, method: "tools/call", params: { name: "youstudio_video", arguments: { step, preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" }, body: JSON.stringify(body) });
  const text = await r.text();
  const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}

// ① 지시
const r1 = await call("brief", carry);
if (r1.status !== "execute" || r1.jobs_kind !== "judge") throw new Error("① 예상 밖: " + r1.status + "/" + r1.jobs_kind);
const job = r1.jobs[0];

// inputs 치환 (파일 → 문자열, 로그에 안 찍음)
let bodyStr = JSON.stringify(job.request.body);
for (const inp of job.inputs) {
  const content = fs.readFileSync(inp.path, "utf8");
  bodyStr = bodyStr.replace(JSON.stringify(inp.placeholder).slice(1, -1), () => JSON.stringify(content).slice(1, -1));
}
// auth: 환경변수에서 읽어 헤더로만 (사용자 환경변수 — 새 프로세스라 레지스트리 값을 읽는다)
const key = process.env[job.auth.env] || execFileSync("powershell", ["-NoProfile", "-Command", `[Environment]::GetEnvironmentVariable('${job.auth.env}','User')`], { encoding: "utf8" }).trim();
if (!key) throw new Error(job.auth.env + " 없음");
const t0 = Date.now();
const resp = await fetch(job.request.url, { method: job.request.method, headers: { ...job.request.headers, Authorization: "Bearer " + key }, body: bodyStr });
const rawText = await resp.text();
fs.mkdirSync(job.out.replace(/\/[^/]+$/, ""), { recursive: true });
fs.writeFileSync(job.out, rawText, "utf8");
console.log(`judge http=${resp.status} time=${((Date.now() - t0) / 1000).toFixed(1)}s bytes=${rawText.length} → ${job.out}`);
const raw = JSON.parse(rawText);
if (raw.error) throw new Error("모델 오류: " + JSON.stringify(raw.error));
const cand = raw.candidates?.[0];
console.log("finishReason=" + cand?.finishReason + " usage=" + JSON.stringify(raw.usageMetadata));
if (cand?.finishReason !== "STOP") throw new Error("잘림/비정상 finishReason=" + cand?.finishReason);
const textOut = (cand.content?.parts ?? []).map((p) => p.text ?? "").join("");
const briefJson = JSON.parse(textOut);

// ② 결과 검사
const r2 = await call("brief", { ...carry, brief: briefJson });
for (const wf of r2.write_files ?? []) {
  const content = typeof wf.content === "string" ? wf.content : JSON.stringify(wf.content, null, 2);
  fs.writeFileSync(wf.path, content, "utf8");
  console.log("wrote", wf.path);
}
const { write_files, ...rest } = r2;
console.log(JSON.stringify({ status: rest.status, next_step: rest.next_step, message: rest.message, metrics: rest.metrics, warnings: rest.warnings }, null, 2));
if (rest.status === "execute") {
  const doc = write_files[0].content;
  console.log("logline: " + doc.logline);
  for (const e of doc.events) console.log(`${String(e.n).padStart(2)} | ${e.start.toFixed(1).padStart(6)} → ${e.end.toFixed(1).padStart(6)} | ★${e.importance}${e.spoiler ? " S" : "  "} | ${e.summary}`);
}
