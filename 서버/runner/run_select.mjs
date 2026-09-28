// runner 역할: select ① 지시 → do[](ffmpeg) → judge(judge_run.py — agy 먼저, 막히면 멈춤) → measure(gemini_json_text, 점 경로) → select ② → write_files
import fs from "node:fs";
import { authHeaders } from "./기기.mjs"; // 발급 대장 인증(토큰·기기 id) — 설계/인증_이메일허가제.md 7
import path from "node:path";
import { execFileSync } from "node:child_process";
import { judgeRun } from "./judge_run.mjs"; // judge 는 judge_run.py 하나로 — 영상·그림 판정은 agy 가 막히면 멈춤 (2026-09-26 사장님)
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const briefDoc = JSON.parse(fs.readFileSync(W + "/brief/brief.json", "utf8"));
const facts = JSON.parse(fs.readFileSync(W + "/facts.json", "utf8"));
const transcript = JSON.parse(fs.readFileSync(W + "/transcript/transcript.json", "utf8"));
const carry = {
  workdir: W,
  source: { kind: "local_video", path: "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4", title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" },
  transcript_path: W + "/transcript/transcript.json",
  brief_path: W + "/brief/brief.json",
  brief: briefDoc,
  facts,
  utterance_spans: transcript.utterances.map((u) => [u.start, u.end]),
};
let id = 0;
async function call(step, payload) {
  const body = { jsonrpc: "2.0", id: ++id, method: "tools/call", params: { name: "youstudio_video", arguments: { step, preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25", ...authHeaders() }, body: JSON.stringify(body) });
  const text = await r.text();
  const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}
const setPath = (obj, dotted, val) => { const ks = dotted.split("."); let o = obj; for (let i = 0; i < ks.length - 1; i++) { const k = ks[i]; const nk = ks[i + 1]; if (o[k] === undefined) o[k] = /^\d+$/.test(nk) ? [] : {}; o = o[k]; } o[ks.at(-1)] = val; };

// ① 지시
const r1 = await call("select", carry);
if (r1.status !== "execute" || r1.jobs_kind !== "judge") throw new Error("① 예상 밖: " + JSON.stringify({ status: r1.status, message: r1.message }));
console.log("plan:", JSON.stringify(r1.plan), "warnings:", JSON.stringify(r1.warnings ?? []));

// do[] — ffmpeg 그대로
for (const d of r1.do ?? []) {
  const outArg = d.argv.at(-1);
  fs.mkdirSync(path.dirname(outArg), { recursive: true });
  const t0 = Date.now();
  execFileSync(d.argv[0], d.argv.slice(1), { stdio: ["ignore", "ignore", "inherit"] });
  console.log(`do ${d.name} ok ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}

// jobs — judge: judge_run.py 하나로 (agy 먼저 · 영상·그림 판정이라 agy 가 막히면 멈춤 — EvoLink·순정 Files API 로 안 감,
//   사장님 결정 ②④ 2026-09-26). agy 는 @inline_file/@file_uri 자리표의 로컬 파일을 그대로 본다 — 업로드·base64 가 필요 없다.
const visualPayload = {};
for (const job of r1.jobs) {
  const t0 = Date.now();
  const jr = judgeRun(job);
  if (jr.code !== 0) {
    console.error(`★judge ${job.name} 종료코드 ${jr.code} — ${jr.why}. 멈춘다(EvoLink·구글로 손수 보내지 않는다).`);
    process.exit(jr.code);
  }
  const raw = jr.resp;
  console.log(`judge ${job.name} ${raw.route ?? "?"} ${((Date.now() - t0) / 1000).toFixed(1)}s → ${path.basename(job.out)}`);
  const cand = raw.candidates?.[0];
  if (cand?.finishReason !== "STOP") throw new Error("잘림/비정상 finishReason=" + cand?.finishReason);
  const parsed = JSON.parse((cand.content?.parts ?? []).map((p) => p.text ?? "").join(""));
  const m = r1.measure.find((x) => x.from === "job:" + job.name);
  setPath(visualPayload, m.as, parsed);
}

// ② 결과
const r2 = await call("select", { ...carry, visual: visualPayload.visual });
for (const wf of r2.write_files ?? []) {
  const content = typeof wf.content === "string" ? wf.content : JSON.stringify(wf.content, null, 2);
  fs.writeFileSync(wf.path, content, "utf8");
  console.log("wrote", wf.path);
}
console.log(JSON.stringify({ status: r2.status, next_step: r2.next_step, message: r2.message, metrics: r2.metrics, gates: r2.gates, warnings: r2.warnings }, null, 2));
if (r2.status === "execute") {
  const doc = r2.write_files.find((w) => /selection\.json$/.test(w.path)).content;
  for (const s of doc.segments) console.log(`${String(s.i).padStart(2)} | ${s.in.toFixed(1).padStart(6)}→${s.out.toFixed(1).padStart(6)} | ${String(s.len_s).padStart(5)}s | ${s.role} | ★${s.importance} | ${s.src.join(",")} | ${s.why.slice(0, 70)}`);
  const vis = r2.write_files.find((w) => /visual\.json$/.test(w.path)).content;
  console.log("--- visual.silent scenes ---");
  vis.silent.forEach((st, k) => st.scenes.forEach((sc) => console.log(`silent_${k} ${sc.start}→${sc.end} ★${sc.importance} ${sc.what}`)));
  console.log("--- ending beats ---");
  console.log(vis.ending?.ending_summary);
  (vis.ending?.beats ?? []).forEach((b) => console.log(`${b.start}→${b.end} ★${b.importance}${b.is_ending_beat ? " END" : ""} [${b.emotion}] ${b.what}`));
}
