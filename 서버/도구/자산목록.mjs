#!/usr/bin/env node
// 도구/자산목록.mjs — 자산/<프리셋>/_목록.json 을 만든다(배포 전 · 배포.sh 가 부른다).
//   서버(Workers Static Assets)는 폴더 목록을 못 내므로, 설치 스크립트가 이 목록을 받아 파일마다 /asset/<프리셋>/<경로> 로 내려받고
//   sha256 으로 되읽어 확인한다. 길 C(토큰 있는 사람만) · 이식원칙 ⑥.
//   node 도구/자산목록.mjs            → 자산/*/_목록.json 갱신
//   node 도구/자산목록.mjs --확인      → 갱신 없이 지금 목록이 실제와 같은지만 본다(종료코드 1 = 다름)
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const 자산 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "자산");
const 확인만 = process.argv.includes("--확인");
let 다름 = 0;
for (const preset of fs.readdirSync(자산).filter((d) => fs.statSync(path.join(자산, d)).isDirectory() && !d.startsWith("."))) {
  const root = path.join(자산, preset);
  const files = [];
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir).sort()) {
      if (name.startsWith(".") || name === "_목록.json") continue;
      const p = path.join(dir, name);
      if (fs.statSync(p).isDirectory()) { walk(p); continue; }
      const buf = fs.readFileSync(p);
      files.push({ path: path.relative(root, p).split(path.sep).join("/"), bytes: buf.length, sha256: crypto.createHash("sha256").update(buf).digest("hex") });
    }
  };
  walk(root);
  const out = { preset, made: new Date().toISOString().slice(0, 10), files, total_bytes: files.reduce((a, f) => a + f.bytes, 0) };
  const target = path.join(root, "_목록.json");
  const now = JSON.stringify(out, null, 1);
  const old = fs.existsSync(target) ? fs.readFileSync(target, "utf8") : "";
  const same = old && JSON.stringify(JSON.parse(old).files) === JSON.stringify(files);
  if (확인만) { if (!same) { 다름 += 1; console.log(`★ ${preset}: _목록.json 이 실제와 다르다`); } else console.log(`${preset}: 같음 (${files.length}개)`); continue; }
  if (!same) fs.writeFileSync(target, now, "utf8");
  console.log(`${preset}: ${files.length}개 · ${(out.total_bytes / 1048576).toFixed(1)}MB → ${path.relative(process.cwd(), target)}${same ? " (그대로)" : ""}`);
}
process.exit(다름 ? 1 : 0);
