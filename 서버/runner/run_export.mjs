import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const rd = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const carry = {
  workdir: W,
  source: { kind: "local_video", path: "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4", title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" },
  transcript_path: W + "/transcript/transcript.json", brief_path: W + "/brief/brief.json", selection_path: W + "/clips/selection.json", script_path: W + "/script/script.json", voice_path: W + "/voice/voice.json", timeline_path: W + "/subtitle/timeline.json",
  timeline: rd(W + "/subtitle/timeline.json"), voice: rd(W + "/voice/voice.json"), script: rd(W + "/script/script.json"), brief: rd(W + "/brief/brief.json"), transcript_metrics: { utterance_count: rd(W + "/transcript/transcript.json").utterance_count },
};
async function call(step, payload) {
  const body = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "youstudio_video", arguments: { step, preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" }, body: JSON.stringify(body) });
  const text = await r.text(); const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}
const r1 = await call("export", carry);
console.log("①", r1.status, "|", r1.message);
if (r1.status !== "execute") process.exit(2);
// do[] 는 **저장소 루트에서** 실행한다 — 조립 스크립트 경로가 저장소 기준(규격 조립.조립기)이다
const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//, "")), "../..");
const measured = {};
const stdouts = {};
for (const d of r1.do) {
  const last = d.argv.at(-1);
  if (/[\\/]/.test(last)) fs.mkdirSync(path.dirname(last), { recursive: true });
  console.log("do", d.name, "…");
  stdouts[d.name] = execFileSync(d.argv[0], d.argv.slice(1), { cwd: REPO, encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] });
}
// measure 는 서버가 시킨 대로만 읽는다 (이름을 코드에 박지 않는다)
for (const m of r1.measure ?? []) {
  const name = m.from.replace(/^job:/, "");
  if (m.unit === "json_stdout") measured[m.as] = JSON.parse(stdouts[name]);
  else measured[m.as] = stdouts[name];
  console.log("measure", m.as, "←", name, JSON.stringify(measured[m.as]).slice(0, 160));
}
const r2 = await call("export", { ...carry, ...measured });
console.log("②", r2.status, "|", r2.message);
if (r2.status === "error") { console.log(r2.instructions?.join("\n")); process.exit(2); }
for (const wf of r2.write_files ?? []) { fs.mkdirSync(path.dirname(wf.path), { recursive: true }); fs.writeFileSync(wf.path, typeof wf.content === "string" ? wf.content : JSON.stringify(wf.content, null, 2), "utf8"); console.log("wrote", wf.path, fs.statSync(wf.path).size, "B"); }
console.log("gates:"); for (const g of r2.gates) console.log(` [${g.step}] ${g.id}: ${g.pass} — ${g.detail}`);
console.log("metrics:", JSON.stringify(r2.metrics));
