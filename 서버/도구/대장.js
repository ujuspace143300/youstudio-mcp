#!/usr/bin/env node
/**
 * 도구/대장.js — 발급 대장 관리(사장님 컴퓨터에서만). 이메일 허가제.
 *   설계: 설계/인증_이메일허가제.md
 *
 * 대장은 Cloudflare KV(LICENSES)에 산다. 이 도구는 wrangler 를 통해 KV 를 읽고 쓴다
 *   (원격 KV: --remote). 로컬 테스트만 하려면 --local.
 *
 * 명령:
 *   node 도구/대장.js 발급  <이메일> [--일수 90] [--대수 2] [--프리셋 린박스,스케치코미디]   새 토큰 발급(랜덤) → 토큰 출력
 *   node 도구/대장.js 프리셋추가 <토큰> <프리셋>                 허용프리셋에 넣는다 (기본 전부 거부 — 명시한 것만 허용)
 *   node 도구/대장.js 프리셋빼기 <토큰> <프리셋>                 허용프리셋에서 뺀다
 *   node 도구/대장.js 목록                                       이메일·만료·기기수·차단 표
 *   node 도구/대장.js 보기  <토큰>                               한 줄 상세
 *   node 도구/대장.js 막기  <토큰>                               blocked=true
 *   node 도구/대장.js 풀기  <토큰>                               blocked=false
 *   node 도구/대장.js 연장  <토큰> <일수>                        만료일을 오늘+일수 로
 *   node 도구/대장.js 기기초기화 <토큰>                          devices=[] (지인 컴퓨터 교체 시)
 *   node 도구/대장.js 대수  <토큰> <수>                          maxDevices 변경(1~50)
 *   node 도구/대장.js 폐기  <토큰>                               대장에서 삭제
 *
 * ★토큰 값은 발급 때 한 번만 화면에 나온다. 대장(KV)에는 토큰이 「키」로만 있고
 *   값 필드에 평문으로 두지 않는다(키 보호 규칙). 잃으면 폐기하고 재발급한다.
 *
 * ※wrangler 를 spawn 한다. 바인딩 이름 LICENSES 는 wrangler.jsonc 와 같아야 한다.
 */
"use strict";
const { execFileSync } = require("node:child_process");
const crypto = require("node:crypto");
const path = require("node:path");

const 서버 = path.resolve(__dirname, "..");
const BINDING = "LICENSES";
const DEVICE_CAP = 50;
const remoteFlag = process.argv.includes("--local") ? [] : ["--remote"];

function arg(name, def) {
  const i = process.argv.indexOf(name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
function ymd(ms) { return new Date(ms).toISOString().slice(0, 10); }

function kv(args) {
  return execFileSync("npx", ["wrangler", "kv", ...args, "--binding", BINDING, ...remoteFlag], {
    cwd: 서버, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"],
  });
}
function kvGet(token) {
  try { return JSON.parse(kv(["key", "get", token])); }
  catch { return null; }
}
function kvPut(token, obj) {
  const tmp = path.join(require("node:os").tmpdir(), "lic_" + Date.now() + ".json");
  require("node:fs").writeFileSync(tmp, JSON.stringify(obj), "utf8");
  kv(["key", "put", token, "--path", tmp]);
  require("node:fs").unlinkSync(tmp);
}

const [, , cmd, a1, a2] = process.argv;

if (cmd === "발급") {
  const email = a1;
  if (!email) { console.error("이메일이 필요하다"); process.exit(1); }
  const days = parseInt(arg("--일수", "90"), 10);
  const dev = Math.min(Math.max(1, parseInt(arg("--대수", "2"), 10)), DEVICE_CAP);
  const token = crypto.randomBytes(32).toString("base64url");
  const now = Date.now();
  const presets = arg("--프리셋", "").split(",").map((s) => s.trim()).filter(Boolean);
  const lic = {
    email, issued: ymd(now), expires: ymd(now + days * 86400000),
    maxDevices: dev, devices: [], blocked: false, presets,
  };
  kvPut(token, lic);
  console.log("발급 완료 — 이 토큰을 지인에게 전달한다(한 번만 보인다):\n");
  console.log("  " + token + "\n");
  console.log(`  이메일 ${email} · 만료 ${lic.expires} · 기기 ${dev}대 · 허용프리셋 ${presets.length ? presets.join("·") : "없음(전부 거부 — 프리셋추가 로 넣어라)"}`);
} else if (cmd === "목록") {
  const out = kv(["key", "list"]);
  let keys = [];
  try { keys = JSON.parse(out); } catch { keys = []; }
  console.log("이메일\t만료\t기기\t대수\t차단\t허용프리셋");
  for (const k of keys) {
    const l = kvGet(k.name);
    if (l) console.log(`${l.email}\t${l.expires}\t${l.devices.length}\t${l.maxDevices}\t${l.blocked ? "★차단" : "-"}\t${(l.presets || []).join(",") || "없음"}`);
  }
} else if (cmd === "보기") {
  console.log(JSON.stringify(kvGet(a1), null, 2));
} else if (cmd === "막기" || cmd === "풀기") {
  const l = kvGet(a1); if (!l) { console.error("없는 토큰"); process.exit(1); }
  l.blocked = cmd === "막기"; kvPut(a1, l);
  console.log(`${l.email} → ${l.blocked ? "차단" : "차단 해제"}`);
} else if (cmd === "연장") {
  const l = kvGet(a1); if (!l) { console.error("없는 토큰"); process.exit(1); }
  const days = parseInt(a2, 10);
  l.expires = ymd(Date.now() + days * 86400000); kvPut(a1, l);
  console.log(`${l.email} → 만료 ${l.expires}`);
} else if (cmd === "기기초기화") {
  const l = kvGet(a1); if (!l) { console.error("없는 토큰"); process.exit(1); }
  l.devices = []; kvPut(a1, l);
  console.log(`${l.email} → 기기 초기화(0대)`);
} else if (cmd === "대수") {
  const l = kvGet(a1); if (!l) { console.error("없는 토큰"); process.exit(1); }
  l.maxDevices = Math.min(Math.max(1, parseInt(a2, 10)), DEVICE_CAP); kvPut(a1, l);
  console.log(`${l.email} → 허용 ${l.maxDevices}대`);
} else if (cmd === "프리셋추가" || cmd === "프리셋빼기") {
  const l = kvGet(a1); if (!l) { console.error("없는 토큰"); process.exit(1); }
  if (!a2) { console.error("프리셋 이름이 필요하다"); process.exit(1); }
  const set = new Set(l.presets || []);
  if (cmd === "프리셋추가") set.add(a2); else set.delete(a2);
  l.presets = [...set]; kvPut(a1, l);
  console.log(`${l.email} → 허용프리셋 ${l.presets.length ? l.presets.join("·") : "없음(전부 거부)"}`);
} else if (cmd === "폐기") {
  kv(["key", "delete", a1]);
  console.log("폐기 완료");
} else {
  console.log(require("node:fs").readFileSync(__filename, "utf8").split("\n").slice(1, 30).join("\n"));
}
