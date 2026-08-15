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
 *   6) tools/call transcript — ① 지시: do[](ffmpeg 추출·크기) + transcribe job(Groq, auth 는 env 이름만)
 *      ② 결과: 발화 정리 → write_files transcript.json · metrics · next_step=brief · 발화 0건 hard_fail
 *   7) tools/call brief — ① 지시: judge job(EvoLink, inputs 파일 치환, auth env 만) ② 결과: 사건 검사·정렬·
 *      write_files brief.json · metrics(사건 수·평균·커버리지) · 0건 hard_fail · 범위 밖 반려
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

// 10) tools/call transcript ① 지시 (payload.asr 없음)
const PROBE_SUMMARY = { duration_s: 929.077, width: 1920, height: 1080, fps: 23.976, audio: true, audio_tracks: 1 };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "transcript", preset: "영화롱폼", payload: { ...CARRY, probe_summary: PROBE_SUMMARY } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "transcript", "transcript① → execute, next_step=transcript(다시 부름)", `${sc?.status}/${sc?.next_step}`);
  const ex = sc?.do?.find((d) => d.name === "extract_audio");
  ok(ex?.argv?.[0] === "ffmpeg" && ex.argv.includes("16000") && ex.argv.includes("-ac") && ex.argv.at(-1) === "C:/youstudio_work/sample/transcript/audio.mp3", "transcript① → do[] ffmpeg 오디오 추출(16kHz 모노 mp3)", ex?.argv?.join(" "));
  ok(sc?.do?.some((d) => d.name === "audio_size" && d.argv[0] === "ffprobe"), "transcript① → do[] audio_size(ffprobe)", "");
  const j = sc?.jobs?.[0];
  ok(sc?.jobs_kind === "transcribe" && j?.provider === "groq" && j?.model === "whisper-large-v3-turbo" && j?.request?.multipart?.response_format === "verbose_json" && j?.request?.multipart?.language === "en", "transcript① → transcribe job(Groq whisper-large-v3-turbo, verbose_json, lang)", JSON.stringify(j?.request?.multipart));
  ok(j?.auth?.env === "GROQ_API_KEY" && !/gsk_/.test(JSON.stringify(sc)), "transcript① → auth 는 env 이름만, 응답에 키 값 없음", JSON.stringify(j?.auth));
  ok(sc?.measure?.some((m) => m.as === "asr" && m.from === "job:groq_asr") && sc?.carry?.includes("probe_summary"), "transcript① → measure asr / carry", JSON.stringify(sc?.measure));
  ok(sc?.instructions?.some((l) => /25MB/.test(l) && /분할 전사는 미정/.test(l)), "transcript① → 지시문에 파일 상한·분할 전사 미정", "");
}

// 11) tools/call transcript ② 결과 (정상)
const ASR_OK = {
  language: "English", duration: 929.08, text: "hello world",
  segments: [
    { id: 0, start: 1.0, end: 3.5, text: " Hello.", no_speech_prob: 0.01 },
    { id: 1, start: 4.0, end: 4.0, text: " (empty span)", no_speech_prob: 0.5 },
    { id: 2, start: 10.25, end: 12.75, text: "  ", no_speech_prob: 0.9 },
    { id: 3, start: 900.0, end: 905.0, text: " Bye.", no_speech_prob: 0.02 },
    { id: 4, start: 928.0, end: 935.0, text: " See you tomorrow at the office.", no_speech_prob: 0.02 },
    { id: 5, start: 940.0, end: 960.0, text: " Thanks for watching.", no_speech_prob: 0.02 },
    { id: 6, start: 316.37, end: 346.35, text: " Thank you.", no_speech_prob: 0.0 },
    { id: 7, start: 346.37, end: 376.35, text: " The End", no_speech_prob: 0.0 },
    { id: 8, start: 500.0, end: 526.0, text: " No way this is a real sentence with words.", no_speech_prob: 0.0 },
  ],
};
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "transcript", preset: "영화롱폼", payload: { ...CARRY, probe_summary: PROBE_SUMMARY, asr: ASR_OK, audio_bytes: { format: { size: "5600000", duration: "929.08" } } } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "brief", "transcript② → execute, next_step=brief", `${sc?.status}/${sc?.next_step}`);
  const m = sc?.metrics ?? {};
  ok(m.utterance_count === 4 && m.speech_s === 34.577 && m.silence_ratio === 0.963 && m.audio_bytes === 5600000, "transcript② → metrics(발화 수·발화 길이·무음 비율)", JSON.stringify(m));
  ok(m.dropped_hallucination === 2 && m.dropped_hallucination_s === 59.96 && sc?.warnings?.some((w) => /환청 규칙/.test(w) && /The End/.test(w)), "transcript② → 환청 규칙(≥25s·≤3단어) 제거 + 경고, 긴 정상 발화는 유지", JSON.stringify(sc?.warnings?.find((w) => /환청/.test(w))));
  ok(m.dropped_after_end === 1 && sc?.warnings?.some((w) => /이후에 시작하는 발화 1건을 제거/.test(w)) && sc?.write_files?.[0]?.content?.warnings?.length >= 1, "transcript② → 영상 길이 이후 시작 발화 제거 + 경고(transcript.json 에도 기록)", JSON.stringify(sc?.warnings?.[0]));
  const wf = sc?.write_files?.[0];
  ok(wf?.path === "C:/youstudio_work/sample/transcript/transcript.json" && wf?.content?.utterances?.length === 4 && wf.content.utterances[0].text === "Hello.", "transcript② → write_files transcript.json(빈 발화 제거)", JSON.stringify(wf?.content?.utterances));
  ok(wf?.content?.utterances?.[2]?.end === 929.077 && sc?.warnings?.some((w) => /잘랐다/.test(w)), "transcript② → 원본 길이 넘는 끝 타임코드 클램프 + 경고", JSON.stringify(sc?.warnings));
  ok(!sc?.warnings?.some((w) => /감지 언어/.test(w)), "transcript② → 언어 이름(English) vs 코드(en) 오경보 없음", JSON.stringify(sc?.warnings));
  ok(sc?.carry?.includes("transcript_path") && sc?.transcript_path === wf?.path, "transcript② → carry transcript_path", sc?.transcript_path);
}

// 12) tools/call transcript ② 발화 0건 → hard_fail
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "transcript", preset: "영화롱폼", payload: { ...CARRY, probe_summary: PROBE_SUMMARY, asr: { language: "en", segments: [] } } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /hard_fail/.test(sc?.message ?? "") && /source\.lang/.test(sc?.message ?? ""), "transcript②(발화 0건) → hard_fail + 수리 지침", (sc?.message ?? "").slice(0, 60));
}

// 13) tools/call transcript (carry 누락 → 반려)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "transcript", preset: "영화롱폼", payload: { workdir: "C:/x" } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /probe_summary/.test(sc?.message ?? ""), "transcript(carry 없음) → 반려 + 고치는 법", sc?.message);
}

// 14) tools/call brief ① 지시 (payload.brief 없음)
const CARRY_T = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "C:/youstudio_work/sample/transcript/transcript.json" };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "brief", preset: "영화롱폼", payload: CARRY_T } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "brief", "brief① → execute, next_step=brief(다시 부름)", `${sc?.status}/${sc?.next_step}`);
  const j = sc?.jobs?.[0];
  ok(sc?.jobs_kind === "judge" && j?.provider === "evolink" && j?.model === "gemini-3.5-flash" && j?.request?.url === "https://api.evolink.ai/v1beta/models/gemini-3.5-flash:generateContent", "brief① → judge job(EvoLink gemini-3.5-flash, v1beta URL)", j?.request?.url);
  const gc = j?.request?.body?.generationConfig;
  ok(gc?.responseMimeType === "application/json" && gc?.thinkingConfig?.thinkingBudget === 0 && gc?.maxOutputTokens === 8192, "brief① → 바디 generationConfig(JSON 강제·thinkingBudget 0·maxOutputTokens)", JSON.stringify({ ...gc, responseSchema: "…" }));
  ok(gc?.responseSchema?.properties?.events?.items?.required?.includes("summary"), "brief① → responseSchema 로 키 고정(summary·start·end·importance)", JSON.stringify(gc?.responseSchema?.properties?.events?.items?.required));
  const txt = j?.request?.body?.contents?.[0]?.parts?.[0]?.text ?? "";
  ok(/\{\{TRANSCRIPT_JSON\}\}/.test(txt) && j?.inputs?.[0]?.placeholder === "{{TRANSCRIPT_JSON}}" && j?.inputs?.[0]?.path === CARRY_T.transcript_path, "brief① → 전사는 inputs 파일 치환(본문 미동봉)", JSON.stringify(j?.inputs));
  ok(/929\.077/.test(txt) && /23개 내외/.test(txt) && /한국어/.test(txt), "brief① → 프롬프트에 원본 길이·사건 수 목표(929s/40s→23)·한국어 요약", "");
  ok(j?.auth?.env === "EVOLINK_API_KEY" && !/sk-/.test(JSON.stringify(sc)), "brief① → auth 는 env 이름만, 응답에 키 값 없음", JSON.stringify(j?.auth));
  ok(sc?.measure?.[0]?.as === "brief" && sc?.measure?.[0]?.unit === "gemini_json_text" && j?.out === "C:/youstudio_work/sample/brief/brief_raw.json", "brief① → measure gemini_json_text / out brief_raw.json", JSON.stringify(sc?.measure));
}

// 15) tools/call brief ② 결과 (정상 — 정렬·클램프·커버리지)
const BRIEF_OK = {
  logline: "두 친구가 돈 때문에 이상한 알바를 고민한다",
  events: [
    { n: 2, start: 100, end: 300.5, summary: "둘째 사건", importance: 4, spoiler: false },
    { n: 1, start: 0, end: 100, summary: "첫째 사건", importance: 2, spoiler: false },
    { n: 3, start: 600, end: 929.6, summary: "마지막 사건", importance: 5, spoiler: true },
  ],
};
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "brief", preset: "영화롱폼", payload: { ...CARRY_T, brief: BRIEF_OK } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "select", "brief② → execute, next_step=select", `${sc?.status}/${sc?.next_step}`);
  const m = sc?.metrics ?? {};
  ok(m.event_count === 3 && m.avg_event_len_s === 209.859 && m.coverage === 0.678 && m.max_gap_s === 299.5, "brief② → metrics(사건 수·평균 길이·커버리지·빈틈)", JSON.stringify(m));
  const wf = sc?.write_files?.[0];
  const ev = wf?.content?.events ?? [];
  ok(wf?.path === "C:/youstudio_work/sample/brief/brief.json" && ev.length === 3 && ev[0].n === 1 && ev[0].start === 0 && ev[2].end === 929.077, "brief② → write_files brief.json(시간순 재번호·끝 클램프)", JSON.stringify(ev.map((e) => [e.n, e.start, e.end])));
  ok(sc?.carry?.includes("brief_path") && sc?.brief_path === wf?.path && sc?.warnings?.some((w) => /커버리지/.test(w)), "brief② → carry brief_path + 커버리지 경고", JSON.stringify(sc?.warnings));
}

// 16) tools/call brief ② 사건 0건 → hard_fail
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "brief", preset: "영화롱폼", payload: { ...CARRY_T, brief: { logline: "", events: [] } } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /hard_fail/.test(sc?.message ?? "") && /brief_raw\.json/.test(sc?.message ?? ""), "brief②(사건 0건) → hard_fail + 수리 지침", (sc?.message ?? "").slice(0, 60));
}

// 17) tools/call brief ② 타임코드 범위 밖 → 반려
{
  const badBrief = { logline: "x", events: [{ n: 1, start: 0, end: 50, summary: "a", importance: 3 }, { n: 2, start: 900, end: 1200, summary: "b", importance: 9 }] };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "brief", preset: "영화롱폼", payload: { ...CARRY_T, brief: badBrief } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /end 1200 > 원본 길이/.test(sc?.message ?? "") && /importance 9/.test(sc?.message ?? "") && /한 번 더 보내라/.test(sc?.message ?? ""), "brief②(범위 밖) → 반려 + 수리 지침(어느 사건이 왜)", (sc?.message ?? "").slice(0, 120));
}

// 18) tools/call brief (carry 누락 → 반려)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "brief", preset: "영화롱폼", payload: { ...CARRY, probe_summary: PROBE_SUMMARY } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /transcript_path/.test(sc?.message ?? ""), "brief(carry 없음) → 반려 + 고치는 법", sc?.message);
}

console.log(process.exitCode ? "\n실패 있음" : "\n전부 통과");
