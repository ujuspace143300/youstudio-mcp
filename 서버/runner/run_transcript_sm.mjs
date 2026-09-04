// runner: transcript ① (Speechmatics batch v2 — 제출 → 폴링 → json-v2) → ② write_files
import fs from "node:fs";
import { authHeaders } from "./기기.mjs"; // 발급 대장 인증(토큰·기기 id) — 설계/인증_이메일허가제.md 7
import { spawnSync } from "node:child_process";
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const SRC = "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4";
const carry = { workdir: W, source: { kind: "local_video", path: SRC, title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" } };
const call = async (payload) => {
  const body = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "youstudio_video", arguments: { step: "transcript", preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25", ...authHeaders() }, body: JSON.stringify(body) });
  const t = await r.text(); const ct = r.headers.get("content-type") ?? "";
  const j = ct.includes("text/event-stream") ? JSON.parse(t.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(t);
  if (j.error) throw new Error(JSON.stringify(j.error));
  return j.result.structuredContent;
};
const key = process.env.SPEECHMATICS_API_KEY;
if (!key) { console.log("SPEECHMATICS_API_KEY 없음"); process.exit(1); }

const r1 = await call(carry);
console.log("①", r1.status, "|", r1.message);
for (const d of r1.do ?? []) {
  const res = spawnSync(d.argv[0], d.argv.slice(1), { encoding: "utf8" });
  if (d.name === "audio_size") var audio_bytes = JSON.parse(res.stdout);
  if (d.name === "silence_scan") var silences_raw = res.stderr ?? "";
  console.log("do", d.name, res.status === 0 ? "ok" : `실패 ${res.status}`);
}
const job = r1.jobs[0];
const audio = job.request.multipart.data_file.slice(1);
const t0 = Date.now();
const fd = new FormData();
fd.append("data_file", new Blob([fs.readFileSync(audio)]), audio.split("/").pop());
fd.append("config", job.request.multipart.config);
let resp = await fetch(job.batch.submit_url, { method: "POST", headers: { authorization: `Bearer ${key}` }, body: fd });
if (!resp.ok) { console.log("제출 실패", resp.status, (await resp.text()).slice(0, 300)); process.exit(2); }
const { id } = await resp.json();
console.log("job id", id, "— 폴링 시작");
let done = false;
while (!done && (Date.now() - t0) / 1000 < job.batch.timeout_s) {
  await new Promise((r) => setTimeout(r, job.batch.poll_s * 1000));
  const st = await (await fetch(job.batch.status_url.replace("{id}", id), { headers: { authorization: `Bearer ${key}` } })).json();
  const s = st?.job?.status ?? st?.status;
  process.stdout.write(`  ${Math.round((Date.now() - t0) / 1000)}s ${s}\n`);
  if (s === "done") done = true;
  else if (s === "rejected" || s === "expired") { console.log("작업 실패", JSON.stringify(st).slice(0, 300)); process.exit(2); }
}
const tr = await (await fetch(job.batch.transcript_url.replace("{id}", id), { headers: { authorization: `Bearer ${key}` } })).json();
const elapsed = Math.round((Date.now() - t0) / 1000);
fs.writeFileSync(job.out, JSON.stringify(tr, null, 1), "utf8");
const nWords = (tr.results ?? []).filter((r) => (r.type ?? "word") === "word").length;
console.log(`전사 완료 ${elapsed}s · 단어 ${nWords} · 저장 ${job.out}`);
fs.writeFileSync(W + "/transcript/_sm_meta.json", JSON.stringify({ job_id: id, elapsed_s: elapsed, words: nWords, audio_s: 929.077, job_info: tr.job ?? null, metadata: tr.metadata ?? null }, null, 1), "utf8");

const r2 = await call({ ...carry, asr: tr, audio_bytes, silences_raw });
console.log("②", r2.status, "|", r2.message);
if (r2.status === "error") { console.log((r2.instructions ?? []).join("\n")); process.exit(2); }
for (const wf of r2.write_files ?? []) { fs.writeFileSync(wf.path, typeof wf.content === "string" ? wf.content : JSON.stringify(wf.content, null, 2), "utf8"); console.log("wrote", wf.path); }
console.log("metrics:", JSON.stringify(r2.metrics));
