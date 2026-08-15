/**
 * test/smoke.mjs — 서버가 살아 있고 MCP 로 말이 통하는지 보는 최소 검사.
 *
 * 전제: 다른 창에서 `npx wrangler dev` 가 떠 있다 (기본 http://localhost:8787).
 * 실행: node test/smoke.mjs            (또는 npm test)
 *       MCP_URL=http://localhost:8788 node test/smoke.mjs   ← 포트가 다르면
 *
 * 검사 4개:
 *   1) initialize      — 서버 이름·지시문이 온다
 *   2) tools/list      — youstudio_video 하나가 있다
 *   3) tools/call setup — 규격(spec)이 실려 오고 next_step=start
 *   4) tools/call start — ffprobe argv 가 조립돼 오고 next_step=probe
 *   5) tools/call probe — 정상 JSON 이면 metrics·carry 가 오고 next_step=transcript
 *      오디오 없는 JSON 이면 hard_fail(status error) + 수리 지침 · payload 없으면 반려
 */
const URL_ = process.env.MCP_URL ?? "http://localhost:8787";
const PROTOCOL = "2025-11-25"; // 2025 세대(stateless) 로 붙는다 — 서버가 legacy 폴백으로 받는다

let id = 0;
async function rpc(method, params) {
  const body = { jsonrpc: "2.0", id: ++id, method, params };
  const r = await fetch(URL_, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      "mcp-protocol-version": PROTOCOL,
    },
    body: JSON.stringify(body),
  });
  const ct = r.headers.get("content-type") ?? "";
  const text = await r.text();
  if (!r.ok) throw new Error(`${method}: HTTP ${r.status} ${ct}\n${text.slice(0, 500)}`);
  // 응답이 SSE(event-stream)면 data: 줄만 모아 마지막 JSON 을 쓴다
  let json;
  if (ct.includes("text/event-stream")) {
    const datas = text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim());
    json = JSON.parse(datas.at(-1));
  } else {
    json = JSON.parse(text);
  }
  if (json.error) throw new Error(`${method}: ${JSON.stringify(json.error)}`);
  return json.result;
}

function ok(cond, label, extra = "") {
  if (!cond) {
    console.error(`  ✗ ${label} ${extra}`);
    process.exitCode = 1;
  } else {
    console.log(`  ✓ ${label} ${extra}`);
  }
}

console.log(`서버: ${URL_}`);

// 0) health
{
  const r = await fetch(URL_ + "/health").then((x) => x.json()).catch((e) => ({ error: String(e) }));
  ok(r.ok === true, "/health 응답", JSON.stringify(r));
}

// 1) initialize
{
  const res = await rpc("initialize", {
    protocolVersion: PROTOCOL,
    capabilities: {},
    clientInfo: { name: "smoke", version: "0" },
  });
  ok(res.serverInfo?.name === "youstudio-mcp", "initialize → serverInfo.name", res.serverInfo?.name);
  ok(typeof res.instructions === "string" && res.instructions.includes("그대로 실행"), "initialize → instructions", JSON.stringify(res.instructions));
}

// 2) tools/list
{
  const res = await rpc("tools/list", {});
  const names = (res.tools ?? []).map((t) => t.name);
  ok(names.length === 1 && names[0] === "youstudio_video", "tools/list → youstudio_video 하나", JSON.stringify(names));
  const stepEnum = res.tools?.[0]?.inputSchema?.properties?.step?.enum;
  ok(Array.isArray(stepEnum) && stepEnum[0] === "setup" && stepEnum.at(-1) === "export", "step enum 10개", JSON.stringify(stepEnum));
}

// 3) tools/call setup
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "setup", preset: "영화롱폼" } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "start", "setup → status=execute, next_step=start", `${sc?.status}/${sc?.next_step}`);
  ok(sc?.jobs_kind === "argv" && sc?.jobs?.length === 2, "setup → ffmpeg/ffprobe 확인 argv 2개", JSON.stringify(sc?.jobs?.map((j) => j.argv.join(" "))));
  ok(sc?.spec && typeof sc.spec === "object" && "_안내" in sc.spec, "setup → spec(규격.json) 실려 옴", Object.keys(sc?.spec ?? {}).join(","));
  ok(Array.isArray(sc?.workdir_layout?.dirs) && sc.workdir_layout.dirs.includes("render"), "setup → 작업 폴더 이름 목록", JSON.stringify(sc?.workdir_layout?.dirs));
}

// 4) tools/call start (정상)
{
  const res = await rpc("tools/call", {
    name: "youstudio_video",
    arguments: {
      step: "start",
      preset: "영화롱폼",
      source: { kind: "local_video", path: "C:/movies/sample.mp4", title: "샘플 (2024)", lang: "en" },
      payload: { workdir: "C:/youstudio_work/sample" },
    },
  });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "probe", "start → next_step=probe", `${sc?.status}/${sc?.next_step}`);
  const j = sc?.jobs?.[0];
  ok(sc?.jobs_kind === "argv" && j?.argv?.[0] === "ffprobe" && j.argv.at(-1) === "C:/movies/sample.mp4", "start → ffprobe argv 조립", j?.argv?.join(" "));
  ok(j?.out === "C:/youstudio_work/sample/probe/probe.json", "start → out 경로 = <workdir>/probe/probe.json", j?.out);
  ok(sc?.measure?.[0]?.as === "probe" && sc?.carry?.includes("workdir"), "start → measure/carry", JSON.stringify({ measure: sc?.measure, carry: sc?.carry }));
}

// 5) tools/call start (source 누락 → 고치는 법이 담긴 반려)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "start", preset: "영화롱폼" } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /다시 부르라/.test(sc?.message ?? ""), "start(source 없음) → 반려 + 고치는 법", sc?.message);
}

// 6) 미구현 단계
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "select", preset: "영화롱폼" } });
  const sc = res.structuredContent;
  ok(sc?.status === "not_implemented" && /단계상세/.test(sc?.message ?? ""), "select → not_implemented 스텁", sc?.message);
}

// 7) tools/call probe (정상 — Full Time 실측과 같은 모양의 ffprobe JSON)
const PROBE_OK = {
  streams: [
    { index: 0, codec_type: "video", codec_name: "h264", width: 1920, height: 1080, r_frame_rate: "24000/1001", avg_frame_rate: "24000/1001", duration: "929.011417" },
    { index: 1, codec_type: "audio", codec_name: "aac", channels: 2, sample_rate: "44100", channel_layout: "stereo", duration: "929.076825", tags: { language: "eng" } },
  ],
  format: { filename: "C:/movies/sample.mp4", nb_streams: 2, duration: "929.076825", size: "256735178", bit_rate: "2210669" },
};
const CARRY = { workdir: "C:/youstudio_work/sample", source: { kind: "local_video", path: "C:/movies/sample.mp4", title: "샘플 (2024)", lang: "en" } };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "probe", preset: "영화롱폼", payload: { ...CARRY, probe: PROBE_OK } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "transcript", "probe → status=execute, next_step=transcript", `${sc?.status}/${sc?.next_step}`);
  const m = sc?.metrics ?? {};
  ok(m.duration_s === 929.077 && m.width === 1920 && m.height === 1080 && m.fps === 23.976 && m.audio === true, "probe → metrics(길이·해상도·fps·오디오)", JSON.stringify(m));
  ok(sc?.jobs_kind === null && sc?.jobs?.length === 0 && sc?.measure?.length === 0, "probe → jobs 없음 (argv 는 start 가 실행)", `${sc?.jobs_kind}/${sc?.jobs?.length}/${sc?.measure?.length}`);
  ok(["source", "workdir", "probe_summary"].every((k) => sc?.carry?.includes(k) && k in sc), "probe → carry(source·workdir·probe_summary) 값 동봉", JSON.stringify(sc?.carry));
  ok(sc?.probe_summary?.audio_tracks === 1 && sc?.probe_summary?.fps_fraction === "24000/1001", "probe → probe_summary 요약", JSON.stringify(sc?.probe_summary));
  ok(sc?.instructions?.some((l) => /ASR 제공자 결정 대기/.test(l)), "probe → 지시문에 'ASR 제공자 결정 대기'", "");
}

// 8) tools/call probe (오디오 트랙 없음 → hard_fail = status error + 수리 지침)
{
  const noAudio = { ...PROBE_OK, streams: PROBE_OK.streams.filter((s) => s.codec_type !== "audio") };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "probe", preset: "영화롱폼", payload: { ...CARRY, probe: noAudio } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && sc?.next_step === "probe", "probe(오디오 없음) → hard_fail(status error), next_step 유지", `${sc?.status}/${sc?.next_step}`);
  ok(/hard_fail/.test(sc?.message ?? "") && /ffmpeg -i/.test(sc?.message ?? ""), "probe(오디오 없음) → 수리 지침 포함", (sc?.message ?? "").slice(0, 80));
}

// 9) tools/call probe (payload.probe 누락 → 반려 + 고치는 법)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "probe", preset: "영화롱폼", payload: { ...CARRY } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /probe\.json/.test(sc?.message ?? ""), "probe(probe 없음) → 반려 + 고치는 법", sc?.message);
}

console.log(process.exitCode ? "\n실패 있음" : "\n전부 통과");
