#!/usr/bin/env node
// 도구/자산목록.mjs — 자산/<프리셋>/_목록.json 을 만들고, 배포용 스테이징 폴더 서버/.assets/ 를 ASCII 키로 채운다.
//   왜 ASCII 키인가 (2026-09-07 지인 실전 테스트에서 잡음): 배포된 Workers Static Assets 에서 한글 경로(린박스/·스케치코미디/…)가
//   전부 404 였다(로컬 miniflare 는 됐다). 비ASCII 경로의 정규화·인코딩이 로컬과 배포본이 다르다 — 원인이 어느 쪽이든
//   **키를 ASCII 로만** 두면 뚫리지 않는다. 사람이 보는 경로(path)는 그대로 두고, 서버에 올라가는 이름만 해시 키다.
//     .assets/<프리셋키 8자>/_index.json           {preset, files:[{path, key, bytes, sha256}], total_bytes}
//     .assets/<프리셋키 8자>/<파일키 16자><확장자>   실물
//   워커(serveAsset)는 /asset/<프리셋>/<경로> 를 받아 _index.json 으로 경로→키를 풀어 실물을 준다. 설치 스크립트는 그대로.
//   node 도구/자산목록.mjs            → 자산/*/_목록.json + .assets/ 갱신 (배포.sh · dev-smoke.sh · 자산스테이징.sh 가 부른다)
//   node 도구/자산목록.mjs --확인      → 갱신 없이 지금 목록이 실제와 같은지만 본다(종료코드 1 = 다름)
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const 서버 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const 자산 = path.resolve(서버, "..", "자산");
const 스테이징 = path.join(서버, ".assets");
const 확인만 = process.argv.includes("--확인");
const sha = (x) => crypto.createHash("sha256").update(x).digest("hex");
/** 프리셋·경로 키 — 파일 이름은 NFC 로 정규화해 센다(맥은 NFD 로 준다 · 메모리 mac-nfd-filename) */
export const presetKey = (preset) => sha(preset.normalize("NFC")).slice(0, 8);
export const fileKey = (rel) => sha(rel.normalize("NFC")).slice(0, 16) + (path.extname(rel).match(/^\.[A-Za-z0-9]{1,8}$/) ? path.extname(rel).toLowerCase() : "");

let 다름 = 0;
if (!확인만) fs.rmSync(스테이징, { recursive: true, force: true });
for (const preset of fs.readdirSync(자산).filter((d) => fs.statSync(path.join(자산, d)).isDirectory() && !d.startsWith("."))) {
  const root = path.join(자산, preset);
  const files = [];
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir).sort()) {
      if (name.startsWith(".") || name === "_목록.json") continue;
      const p = path.join(dir, name);
      if (fs.statSync(p).isDirectory()) { walk(p); continue; }
      const buf = fs.readFileSync(p);
      const rel = path.relative(root, p).split(path.sep).join("/").normalize("NFC");
      files.push({ path: rel, key: fileKey(rel), bytes: buf.length, sha256: sha(buf), _abs: p });
    }
  };
  walk(root);
  const pk = presetKey(preset);
  const out = { preset: preset.normalize("NFC"), preset_key: pk, made: new Date().toISOString().slice(0, 10), files: files.map(({ _abs, ...f }) => f), total_bytes: files.reduce((a, f) => a + f.bytes, 0) };
  const target = path.join(root, "_목록.json");
  const old = fs.existsSync(target) ? fs.readFileSync(target, "utf8") : "";
  const same = old && JSON.stringify(JSON.parse(old).files) === JSON.stringify(out.files);
  if (확인만) { if (!same) { 다름 += 1; console.log(`★ ${preset}: _목록.json 이 실제와 다르다`); } else console.log(`${preset}: 같음 (${files.length}개)`); continue; }
  if (!same) fs.writeFileSync(target, JSON.stringify(out, null, 1), "utf8");
  // 스테이징 — ASCII 키로 복사
  const sdir = path.join(스테이징, pk);
  fs.mkdirSync(sdir, { recursive: true });
  for (const f of files) fs.copyFileSync(f._abs, path.join(sdir, f.key));
  fs.writeFileSync(path.join(sdir, "_index.json"), JSON.stringify(out, null, 1), "utf8");
  console.log(`${preset}: ${files.length}개 · ${(out.total_bytes / 1048576).toFixed(1)}MB → ${path.relative(process.cwd(), target)}${same ? " (그대로)" : ""} · .assets/${pk}/`);
}
process.exit(다름 ? 1 : 0);
