const TR_KO = ["야 마이크 너네 삼촌 발 전문의지", "둘째 줄", "어 그런 생각 해본 적도 없는데", "넷째 줄", "다섯째 줄", "여섯째 줄", "저요?", "여덟째 줄", "잠깐 뭐 좀 도와줄 수 있어요?", "열째 줄", "50달러 드릴게요", "열두째 줄", "열셋째 줄"];
let TR = [];   // subtitle① 응답의 대사줄(시각 기반 id + 영어)로 만든다
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
      // 배포본 검사: YOUSTUDIO_TOKEN=... MCP_URL=https://... npm test
      ...(process.env.YOUSTUDIO_TOKEN ? { authorization: `Bearer ${process.env.YOUSTUDIO_TOKEN}` } : {}),
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
  // 단계 enum = 모든 프리셋 단계의 합집합 (영화롱폼 10 + 스케치코미디 sk_* 9 + 린박스 lb_* 13 = 32)
  ok(
    Array.isArray(stepEnum) && stepEnum[0] === "setup" && stepEnum.includes("export") && stepEnum.includes("sk_deliver") && stepEnum.at(-1) === "lb_deliver" && stepEnum.length === 32,
    "step enum 32개(프리셋 합집합)",
    JSON.stringify(stepEnum),
  );
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

// 3b) tools/call setup — 린박스 (프리셋 3호 등록 확인 · 2026-09-04)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "setup", preset: "린박스" } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "start", "린박스 setup → execute, next_step=start", `${sc?.status}/${sc?.next_step}`);
  ok(typeof sc?.spec?._from === "string" && sc.spec._from.startsWith("스타일/린박스/") && sc?.spec?.layout?.video_box?.h === 1020, "린박스 setup → 린박스 규격이 실려 옴(영상창 1020)", `${sc?.spec?._from} / ${sc?.spec?.layout?.video_box?.h}`);
  ok(JSON.stringify(sc?.workdir_layout?.dirs) === JSON.stringify(["소재", "작업", "완성"]), "린박스 setup → 작업 폴더 소재/작업/완성", JSON.stringify(sc?.workdir_layout?.dirs));
  const r2 = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "lb_blocks", preset: "린박스" } });
  ok(r2.structuredContent?.status === "not_implemented" || /구현/.test(JSON.stringify(r2)), "린박스 lb_blocks → 아직 stub(구현 안 됨)", JSON.stringify(r2.structuredContent?.status ?? r2).slice(0, 80));
  const r3 = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "sk_plan", preset: "린박스" } });
  ok(/error|반려|isError/.test(JSON.stringify(r3)) || r3.isError, "린박스에 없는 단계(sk_plan) → 반려", JSON.stringify(r3).slice(0, 80));
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
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼" } });
  const sc = res.structuredContent;
  ok(res.isError === true && sc?.status === "error" && /timeline/.test(sc?.message ?? ""), "export(빈 payload) → 반려 + 고치는 법 (스텁 없음 — 10단계 전부 구현)", (sc?.message ?? "").slice(0, 80));
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
  ok(sc?.jobs_kind === "transcribe" && j?.provider === "speechmatics" && String(j?.request?.multipart?.data_file ?? "").startsWith("@") && /"language":"en"/.test(String(j?.request?.multipart?.config ?? "")) && j?.batch?.transcript_url?.includes("format=json-v2") && j?.batch?.poll_s > 0, "transcript① → transcribe job(Speechmatics batch v2, 단어 시각, lang)", JSON.stringify(j?.request?.multipart));
  ok(j?.auth?.env === "SPEECHMATICS_API_KEY" && !/gsk_/.test(JSON.stringify(sc)), "transcript① → auth 는 env 이름만, 응답에 키 값 없음", JSON.stringify(j?.auth));
  ok(sc?.measure?.some((m) => m.as === "asr" && m.from === "job:asr") && sc?.carry?.includes("probe_summary"), "transcript① → measure asr / carry", JSON.stringify(sc?.measure));
  ok(sc?.instructions?.some((l) => /25MB/.test(l) && /분할 전사는 미정/.test(l)), "transcript① → 지시문에 파일 상한·분할 전사 미정", "");
  ok(sc?.do?.some((d) => d.name === "silence_scan" && d.argv.some((a) => /silencedetect=noise=-24dB:d=0\.4/.test(a))) && sc?.measure?.some((m) => m.as === "silences_raw" && m.unit === "stderr"), "transcript① → do[] silence_scan(무음 실측) · measure stderr", "");
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
  const SIL_RAW = ["[silencedetect @ 0x1] silence_start: 512.3", "[silencedetect @ 0x1] silence_end: 526.5 | silence_duration: 14.2", "[silencedetect @ 0x1] silence_start: 902.0", "[silencedetect @ 0x1] silence_end: 905.5 | silence_duration: 3.5"].join(String.fromCharCode(10));
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "transcript", preset: "영화롱폼", payload: { ...CARRY, probe_summary: PROBE_SUMMARY, asr: ASR_OK, audio_bytes: { format: { size: "5600000", duration: "929.08" } }, silences_raw: SIL_RAW } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "brief", "transcript② → execute, next_step=brief", `${sc?.status}/${sc?.next_step}`);
  const m = sc?.metrics ?? {};
  ok(m.utterance_count === 4 && m.speech_s === 17.877 && m.silence_ratio === 0.981 && m.audio_bytes === 5600000, "transcript② → metrics(발화 수·발화 길이·무음 비율)", JSON.stringify(m));
  ok(m.dropped_hallucination === 2 && m.dropped_hallucination_s === 59.96 && sc?.warnings?.some((w) => /환청 규칙/.test(w) && /The End/.test(w)), "transcript② → 환청 규칙(≥26s·≤3단어) 제거 + 경고, 긴 정상 발화는 유지", JSON.stringify(sc?.warnings?.find((w) => /환청/.test(w))));
  ok(m.dropped_after_end === 1 && sc?.warnings?.some((w) => /이후에 시작하는 발화 1건을 제거/.test(w)) && sc?.write_files?.[0]?.content?.warnings?.length >= 1, "transcript② → 영상 길이 이후 시작 발화 제거 + 경고(transcript.json 에도 기록)", JSON.stringify(sc?.warnings?.[0]));
  const wf = sc?.write_files?.[0];
  ok(m.stretched_cut === 2 && wf?.content?.utterances?.find((u) => /No way this is a real/.test(u.text))?.end === 512.3 && wf?.content?.utterances?.find((u) => /Bye/.test(u.text))?.end === 902 && m.silences_measured === 2 && wf?.content?.silences?.length === 2, "transcript② → 발화 꼬리 무음을 실측대로 벗김(끝 = 마지막 소리 끝) + silences 기록", JSON.stringify([wf?.content?.utterances?.find((u) => /No way/.test(u.text))?.end, wf?.content?.utterances?.find((u) => /Bye/.test(u.text))?.end]));
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
const CARRY_SC = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "C:/youstudio_work/sample/transcript/transcript.json", brief_path: "C:/youstudio_work/sample/brief/brief.json", selection_path: "C:/youstudio_work/sample/clips/selection.json", selection: SEL, visual: { silent: [], ending: { ending_summary: "넘어지지만 다시 일어선다", beats: [] } }, facts: { visual_facts: [{ t_s: 737.4, fact: "마이클이 노인이 되어 있음" }] }, brief: { logline: "네모 칸에 서 있는 일", events: [] }, utterance_spans: [[80, 84], [86, 90], [92, 96], [98, 102], [104, 108]] };
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

// 24-b) script ① — 줄 나눔 책임과 규칙 전문을 내려보낸다 (2026-08-17 B안)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: CARRY_SC } });
  const sc = res.structuredContent;
  const ins = (sc?.instructions ?? []).join(" ");
  ok(sc?.status === "need_input" && /lines/.test(ins) && /줄 나눔도 집필자의 일/.test(ins) && typeof sc?.line_break_guide === "string" && /금지 패턴/.test(sc.line_break_guide) && sc?.sub_limits?.나레_한줄_최대자수 > 0, "script① → 줄 나눔 지시 + line_break_guide(규칙 전문) + sub_limits", `guide ${String(sc?.line_break_guide ?? "").length}자 · 상한 ${sc?.sub_limits?.나레_한줄_최대자수}`);
}
// 24-c) script ② 줄 나눔 불통 — 조사로 시작하는 줄 · 이어붙임 불일치 · 자수 초과
{
  const bad = { blocks: [
    { pos: { kind: "over", seg: 1 }, text: "당장 쥐어 주는 현금에 청년은 선 안에 섭니다", lines: ["당장 쥐어 주는 현금에 청년은 선", "안에 섭니다"], intent: "x" },
    { pos: { kind: "over", seg: 3 }, text: "그렇게 그는.. 처음으로 선 밖으로 나섰습니다..!", lines: ["그렇게 그는..", "처음으로 선 밖으로"], intent: "x" },
  ] };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: { ...CARRY_SC, script: bad } } });
  const sc = res.structuredContent;
  const msg = sc?.message ?? "";
  ok(res.isError === true && /줄바꿈 ⓑ/.test(msg) && /안에/.test(msg) && /이어 붙인 것이 본문과 다르다/.test(msg), "script②(줄 나눔 위반) → 반려: ⓑ 조사·의존명사로 시작 + 이어붙임 불일치", msg.slice(0, 150));
}
// 25) script ② 통과 — 지무비체 블록 (G-턴비 대역 안)
{
  const good = { blocks: [
    { pos: { kind: "over", seg: 1 }, text: "계단 앞에서 시답잖은 농담이나 주고받던.. 청년 하나가 있었습니다", lines: ["계단 앞에서 시답잖은", "농담이나 주고받던..", "청년 하나가 있었습니다"], intent: "훅 — 익명 인물" },
    { pos: { kind: "bridge", bridge: 0 }, text: "친구들의 놀림은 이어졌고.. 그날도 그런 하루로 끝날 것 같았죠", intent: "이음" },
    { pos: { kind: "before", seg: 2 }, text: "허나 그때.. 정장 차림의 남자가 다가옵니다", intent: "표지어" },
    { pos: { kind: "over", seg: 3 }, text: "네모 칸에서 시작한 하루가.. 어느새 평생이 되어 있었죠", intent: "시각 사실 — 노화" },
    { pos: { kind: "over", seg: 3 }, text: "그렇게 그는.. 처음으로 선 밖으로 나섰습니다..!", intent: "닫기" },
  ] };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: { ...CARRY_SC, script: good } } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "voice", "script②(통과) → execute, next_step=voice", `${sc?.status}/${sc?.next_step} ${sc?.message ?? ""}`);
  const m = sc?.metrics ?? {};
  ok(m.block_count === 5 && m.avg_chars > 0 && m.dialogue_s === 20 && typeof m.nar_share_est === "number" && typeof m.nar_dialogue_ratio_est === "number" && /추정/.test(m.note ?? ""), "script② → metrics(블록 수·평균 자수·나레 시간점유·나레:대사 추정 비율, 추정 표시)", JSON.stringify(m));
  const wf = sc?.write_files?.[0];
  ok(wf?.path === "C:/youstudio_work/sample/script/script.json" && wf?.content?.blocks?.length === 5 && wf.content.blocks[0].pieces === 2 && wf.content.blocks[0].lines?.length === 3 && wf.content.blocks[1].lines === null, "script② → write_files script.json(블록·조각 수 · 집필 줄 lines[] 그대로 · 안 준 블록은 null)", wf?.path);
  ok(sc?.gates?.some((g) => /나레 시간점유/.test(g.id) && g.hard === true && g.pass === true) && sc?.gates?.some((g) => /G-턴비/.test(g.id) && g.hard === false) && sc?.carry?.includes("script_path"), "script② → 나레 시간점유(G27) hard 통과 · G-턴비 soft · carry script_path", JSON.stringify(sc?.gates?.map((g) => [g.id, g.pass])));
}

// 26) script ② G-턴비 불통 (나레 과다) → 수리 지침
{
  const heavy = { blocks: Array.from({ length: 12 }, (_, i) => ({ pos: { kind: "over", seg: 3 }, text: `노인이 된 마이클이 광장을 떠나.. 보드를 타다 넘어집니다 ${i}`, intent: "x" })) };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "script", preset: "영화롱폼", payload: { ...CARRY_SC, script: heavy } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /나레 시간점유/.test(sc?.message ?? "") && /나레 과다/.test(sc?.message ?? "") && /자\)를 덜어내라/.test(sc?.message ?? ""), "script②(나레 시간점유 과다) → 반려 + 수리 지침(몇 초·몇 자를 어떻게)", (sc?.message ?? "").slice(0, 160));
}

// 27) tools/call voice ① — 보이스 미정이면 반려(수리 지침), 정해졌으면 synthesize jobs
const SCRIPT_DOC = { blocks: [
  { n: 1, pos: { kind: "over", seg: 1 }, text: "계단 앞에서 발가락 얘기로 낄낄대던.. 보드 든 청년이 있죠", chars: 33, est_s: 8.25 },
  { n: 2, pos: { kind: "bridge", bridge: 0 }, text: "친구들의 놀림은 그날도 이어졌고.. 늘 그런 하루일 듯했습니다", chars: 34, est_s: 8.5 },
], metrics: { dialogue_s: 40, total_chars: 67, nar_est_s: 16.75, nar_share_est: 0.295 } };
const CARRY_V = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "C:/youstudio_work/sample/transcript/transcript.json", brief_path: "C:/youstudio_work/sample/brief/brief.json", selection_path: "C:/youstudio_work/sample/clips/selection.json", script_path: "C:/youstudio_work/sample/script/script.json", script: SCRIPT_DOC };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "voice", preset: "영화롱폼", payload: CARRY_V } });
  const sc = res.structuredContent;
  if (sc?.status === "error") {
    ok(/보이스_ID/.test(sc?.message ?? "") && /voice\/samples/.test(sc?.message ?? "") && /보이스_후보|Kyle/.test(sc?.message ?? ""), "voice①(보이스 미정) → 반려 + 샘플·후보 안내", (sc?.message ?? "").slice(0, 100));
  } else {
    const j = sc?.jobs?.[0];
    ok(sc?.status === "execute" && sc?.jobs_kind === "synthesize" && sc?.jobs?.length === 2 && j?.provider === "elevenlabs" && j?.model === "eleven_v3" && /api\.elevenlabs\.io\/v1\/text-to-speech\/.+\?output_format=pcm_\d+/.test(j?.request?.url ?? ""), "voice①(보이스 있음) → synthesize job 블록수만큼(eleven_v3, pcm)", j?.request?.url);
    ok(j?.auth?.env === "ELEVENLABS_API_KEY" && /xi-api-key/.test(j?.auth?.header ?? "") && !/sk_1bf/.test(JSON.stringify(sc)), "voice① → auth env 만, 키 값 없음", JSON.stringify(j?.auth?.env));
    const silPost = (sc?.post ?? []).filter((x) => x.name?.startsWith("silence_")), silM = (sc?.measure ?? []).filter((m) => m.as?.startsWith("speech_raw."));
    ok(sc?.post?.length === 4 && silPost.length === 2 && silPost[0].argv.join(" ").includes("silencedetect=noise=-40dB:d=0.2") && silM.length === 2 && silM[0].unit === "stderr" && sc.post[0].argv[0] === "ffmpeg" && sc.post[0].argv.includes("s16le") && sc?.measure?.[0]?.unit === "tts_timestamps" && sc?.measure?.[0]?.as === "voice_ts.b01" && /with-timestamps/.test(j?.request?.url ?? ""), "voice① → with-timestamps URL · post[] pcm→wav + 무음스캔 · measure tts_timestamps/stderr", JSON.stringify(sc?.measure?.[0]));
  }
}

// 28) voice ② 통과 — 바이트 → 실측 길이·자당초·시간점유 재계산·여유
{
  const SIL_B01 = ["[silencedetect @ 0x1] silence_start: 2.2", "[silencedetect @ 0x1] silence_end: 3.7 | silence_duration: 1.5"].join(String.fromCharCode(10));
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "voice", preset: "영화롱폼", payload: { ...CARRY_V, voice_ts: { b01: { audio_bytes: 24000 * 2 * 5.28, alignment: { characters: ["계", "단"], character_start_times_seconds: [0, 0.2], character_end_times_seconds: [0.2, 0.4] } }, b02: { audio_bytes: 24000 * 2 * 5.5 } }, speech_raw: { b01: SIL_B01, b02: "" } } } });
  { const sc2 = res.structuredContent;
    const cat = sc2?.do?.find((d) => d.name === "nar_concat");
    const j0 = sc2?.jobs?.[0];
    ok(sc2?.status === "execute" && sc2?.next_step === "voice" && sc2?.jobs_kind === "transcribe" && sc2?.jobs?.length === 1
      && /nar_concat\.wav$/.test(cat?.argv?.at(-1) ?? "") && /adelay=/.test((cat?.argv ?? []).join(" "))
      && j0?.provider === "speechmatics" && String(j0?.request?.multipart?.data_file ?? "").startsWith("@")
      && /v2\/jobs/.test(j0?.batch?.submit_url ?? "") && j0?.auth?.env === "SPEECHMATICS_API_KEY"
      && sc2?.measure?.[0]?.as === "asr_nar" && Array.isArray(sc2?.offsets) && sc2.offsets.length === 2 && sc2.offsets[1].off > 0,
      "voice②→③ 단어 실측 국면(이어붙임 do[] + Speechmatics 배치 1콜 + 오프셋 표)", JSON.stringify([sc2?.jobs?.length, sc2?.measure?.[0]?.as, sc2?.offsets])); }
  // 나레 전사(json-v2) 픽스처 — b01 은 0s 부터, b02 는 (5.28 + 1.0 무음) = 6.28s 부터
  const SMW = (words, off) => words.map(([w, s2, e2]) => ({ type: "word", start_time: off + s2, end_time: off + e2, alternatives: [{ content: w }] }));
  const ASR_NAR = { results: [
    ...SMW([["계단", 0, 0.5], ["앞에서", 0.5, 1.0], ["발가락", 1.0, 1.5], ["얘기로", 1.5, 2.0], ["낄낄대던", 2.0, 2.6], ["보드", 2.9, 3.3], ["든", 3.3, 3.5], ["청년이", 3.5, 4.2], ["있죠", 4.2, 4.9]], 0),
    ...SMW([["친구들의", 0, 0.6], ["놀림은", 0.6, 1.1], ["그날도", 1.1, 1.6], ["이어졌고", 1.6, 2.2], ["늘", 2.5, 2.7], ["그런", 2.7, 3.1], ["하루일", 3.1, 3.6], ["듯했습니다", 3.6, 4.4]], 6.28),
  ] };
  const HEARD = { b01: "계단 앞에서 발가락 얘기로 낄낄대던 보드 든 청년이 있죠", b02: "친구들의 놀림은 그날도 이어졌고 늘 그런 하루일 듯했습니다" };
  const res3 = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "voice", preset: "영화롱폼", payload: { ...CARRY_V, voice_ts: { b01: { audio_bytes: 24000 * 2 * 5.28, alignment: { characters: ["계", "단"], character_start_times_seconds: [0, 0.2], character_end_times_seconds: [0.2, 0.4] } }, b02: { audio_bytes: 24000 * 2 * 5.5 } }, speech_raw: { b01: SIL_B01, b02: "" }, asr_nar: ASR_NAR } } });
  const sc = res3.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "subtitle", "voice② → execute, next_step=subtitle", `${sc?.status}/${sc?.next_step} ${(sc?.message ?? "").slice(0, 80)}`);
  const m = sc?.metrics ?? {};
  ok(m.block_count === 2 && m.total_s === 10.78 && m.sec_per_char_measured === 0.161 && m.sec_per_char_est === 0.122 && typeof m.nar_share_measured === "number" && typeof m.headroom_chars === "number", "voice② → metrics(총 길이·실측 자당초 vs 추정·시간점유 실측·여유 자수)", JSON.stringify(m));
  { const vd = sc?.write_files?.find((w) => /voice\.json$/.test(w.path))?.content; const b1 = vd?.blocks?.find((b) => b.n === 1); const b2 = vd?.blocks?.find((b) => b.n === 2);
    ok(Array.isArray(b1?.speech) && b1.speech.length === 2 && b1.speech[0][1] === 2.2 && b1.speech[1][0] === 3.7 && b2?.speech === null && vd?.metrics?.blocks_with_speech === 1 && (vd?.warnings ?? []).some((w) => /발성 구간 실측이 1블록 없다/.test(w)), "voice② → 발성 구간 실측 파싱(speech·metrics·경고)", JSON.stringify([b1?.speech, vd?.metrics?.blocks_with_speech])); }
  const wf = sc?.write_files?.[0];
  ok(wf?.path === "C:/youstudio_work/sample/voice/voice.json" && wf?.content?.blocks?.[0]?.dur_s === 5.28 && /b01\.wav$/.test(wf.content.blocks[0].wav) && wf.content.blocks[0].chars_t?.length === 2 && wf.content.blocks[1].chars_t === null && sc?.metrics?.blocks_with_timestamps === 1, "voice② → write_files voice.json(블록별 실측 길이·wav·글자별 시각)", "");
  ok((wf?.content?.blocks ?? []).every((b) => Array.isArray(b.words) && b.words.length > 0) && sc?.metrics?.words_total > 0 && wf.content.blocks[1].words[0].s < 1.0, "voice② → 블록마다 단어 실측 words[](이어붙임 좌표 → 블록 안 초로 환산)", JSON.stringify((wf?.content?.blocks ?? []).map((b) => [(b.words ?? []).length, (b.words ?? [])[0]?.s])));
  ok(sc?.record_to_ours?.tts?.자당초?.value === 0.161 && sc?.record_to_ours?.tts?.자당초?.n === 2 && sc?.instructions?.some((l) => /우리실측\.json/.test(l)), "voice② → record_to_ours(우리실측.json tts.자당초) + 기록 지시", JSON.stringify(sc?.record_to_ours?.tts?.자당초?.value));
  { const bad = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "voice", preset: "영화롱폼", payload: { ...CARRY_V, voice_ts: { b01: { audio_bytes: 24000 * 2 * 5.28 }, b02: { audio_bytes: 24000 * 2 * 5.5 } }, speech_raw: { b01: SIL_B01, b02: "" }, asr_nar: { results: [...ASR_NAR.results.filter((r) => r.start_time >= 6.28).map((r) => ({ ...r, start_time: r.start_time - 6.28, end_time: r.end_time - 6.28 })), ...ASR_NAR.results.filter((r) => r.start_time < 6.28).map((r) => ({ ...r, start_time: r.start_time + 6.28, end_time: r.end_time + 6.28 }))] } } } });
    const scb = bad.structuredContent;
    ok(scb?.status === "error" && /G-나레문구일치/.test(scb?.message ?? "") && /재사용 없이 새로 합성/.test((scb?.instructions ?? []).join(" ")) && !scb?.write_files?.length, "voice③(문구 어긋남) → hard_fail + 수리 지침(재합성·캐시 폐기)", (scb?.message ?? "").slice(0, 90)); }
}

// 29) voice ② 합성 실패 → hard_fail
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "voice", preset: "영화롱폼", payload: { ...CARRY_V, voice_ts: { b01: { audio_bytes: 24000 * 2 * 5 }, b02: { audio_bytes: 0 } } } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /hard_fail: 합성 실패 1건/.test(sc?.message ?? "") && /블록 2/.test(sc?.message ?? "") && /401|quota|voice_not_fine_tuned/.test(sc?.message ?? ""), "voice②(0바이트) → hard_fail + 수리 지침(원인별)", (sc?.message ?? "").slice(0, 120));
}

// 30) tools/call subtitle ① — 타임라인 + need_input(번역)
const V_BLOCKS = [
  { n: 1, pos: { kind: "over", seg: 1 }, text: "계단 앞에서 발가락 얘기로 낄낄대던.. 보드 든 청년이 있죠", dur_s: 4.0, wav: "C:/youstudio_work/sample/voice/b01.wav", chars_t: null },
  { n: 2, pos: { kind: "bridge", bridge: 0 }, text: "친구들의 놀림은 그날도 이어졌고.. 늘 그런 하루일 듯했습니다", dur_s: 4.9, wav: "C:/youstudio_work/sample/voice/b02.wav", chars_t: null },
  { n: 3, pos: { kind: "before", seg: 2 }, text: "허나 그때.. 정장 남자가 오십 달러를 꺼냅니다", dur_s: 3.1, wav: "C:/youstudio_work/sample/voice/b03.wav", chars_t: null },
  { n: 4, pos: { kind: "over", seg: 3 }, text: "고용주만 그대로인 광장을.. 마이클은 처음으로 떠납니다", dur_s: 3.1, wav: "C:/youstudio_work/sample/voice/b04.wav", chars_t: [{ c: "고", s: 0, e: 0.2 }, { c: "용", s: 0.2, e: 0.4 }] },
];
const SEL_S = { segments: [
  { i: 1, in: 0, out: 26.3, len_s: 26.3, role: "나레이션덮기", kind: "dialogue", src: ["brief#1"], why: "친구들" },
  { i: 2, in: 75.9, out: 95.9, len_s: 20, role: "원본대사", kind: "dialogue", src: ["brief#3"], why: "낯선 남자" },
  { i: 3, in: 780, out: 854.3, len_s: 74.3, role: "시각몽타주", kind: "ending", src: ["visual:ending(통째)"], why: "결말" },
], narration_bridges: [{ start: 26.3, end: 75.9, len_s: 49.6, events: [] }] };
const UTTS = [{ start: 1, end: 3, text: "Dude, Mike, your uncle is a podiatrist, right?" }, { start: 3.2, end: 9, text: "line two" }, { start: 10, end: 12, text: "Yeah, it never really crossed my mind." }, { start: 12.5, end: 20, text: "line four" }, { start: 20.5, end: 26, text: "line five" }, { start: 76, end: 78, text: "line six" }, { start: 78.1, end: 79, text: "Me?" }, { start: 79.2, end: 80.5, text: "line eight" }, { start: 80.7, end: 84, text: "Are you guys able to help me with something real quick?" }, { start: 84.2, end: 85.6, text: "line ten" }, { start: 85.8, end: 87.5, text: "I will give you 50 bucks." }, { start: 87.7, end: 92, text: "line twelve" }, { start: 92.2, end: 95.8, text: "line thirteen" }, { start: 300, end: 302, text: "unrelated" }];
const CARRY_SUB = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "x", brief_path: "x", selection_path: "x", script_path: "x", voice_path: "x", selection: SEL_S, voice: { blocks: V_BLOCKS }, transcript_utterances: UTTS, visual: { silent: [{ scenes: [{ start: 30, end: 40, what: "놀림 장면" }] }] } };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "subtitle", preset: "영화롱폼", payload: CARRY_SUB } });
  const sc = res.structuredContent;
  ok(sc?.status === "need_input" && sc?.need_input?.keys?.includes("translations") && sc?.next_step === "subtitle", "subtitle① → need_input(translations)", `${sc?.status} ${(sc?.message ?? "").slice(0, 80)}`);
  const lines = sc?.material?.dialogue_lines ?? [];
  ok(lines.length === 13 && lines.every((l) => /^d\d{6}$/.test(l.id)) && !lines.some((l) => /unrelated/.test(l.en)), "subtitle① → 번역 대상 = 대사 역할 구간 안 발화만(13줄, 시각몽타주·미선택 제외)", JSON.stringify(lines.map((l) => l.id)));
  TR = lines.map((l, i) => ({ id: l.id, ko: TR_KO[i] ?? `줄 ${i + 1}`, en: l.en }));
  ok(sc?.style_guide?.some((l) => /지무비 구어체/.test(l)) && sc?.style_guide?.some((l) => /29자/.test(l)), "subtitle① → 번역 문체 안내(지무비 구어체·29자)", "");
  const tp = sc?.material?.timeline_preview;
  ok(tp?.total_s > 26.3 + 20 + 74.3 && tp?.cuts >= 5, "subtitle① → 타임라인 총장 = 구간합 + 브리지 컷 + before 연장", JSON.stringify(tp));
}
// 31) subtitle ② 통과
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "subtitle", preset: "영화롱폼", payload: { ...CARRY_SUB, translations: TR } } });
  const sc = res.structuredContent;
  if (process.env.DBG === "1") { const D = sc?.diagnostics ?? {}; console.log("DBG status", sc?.status, "metrics", JSON.stringify(sc?.metrics ?? D.metrics)); console.log("DBG dropped", JSON.stringify(D.dlg_dropped ?? [])); console.log("DBG dead", JSON.stringify((D.dead_spans_top ?? []).slice(0, 5))); }
  ok(sc?.status === "execute" && sc?.next_step === "export", "subtitle② → execute, next_step=export", `${sc?.status}/${sc?.next_step} ${(sc?.message ?? "").slice(0, 100)}`);
  const tl = sc?.write_files?.find((w) => /timeline\.json$/.test(w.path))?.content;
  const pics = tl?.picture ?? [];
  ok(pics.some((p) => p.kind === "bridge" && p.src_in === 30 && /앵커 장면/.test(p.why ?? "")) && pics.some((p) => p.kind === "extend" && p.seg === 2), "subtitle② → 브리지 컷(판정 장면 앵커 30s) + before 연장 컷", JSON.stringify(pics.map((p) => [p.kind, p.src_in, p.src_out])));
  const nars = tl?.narration ?? [];
  const n4 = nars.find((n) => n.n === 4);
  ok(nars.length === 4 && n4 && /균등/.test(n4.anchor) && nars.find((n) => n.n === 1)?.anchor.includes("틈"), "subtitle② → over 배치(시각몽타주 균등 · 대사 역할은 틈)", JSON.stringify(nars.map((n) => [n.n, n.t0, n.anchor.slice(0, 20)])));
  const cues = tl?.cues ?? [];
  const narCues = cues.filter((c) => c.lane === "nar"), dlgCues = cues.filter((c) => c.lane === "dlg");
  ok(dlgCues.length >= 10 && narCues.length >= 4 && narCues.every((c) => c.text.length <= 24) && dlgCues.every((c) => c.text.length <= 34), "subtitle② → 큐(나레 ≤24자·대사 ≤34자 — 2026-08-19 2판 상한)", `nar=${narCues.length} dlg=${dlgCues.length}`);
  // R1/R3 (2026-08-17): 나레 큐는 음성 밖 금지 · 나레×대사 자막 동시 표시 금지
  const narInVoice = narCues.every((c) => { const n = (tl?.narration ?? []).find((x) => `n${x.n}` === c.ref); return n && c.t0 >= n.t0 - 0.05 && c.t1 <= n.t1 + 0.05; });
  let crossOv = 0; for (const n of narCues) for (const d of dlgCues) crossOv += Math.max(0, Math.min(n.t1, d.t1) - Math.max(n.t0, d.t0));
  ok(narInVoice && crossOv < 0.001 && tl?.metrics?.cross_overlap_s === 0 && (tl?.metrics?.dlg_cues_dropped ?? 0) >= 1, "subtitle② → 나레 큐 ⊆ 음성 구간 · 교차 겹침 0(대사 큐 잘림/버림)", `cross=${crossOv.toFixed(3)} dropped=${tl?.metrics?.dlg_cues_dropped} trimmed=${tl?.metrics?.dlg_cues_trimmed}`);
  ok(sc?.metrics?.overlaps === 0 && sc?.gates?.some((g) => /겹침/.test(g.id) && g.pass) && sc?.gates?.some((g) => /죽은시간/.test(g.id) && g.hard), "subtitle② → 게이트(겹침 0 · 죽은시간 hard)", JSON.stringify(sc?.gates?.map((g) => [g.id, g.pass])));
  ok(sc?.gates?.some((g) => g.id === "G-대사선행" && g.hard), "subtitle② → G-대사선행 게이트 존재(hard)", JSON.stringify(sc?.gates?.find((g) => g.id === "G-대사선행")?.detail ?? ""));
  ok(sc?.gates?.some((g) => /G-교차겹침/.test(g.id) && g.pass && g.hard) && sc?.gates?.some((g) => /G-자막음성일치/.test(g.id) && g.pass && g.hard), "subtitle② → 새 게이트 2개(G-교차겹침·G-자막음성일치) hard 통과", JSON.stringify(sc?.gates?.map((g) => g.id)));
  const lb = sc?.gates?.find((g) => g.id === "G-줄바꿈");
  ok(lb?.pass === true && lb?.hard === true && /집필 줄|폴백 분할/.test(lb?.detail ?? "") && typeof lb?.fix === "string", "subtitle② → G-줄바꿈(확정 ⓑⓒⓔ hard · 의심 ⓐⓓ 경고 · 수리 지침)", (lb?.detail ?? "").slice(0, 90));
  const srt = sc?.write_files?.find((w) => /subtitle\.srt$/.test(w.path))?.content ?? "";
  ok(/^1\n\d\d:\d\d:\d\d,\d{3} --> /.test(srt) && /– 저요\?/.test(srt) && sc?.write_files?.length === 4, "subtitle② → SRT 3종+timeline (합본 대사 접두 –)", srt.slice(0, 60).replace(/\n/g, "\\n"));
  ok(typeof sc?.metrics?.dead_ratio === "number" && sc?.metrics?.hold_s === 74.3 && sc?.metrics?.added_time_s > 0, "subtitle② → metrics(죽은 시간 비율·홀드 제외·추가 시간)", JSON.stringify({ dead: sc?.metrics?.dead_ratio, hold: sc?.metrics?.hold_s, added: sc?.metrics?.added_time_s }));
}
// 32) subtitle ② 번역 초과·누락 → 반려
{
  const bad = [...TR.slice(2)].map((x) => ({ ...x })); bad.unshift({ ...TR[0], ko: "야 마이크 너네 삼촌이 발 전문의라고 했지 맞지 진짜 그랬잖아 기억나" }, { ...TR[1], ko: "둘째, 줄" }); bad.pop(); // 마지막 줄 누락
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "subtitle", preset: "영화롱폼", payload: { ...CARRY_SUB, translations: bad } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /대사 \d+자 > 34자/.test(sc?.message ?? "") && /대사 자막에 마침표·쉼표 금지/.test(sc?.message ?? "") && /번역 누락 1줄/.test(sc?.message ?? ""), "subtitle②(초과·구두점·누락) → 반려 + 어느 줄이 왜", (sc?.message ?? "").slice(0, 160));
}

// 33) tools/call export ① — 나레 믹스 do[] + measure
const TL_FIX = {
  total_s: 30, picture: [
    { k: 0, kind: "segment", role: "원본대사", src_in: 75.9, src_out: 95.9, t0: 0, t1: 20, audio: "keep", seg: 2 },
    { k: 1, kind: "bridge", role: "브리지", src_in: 30, src_out: 35, t0: 20, t1: 25, audio: "duck", bridge: 0 },
    { k: 2, kind: "segment", role: "시각몽타주", src_in: 780, src_out: 785, t0: 25, t1: 30, audio: "hold", seg: 3 },
  ],
  narration: [{ n: 1, t0: 1, t1: 5, wav: "C:/youstudio_work/sample/voice/b01.wav", text: "계단 앞에서.. 청년이 있죠" }, { n: 2, t0: 20.4, t1: 24.4, wav: "C:/youstudio_work/sample/voice/b02.wav", text: "친구들의 놀림은.. 듯했습니다" }],
  cues: [
    { lane: "nar", t0: 0, t1: 3, text: "계단 앞에서..", ref: "n1" }, { lane: "nar", t0: 3, t1: 5, text: "청년이 있죠", ref: "n1" },
    { lane: "dlg", t0: 2.2, t1: 6, text: "저요?", ref: "d001" }, { lane: "dlg", t0: 6.5, t1: 12, text: "잠깐 뭐 좀 도와줄 수 있어요?", ref: "d002" }, { lane: "dlg", t0: 12.5, t1: 20, text: "50달러 줄게요", ref: "d003" },
    { lane: "nar", t0: 20, t1: 22.5, text: "친구들의 놀림은..", ref: "n2" }, { lane: "nar", t0: 22.5, t1: 25, text: "듯했습니다", ref: "n2" },
  ],
};
const VOICE_FIX = { blocks: [{ n: 1, bytes: 192000, dur_s: 4, wav: "C:/youstudio_work/sample/voice/b01.wav" }, { n: 2, bytes: 192000, dur_s: 4, wav: "C:/youstudio_work/sample/voice/b02.wav" }], metrics: { total_s: 8, sec_per_char_measured: 0.12 } };
const CARRY_EX = { ...CARRY, probe_summary: PROBE_SUMMARY, transcript_path: "x", brief_path: "x", selection_path: "x", script_path: "x", voice_path: "x", timeline_path: "C:/youstudio_work/sample/subtitle/timeline.json", timeline: TL_FIX, voice: VOICE_FIX, script: { metrics: { dialogue_s: 8 } }, brief: { events: [{ n: 1, start: 0, end: 30 }] }, transcript_metrics: { utterance_count: 195 } };
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: CARRY_EX } });
  const sc = res.structuredContent;
  const mix = sc?.do?.find((d) => d.name === "narration_mix");
  ok(sc?.status === "execute" && sc?.next_step === "export" && mix?.argv?.[0] === "ffmpeg" && /adelay=1000\|1000/.test(mix.argv.join(" ")) && /amix=inputs=2/.test(mix.argv.join(" ")) && /apad=whole_dur=30/.test(mix.argv.join(" ")), "export① → 나레 믹스 ffmpeg(adelay 실측 t0 · amix · apad 총장)", mix?.argv?.slice(-3).join(" "));
  ok(sc?.measure?.[0]?.as === "mix_probe" && sc?.do?.some((d) => d.name === "mix_probe"), "export① → mix_probe measure", "");
  const asm = sc?.do?.find((d) => d.name === "prproj_assemble");
  const a = (asm?.argv ?? []).join(" ");
  ok(sc?.do?.length === 3 && asm?.argv?.[0] === "python" && /조립_prproj\.py/.test(a) && /--timeline C:\/youstudio_work\/sample\/subtitle\/timeline\.json/.test(a) && /--out .*sample\/render\/샘플_2024\.prproj/.test(a) && /--json/.test(a) && sc?.measure?.some((m) => m.as === "prproj_report" && m.from === "job:prproj_assemble" && m.unit === "json_stdout"), "export① → prproj 조립 job(argv 저장소 기준 경로 · timeline/voice 파일 경로 · --json) + prproj_report measure", a.slice(0, 120));
  ok(/저장소 루트에서/.test((sc?.instructions ?? []).join(" ")), "export① → 지시: do[] 는 저장소 루트에서 실행", "");
}
// 33-b) export ① timeline_path 없음 → 반려(조립기는 payload 사본이 아니라 디스크 파일을 읽는다)
{
  const { timeline_path: _drop, ...noPath } = CARRY_EX;
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: noPath } });
  const sc = res.structuredContent;
  ok(res.isError === true && /timeline_path/.test(sc?.message ?? ""), "export①(timeline_path 없음) → 반려 + 수리 지침", (sc?.message ?? "").slice(0, 80));
}
// 조립기(서버/runner/조립_prproj.py --json)가 돌려주는 자기검증 요약 — 픽스처
const PRPROJ_FIX = {
  pass: true, out: "C:/youstudio_work/sample/render/샘플_2024.prproj", report: "C:/youstudio_work/sample/render/샘플_2024.prproj.report.json",
  donor: "도너/볼케이노_FullTime_v26_b05_ppro-v45.prproj", total_s: 30,
  counts: { V1: 3, A1: 2, A3: 1, A2: 2, V2: 3, V3: 4, V4: 0, links: 3 },
  checks: [{ check: "ObjectID 유일", pass: true, detail: "중복 0" }, { check: "댕글링 참조 0", pass: true, detail: "없음" }, { check: "timeline.json 대조(자막 문구·시각 · 컷/나레 시각)", pass: true, detail: "불일치 0" }],
  failed: [],
};
const MIX_OK = { format: { duration: "30.000000", size: "1440044" } };
// 34) export ② — prproj(본선) · XML · SRT · manifest · 게이트 전체 재검사 → done
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: { ...CARRY_EX, mix_probe: MIX_OK, prproj_report: PRPROJ_FIX } } });
  const sc = res.structuredContent;
  ok(sc?.status === "done" && sc?.next_step === null, "export② → status=done, next_step=null", `${sc?.status}/${sc?.next_step} ${(sc?.message ?? "").slice(0, 80)}`);
  const xml = sc?.write_files?.find((w) => /\.xml$/.test(w.path))?.content ?? "";
  ok(/<xmeml version="5">/.test(xml) && /<timebase>24<\/timebase><ntsc>TRUE<\/ntsc>/.test(xml) && /<width>1920<\/width><height>1080<\/height>/.test(xml), "export② → FCP XML v5 · 24 ntsc(23.976) · 1920x1080", xml.slice(0, 80).replace(/\n/g, " "));
  const count = (re) => (xml.match(re) ?? []).length;
  ok(count(/<clipitem id="v1-/g) === 3 && count(/<clipitem id="a1-/g) === 2 && count(/<clipitem id="a3-/g) === 1 && count(/<clipitem id="a2-/g) === 2 && count(/<generatoritem id="v2-/g) === 3 && count(/<generatoritem id="v3-/g) === 4, "export② → 트랙 요소 수 = 실측(V1 3·A1 2(살림)·A3 1(덕킹 별도)·A2 2·V2 3·V3 4)", `${count(/<clipitem id="v1-/g)}/${count(/<clipitem id="a1-/g)}/${count(/<clipitem id="a3-/g)}/${count(/<clipitem id="a2-/g)}/${count(/<generatoritem id="v2-/g)}/${count(/<generatoritem id="v3-/g)}`);
  ok(/<in>1820<\/in>/.test(xml) && /<start>480<\/start>/.test(xml) && /Audio Levels/.test(xml) && /<value>0\.25<\/value>/.test(xml), "export② → 원본 in 프레임(75.9s→1820) · 타임라인 프레임(20s→480) · A3 덕킹 컷 Audio Levels 0.25", "");
  ok(/<value>SDGwanghwamun<\/value>/.test(xml) && /<value>SourceHanSerifK-Bold<\/value>/.test(xml) && /<vert>0\.398148<\/vert>/.test(xml) && /<vert>0\.401852<\/vert>/.test(xml) && /<vert>430<\/vert>/.test(xml) && /<vert>434<\/vert>/.test(xml) && /file:\/\/localhost\/C:\/movies\/sample\.mp4/.test(xml), "export② → 폰트 xml명(PS) · **아랫변 정렬 한 레인**(나레 y970/origin 0.398148 · 대사 y974/0.401852 — 잉크 아랫변 983, 2026-08-20) + Basic Motion center 병기 · pathurl", "");
  const man = sc?.write_files?.find((w) => /manifest\.json$/.test(w.path))?.content;
  ok(Array.isArray(man?.프리미어_후속) && man.프리미어_후속[0]?.위치_px?.y === 970 && man.프리미어_후속[1]?.위치_px?.y === 974 && man.프리미어_후속[0]?.위치_px?.x === 960 && man.프리미어_후속[1]?.origin_y === 0.401852, "export② → manifest.프리미어_후속(아랫변 정렬 — 나레 y970 · 대사 y974, 규격 자막.위치)", JSON.stringify(man?.프리미어_후속?.map((r) => r.위치_px)));
  ok(man?.counts?.cuts === 3 && man?.counts?.cues === 7 && man?.fonts?.나레?.패밀리 === "Source Han Serif K" && Array.isArray(man?.gates) && man.gates.every((g) => g.pass !== false) && man?.sequence?.total_s === 30, "export② → manifest(재료·총 길이·게이트 전부 통과·폰트)", JSON.stringify(man?.gates?.map((g) => [g.step, g.pass])));
  ok(sc?.write_files?.length === 5 && sc?.write_files?.some((w) => /subtitle_dlg\.srt$/.test(w.path)), "export② → write_files 5개(XML·SRT 3종·manifest)", JSON.stringify(sc?.write_files?.map((w) => w.path.split("/").pop())));
  const g = (id) => sc?.gates?.find((x) => x.id === id);
  ok(g("G-prproj자기검증")?.pass === true && g("G-prproj요소수 = 타임라인 실측")?.pass === true && typeof g("G-prproj자기검증")?.fix === "string", "export② → prproj 게이트 2개 통과(수리 지침 포함)", g("G-prproj요소수 = 타임라인 실측")?.detail);
  ok(man?.산출물?.본선 === PRPROJ_FIX.out && /prproj/.test(man?.산출물?.종류 ?? "") && man?.materials?.prproj === PRPROJ_FIX.out && /더블클릭/.test((sc?.instructions ?? []).join(" ")), "export② → manifest.산출물 = .prproj 본선 + XML 은 폴백 · 지시는 '더블클릭'", JSON.stringify(man?.산출물));
}
// 34-b) export ② 조립 결과 없음 → 반려
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: { ...CARRY_EX, mix_probe: MIX_OK } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /prproj_report/.test(sc?.message ?? "" + (sc?.instructions ?? []).join(" ")) || /자기검증 결과/.test(sc?.message ?? ""), "export②(prproj_report 없음) → 반려", (sc?.message ?? "").slice(0, 70));
}
// 34-c) export ② 조립 자기검증 불통 → hard_fail (게이트가 조립기 판정을 그대로 물려받는다)
{
  const bad = { ...PRPROJ_FIX, pass: false, checks: [...PRPROJ_FIX.checks, { check: "댕글링 참조 0", pass: false, detail: "끊긴 참조 3" }], failed: ["댕글링 참조 0"] };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: { ...CARRY_EX, mix_probe: MIX_OK, prproj_report: bad } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /G-prproj자기검증/.test(sc?.message ?? ""), "export②(조립 자기검증 불통) → hard_fail", (sc?.message ?? "").slice(0, 110));
}
// 34-d) export ② 조립 요소 수 ≠ 타임라인 → hard_fail
{
  const bad = { ...PRPROJ_FIX, counts: { ...PRPROJ_FIX.counts, V2: 2 } };
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: { ...CARRY_EX, mix_probe: MIX_OK, prproj_report: bad } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /G-prproj요소수/.test(sc?.message ?? "") && /2≠3/.test(sc?.message ?? ""), "export②(조립 요소 수 불일치) → hard_fail", (sc?.message ?? "").slice(0, 110));
}
// 35) export ② 믹스 길이 불일치 → hard_fail
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: { ...CARRY_EX, mix_probe: { format: { duration: "12.0" } }, prproj_report: PRPROJ_FIX } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /믹스 길이 12s 가 타임라인 총장 30s/.test(sc?.message ?? ""), "export②(믹스 길이 불일치) → hard_fail + 수리 지침", (sc?.message ?? "").slice(0, 100));
}
// 36) export ② 최종 재검사 불통 (죽은 시간 — 큐 없음)
{
  const res = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "export", preset: "영화롱폼", payload: { ...CARRY_EX, timeline: { ...TL_FIX, cues: [] }, mix_probe: { format: { duration: "30.0" } }, prproj_report: PRPROJ_FIX } } });
  const sc = res.structuredContent;
  ok(res.isError === true && /최종 재검사 불통/.test(sc?.message ?? "") && /G-죽은시간/.test(sc?.message ?? ""), "export②(재검사 불통) → 어느 단계 게이트인지 + 돌아가라", (sc?.message ?? "").slice(0, 120));
}

// 37) 규격 키 ↔ 코드 대조 (2026-08-17 주간정비) — 설정을 바꿨는데 수치가 안 변하는 사고를 막는다
{
  const { readFileSync, readdirSync, statSync, existsSync } = await import("node:fs");
  const root = new URL("../../", import.meta.url);
  const spec = JSON.parse(readFileSync(new URL("스타일/영화롱폼/규격.json", root), "utf8"));
  // 규격을 읽는 쪽 전부 — 서버(.ts) · 러너(.mjs) · 도너 스크립트(.py)
  const files = [], tsFiles = [];
  const 훑기 = (dir, exts, into) => { if (!existsSync(dir)) return; (function walk(u) { for (const e of readdirSync(u)) { if (statSync(new URL(e, u)).isDirectory()) walk(new URL(e + "/", u)); else if (exts.some((x) => e.endsWith(x))) into.push(new URL(e, u)); } })(dir); };
  훑기(new URL("서버/src/", root), [".ts"], tsFiles);
  files.push(...tsFiles);
  훑기(new URL("서버/runner/", root), [".mjs"], files);
  훑기(new URL("도너/", root), [".py"], files);
  const src = files.map((f) => readFileSync(f, "utf8")).join("\n");

  // 키 이름이 **토큰으로** 쓰였는지 본다(따옴표·점·대괄호 뒤 + 뒤에 글자 안 붙음) — 「임계」가 「임계_s」에 묻히지 않게
  const 쓰임 = (k) => { const 글자 = (c) => c !== undefined && /[가-힣A-Za-z0-9_]/.test(c); let i = -1; while ((i = src.indexOf(k, i + 1)) !== -1) { const 앞 = src[i - 1], 뒤 = src[i + k.length]; if ((앞 === String.fromCharCode(34) || 앞 === "'" || 앞 === "." || 앞 === "[") && !글자(뒤)) return true; } return false; };

  // 부모 키가 읽히면 그 아래는 값 통째로 넘어간다(예: 음성.voice_settings → API 로 그대로) — 자식까지 훑지 않는다
  const 죽은키 = [];
  (function walk(o, path, 부모읽힘) {
    for (const [k, v] of Object.entries(o)) {
      if (k.startsWith("_")) continue;
      const full = path ? path + "." + k : k;
      const 읽힘 = 부모읽힘 || 쓰임(k);
      if (!읽힘) { 죽은키.push(full); continue; }               // 여기서 끊고 자식은 안 본다
      if (v && typeof v === "object" && !Array.isArray(v)) walk(v, full, 읽힘);
    }
  })(spec, "", false);
  ok(죽은키.length === 0, "규격 키 → 코드: 규격에 있는데 아무도 안 읽는 키 0개", 죽은키.join(" · "));

  // 코드가 읽는데 규격에 없는 키 (예: 「임계」 vs 「임계_s」 오타 → 설정이 조용히 무시된다)
  const 이름집합 = new Set();
  // 배열 원소 안의 키까지 모은다(예: 음성.보이스_후보[].이름) — 코드 타입이 그 이름을 쓴다
  (function walk(o) { if (Array.isArray(o)) { for (const v of o) if (v && typeof v === "object") walk(v); return; } for (const [k, v] of Object.entries(o)) { if (k.startsWith("_")) continue; 이름집합.add(k); if (v && typeof v === "object") walk(v); } })(spec);
  // 코드가 선언한 규격 타입(interface *Spec)의 한글 속성 = 코드가 기대하는 규격 키
  const 없는키 = [];
  for (const f of tsFiles) {
    const t = readFileSync(f, "utf8");
    for (const m of t.matchAll(/interface\s+(\w*Spec)\s*\{/g)) {
      let depth = 0, i = m.index + m[0].length - 1, end = i;
      for (; end < t.length; end++) { if (t[end] === "{") depth++; else if (t[end] === "}") { depth--; if (!depth) break; } }
      const body = t.slice(i, end);
      for (const q of body.matchAll(/(?<![A-Za-z0-9_가-힣])([가-힣][가-힣A-Za-z0-9_]*)\s*\??\s*:/g)) {
        if (!이름집합.has(q[1])) 없는키.push(f.href.split("/").pop() + " " + m[1] + ": " + q[1]);
      }
    }
  }
  ok(없는키.length === 0, "코드 → 규격 키: 코드 타입이 기대하는데 규격에 없는 키 0개", [...new Set(없는키)].join(" · "));
}

// ── 스케치코미디 프리셋 (2026-08-28, sketch2 이식) ────────────────────────────
// 게이트를 통과하는 최소 편.json — 실제 8vLYMfEGZvM 편의 값을 다듬은 것
const SK = {
  slug: "TESTID_A",
  source: { url: "https://www.youtube.com/watch?v=TESTID", id: "TESTID", dur: 480.6, fps: 23.976 },
  title: ["피규어 박스 좀", "구겨진 게 죄야?"],
  title_candidates: [["후보 하나!"], ["후보 둘?"], ["후보 셋..."], ["후보 넷!"], ["후보 다섯?"]],
  hashtag: "#피규어_박스",
  // 훅은 대사(G-훅대사) — hooks[0].t0 이 Hook 조각(280~288) 안에 있어야 한다
  hooks: [{ t0: 282, text: "박스 구겨졌다고 환불이요?" }, { t0: 330, text: "훅2" }, { t0: 472, text: "훅3" }],
  // 절대 규칙(2026-09-01): 총 66초(60~80) · 클러스터 280~368 밀도 58/88=0.659 · Climax 60.6% 지점
  // 마지막 P5(470~478, 8초)는 결말 점프 — 밀도 계산에서 빠진다
  segments: [
    { t0: 280.0, t1: 288.0, punch: 10, phase: 1, keep: true },
    { t0: 292.0, t1: 304.0, punch: 5, phase: 2, keep: true, narration: "친구의 피규어 박스가 구겨졌다" },
    { t0: 315.0, t1: 335.0, punch: 8, phase: 3, keep: true },
    { t0: 350.0, t1: 368.0, punch: 9, phase: 4, keep: true },
    { t0: 470.0, t1: 478.0, punch: 10, phase: 5, keep: true },
  ],
  subs: Array.from({ length: 18 }, (_, i) => ({ t: i * 2.5, text: `자막 ${i}`, kind: "line" })),
  comments: [],
  credit: { channel: "띱 Deep", title: "테스트" },
  // 절대 지침(정답지 G-결말, 2026-09-01) — 편은 반전 또는 결론으로 끝나야 한다
  ending: { type: "결론", desc: "구겨진 박스를 새것으로 바꿔 주며 소동이 끝난다" },
};
const SK_CARRY = { workdir: "C:/sketch_work/test", project_path: "C:/sketch_work/test/projects/TESTID_A.json", source: SK.source };
const skCall = (step, args = {}) => rpc("tools/call", { name: "youstudio_video", arguments: { step, preset: "스케치코미디", ...args } });

// S1) setup — 프리셋별 규격·작업 폴더
{
  const res = await skCall("setup");
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "start", "sk setup → next_step=start", `${sc?.status}/${sc?.next_step}`);
  ok(typeof sc?.spec?._안내 === "string" && String(sc.spec._안내).includes("스케치코미디"), "sk setup → 스케치코미디 규격이 실려 옴", String(sc?.spec?._안내).slice(0, 40));
  ok(JSON.stringify(sc?.workdir_layout?.dirs) === JSON.stringify(["projects", "work", "out"]), "sk setup → workDirs=projects/work/out", JSON.stringify(sc?.workdir_layout?.dirs));
}
// S2) 다른 프리셋의 단계는 반려된다 (파이프라인 등록표)
{
  const r1 = await skCall("probe", { payload: {} });
  ok(r1.isError === true && /단계가 아니다/.test(r1.structuredContent?.message ?? ""), "sk: probe 는 스케치코미디 단계가 아니다 → 반려", r1.structuredContent?.message);
  const r2 = await rpc("tools/call", { name: "youstudio_video", arguments: { step: "sk_plan", preset: "영화롱폼", payload: {} } });
  ok(r2.isError === true && /단계가 아니다/.test(r2.structuredContent?.message ?? ""), "영화롱폼: sk_plan 반려 + 단계 순서 안내", r2.structuredContent?.message);
}
// S3) start — 유튜브 소재 + config 생성 지시
{
  const res = await skCall("start", { source: { kind: "youtube", url: SK.source.url, slug: "TESTID_A" }, payload: { workdir: SK_CARRY.workdir } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "sk_plan", "sk start → next_step=sk_plan", `${sc?.status}/${sc?.next_step}`);
  const j = sc?.jobs?.[0];
  ok(sc?.jobs_kind === "argv" && j?.argv?.includes("규격조립.py") && j?.argv?.at(-1) === SK_CARRY.workdir, "sk start → 규격조립 argv(--workdir)", j?.argv?.join(" "));
  ok((sc?.instructions ?? []).join(" ").includes("서버/runner/스케치코미디"), "sk start → 러너 폴더 지시", "");
  const bad = await skCall("start", { source: { kind: "local_video", path: "C:/x.mp4" }, payload: { workdir: "C:/w" } });
  ok(bad.isError === true && /유튜브/.test(bad.structuredContent?.message ?? ""), "sk start(로컬 파일) → 반려", bad.structuredContent?.message);
}
// S4) sk_plan — plan argv 조립 (slug·focus 전달)
{
  const res = await skCall("sk_plan", { payload: { workdir: SK_CARRY.workdir, source: { kind: "youtube", url: SK.source.url, slug: "TESTID_B", focus_sec: 421 } } });
  const sc = res.structuredContent;
  const a = sc?.jobs?.[0]?.argv ?? [];
  ok(sc?.next_step === "sk_check" && a.includes("s2pipe.plan") && a.includes(SK.source.url), "sk_plan → plan argv + next=sk_check", a.join(" "));
  ok(a.includes("--config") && a.includes("C:/sketch_work/test/config.json"), "sk_plan → --config <workdir>/config.json", "");
  ok(a.includes("--slug") && a.includes("TESTID_B") && a.includes("--focus") && a.includes("421"), "sk_plan → A/B slug·focus 전달", "");
}
// S5) sk_check — 게이트 통과 (밀도·5-Phase·나레 패딩)
{
  const res = await skCall("sk_check", { payload: { ...SK_CARRY, project: SK } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "sk_cut", "sk_check(정상) → 통과, next=sk_cut", `${sc?.status}/${sc?.next_step} ${JSON.stringify(sc?.rejected ?? [])}`);
  ok(sc?.metrics?.total_sec === 66 && Math.abs(sc.metrics.density - 0.659) < 0.001, "sk_check → metrics(길이 66s·밀도 0.659, 결말 점프 제외)", JSON.stringify(sc?.metrics));
  ok(sc?.tts_est?.chars === 16 && sc?.carry?.includes("tts_est"), "sk_check → TTS 예상 분량 carry(나레 16자)", JSON.stringify(sc?.tts_est));
  ok((sc?.instructions ?? []).join(" ").includes("사장님 승인"), "sk_check 통과 → 렌더 전 사장님 승인 지시(2026-09-01 절차)", "");
}
// S6) sk_check — 반려들 (훅 약함 · Climax 위치 · sketch 대본 혼입 · P5 나레이션)
{
  const weak = { ...SK, segments: SK.segments.map((s, i) => (i === 0 ? { ...s, punch: 4 } : s)) };
  const r1 = await skCall("sk_check", { payload: { ...SK_CARRY, project: weak } });
  ok(r1.isError === true && (r1.structuredContent?.rejected ?? []).some((b) => b.includes("훅이 약하다")), "sk_check(훅 punch 4) → 반려", JSON.stringify(r1.structuredContent?.rejected));
  const early = { ...SK, segments: SK.segments.map((s, i) => (i === 2 ? { ...s, t1: 328.0 } : s)) };
  const r2 = await skCall("sk_check", { payload: { ...SK_CARRY, project: early } });
  ok(r2.isError === true && (r2.structuredContent?.rejected ?? []).some((b) => b.includes("Climax 가 너무 빠르다")), "sk_check(Climax 51%) → 반려", JSON.stringify(r2.structuredContent?.rejected));
  const sketch1 = { ...SK, segments: SK.segments.map(({ phase, ...s }) => s) };
  const r3 = await skCall("sk_check", { payload: { ...SK_CARRY, project: sketch1 } });
  ok(r3.isError === true && (r3.structuredContent?.rejected ?? [])[0]?.includes("sketch 대본"), "sk_check(phase 없음) → sketch 대본 혼입 반려", "");
  const narrP5 = { ...SK, segments: SK.segments.map((s, i) => (i === 4 ? { ...s, narration: "마무리 설명" } : s)) };
  const r4 = await skCall("sk_check", { payload: { ...SK_CARRY, project: narrP5 } });
  ok(r4.isError === true && (r4.structuredContent?.rejected ?? []).some((b) => b.includes("배우 말이 들려야 한다")), "sk_check(P5 나레이션) → 반려", "");
  // 절대 지침(정답지 G-결말, 2026-09-01) — 결말 없이는 통과 못 한다
  const { ending: _e, ...noEnd } = SK;
  const r5 = await skCall("sk_check", { payload: { ...SK_CARRY, project: noEnd } });
  ok(r5.isError === true && (r5.structuredContent?.rejected ?? []).some((b) => b.includes("ending 이 없다")), "sk_check(ending 없음) → G-결말 반려", JSON.stringify(r5.structuredContent?.rejected));
  const weakEnd = { ...SK, segments: SK.segments.map((s, i) => (i === 4 ? { ...s, punch: 9 } : s)) };
  const r6 = await skCall("sk_check", { payload: { ...SK_CARRY, project: weakEnd } });
  ok(r6.isError === true && (r6.structuredContent?.rejected ?? []).some((b) => b.includes("결말이 약하다")), "sk_check(마지막 punch 9) → G-결말 반려", JSON.stringify(r6.structuredContent?.rejected));
  // 절대 규칙 2(2026-09-01) — 무언 컷 훅 반려 · 60초 미만 길이 반려
  const muteHook = { ...SK, hooks: [{ t0: 400, text: "훅 조각 밖의 대사" }] };
  const r7 = await skCall("sk_check", { payload: { ...SK_CARRY, project: muteHook } });
  ok(r7.isError === true && (r7.structuredContent?.rejected ?? []).some((b) => b.includes("훅 조각")), "sk_check(무언 컷 훅) → G-훅대사 반려", JSON.stringify(r7.structuredContent?.rejected));
  const short = { ...SK, segments: SK.segments.map((s, i) => (i === 2 ? { ...s, t1: 320.0 } : s)) };
  const r8 = await skCall("sk_check", { payload: { ...SK_CARRY, project: short } });
  ok(r8.isError === true && (r8.structuredContent?.rejected ?? []).some((b) => b.includes("절대 규칙")), "sk_check(총 51초) → G-길이 반려(60~80 절대)", JSON.stringify(r8.structuredContent?.rejected));
  // 절대 규칙 3(2026-09-01) — 나레이션·자막 구두점 금지 (물음표·느낌표는 허용)
  const punct = { ...SK, subs: [...SK.subs, { t: 40, text: "마침표가 있다.", kind: "line" }, { t: 41, text: "물음표는 되나?", kind: "line" }] };
  const r9 = await skCall("sk_check", { payload: { ...SK_CARRY, project: punct } });
  const r9bad = r9.structuredContent?.rejected ?? [];
  ok(r9.isError === true && r9bad.some((b) => b.includes("구두점 금지") && b.includes("자막 1줄")), "sk_check(자막 마침표) → G-구두점 반려(?·! 는 허용)", JSON.stringify(r9bad));
}
// S7) 유료 단계 — 비용 보고 지시가 박혀 있다
{
  const cut = await skCall("sk_cut", { payload: { ...SK_CARRY, tts_est: { chars: 15, est_sec: 2.4 } } });
  const sc = cut.structuredContent;
  ok(sc?.next_step === "sk_subs" && sc?.jobs?.[0]?.argv?.includes("make.py"), "sk_cut → make.py argv, next=sk_subs", sc?.jobs?.[0]?.argv?.join(" "));
  ok((sc?.instructions ?? []).join(" ").includes("승인") && /Typecast/.test((sc?.instructions ?? []).join(" ")), "sk_cut → 유료(Typecast) 승인 지시", "");
  ok(/15자/.test(sc?.message ?? ""), "sk_cut → 예상 분량이 메시지에", sc?.message);
  const asr = await skCall("sk_asr", { payload: SK_CARRY });
  ok(asr.structuredContent?.next_step === "sk_sync" && /Speechmatics/.test((asr.structuredContent?.instructions ?? []).join(" ")), "sk_asr → 유료(Speechmatics) 승인 지시, next=sk_sync", "");
}
// S8) sk_subs·sk_sync·sk_recheck·sk_render 사슬
{
  const subs = await skCall("sk_subs", { payload: SK_CARRY });
  ok(subs.structuredContent?.next_step === "sk_asr" && subs.structuredContent?.jobs?.[0]?.argv?.includes("s2pipe.subs"), "sk_subs → next=sk_asr", "");
  const sync = await skCall("sk_sync", { payload: SK_CARRY });
  ok(sync.structuredContent?.next_step === "sk_recheck" && /멈추면 손대지/.test((sync.structuredContent?.instructions ?? []).join(" ")), "sk_sync → next=sk_recheck + 정렬 중단 지시", "");
  ok(/subs_before_sync/.test(sync.structuredContent?.jobs?.[0]?.note ?? ""), "sk_sync → 맞물림 중단 규칙 명시", "");
  const re = await skCall("sk_recheck", { payload: { ...SK_CARRY, project: SK } });
  ok(re.structuredContent?.status === "execute" && re.structuredContent?.next_step === "sk_render", "sk_recheck(정상) → next=sk_render", "");
  const rd = await skCall("sk_render", { payload: SK_CARRY });
  ok(rd.structuredContent?.next_step === "sk_deliver" && /캐시/.test(rd.structuredContent?.message ?? ""), "sk_render → TTS 캐시 재사용, next=sk_deliver", "");
  const missing = await skCall("sk_cut", { payload: {} });
  ok(missing.isError === true && /workdir·project_path/.test(missing.structuredContent?.message ?? ""), "sk_cut(carry 누락) → 반려 + 고치는 법", "");
}
// S9) sk_deliver — 사람확인 + A/B 안내
{
  const res = await skCall("sk_deliver", { payload: SK_CARRY });
  const sc = res.structuredContent;
  ok(sc?.status === "done" && sc?.next_step === null, "sk_deliver → done/null", `${sc?.status}/${sc?.next_step}`);
  ok(Array.isArray(sc?.사람확인) && sc.사람확인.length === 7, "sk_deliver → 사람확인 7항목(G-결말 사람몫 포함)", String(sc?.사람확인?.length));
  ok((sc?.instructions ?? []).join(" ").includes("_B"), "sk_deliver(A 편) → B 편 안내", "");
  const b = await skCall("sk_deliver", { payload: { ...SK_CARRY, source: { ...SK_CARRY.source, kind: "youtube", url: SK.source.url, slug: "TESTID_B" } } });
  ok((b.structuredContent?.instructions ?? []).join(" ").includes("두 채널에 나눠"), "sk_deliver(B 편) → 두 채널 안내", "");
}

// ── 린박스 (프리셋 3호) — 앞 7단계 «볼케이노 산출물 베끼기» · 한 단계씩 (2026-09-04) ──────────
const LB_SRC = { kind: "local_video", path: "C:/drama/신병4_EP4_EPK.mp4", title: "신병4", lang: "ko" };
const LB = { workdir: "C:/lb_work/신병", ep: "EP19", start_s: 1495, end_s: 1635 };
const lbCall = (step, args) => rpc("tools/call", { name: "youstudio_video", arguments: { step, preset: "린박스", ...args } });
// L1) start
{
  const bad = await lbCall("start", { payload: LB });
  ok(bad.structuredContent?.status === "error" && /local_video/.test(bad.structuredContent?.message ?? ""), "린박스 start(소재 없음) → 반려 + 고치는 법", bad.structuredContent?.message?.slice(0, 60));
  const bad2 = await lbCall("start", { source: LB_SRC, payload: { ...LB, ep: "19화" } });
  ok(bad2.structuredContent?.status === "error" && /EP01/.test(bad2.structuredContent?.message ?? ""), "린박스 start(편 이름 꼴 아님) → 반려", bad2.structuredContent?.message?.slice(0, 60));
  const bad3 = await lbCall("start", { source: LB_SRC, payload: { ...LB, end_s: 1400 } });
  ok(bad3.structuredContent?.status === "error" && /start_s/.test(bad3.structuredContent?.message ?? ""), "린박스 start(끝 ≤ 시작) → 반려", bad3.structuredContent?.message?.slice(0, 60));
  const res = await lbCall("start", { source: LB_SRC, payload: LB });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "lb_probe", "린박스 start → execute, next=lb_probe", `${sc?.status}/${sc?.next_step}`);
  ok(sc?.jobs_kind === "argv" && sc?.jobs?.length === 2 && sc.jobs[0].name === "probe" && sc.jobs[1].name === "cropdetect" && sc.jobs[1].argv.includes("cropdetect=24:16:0") && sc.jobs[1].argv[sc.jobs[1].argv.indexOf("-ss") + 1] === "1565", "린박스 start → ffprobe + 구간 한가운데(1565s) cropdetect argv", JSON.stringify(sc?.jobs?.map((j) => j.name)));
  ok(JSON.stringify(sc?.measure?.map((m) => [m.as, m.unit])) === JSON.stringify([["probe", "json_stdout"], ["cropdetect_raw", "stderr"]]), "린박스 start → measure probe(json)·cropdetect_raw(stderr)", JSON.stringify(sc?.measure));
  ok(sc?.ep_dir === "C:/lb_work/신병/작업/EP19" && sc?.carry?.includes("ep") && sc?.carry?.includes("end_s"), "린박스 start → 편 폴더 작업/EP19 · carry 에 편·구간", `${sc?.ep_dir} ${JSON.stringify(sc?.carry)}`);
}
// L2) lb_probe
{
  const LB_CARRY = { source: LB_SRC, ...LB, ep_dir: "C:/lb_work/신병/작업/EP19" };
  const PROBE_LB = { ...PROBE_OK, streams: [{ ...PROBE_OK.streams[0], start_time: "0.000000", duration: "2100.0" }, PROBE_OK.streams[1]], format: { ...PROBE_OK.format, duration: "2100.0" } };
  const CROP = "[Parsed_cropdetect_0 @ 0x1] x1:0 x2:1919 y1:140 y2:939 w:1920 h:800 x:0 y:140 pts:12 t:0.5 crop=1920:800:0:140\n[Parsed_cropdetect_0 @ 0x1] x1:0 x2:1919 y1:140 y2:939 w:1920 h:800 x:0 y:140 pts:24 t:1.0 crop=1920:800:0:140\n";
  const bad = await lbCall("lb_probe", { payload: LB_CARRY });
  ok(bad.structuredContent?.status === "error" && /probe/.test(bad.structuredContent?.message ?? ""), "lb_probe(probe 없음) → 반려", bad.structuredContent?.message?.slice(0, 60));
  const out = await lbCall("lb_probe", { payload: { ...LB_CARRY, probe: PROBE_OK, cropdetect_raw: CROP } });
  ok(out.structuredContent?.status === "error" && /소재 길이/.test(out.structuredContent?.message ?? ""), "lb_probe(구간 끝 1635 > 소재 929초) → 반려", out.structuredContent?.message?.slice(0, 60));
  const res = await lbCall("lb_probe", { payload: { ...LB_CARRY, probe: PROBE_LB, cropdetect_raw: CROP } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "lb_cut", "lb_probe → execute, next=lb_cut", `${sc?.status}/${sc?.next_step}`);
  const m = sc?.metrics ?? {};
  ok(m.fps === 23.976 && m.fps_fraction === "24000/1001" && m.letterbox_top === 140 && m.letterbox_bottom === 140 && m.win === Math.round((800 * 1080) / 1020) && m.span_s === 140, "lb_probe → metrics(fps 23.976 · 레터박스 140/140 · WIN 847 · 구간 140초)", JSON.stringify(m));
  ok(sc?.write_files?.[0]?.path === "C:/lb_work/신병/작업/EP19/프레임률" && sc.write_files[0].content === "24000/1001", "lb_probe → write_files 프레임률 = 24000/1001 (§82)", JSON.stringify(sc?.write_files?.[0]));
  ok(sc?.probe_summary?.letterbox?.content_h === 800 && sc?.carry?.includes("probe_summary"), "lb_probe → probe_summary(레터박스) carry", JSON.stringify(sc?.probe_summary?.letterbox));
  const noCrop = await lbCall("lb_probe", { payload: { ...LB_CARRY, probe: PROBE_LB } });
  ok(noCrop.structuredContent?.status === "execute" && (noCrop.structuredContent?.warnings ?? []).some((w) => /레터박스/.test(w)) && noCrop.structuredContent?.metrics?.win === Math.round((1080 * 1080) / 1020), "lb_probe(cropdetect 없음) → 경고 + WIN 은 원본 높이로", JSON.stringify(noCrop.structuredContent?.warnings));
}

// L3) lb_cut
{
  const LB_CARRY = { source: LB_SRC, ...LB, ep_dir: "C:/lb_work/신병/작업/EP19", probe_summary: { fps_fraction: "24000/1001", win: 847 } };
  const bad = await lbCall("lb_cut", { payload: { ...LB_CARRY } });
  ok(bad.structuredContent?.status === "error" && /payload\.repo/.test(bad.structuredContent?.message ?? ""), "lb_cut(repo 없음) → 반려 + 고치는 법", bad.structuredContent?.message?.slice(0, 60));
  const res = await lbCall("lb_cut", { payload: { ...LB_CARRY, repo: "C:/youstudio-mcp" } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "lb_transcript" && sc?.jobs_cwd === "C:/lb_work/신병/작업/EP19", "lb_cut → execute, next=lb_transcript, jobs_cwd=편 폴더", `${sc?.status}/${sc?.next_step}/${sc?.jobs_cwd}`);
  const names = sc?.jobs?.map((j) => j.name);
  ok(JSON.stringify(names) === JSON.stringify(["cut", "keep", "cut_probe", "scene_cuts"]), "lb_cut → jobs 4 (cut·keep·cut_probe·scene_cuts)", JSON.stringify(names));
  const cut = sc?.jobs?.[0]?.argv ?? [];
  ok(cut.indexOf("-i") < cut.indexOf("-ss") && cut[cut.indexOf("-ss") + 1] === "1495" && cut[cut.indexOf("-to") + 1] === "1635" && cut.includes("libx264") && cut[cut.indexOf("-crf") + 1] === "16" && cut[cut.indexOf("-b:a") + 1] === "320k" && !cut.includes("-r") && cut.at(-1) === "C:/lb_work/신병/작업/EP19/구간.mp4", "lb_cut → cut argv: -i 뒤 -ss/-to · 재인코딩 crf16 · 320k · -r 없음", cut.join(" ").slice(0, 120));
  ok(sc?.jobs?.[1]?.argv?.includes("copy") && sc.jobs[1].argv.at(-1) === "C:/lb_work/신병/작업/EP19/구간_원본.mp4", "lb_cut → keep: 구간_원본.mp4 스트림 복사(§84)", sc?.jobs?.[1]?.argv?.join(" "));
  ok(sc?.jobs?.[3]?.argv?.[1] === "C:/youstudio-mcp/서버/runner/린박스/도구/장면컷.py" && sc.jobs[3].argv.includes("--쓰기"), "lb_cut → scene_cuts: repo 밑 러너 도구 장면컷.py --쓰기", sc?.jobs?.[3]?.argv?.join(" "));
  ok(JSON.stringify(sc?.measure?.map((m) => [m.as, m.unit])) === JSON.stringify([["cut_probe", "json_stdout"], ["scene_cuts_log", "stdout"]]) && sc?.carry?.includes("repo") && sc?.carry?.includes("probe_summary"), "lb_cut → measure(cut_probe·scene_cuts_log) · carry 에 repo·probe_summary", JSON.stringify(sc?.measure));
}

// L4) lb_transcript — ① 절단 검사 + 유료 지시 ② 결과 검사
{
  const LB_C = { source: LB_SRC, ...LB, ep_dir: "C:/lb_work/신병/작업/EP19", repo: "C:/youstudio-mcp", probe_summary: { fps_fraction: "24000/1001" } };
  const CUT_PROBE = { streams: [{ codec_type: "video", start_time: "0.000000", duration: "140.02" }, { codec_type: "audio" }], format: { duration: "140.021000" } };
  const SCENE_LOG = "소재 구간.mp4 — 140.0초 · 23.98fps · 프레임 3357개\n찾은 장면전환 21개  (9.0개/분)\nscene_cuts.txt 에 21개를 적었다.\n";
  const bad = await lbCall("lb_transcript", { payload: LB_C });
  ok(bad.structuredContent?.status === "error" && /cut_probe/.test(bad.structuredContent?.message ?? ""), "lb_transcript(cut_probe 없음) → 반려", bad.structuredContent?.message?.slice(0, 50));
  const short = await lbCall("lb_transcript", { payload: { ...LB_C, cut_probe: { ...CUT_PROBE, format: { duration: "120.0" } }, scene_cuts_log: SCENE_LOG } });
  ok(short.structuredContent?.status === "error" && /0\.5초/.test(short.structuredContent?.message ?? ""), "lb_transcript(절단본 120초 ≠ 140초) → 반려 + 재절단 지시", short.structuredContent?.message?.slice(0, 60));
  const res = await lbCall("lb_transcript", { payload: { ...LB_C, cut_probe: CUT_PROBE, scene_cuts_log: SCENE_LOG, dictionary: [{ content: "김현욱", sounds_like: ["김현국"] }] } });
  const sc = res.structuredContent;
  ok(sc?.status === "execute" && sc?.next_step === "lb_transcript" && sc?.jobs_cwd === "C:/lb_work/신병/작업/EP19", "lb_transcript① → execute, 다시 자기 자신(검사 위해), cwd 편 폴더", `${sc?.status}/${sc?.next_step}`);
  ok(/유료/.test(sc?.message ?? "") && /7분/.test(sc?.message ?? "") && /승인/.test(sc?.instructions?.[0] ?? ""), "lb_transcript① → ★유료 비용(140초×3벌 = 7분) 보고·승인 지시", sc?.message?.slice(0, 80));
  ok(sc?.do?.[0]?.name === "write_dict" && sc.do[0].argv.at(-1).includes("김현욱"), "lb_transcript① → do: 사전.json(낱말사전) 먼저 쓰기", sc?.do?.[0]?.argv?.at(-1)?.slice(0, 60));
  ok(JSON.stringify(sc?.jobs?.map((j) => j.name)) === JSON.stringify(["transcribe", "speakers", "read_words"]) && sc.jobs[0].argv[1] === "C:/youstudio-mcp/서버/runner/린박스/도구/전사.py" && sc.jobs[1].optional === true, "lb_transcript① → jobs 전사.py·화자표.py(optional)·대사 읽기", JSON.stringify(sc?.jobs?.map((j) => j.name)));
  ok(sc?.metrics?.scene_count === 21 && sc?.scene_count === 21 && sc?.carry?.includes("scene_count"), "lb_transcript① → 장면컷 21개 읽어 carry", JSON.stringify(sc?.metrics));
  const WORDS = { words: [{ s: 0.74, e: 1.43, t: "기절했어", c: 0.9, spk: "S1", votes: 3, sure: true }, { s: 2.03, e: 2.15, t: "주", c: 0.5, spk: "S1", votes: 1, sure: false }, { s: 6.3, e: 7.78, t: "일이", c: 0.95, spk: "S2", votes: 3, sure: true }] };
  const empty = await lbCall("lb_transcript", { payload: { ...LB_C, scene_count: 21, 대사: { words: [] } } });
  ok(empty.structuredContent?.status === "error" && /낱말이 하나도/.test(empty.structuredContent?.message ?? ""), "lb_transcript②(낱말 0) → 반려", empty.structuredContent?.message?.slice(0, 50));
  const r2 = await lbCall("lb_transcript", { payload: { ...LB_C, scene_count: 21, 대사: WORDS } });
  const s2 = r2.structuredContent;
  ok(s2?.status === "execute" && s2?.next_step === "lb_plan" && s2?.metrics?.words === 3 && s2?.metrics?.speech_s === 2.29 && s2?.metrics?.sure_ratio_pct === 67 && s2?.metrics?.speakers === 2 && s2?.carry?.includes("대사"), "lb_transcript② → next=lb_plan · metrics(낱말 3·말 2.29초·일치 67%·화자 2) · 대사 carry", JSON.stringify(s2?.metrics));
}

// L5) lb_plan — ① 쓸거리·밀도 게이트 → need_input(하단) ② 편정보 검사 → write_files
{
  const LB_C = { source: LB_SRC, ...LB, ep_dir: "C:/lb_work/신병/작업/EP19", repo: "C:/youstudio-mcp", probe_summary: { fps_fraction: "24000/1001" }, scene_count: 21 };
  // 말 40초 → 어림 52초 (통과) · 앞 30초 창 비어 있음
  const mk = (n, from, each = 1.0, gap = 0.2) => Array.from({ length: n }, (_, i) => ({ s: from + i * (each + gap), e: from + i * (each + gap) + each, t: "말", sure: true, spk: "S1" }));
  const WORDS_OK = { words: mk(40, 40) };
  const WORDS_SHORT = { words: mk(10, 5) };
  const r0 = await lbCall("lb_plan", { payload: { ...LB_C } });
  ok(r0.structuredContent?.status === "error" && /대사/.test(r0.structuredContent?.message ?? ""), "lb_plan(대사 없음) → 반려", r0.structuredContent?.message?.slice(0, 50));
  const r1 = await lbCall("lb_plan", { payload: { ...LB_C, 대사: WORDS_SHORT } });
  ok(r1.structuredContent?.status === "error" && r1.structuredContent?.next_step === "start" && /막힘/.test(r1.structuredContent?.message ?? "") && r1.structuredContent?.metrics?.est_final_s < 40, "lb_plan(말 10초) → ★막힘(§83) · start 로 돌아가 다른 구간", `${r1.structuredContent?.metrics?.est_final_s}`);
  const r2 = await lbCall("lb_plan", { payload: { ...LB_C, 대사: WORDS_OK, used_ranges: [[1495 + 40, 1495 + 45]] } });
  const s2 = r2.structuredContent;
  ok(s2?.status === "need_input" && s2?.next_step === "lb_plan" && s2?.need_input?.keys?.includes("편정보.로고") && s2?.need_input?.keys?.includes("편정보.하단확인"), "lb_plan① → need_input(하단: 로고·크레딧·방영정보·크레딧함께·하단확인)", JSON.stringify(s2?.need_input?.keys));
  const m2 = s2?.metrics ?? {};
  ok(m2.speech_s === 40 && m2.overlap_s === 4.2 && m2.usable_s === 35.8 && m2.est_final_s === 46.494 && m2.empty_30s_windows === 3 && m2.max_gap_s === 52.2 && m2.max_gap_at_s === 87.8, "lb_plan① → metrics(말 40초 · 겹침 4.2 · 어림 46.5 · 빈 창 3/5 · 최대 틈 52.2초 꼬리)", JSON.stringify(m2));
  ok((s2?.warnings ?? []).some((w) => /겹친다/.test(w)) && (s2?.warnings ?? []).some((w) => /무음|틈/.test(w)) && s2?.편정보_틀?.마스터 === "신병4_EP4_EPK.mp4" && s2?.편정보_틀?.로고y === 1504, "lb_plan① → 겹침·긴 틈 경고 · 편정보 틀(마스터·로고y 1504)", JSON.stringify(s2?.warnings));
  const bad = await lbCall("lb_plan", { payload: { ...LB_C, 대사: WORDS_OK, 편정보: { 로고: "없음", 크레딧: [], 하단확인: false } } });
  ok(bad.structuredContent?.status === "error" && /크레딧 문구가 비었다/.test(bad.structuredContent?.message ?? "") && /하단확인/.test(bad.structuredContent?.message ?? ""), "lb_plan②(크레딧 비고 하단확인 false) → 반려 2건", bad.structuredContent?.message?.slice(0, 80));
  const bad2 = await lbCall("lb_plan", { payload: { ...LB_C, 대사: WORDS_OK, 편정보: { 로고: "C:/drama/logo_w.png", 크레딧: ["<작품명>", "지금 정주행!"], 로고y: 1800, 하단확인: true } } });
  ok(bad2.structuredContent?.status === "error" && /보기 문구/.test(bad2.structuredContent?.message ?? "") && /매트/.test(bad2.structuredContent?.message ?? ""), "lb_plan②(보기 문구·로고 매트 밖) → 반려", bad2.structuredContent?.message?.slice(0, 80));
  const r3 = await lbCall("lb_plan", { payload: { ...LB_C, 대사: WORDS_OK, 편정보: { 로고: "C:/drama/New Recruit_logo_w.png", 크레딧: ["〈신병4 사보타주〉", "는 본편에서!"], 방영정보: "", 크레딧함께: false, 하단확인: true } } });
  const s3 = r3.structuredContent;
  ok(s3?.status === "execute" && s3?.next_step === "lb_script" && s3?.jobs?.[0]?.name === "copy_logo" && s3.jobs[0].argv.at(-1) === "C:/drama/New Recruit_logo_w.png", "lb_plan② → execute, next=lb_script, 로고 복사 job", `${s3?.status}/${s3?.next_step}`);
  const wf = s3?.write_files?.[0];
  ok(wf?.path === "C:/lb_work/신병/작업/EP19/편정보.json" && wf?.content?.로고 === "logo/logo_bottom.png" && wf?.content?.완성본 === "자동" && wf?.content?.구간오프셋 === 1495 && wf?.content?.마스터 === "신병4_EP4_EPK.mp4" && wf?.content?.하단확인 === true && wf?.content?.나레TTS?.voice?.includes("tc_62686be9deec4c1bb7fd077c"), "lb_plan② → write_files 편정보.json(로고 logo/logo_bottom.png · 완성본 자동 · 구간오프셋 1495 · 이나)", JSON.stringify(wf?.content).slice(0, 160));
  const r4 = await lbCall("lb_plan", { payload: { ...LB_C, 대사: WORDS_OK, 편정보: { 로고: "없음", 크레딧: ["<더 글로리>는", "넷플릭스에서!"], 하단확인: true } } });
  ok(r4.structuredContent?.status === "execute" && r4.structuredContent?.jobs?.length === 0 && r4.structuredContent?.write_files?.[0]?.content?.로고 === "없음", "lb_plan②(로고 없음) → 복사 job 없음 · 로고 «없음»", JSON.stringify(r4.structuredContent?.write_files?.[0]?.content?.로고));
}

// L6) lb_script — ① need_input ② 서버 검사 + 게이트 도구 ③ 로그 검사
{
  const 편정보 = { 제목: ["", ""], 크레딧: ["〈신병4 사보타주〉", "는 본편에서!"], 로고: "logo/logo_bottom.png", 하단확인: true };
  const LB_C = { source: LB_SRC, ...LB, ep_dir: "C:/lb_work/신병/작업/EP19", repo: "C:/youstudio-mcp", probe_summary: {}, scene_count: 21, 대사: { words: [{ s: 1, e: 2, t: "말" }] }, 편정보 };
  const r1 = await lbCall("lb_script", { payload: LB_C });
  ok(r1.structuredContent?.status === "need_input" && r1.structuredContent?.need_input?.keys?.includes("title_choice") && r1.structuredContent?.need_input?.keys?.includes("authored"), "lb_script① → need_input(authored·title_candidates·title_choice)", JSON.stringify(r1.structuredContent?.need_input?.keys));
  const D = (s, e, cap) => [s, e, cap, "quote", cap.replace(/\|/g, " ")];
  const GOOD = {
    HEADLINE: ["폭로 글 범인으로", "몰린 신병의 정체"], CREDIT: 편정보.크레딧,
    BLOCKS: [
      ["N", "부대 카페에 총기 사고 은폐 글이 올라왔는데", [[2.15, 1]]],
      ["D", [D(6.3, 7.78, "일이 있는|거 아냐"), D(15.04, 17.05, "아 이거 뭐야|미치겠네")]],
      ["N", "누군가 부대 카페에 글을 올린 거였고", [[20.0, 1]]],
      ["D", [D(24.0, 40.0, "이병 김현욱"), D(41.0, 60.0, "현욱아 그냥|말을 해")]],
      ["N", "선임을 두고 먼저 들어가 버린 신병이었던 거죠", [[70.0, 1]]],
    ],
    EFFECTS_BY_BLOCK: [[0, 0.15, 0.85, "#F070C0", "비상", 540, 640], [3, 0.2, 0.85, "#F070C0", "추궁", 540, 640], [3, 0.5, 0.85, "#F070C0", "한숨", 540, 700], [4, 0.1, 0.85, "#F070C0", "하극상", 540, 640]],
    강조: ["말을 해"],
  };
  const noChoice = await lbCall("lb_script", { payload: { ...LB_C, authored: GOOD } });
  ok(noChoice.structuredContent?.status === "error" && /title_choice/.test(noChoice.structuredContent?.message ?? ""), "lb_script②(사장님 선택 없음) → 반려", noChoice.structuredContent?.message?.slice(0, 60));
  const BAD = { ...GOOD, HEADLINE: ["폭로 글 범인으로 몰린 신병", "정체😱"], BLOCKS: [["N", "부대 카페에, 글이", [[2, 1]]], ["D", [D(6.3, 7.78, "일이 있는 거 아냐.")]]], EFFECTS_BY_BLOCK: [[0, 0.1, 0.8, "#F070C0", "비상", 540, 1300]] };
  const bad = await lbCall("lb_script", { payload: { ...LB_C, authored: BAD, title_choice: BAD.HEADLINE } });
  const bm = bad.structuredContent?.message ?? "";
  ok(bad.structuredContent?.status === "error" && /10자/.test(bm) && /이모지/.test(bm) && /구두점/.test(bm) && /안전대/.test(bm) && /최소 40초/.test(bm), "lb_script②(10자 초과·이모지·구두점·모션 y 밖·길이 미달) → 반려 사유 전부", bm.slice(0, 120));
  const r2 = await lbCall("lb_script", { payload: { ...LB_C, authored: GOOD, title_candidates: [GOOD.HEADLINE, ["a", "b"], ["c", "d"], ["e", "f"]], title_choice: GOOD.HEADLINE } });
  const s2 = r2.structuredContent;
  ok(s2?.status === "execute" && s2?.next_step === "lb_script" && s2?.do?.[0]?.name === "write_authored" && JSON.stringify(s2?.jobs?.map((j) => j.name)) === JSON.stringify(["script_check", "title_check"]) && s2?.jobs?.[0]?.argv?.[1] === "C:/youstudio-mcp/서버/runner/린박스/도구/대본검사.py", "lb_script② → authored.json 쓰기(do) + 대본검사·제목검사 jobs, 다시 자기 자신", JSON.stringify(s2?.jobs?.map((j) => j.name)));
  const m = s2?.metrics ?? {};
  ok(m.n_blocks === 3 && m.d_blocks === 2 && m.dlg_sec === 38.49 && m.narr_chars === 52 && m.narr_sec === 5.098 && m.est_sec === 43.588 && m.dlg_ratio_pct === 88 && m.effects === 4 && m.emph === 1, "lb_script② → metrics(N3 D2 · 원음 38.49초 · 나레 52자=5.1초 · 어림 43.6 · 88:12 · 모션 4 · 강조 1)", JSON.stringify(m));
  ok((s2?.warnings ?? []).some((w) => /15~19장/.test(w)), "lb_script② → 나레 3장(15~19 밖) 경고", JSON.stringify(s2?.warnings));
  const fail = await lbCall("lb_script", { payload: { ...LB_C, authored: GOOD, title_choice: GOOD.HEADLINE, script_log: "■ 대본 검사\n  ✗ b03  전환 24.500 → 앞 0.50초 / 뒤 15.50초\n  막힘 1건 — 고치기 전에는 굽지 마라\n", title_log: "  제목이 지침서를 지킨다 ✓\n" } });
  ok(fail.structuredContent?.status === "error" && /막았다/.test(fail.structuredContent?.message ?? "") && /b03/.test(fail.structuredContent?.message ?? ""), "lb_script③(대본검사 ✗) → 반려 + 고치는 길", fail.structuredContent?.message?.slice(0, 80));
  const r3 = await lbCall("lb_script", { payload: { ...LB_C, authored: GOOD, title_choice: GOOD.HEADLINE, script_log: "  대본에서 보이는 튐 없음 ✓\n", title_log: "  제목이 지침서를 지킨다 ✓\n", script_metrics: m } });
  const s3 = r3.structuredContent;
  ok(s3?.status === "execute" && s3?.next_step === "lb_voice" && s3?.write_files?.[0]?.path?.endsWith("/편정보.json") && JSON.stringify(s3.write_files[0].content?.제목) === JSON.stringify(GOOD.HEADLINE) && s3?.carry?.includes("authored"), "lb_script③ → next=lb_voice · 편정보 제목 갱신 · authored carry", JSON.stringify(s3?.write_files?.[0]?.content?.제목));
}

// L7) lb_voice — ① Typecast synthesize 지시 ② wav 검사 → narr_align ③ narr_words 검사
{
  const AUTH = { HEADLINE: ["폭로 글 범인으로", "몰린 신병의 정체"], CREDIT: ["a", "b"], BLOCKS: [["N", "부대 카페에 총기 사고 은폐 글이 올라왔는데", [[2.15, 1]]], ["D", [[6.3, 7.78, "일이 있는 거 아냐", "quote", "일이 있는 거 아냐"]]], ["N", "누군가 부대 카페에 3개 글을 올린 거였고", [[20, 1]]]], EFFECTS_BY_BLOCK: [] };
  const LB_C = { source: LB_SRC, ...LB, ep_dir: "C:/lb_work/신병/작업/EP19", repo: "C:/youstudio-mcp", probe_summary: {}, scene_count: 21, 대사: { words: [] }, 편정보: {}, authored: AUTH };
  const r0 = await lbCall("lb_voice", { payload: { ...LB_C, authored: { BLOCKS: [["D", [[1, 2, "x", "quote", "x"]]]] } } });
  ok(r0.structuredContent?.status === "error" && /나레\(N\) 블록이 없다/.test(r0.structuredContent?.message ?? ""), "lb_voice(N 블록 없음) → 반려", r0.structuredContent?.message?.slice(0, 50));
  const r1 = await lbCall("lb_voice", { payload: LB_C });
  const s1 = r1.structuredContent;
  ok(s1?.status === "execute" && s1?.next_step === "lb_voice" && s1?.jobs_kind === "synthesize" && s1?.jobs?.length === 2 && s1?.jobs_cwd === "C:/lb_work/신병/작업/EP19", "lb_voice① → synthesize 2건(N 블록 0·2), 다시 자기 자신", `${s1?.jobs_kind}/${s1?.jobs?.length}`);
  const j0 = s1?.jobs?.[0] ?? {};
  ok(j0.name === "n00" && j0.provider === "typecast" && j0.request?.url === "https://api.typecast.ai/v1/text-to-speech" && j0.request?.body?.voice_id === "tc_62686be9deec4c1bb7fd077c" && j0.request?.body?.prompt?.emotion_preset === "normal" && j0.request?.body?.output?.audio_tempo === 1.2 && j0.request?.body?.model === "ssfm-v30" && j0.auth?.header === "X-API-KEY" && j0.auth?.env === "TYPECAST_API_KEY", "lb_voice① → Typecast 본문 = 이나·normal·1.2배속·ssfm-v30, X-API-KEY 본인 키", JSON.stringify(j0.request?.body).slice(0, 120));
  ok(/\/cache\/tts\/[0-9a-f]{16}\.raw\.wav$/.test(j0.out ?? "") && j0.skip_if?.min_bytes === 2000 && j0.post_steps?.length === 2 && j0.post_steps[1].out === "C:/lb_work/신병/작업/EP19/blocks/n00.wav" && j0.post_steps[0].out === "C:/lb_work/신병/작업/EP19/narr_norm/n00.wav", "lb_voice① → raw 캐시 키 16자 · skip_if 2000B · 후처리 2단계(narr_norm 1ch → blocks 2ch)", `${j0.out} ${JSON.stringify(j0.post_steps?.map((s) => s.out))}`);
  ok(s1?.post?.length === 4 && s1.post[1].argv.includes("silenceremove=start_periods=1:start_threshold=-38dB:start_silence=0.1:stop_periods=-1:stop_threshold=-38dB:stop_duration=0.20:stop_silence=0.02,loudnorm=I=-23:TP=-3:LRA=9") && s1.post[0].argv.includes("loudnorm=I=-23.0:TP=-3:LRA=9"), "lb_voice① → post ffmpeg 4건(볼케이노 stitch_narr steps 그대로)", JSON.stringify(s1?.post?.map((p) => p.name)));
  ok(JSON.stringify(s1?.measure?.map((m) => [m.as, m.unit])) === JSON.stringify([["n00_secs", "seconds"], ["n02_secs", "seconds"]]) && /유료/.test(s1?.message ?? "") && /35자/.test(s1?.message ?? "") && (s1?.warnings ?? []).some((w) => /숫자/.test(w)), "lb_voice① → measure nNN_secs · ★유료 글자 수(35자) 보고 · 숫자 경고", `${s1?.message?.slice(0, 60)} ${JSON.stringify(s1?.warnings)}`);
  const sameKey = await lbCall("lb_voice", { payload: LB_C });
  ok(sameKey.structuredContent?.jobs?.[0]?.out === j0.out, "lb_voice① → 같은 문장 = 같은 캐시 키(재과금 없음)", "");
  const bad = await lbCall("lb_voice", { payload: { ...LB_C, n00_secs: 2.29, n02_secs: 0.1 } });
  ok(bad.structuredContent?.status === "error" && /너무 짧다/.test(bad.structuredContent?.message ?? ""), "lb_voice②(n02 0.1초) → 반려", bad.structuredContent?.message?.slice(0, 60));
  const r2 = await lbCall("lb_voice", { payload: { ...LB_C, n00_secs: 2.29, n02_secs: 1.96 } });
  const s2 = r2.structuredContent;
  ok(s2?.status === "execute" && s2?.next_step === "lb_voice" && s2?.jobs?.[0]?.name === "narr_align" && s2.jobs[0].argv[1] === "C:/youstudio-mcp/서버/runner/린박스/도구/narr_align.py" && /Speechmatics 1건/.test(s2?.message ?? "") && s2?.wav_secs?.["0"] === 2.29 && s2?.metrics?.chars_per_sec === 8.235, "lb_voice② → wav 확인(4.25초·35자=8.2자/초) → ★Speechmatics narr_align 지시", JSON.stringify(s2?.metrics));
  const r3 = await lbCall("lb_voice", { payload: { ...LB_C, wav_secs: { "0": 2.29, "2": 1.96 }, narr_words: { "0": [[0.1, 0.5, "부대"]], "2": [] } } });
  ok(r3.structuredContent?.status === "error" && /낱말이 없는 나레 블록: 2/.test(r3.structuredContent?.message ?? ""), "lb_voice③(블록 2 낱말 없음) → 반려", r3.structuredContent?.message?.slice(0, 60));
  const r4 = await lbCall("lb_voice", { payload: { ...LB_C, wav_secs: { "0": 2.29, "2": 1.96 }, narr_words: { "0": [[0.1, 0.5, "부대"], [0.6, 1.0, "카페에"]], "2": [[0.2, 0.7, "누군가"]] } } });
  ok(r4.structuredContent?.status === "execute" && r4.structuredContent?.next_step === "lb_blocks" && r4.structuredContent?.metrics?.narr_words === 3 && r4.structuredContent?.carry?.includes("narr_words"), "lb_voice③ → next=lb_blocks · narr_words 3 · carry", JSON.stringify(r4.structuredContent?.metrics));
}

console.log(process.exitCode ? "\n실패 있음" : "\n전부 통과");
