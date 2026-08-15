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
  ok(sc?.status === "not_implemented" && /단계와게이트/.test(sc?.message ?? ""), "select → not_implemented 스텁", sc?.message);
}

console.log(process.exitCode ? "\n실패 있음" : "\n전부 통과");
