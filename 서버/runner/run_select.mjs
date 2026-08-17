// runner 역할: select ① 지시 → do[](ffmpeg) → judge(Google: @inline_file/@file_uri 치환, auth env) → measure(gemini_json_text, 점 경로) → select ② → write_files
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
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
  const r = await fetch(URL_, { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" }, body: JSON.stringify(body) });
  const text = await r.text();
  const ct = r.headers.get("content-type") ?? "";
  const json = ct.includes("text/event-stream") ? JSON.parse(text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).at(-1)) : JSON.parse(text);
  if (json.error) throw new Error(JSON.stringify(json.error));
  return json.result.structuredContent;
}
const key = (env) => process.env[env] || execFileSync("powershell", ["-NoProfile", "-Command", `[Environment]::GetEnvironmentVariable('${env}','User')`], { encoding: "utf8" }).trim();
const setPath = (obj, dotted, val) => { const ks = dotted.split("."); let o = obj; for (let i = 0; i < ks.length - 1; i++) { const k = ks[i]; const nk = ks[i + 1]; if (o[k] === undefined) o[k] = /^\d+$/.test(nk) ? [] : {}; o = o[k]; } o[ks.at(-1)] = val; };

// Files API 업로드 (재개 가능 프로토콜) → file_uri, ACTIVE 대기
async function uploadFile(apiKey, uploadBase, filePath, mime) {
  const bytes = fs.readFileSync(filePath);
  const start = await fetch(uploadBase, { method: "POST", headers: { "x-goog-api-key": apiKey, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": String(bytes.length), "X-Goog-Upload-Header-Content-Type": mime, "Content-Type": "application/json" }, body: JSON.stringify({ file: { display_name: path.basename(filePath) } }) });
  if (!start.ok) throw new Error(`upload start ${start.status}: ${(await start.text()).slice(0, 300)}`);
  const upUrl = start.headers.get("x-goog-upload-url");
  const fin = await fetch(upUrl, { method: "POST", headers: { "Content-Length": String(bytes.length), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize" }, body: bytes });
  if (!fin.ok) throw new Error(`upload finalize ${fin.status}: ${(await fin.text()).slice(0, 300)}`);
  let file = (await fin.json()).file;
  const t0 = Date.now();
  while (file.state !== "ACTIVE") {
    if (file.state === "FAILED") throw new Error("file processing FAILED " + file.name);
    if (Date.now() - t0 > 120000) throw new Error("file ACTIVE 대기 초과 " + file.name);
    await new Promise((r) => setTimeout(r, 2000));
    const g = await fetch(`https://generativelanguage.googleapis.com/v1beta/${file.name}`, { headers: { "x-goog-api-key": apiKey } });
    file = await g.json();
  }
  return { uri: file.uri, mime: file.mimeType ?? mime };
}

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

// jobs — judge (Google)
const visualPayload = {};
for (const job of r1.jobs) {
  const apiKey = key(job.auth.env);
  if (!apiKey) throw new Error(job.auth.env + " 없음");
  const uploadBase = "https://generativelanguage.googleapis.com/upload/v1beta/files";
  const body = JSON.parse(JSON.stringify(job.request.body));
  let nInline = 0, nUri = 0;
  for (const c of body.contents) {
    for (let i = 0; i < c.parts.length; i++) {
      const p = c.parts[i];
      if (p["@inline_file"]) {
        const { path: fp, mime } = p["@inline_file"];
        c.parts[i] = { inline_data: { mime_type: mime, data: fs.readFileSync(fp).toString("base64") } };
        nInline++;
      } else if (p["@file_uri"]) {
        const { path: fp, mime } = p["@file_uri"];
        const up = await uploadFile(apiKey, uploadBase, fp, mime);
        c.parts[i] = { file_data: { mime_type: up.mime, file_uri: up.uri } };
        nUri++;
        console.log(`  uploaded ${path.basename(fp)} → ACTIVE`);
      }
    }
  }
  const t0 = Date.now();
  const hName = job.auth.header.split(":")[0].trim();
  const hVal = job.auth.header.includes("Bearer") ? "Bearer " + apiKey : apiKey;
  const resp = await fetch(job.request.url, { method: job.request.method, headers: { ...job.request.headers, [hName]: hVal }, body: JSON.stringify(body) });
  const rawText = await resp.text();
  fs.mkdirSync(path.dirname(job.out), { recursive: true });
  fs.writeFileSync(job.out, rawText, "utf8");
  console.log(`judge ${job.name} http=${resp.status} ${((Date.now() - t0) / 1000).toFixed(1)}s inline=${nInline} uri=${nUri} → ${path.basename(job.out)}`);
  const raw = JSON.parse(rawText);
  if (raw.error) throw new Error(job.name + " 모델 오류: " + JSON.stringify(raw.error).slice(0, 400));
  const cand = raw.candidates?.[0];
  console.log(`  finishReason=${cand?.finishReason} usage=${JSON.stringify(raw.usageMetadata)}`);
  if (cand?.finishReason !== "STOP") throw new Error("잘림/비정상 finishReason=" + cand?.finishReason);
  const textOut = (cand.content?.parts ?? []).map((p) => p.text ?? "").join("");
  const parsed = JSON.parse(textOut);
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
