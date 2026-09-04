// runner: script ① (need_input) → 사람(클로드)이 blocks 파일을 쓴다 → script ② 검사 → write_files
import fs from "node:fs";
import { authHeaders } from "./기기.mjs"; // 발급 대장 인증(토큰·기기 id) — 설계/인증_이메일허가제.md 7
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const rd = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const transcript = rd(W + "/transcript/transcript.json");
const carry = {
  workdir: W,
  source: { kind: "local_video", path: "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4", title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" },
  transcript_path: W + "/transcript/transcript.json", brief_path: W + "/brief/brief.json", selection_path: W + "/clips/selection.json",
  selection: rd(W + "/clips/selection.json"), visual: rd(W + "/clips/visual.json"), facts: rd(W + "/facts.json"), brief: rd(W + "/brief/brief.json"),
  utterance_spans: transcript.utterances.map((u) => [u.start, u.end]),
};
async function call(step, payload) {
  const body = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "youstudio_video", arguments: { step, preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25", ...authHeaders() }, body: JSON.stringify(body) });
  const text = await r.text(); const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}
const mode = process.argv[2] ?? "material";
if (mode === "material") {
  const r1 = await call("script", carry);
  console.log("status:", r1.status, "|", r1.message);
  const m = r1.material;
  console.log("logline:", m.logline);
  console.log("--- segments ---");
  for (const s of m.segments) console.log(`seg ${s.i} | ${s.in}→${s.out} (${s.len_s}s) | ${s.role} ★${s.importance} | ${s.src.join(",")} | ${s.why.slice(0, 90)}`);
  console.log("--- bridges ---");
  for (const b of m.bridges) console.log(`bridge ${b.k} | ${b.start}→${b.end} (${b.len_s}s) | ${b.events.map((e) => `#${e.n}★${e.importance} ${e.summary}`).join(" / ")}`);
  console.log("--- visual_facts ---"); for (const v of m.visual_facts) console.log(`${v.t_s}s ${v.fact}`);
  console.log("--- scenes ---"); for (const s of m.scenes) console.log(`s${s.stretch} ${s.start}→${s.end} ★${s.importance} ${s.what} ${s.visual_facts ? "[" + s.visual_facts + "]" : ""}`);
  console.log("--- ending ---"); console.log(m.ending?.summary); for (const b of m.ending?.beats ?? []) console.log(`${b.start}→${b.end} ★${b.importance}${b.is_ending_beat ? " END" : ""} [${b.emotion}] ${b.what}`);
  console.log("--- events ---"); for (const e of m.events) console.log(`#${e.n} ${e.start}→${e.end} ★${e.importance}${e.spoiler ? " S" : ""} ${e.summary}`);
} else {
  const blocks = rd(mode);
  const r2 = await call("script", { ...carry, script: blocks });
  console.log("status:", r2.status, "|", r2.message);
  if (r2.status === "error") { console.log("instructions:", r2.instructions.join("\n")); process.exit(2); }
  for (const wf of r2.write_files ?? []) { fs.mkdirSync(wf.path.replace(/\/[^/]+$/, ""), { recursive: true }); fs.writeFileSync(wf.path, JSON.stringify(wf.content, null, 2), "utf8"); console.log("wrote", wf.path); }
  console.log(JSON.stringify(r2.metrics, null, 1));
  console.log("gates:", JSON.stringify(r2.gates.map((g) => [g.id, g.pass])));
  console.log("warnings:", JSON.stringify(r2.warnings ?? [], null, 1));
}
