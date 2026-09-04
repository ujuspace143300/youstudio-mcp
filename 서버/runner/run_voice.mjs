// runner: voice ① → synthesize(auth env, out pcm) → post(ffmpeg wrap) → measure bytes → voice ② → write_files + record_to_ours(우리실측.json)
import fs from "node:fs";
import { authHeaders } from "./기기.mjs"; // 발급 대장 인증(토큰·기기 id) — 설계/인증_이메일허가제.md 7
import path from "node:path";
import { execFileSync } from "node:child_process";
const URL_ = "http://localhost:8787";
const W = "C:/Users/user/Desktop/youstudio_work/fulltime";
const REPO = "C:/Users/user/Desktop/youstudio-mcp";
const rd = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const carry = {
  workdir: W,
  source: { kind: "local_video", path: "C:/Users/user/Desktop/볼케이노 MCP/쇼폭_영화롱폼/23. FULL TIME  Omeleto.mp4", title: "Full Time (2023)", lang: "en" },
  probe_summary: { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, fps_fraction: "24000/1001", video_codec: "h264", audio: true, audio_tracks: 1, audio_codec: "aac", audio_channels: 2, audio_sample_rate: 44100, audio_lang: "eng" },
  transcript_path: W + "/transcript/transcript.json", brief_path: W + "/brief/brief.json", selection_path: W + "/clips/selection.json", script_path: W + "/script/script.json",
  script: rd(W + "/script/script.json"),
};
async function call(step, payload) {
  const body = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "youstudio_video", arguments: { step, preset: "영화롱폼", payload } } };
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25", ...authHeaders() }, body: JSON.stringify(body) });
  const text = await r.text(); const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}
const key = (env) => process.env[env] || execFileSync("powershell", ["-NoProfile", "-Command", `[Environment]::GetEnvironmentVariable('${env}','User')`], { encoding: "utf8" }).trim();
const setPath = (obj, dotted, val) => { const ks = dotted.split("."); let o = obj; for (let i = 0; i < ks.length - 1; i++) { o[ks[i]] ??= {}; o = o[ks[i]]; } o[ks.at(-1)] = val; };

const r1 = await call("voice", carry);
if (r1.status !== "execute") { console.log("①", r1.status, r1.message); process.exit(2); }
console.log("plan:", JSON.stringify(r1.plan));
const measured = {};
// 재사용: 이전 voice.json 에서 같은 본문(text)의 pcm 이 있으면 합성하지 않고 그대로 쓴다 (runner 최적화 — 서버는 바이트만 잰다)
// [2026-08-17 회귀 수리] 캐시 규칙:
//   ① **직전 실행본(voice_prev.json)만** 쓴다 — 옛 판을 쓰면 대본이 밀렸을 때 '문구는 맞고 파일은 남의 것'이 된다.
//   ② 값에 **파일 해시(pcm_md5)** 를 함께 저장하고, 지금 디스크의 파일 해시와 **같을 때만** 재사용한다.
//   ③ 블록 수·문구가 하나라도 다르면 캐시를 통째로 버린다(대본 변경).
import crypto from "node:crypto";
const md5 = (buf) => crypto.createHash("md5").update(buf).digest("hex");
const prevPath = W + "/voice/voice_prev.json";
const prev = fs.existsSync(prevPath) ? rd(prevPath) : { blocks: [] };
const jobTexts = r1.jobs.map((j) => j.request.body.text);
const prevTexts = (prev.blocks ?? []).map((b) => b.text);
const cacheUsable = prevTexts.length === jobTexts.length && prevTexts.every((t, i) => t === jobTexts[i]);
const stage = {};
if (!cacheUsable) {
  console.log(`캐시 폐기 — 대본이 바뀌었다(직전 ${prevTexts.length}블록 vs 지금 ${jobTexts.length}블록, 문구 일치 ${prevTexts.filter((t, i) => t === jobTexts[i]).length})`);
} else {
  for (const b of prev.blocks) {
    const pcm = b.wav.replace(/\.wav$/, ".pcm");
    if (!fs.existsSync(pcm) || !b.chars_t || !b.pcm_md5) continue;
    const buf = fs.readFileSync(pcm);
    if (md5(buf) !== b.pcm_md5) { console.log(`캐시 무시 ${b.wav.split("/").pop()} — 파일 해시가 기록과 다르다`); continue; }
    stage[b.text] = { pcm: buf, chars_t: b.chars_t };
  }
}
let reused = 0, synthesized = 0;
for (const job of r1.jobs) {
  const text = job.request.body.text;
  if (process.env.REUSE === "1" && stage[text]) {
    const st = stage[text];
    fs.mkdirSync(path.dirname(job.out), { recursive: true }); fs.writeFileSync(job.out, st.pcm);
    setPath(measured, `voice_ts.${job.name}`, { audio_bytes: st.pcm.length, alignment: { characters: st.chars_t.map((c) => c.c), character_start_times_seconds: st.chars_t.map((c) => c.s), character_end_times_seconds: st.chars_t.map((c) => c.e) } });
    reused++; continue;
  }
  synthesized++;
  const apiKey = key(job.auth.env);
  const hName = job.auth.header.split(":")[0].trim();
  const t0 = Date.now();
  const resp = await fetch(job.request.url, { method: job.request.method, headers: { ...job.request.headers, [hName]: apiKey }, body: JSON.stringify(job.request.body) });
  fs.mkdirSync(path.dirname(job.out), { recursive: true });
  if (!resp.ok) { const t = await resp.text(); console.log(`${job.name} HTTP ${resp.status} ${t.slice(0, 200)}`); fs.writeFileSync(job.out, Buffer.alloc(0)); setPath(measured, `voice_ts.${job.name}`, { audio_bytes: 0 }); continue; }
  // measure unit tts_timestamps: audio_base64 → pcm 파일, payload 에는 {audio_bytes, alignment}
  const j = await resp.json();
  const buf = Buffer.from(j.audio_base64, "base64");
  fs.writeFileSync(job.out, buf);
  const al = j.alignment ?? j.normalized_alignment ?? null;
  setPath(measured, `voice_ts.${job.name}`, { audio_bytes: buf.length, alignment: al ? { characters: al.characters, character_start_times_seconds: al.character_start_times_seconds, character_end_times_seconds: al.character_end_times_seconds } : undefined });
  console.log(`${job.name} ${buf.length}B ≈ ${(buf.length / 48000).toFixed(2)}s · 글자 ${al?.characters?.length ?? 0} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
}
for (const p of r1.post ?? []) execFileSync(p.argv[0], p.argv.slice(1), { stdio: ["ignore", "ignore", "inherit"] });
console.log("post: wav", (r1.post ?? []).length, "개 · 재사용", reused, "· 새 합성", synthesized);
// post[] 의 무음스캔(silencedetect) 실행 → speech_raw (재합성 없음)
import { spawnSync } from "node:child_process";
const speech_raw = {};
for (const pj of (r1.post ?? [])) {
  if (!String(pj.name ?? "").startsWith("silence_")) continue;
  const r = spawnSync(pj.argv[0], pj.argv.slice(1), { encoding: "utf8" });
  speech_raw[String(pj.name).replace(/^silence_/, "")] = r.stderr ?? "";
}
console.log("무음스캔", Object.keys(speech_raw).length, "블록");
let r2 = await call("voice", { ...carry, voice_ts: measured.voice_ts, speech_raw });
// ③ 단어 실측 국면 (2026-08-18) — do[] 로 wav 를 이어 붙이고, Speechmatics 배치 1콜로 단어 시각을 받는다.
//   문구 일치도 같은 전사로 판정한다(옛 Groq 27콜 대체). 배치 흐름은 run_transcript_sm.mjs 와 같다.
if (r2.status === "execute" && r2.jobs_kind === "transcribe") {
  for (const d of r2.do ?? []) {
    fs.mkdirSync(path.dirname(d.argv.at(-1)), { recursive: true });
    const res = spawnSync(d.argv[0], d.argv.slice(1), { encoding: "utf8" });
    console.log("do", d.name, res.status === 0 ? "ok" : `실패 ${res.status} ${(res.stderr ?? "").slice(0, 200)}`);
    if (res.status !== 0) process.exit(2);
  }
  const job = r2.jobs[0];
  // 전사 재사용: 같은 wav 묶음이면 다시 부르지 않는다(REUSE=1) — 외부 호출은 돈이다
  if (process.env.REUSE === "1" && fs.existsSync(job.out)) {
    const tr0 = rd(job.out);
    const n0 = (tr0.results ?? []).filter((r) => (r.type ?? "word") === "word").length;
    console.log(`나레 전사 재사용 ${job.out} (단어 ${n0}) — 새로 부르지 않는다`);
    r2 = await call("voice", { ...carry, voice_ts: measured.voice_ts, speech_raw, asr_nar: tr0 });
  } else {
  const apiKey = key(job.auth.env);
  const audio = job.request.multipart.data_file.slice(1);
  const t0 = Date.now();
  const fd = new FormData();
  fd.append("data_file", new Blob([fs.readFileSync(audio)]), audio.split("/").pop());
  fd.append("config", job.request.multipart.config);
  let resp = await fetch(job.batch.submit_url, { method: "POST", headers: { authorization: `Bearer ${apiKey}` }, body: fd });
  if (!resp.ok) { console.log("제출 실패", resp.status, (await resp.text()).slice(0, 300)); process.exit(2); }
  const { id } = await resp.json();
  console.log(`나레 전사 job ${id} — 오디오 ${(fs.statSync(audio).size / 48000).toFixed(1)}s · 폴링 시작`);
  let done = false;
  while (!done && (Date.now() - t0) / 1000 < job.batch.timeout_s) {
    await new Promise((r) => setTimeout(r, job.batch.poll_s * 1000));
    const st = await (await fetch(job.batch.status_url.replace("{id}", id), { headers: { authorization: `Bearer ${apiKey}` } })).json();
    const s2 = st?.job?.status ?? st?.status;
    console.log(`  ${Math.round((Date.now() - t0) / 1000)}s ${s2}`);
    if (s2 === "done") done = true;
    else if (s2 === "rejected" || s2 === "expired") { console.log("작업 실패", JSON.stringify(st).slice(0, 300)); process.exit(2); }
  }
  const tr = await (await fetch(job.batch.transcript_url.replace("{id}", id), { headers: { authorization: `Bearer ${apiKey}` } })).json();
  const elapsed = Math.round((Date.now() - t0) / 1000);
  fs.writeFileSync(job.out, JSON.stringify(tr, null, 1), "utf8");
  const nWords = (tr.results ?? []).filter((r) => (r.type ?? "word") === "word").length;
  console.log(`나레 전사 완료 ${elapsed}s · 단어 ${nWords} · 저장 ${job.out}`);
  fs.writeFileSync(W + "/voice/_sm_nar_meta.json", JSON.stringify({ job_id: id, elapsed_s: elapsed, words: nWords, concat_s: r2.metrics?.concat_total_s ?? null, gap_s: r2.metrics?.concat_gap_s ?? null, offsets: r2.offsets ?? null, job_info: tr.job ?? null, metadata: tr.metadata ?? null }, null, 1), "utf8");
  r2 = await call("voice", { ...carry, voice_ts: measured.voice_ts, speech_raw, asr_nar: tr });
  }
}
console.log("②", r2.status, "|", r2.message);
if (r2.status !== "execute") { console.log(r2.instructions?.join("\n")); process.exit(2); }
for (const wf of r2.write_files ?? []) {
  if (/voice\.json$/.test(wf.path) && wf.content && Array.isArray(wf.content.blocks)) {
    for (const b of wf.content.blocks) { const pcm = b.wav.replace(/\.wav$/, ".pcm"); if (fs.existsSync(pcm)) b.pcm_md5 = md5(fs.readFileSync(pcm)); }
  }
  fs.writeFileSync(wf.path, JSON.stringify(wf.content, null, 2), "utf8");
}
// 다음 실행 캐시 = 이번 실행본
if ((r2.write_files ?? []).some((w) => /voice\.json$/.test(w.path))) fs.copyFileSync(W + "/voice/voice.json", W + "/voice/voice_prev.json");
// record_to_ours → 저장소 우리실측.json tts
const oursPath = REPO + "/스타일/영화롱폼/우리실측.json";
const ours = rd(oursPath); ours.tts = { ...(ours.tts ?? {}), ...r2.record_to_ours.tts };
fs.writeFileSync(oursPath, JSON.stringify(ours, null, 2) + "\n", "utf8");
console.log("우리실측.json tts:", JSON.stringify(ours.tts));
console.log(JSON.stringify(r2.metrics, null, 1));
console.log("warnings:", JSON.stringify(r2.warnings ?? []));
const doc = r2.write_files[0].content;
for (const b of doc.blocks) console.log(`b${String(b.n).padStart(2, "0")} ${String(b.dur_s.toFixed(2)).padStart(5)}s ${b.chars}자 ${b.sec_per_char}s/자 ts=${b.chars_t ? b.chars_t.length : 0} | ${b.text.slice(0, 40)}`);
