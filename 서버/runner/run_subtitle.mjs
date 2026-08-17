// runner: subtitle ① (need_input 번역) → 사람(클로드)이 translations 파일을 쓴다 → ② → write_files
import fs from "node:fs";
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const rd = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const carry = {
  workdir: W,
  source: { kind: "local_video", path: "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4", title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" },
  transcript_path: W + "/transcript/transcript.json", brief_path: W + "/brief/brief.json", selection_path: W + "/clips/selection.json", script_path: W + "/script/script.json", voice_path: W + "/voice/voice.json",
  selection: rd(W + "/clips/selection.json"), voice: rd(W + "/voice/voice.json"), script: rd(W + "/script/script.json"), transcript_utterances: rd(W + "/transcript/transcript.json").utterances, transcript_words: rd(W + "/transcript/transcript.json").words ?? [], transcript_silences: rd(W + "/transcript/transcript.json").silences ?? [], visual: rd(W + "/clips/visual.json"),
};
async function call(step, payload) {
  const body = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "youstudio_video", arguments: { step, preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" }, body: JSON.stringify(body) });
  const text = await r.text(); const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}
const mode = process.argv[2] ?? "material";
if (mode === "material") {
  const r1 = await call("subtitle", carry);
  console.log("status:", r1.status, "|", r1.message);
  console.log("style_guide:", (r1.style_guide ?? []).join("\n  "));
  fs.writeFileSync(W + "/subtitle/_lines.json", JSON.stringify(r1.material.dialogue_lines, null, 1), "utf8");
  for (const l of r1.material.dialogue_lines) console.log(`${l.id} seg${l.seg} ${l.t} | ${l.en}`);
} else {
  const translations = rd(mode);
  const r2 = await call("subtitle", { ...carry, translations });
  console.log("status:", r2.status, "|", r2.message);
  if (r2.status === "error") { if (r2.diagnostics) { console.log("dead_by_role:", JSON.stringify(r2.diagnostics.dead_by_role)); for (const d of r2.diagnostics.dead_spans_top) console.log(`${d.t0}→${d.t1} (${d.len}s) ${d.picture ? `${d.picture.kind} ${d.picture.role} seg${d.picture.seg} src ${d.picture.src}` : ""}`); console.log("metrics:", JSON.stringify(r2.diagnostics.metrics)); } process.exit(2); }
  for (const wf of r2.write_files ?? []) { fs.mkdirSync(wf.path.replace(/\/[^/]+$/, ""), { recursive: true }); fs.writeFileSync(wf.path, typeof wf.content === "string" ? wf.content : JSON.stringify(wf.content, null, 2), "utf8"); console.log("wrote", wf.path); }
  console.log(JSON.stringify(r2.metrics, null, 1));
  console.log("gates:", JSON.stringify(r2.gates.map((g) => [g.id, g.pass, g.detail.slice(0, 120)]), null, 1));
  console.log("warnings:", JSON.stringify(r2.warnings ?? [], null, 1));
  const tl = r2.write_files.find((w) => /timeline\.json$/.test(w.path)).content;
  console.log("--- picture ---");
  for (const p of tl.picture) console.log(`${String(p.k).padStart(2)} ${p.kind.padEnd(7)} ${p.role.padEnd(6)} src ${p.src_in}→${p.src_out} | t ${p.t0}→${p.t1} | ${p.audio} ${p.why ?? ""}`);
  console.log("--- dead spans top ---"); for (const d of tl.dead_spans_top) console.log(`${d.t0}→${d.t1} (${d.len}s)`);
}
