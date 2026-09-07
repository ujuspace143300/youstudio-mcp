// test/kv-smoke.mjs — 대장(KV) 인증 경로 스모크. test/kv-smoke.sh 가 로컬 KV 에 TOK_LB(린박스만 허용)를 넣고 띄운 서버로 돈다.
//   환경: MCP_URL · YOUSTUDIO_TOKEN(대장 토큰) · YOUSTUDIO_DEVICE · ADMIN_TOKEN
import crypto from "node:crypto";
const URL_ = process.env.MCP_URL ?? "http://127.0.0.1:8791";
const TOK = process.env.YOUSTUDIO_TOKEN ?? "TOK_LB", DEV = process.env.YOUSTUDIO_DEVICE ?? "devA", ADMIN = process.env.ADMIN_TOKEN ?? "";
const H = { authorization: "Bearer " + TOK, "x-youstudio-device": DEV };
let fail = 0;
function ok(c, label, extra = "") { if (c) console.log("  ✓ " + label + " " + extra); else { console.error("  ✗ " + label + " " + extra); fail = 1; } }
const j = async (r) => { try { return await r.json(); } catch { return {}; } };
console.log("대장 스모크: " + URL_);
const health = await j(await fetch(URL_ + "/health"));
ok(health.auth === "license" && health.assets === true, "/health auth=license · assets", JSON.stringify(health));
ok((await fetch(URL_ + "/asset/린박스/_목록.json")).status === 401, "무토큰 /asset → 401");
ok((await fetch(URL_ + "/asset/린박스/_목록.json", { headers: { authorization: "Bearer " + TOK } })).status === 401, "토큰만(기기 없음) /asset → 401(-32005)");
const man = await fetch(URL_ + "/asset/린박스/_목록.json", { headers: H });
const m = await j(man);
ok(man.status === 200 && Array.isArray(m.files) && m.files.length >= 3, "발급 토큰+기기 → /asset/린박스/_목록.json 200 · 파일 " + (m.files?.length ?? "?"), String(man.status));
let allOk = true;
for (const f of m.files ?? []) {
  const r = await fetch(URL_ + "/asset/린박스/" + f.path.split("/").map(encodeURIComponent).join("/"), { headers: H });
  const buf = Buffer.from(await r.arrayBuffer());
  const sha = crypto.createHash("sha256").update(buf).digest("hex");
  if (!(r.status === 200 && buf.length === f.bytes && sha === f.sha256)) { allOk = false; console.error("    ✗ " + f.path + " " + r.status + " " + buf.length + "/" + f.bytes); }
}
ok(allOk, "발급 토큰+기기 → 린박스 자산 전부 200 · 바이트·sha256 일치 (" + (m.files?.length ?? 0) + "개)");
const other = await fetch(URL_ + "/asset/스케치코미디/_목록.json", { headers: H });
ok(other.status === 401 && (await j(other)).error?.code === -32007, "허용 안 된 프리셋 /asset → 401 -32007");
ok((await fetch(URL_ + "/asset/린박스/fonts/없는파일.otf", { headers: H })).status === 404, "있는 프리셋·없는 파일 → 404");
const mcp = await fetch(URL_ + "/", { method: "POST", headers: { ...H, "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "youstudio_video", arguments: { step: "setup", preset: "린박스" } } }) });
ok(mcp.status === 200, "발급 토큰+기기 → MCP tools/call 린박스 setup 200", String(mcp.status));
const mcp2 = await fetch(URL_ + "/", { method: "POST", headers: { ...H, "content-type": "application/json", accept: "application/json, text/event-stream", "mcp-protocol-version": "2025-11-25" }, body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "youstudio_video", arguments: { step: "setup", preset: "스케치코미디" } } }) });
ok(mcp2.status === 401, "발급 토큰 → MCP 스케치코미디 → 401(프리셋 권한)", String(mcp2.status));
if (ADMIN) {
  ok((await fetch(URL_ + "/admin/api/list", { headers: H })).status === 401, "대장 토큰으로 /admin/api → 401");
  const lst = await j(await fetch(URL_ + "/admin/api/list", { headers: { authorization: "Bearer " + ADMIN } }));
  ok(Array.isArray(lst.rows) && lst.rows.length === 1 && !JSON.stringify(lst).includes(TOK), "관리자 목록 1줄 · 토큰 값 노출 없음", JSON.stringify(lst.rows?.[0]?.presets));
  const iss = await j(await fetch(URL_ + "/admin/api/issue", { method: "POST", headers: { authorization: "Bearer " + ADMIN, "content-type": "application/json" }, body: JSON.stringify({ email: "f@x.com", days: 30, maxDevices: 2, presets: ["스케치코미디"] }) }));
  ok(typeof iss.token === "string" && iss.token.length >= 40, "관리자 발급 → 토큰 1회");
  const r2 = await fetch(URL_ + "/asset/스케치코미디/_목록.json", { headers: { authorization: "Bearer " + iss.token, "x-youstudio-device": "devB" } });
  ok(r2.status === 200 && ((await j(r2)).files?.length ?? 0) > 100, "새 발급 토큰 → 스케치코미디 자산 목록 200");
  const rid = iss.license?.id;
  const rv = await j(await fetch(URL_ + "/admin/api/revoke", { method: "POST", headers: { authorization: "Bearer " + ADMIN, "content-type": "application/json" }, body: JSON.stringify({ id: rid }) }));
  ok(rv.ok === true && (await fetch(URL_ + "/asset/스케치코미디/_목록.json", { headers: { authorization: "Bearer " + iss.token, "x-youstudio-device": "devB" } })).status === 401, "폐기 → 그 토큰 /asset 401");
}
console.log(fail ? "\n실패 있음" : "\n전부 통과");
process.exit(fail);
