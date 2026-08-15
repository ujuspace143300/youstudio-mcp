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
 *   8) tools/call select — ① 지시: do[](프레임·클립) + judge 3콜(Google, @inline_file/@file_uri, auth env 만)
 *      ② 결과: 우선순위 채움 → 시간순·비겹침·크레딧 이전 · 역할 · metrics(최대 미선택 스트레치) · 게이트 · write_files 2개
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
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "voice", preset: "영화롱폼" } });
  const sc = res.structuredContent;
  ok(sc?.status === "not_implemented" && /단계상세/.test(sc?.message ?? ""), "voice → not_implemented 스텁", sc?.message);
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
  ok(m.dropped_hallucination === 2 && m.dropped_hallucination_s === 59.96 && sc?.warnings?.some((w) => /환청 규칙/.test(w) && /The End/.test(w)), "transcript② → 환청 규칙(≥26s·≤3단어) 제거 + 경고, 긴 정상 발화는 유지", JSON.stringify(sc?.warnings?.find((w) => /환청/.test(w))));
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

// 19) tools/call select ① 지시 (payload.visual 없음)
const FACTS = {
  credits_start_s: 854.3,
  ending_visual_only: { start_s: 780.0, end_s: 854.3, note: "대사 없는 시각적 결말" },
  silent_visual_stretches: [{ start_s: 316.4, end_s: 376.4, note: "혼자 서 있음" }, { start_s: 469.6, end_s: 609.6, note: "몽타주" }],
};
const BRIEF_DOC = { events: [
  { n: 1, start: 0, end: 34.8, summary: "친구들과 황당한 대화", importance: 2, spoiler: false },
  { n: 2, start: 76.4, end: 95.5, summary: "낯선 남자 등장, 50달러", importance: 4, spoiler: false },
  { n: 3, start: 110.5, end: 134.8, summary: "네모 칸에 서 있어 달라", importance: 5, spoiler: false },
  { n: 7, start: 95.5, end: 108.0, summary: "짧은 ★4 — 앞 구간에 흡수돼야 함", importance: 4, spoiler: false },
  { n: 4, start: 376.4, end: 408.4, summary: "소매치기 도움 거절", importance: 4, spoiler: false },
  { n: 5, start: 720.7, end: 759.8, summary: "2,000달러·은퇴 선언", importance: 5, spoiler: true },
  { n: 6, start: 870.7, end: 924.2, summary: "엔딩곡", importance: 1, spoiler: true },
] };
const UTT = [[1, 3], [80, 82], [115, 118], [120, 125], [380, 385], [400, 402], [725, 730], [740, 745], [880, 890]];
const CARRY_S = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "C:/youstudio_work/sample/transcript/transcript.json", brief_path: "C:/youstudio_work/sample/brief/brief.json", brief: BRIEF_DOC, facts: FACTS, utterance_spans: UTT };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "select", preset: "영화롱폼", payload: CARRY_S } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "select", "select① → execute, next_step=select(다시 부름)", `${sc?.status}/${sc?.next_step}`);
  const fr = sc?.do?.find((d) => d.name === "frames_silent_0");
  ok(fr?.argv?.[0] === "ffmpeg" && fr.argv.includes("fps=1/5,scale=640:-2") && sc?.do?.filter((d) => d.name.startsWith("clip_ending_")).length === 5, "select① → do[] 무음 구간 프레임(5s 간격) + 결말 클립 5개(15s)", `${fr?.argv?.join(" ").slice(0, 80)} … clips=${sc?.do?.filter((d) => d.name.startsWith("clip_ending_")).length}`);
  const js = sc?.jobs?.find((j) => j.name === "judge_silent_0"), je = sc?.jobs?.find((j) => j.name === "judge_ending");
  ok(sc?.jobs_kind === "judge" && sc?.jobs?.length === 3 && js?.provider === "evolink" && /api\.evolink\.ai\/v1beta\/models\/gemini-3\.5-flash:generateContent/.test(js?.request?.url ?? "") && sc?.plan?.backend === "evolink", "select① → judge job 3개(무음 2 + 결말 1), 기본 evolink gemini-3.5-flash (google 은 규격 스위치)", js?.request?.url);
  ok(js?.auth?.env === "EVOLINK_API_KEY" && /Authorization: Bearer/.test(js?.auth?.header ?? "") && !/AQ\.|sk-L|gsk_i/.test(JSON.stringify(sc)), "select① → auth EVOLINK_API_KEY(Bearer), 응답에 키 값 없음", JSON.stringify(js?.auth?.env));
  const parts0 = js?.request?.body?.contents?.[0]?.parts ?? [], partsE = je?.request?.body?.contents?.[0]?.parts ?? [];
  const nInline = parts0.filter((p) => p["@inline_file"]).length, nClipInline = partsE.filter((p) => p["@inline_file"]).length, nUri = partsE.filter((p) => p["@file_uri"]).length;
  ok(nInline === 12 && js?.media?.count === 12 && /\[t=316\.4s\]/.test(JSON.stringify(parts0)) && nClipInline === 5 && nUri === 0 && je?.media?.kind === "@inline_file", "select① → 프레임 12장 @inline_file(+시각 표시) / 클립 5개도 @inline_file(기본 inline, Files API 는 스위치)", `inline=${nInline} clipInline=${nClipInline} uri=${nUri}`);
  ok(js?.request?.body?.generationConfig?.responseSchema?.properties?.scenes && je?.request?.body?.generationConfig?.responseSchema?.properties?.beats, "select① → responseSchema(scenes / beats)", "");
  ok(sc?.measure?.some((m) => m.as === "visual.silent.0" && m.unit === "gemini_json_text") && sc?.measure?.some((m) => m.as === "visual.ending") && sc?.carry?.includes("facts") && sc?.carry?.includes("brief"), "select① → measure visual.* / carry facts·brief", JSON.stringify(sc?.measure?.map((m) => m.as)));
  ok(sc?.plan?.target_s === 510 && sc?.plan?.budget_s === 586.5 && sc?.plan?.usable_end_s === 854.3, "select① → 목표 510s · 예산 586.5s · 크레딧 이후 제외", JSON.stringify(sc?.plan));
}

// 20) tools/call select ② 결과 (정상)
const VISUAL = {
  silent: [
    { scenes: [{ start: 316.4, end: 346, what: "마이클이 고개를 숙이고 서 있다", people: "마이클", visual_facts: "", importance: 1 }, { start: 346, end: 376.4, what: "광장 와이드, 그대로 서 있음", people: "마이클", visual_facts: "", importance: 1 }] },
    { scenes: [{ start: 469.6, end: 520, what: "정장으로 출근길을 달린다", people: "마이클", visual_facts: "정장", importance: 3 }, { start: 520, end: 609.6, what: "밤 아파트 창·다시 광장", people: "마이클", visual_facts: "밤", importance: 3 }] },
  ],
  ending: { ending_summary: "노인이 된 마이클이 광장을 떠나 스케이트를 타다 넘어진다.", beats: [
    { start: 780, end: 800, what: "노인 마이클이 광장에 서 있다", emotion: "쓸쓸함", importance: 3, is_ending_beat: false },
    { start: 800, end: 836, what: "벤치의 여성에게 다가가 무언가 건넨다", emotion: "따뜻함", importance: 4, is_ending_beat: false },
    { start: 836, end: 843.8, what: "스케이트를 타다 넘어져 쓰러진다, 블랙", emotion: "충격", importance: 5, is_ending_beat: true },
    { start: 843.8, end: 854.3, what: "스케이트 타는 뒷모습", emotion: "여운", importance: 2, is_ending_beat: false },
  ] },
};
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "select", preset: "영화롱폼", payload: { ...CARRY_S, visual: VISUAL } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "script", "select② → execute, next_step=script", `${sc?.status}/${sc?.next_step} ${sc?.message ?? ""}`);
  const segs = sc?.write_files?.find((w) => /selection\.json$/.test(w.path))?.content?.segments ?? [];
  const sorted = segs.every((s, i) => i === 0 || s.in >= segs[i - 1].out);
  ok(segs.length > 0 && sorted && segs.every((s) => s.out <= 854.3), "select② → 구간 시간순·비겹침·크레딧 이전", JSON.stringify(segs.map((s) => [s.in, s.out, s.role])));
  const ending = segs.filter((s) => s.kind === "ending");
  ok(ending.length === 1 && ending[0].in === 780 && ending[0].out === 854.3 && /통째/.test(ending[0].src.join(",")), "select② → 결말 통째(780~854.3, END 비트 포함) 한 구간", JSON.stringify(ending.map((s) => [s.in, s.out, s.src])));
  const absorbed = segs.find((s) => s.src.includes("brief#7"));
  ok(absorbed && absorbed.src.includes("brief#2") && absorbed.out >= 108 && (sc?.metrics?.absorbed_candidates ?? 0) >= 1, "select② → 창 최소보다 짧은 ★4 후보를 인접 구간에 흡수", JSON.stringify(absorbed && [absorbed.in, absorbed.out, absorbed.src]));
  const br = sc?.write_files?.find((w) => /selection\.json$/.test(w.path))?.content?.narration_bridges ?? [];
  ok(br.length >= 1 && br.every((b) => b.len_s >= 20 && b.end <= 854.3) && br.some((b) => b.start === 134.8 && b.end === 316.4), "select② → 나레이션 브리지 후보(≥20s 미선택 구간, 크레딧 제외)", JSON.stringify(br.map((b) => [b.start, b.end, b.events.map((e) => e.n)])));
  const roles = Object.fromEntries(segs.map((s) => [s.src.join(","), s.role]));
  ok(roles["brief#3"] === "원본대사" && roles["brief#1"] === "나레이션덮기" && segs.some((s) => s.role === "시각몽타주"), "select② → 역할(≥4 원본대사 / ≤3 나레이션덮기 / 무음 시각몽타주)", JSON.stringify(roles));
  const m = sc?.metrics ?? {};
  ok(m.count === segs.length && m.total_s <= 586.5 && typeof m.max_unselected_stretch?.len === "number" && m.max_unselected_stretch.end <= 854.3 && typeof m.blocks_per_min_proxy === "number", "select② → metrics(구간 수·총 길이≤예산·최대 미선택 스트레치·분당 블록 대용치)", JSON.stringify(m));
  ok(segs.every((s) => s.out - s.in >= 20 - 0.01), "select② → 창 최소 20s 충족", JSON.stringify(segs.map((s) => s.len_s)));
  const g16 = sc?.gates?.find((g) => /G16/.test(g.id));
  ok(g16?.hard === true && g16?.pass === true && sc?.gates?.some((g) => /G25/.test(g.id) && g.hard === false) && !sc?.gates?.some((g) => /G13|G63/.test(g.id)), "select② → 게이트 G-반복(G16) hard 통과 · G-밀도 soft · G13/G63 은 select 게이트 아님", JSON.stringify(sc?.gates?.map((g) => [g.id, g.pass])));
  ok(sc?.write_files?.length === 2 && sc?.carry?.includes("selection_path"), "select② → write_files visual.json+selection.json / carry selection_path", sc?.selection_path);
}

// 21) select ② 무음 판정 부족 → hard_fail
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "select", preset: "영화롱폼", payload: { ...CARRY_S, visual: { silent: [VISUAL.silent[0]], ending: VISUAL.ending } } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /무음 구간 판정 결과가 부족/.test(sc?.message ?? ""), "select②(무음 판정 부족) → hard_fail + 수리 지침", (sc?.message ?? "").slice(0, 80));
}

// 22) select (brief 누락) → 반려
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "select", preset: "영화롱폼", payload: { ...CARRY, probe_summary: PROBE_SUMMARY } } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /payload\.brief/.test(sc?.message ?? ""), "select(brief 없음) → 반려 + 고치는 법", (sc?.message ?? "").slice(0, 80));
}

// 23) tools/call script ① need_input (payload.script 없음)
const SEL = { segments: [
  { i: 1, in: 0, out: 26.3, len_s: 26.3, role: "나레이션덮기", importance: 2, kind: "dialogue", src: ["brief#1"], why: "친구들과 황당한 대화" },
  { i: 2, in: 75.9, out: 135, len_s: 59.1, role: "원본대사", importance: 4, kind: "dialogue", src: ["brief#3"], why: "낯선 남자, 50달러 · 네모 칸" },
  { i: 3, in: 780, out: 854.3, len_s: 74.3, role: "시각몽타주", importance: 5, kind: "ending", src: ["visual:ending(통째)"], why: "노인 마이클이 스케이트를 타다 넘어진다" },
], narration_bridges: [ { start: 26.3, end: 75.9, len_s: 49.6, events: [{ n: 2, summary: "친구들의 놀림", importance: 2 }] } ] };
const CARRY_SC = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "C:/youstudio_work/sample/transcript/transcript.json", brief_path: "C:/youstudio_work/sample/brief/brief.json", selection_path: "C:/youstudio_work/sample/clips/selection.json", selection: SEL, visual: { silent: [], ending: { ending_summary: "넘어지지만 다시 일어선다", beats: [] } }, facts: { visual_facts: [{ t_s: 737.4, fact: "마이클이 노인이 되어 있음" }] }, brief: { logline: "네모 칸에 서 있는 일", events: [] }, utterance_spans: [[80, 90], [92, 100], [102, 110], [112, 120], [122, 130]] };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: CARRY_SC } });
  const sc = res.structuredContent;
  ok(sc?.status === "need_input" && sc?.next_step === "script" && sc?.need_input?.keys?.includes("script"), "script① → status=need_input(script), 서버 멈춤", `${sc?.status}/${sc?.next_step}`);
  ok(typeof sc?.guide === "string" && /지무비체를 그대로 채택/.test(sc.guide) && /## 4\. 블록 모양/.test(sc.guide), "script① → guide = 나레이션.md 전문(텍스트 import)", (sc?.guide ?? "").slice(0, 40));
  ok(Array.isArray(sc?.rules?.금지표현) && sc.rules.금지표현.length === 7 && sc?.answer_bands?.["G-턴비_나레대사_시간비"]?.min === 0.55, "script① → rules(규격 나레이션)·answer_bands(정답지 대본) 동봉", "");
  ok(sc?.material?.segments?.length === 3 && sc?.material?.bridges?.length === 1 && sc?.material?.visual_facts?.length === 1 && sc?.material?.ending?.summary, "script① → material(구간·브리지·시각 사실·결말)", "");
  ok(sc?.carry?.includes("selection") && sc?.carry?.includes("utterance_spans") && sc?.jobs?.length === 0, "script① → carry 에 재료 포함, jobs 없음", JSON.stringify(sc?.carry));
}

// 24) script ② 불통 — 금지 표현·평서체·마침표·..?·레지스터·상한 초과
{
  const bad = { blocks: [
    { pos: { kind: "over", seg: 1 }, text: "여러분은 알고 계셨나요 이 남자의 하루를", intent: "x" },
    { pos: { kind: "over", seg: 1 }, text: "마이클은 친구들과 시답잖은 농담을 주고받는다", intent: "평서체" },
    { pos: { kind: "bridge", bridge: 0 }, text: "하지만 친구들은 웃기만 했죠.", intent: "레지스터+마침표" },
    { pos: { kind: "before", seg: 2 }, text: "이 남자는 누구일까요..?", intent: "..?" },
    { pos: { kind: "over", seg: 3 }, text: "네모 칸에서 시작된 그의 하루는 어느새 평생이 되어 버렸고 머리는 하얗게 세어 버렸으며 광장은 그대로였습니다", intent: "40자 초과" },
  ] };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: { ...CARRY_SC, script: bad } } });
  const sc = res.structuredContent;
  const m = sc?.message ?? "";
  ok(res.isError === true && sc?.status === "error" && /블록 1: 금지 표현/.test(m) && /블록 2: 평서체/.test(m) && /블록 3: (쉼표|마침표|나레 레지스터)/.test(m) && /블록 4: `\.\.\?`/.test(m) && /블록 5: \d+자 > 문장 상한 40자/.test(m), "script②(불통) → 어느 블록이 왜인지 + 수리 지침", m.slice(0, 160));
}

// 25) script ② 통과 — 지무비체 블록 (G-턴비 대역 안)
{
  const good = { blocks: [
    { pos: { kind: "over", seg: 1 }, text: "계단 앞에서 시답잖은 농담이나 주고받던.. 청년 하나가 있었습니다", intent: "훅 — 익명 인물" },
    { pos: { kind: "bridge", bridge: 0 }, text: "친구들의 놀림은 이어졌고.. 그날도 그런 하루로 끝날 것 같았죠", intent: "이음" },
    { pos: { kind: "before", seg: 2 }, text: "허나 그때.. 정장 차림의 남자가 다가옵니다", intent: "표지어" },
    { pos: { kind: "over", seg: 3 }, text: "네모 칸에서 시작한 하루가.. 어느새 평생이 되어 있었죠", intent: "시각 사실 — 노화" },
    { pos: { kind: "over", seg: 3 }, text: "그렇게 그는.. 처음으로 선 밖으로 나섰습니다..!", intent: "닫기" },
  ] };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: { ...CARRY_SC, script: good } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "voice", "script②(통과) → execute, next_step=voice", `${sc?.status}/${sc?.next_step} ${sc?.message ?? ""}`);
  const m = sc?.metrics ?? {};
  ok(m.block_count === 5 && m.avg_chars > 0 && m.dialogue_s === 42 && typeof m.nar_share_est === "number" && typeof m.nar_dialogue_ratio_est === "number" && /추정/.test(m.note ?? ""), "script② → metrics(블록 수·평균 자수·나레 시간점유·나레:대사 추정 비율, 추정 표시)", JSON.stringify(m));
  const wf = sc?.write_files?.[0];
  ok(wf?.path === "C:/youstudio_work/sample/script/script.json" && wf?.content?.blocks?.length === 5 && wf.content.blocks[0].pieces === 2, "script② → write_files script.json(블록·조각 수)", wf?.path);
  ok(sc?.gates?.some((g) => /나레 시간점유/.test(g.id) && g.hard === true && g.pass === true) && sc?.gates?.some((g) => /G-턴비/.test(g.id) && g.hard === false) && sc?.carry?.includes("script_path"), "script② → 나레 시간점유(G27) hard 통과 · G-턴비 soft · carry script_path", JSON.stringify(sc?.gates?.map((g) => [g.id, g.pass])));
}

// 26) script ② G-턴비 불통 (나레 과다) → 수리 지침
{
  const heavy = { blocks: Array.from({ length: 12 }, (_, i) => ({ pos: { kind: "over", seg: 3 }, text: `노인이 된 마이클이 광장을 떠나.. 보드를 타다 넘어집니다 ${i}`, intent: "x" })) };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: { ...CARRY_SC, script: heavy } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /나레 시간점유/.test(sc?.message ?? "") && /나레 과다/.test(sc?.message ?? "") && /자\)를 덜어내라/.test(sc?.message ?? ""), "script②(나레 시간점유 과다) → 반려 + 수리 지침(몇 초·몇 자를 어떻게)", (sc?.message ?? "").slice(0, 160));
}

console.log(process.exitCode ? "\n실패 있음" : "\n전부 통과");
