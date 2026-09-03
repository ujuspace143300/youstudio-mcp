#!/usr/bin/env node
// 설치도우미.mjs — 지인이 유스튜디오를 클로드코드에 붙일 때 한 번 돌린다.
//   설계: 설계/인증_이메일허가제.md · 설치 안내(아티팩트) 2단계
//
//   하는 일:
//     ① 이 컴퓨터의 설치 id 를 만든다(없으면). ~/.youstudio/device
//     ② 관리자에게 받은 토큰 + 그 id 로 `claude mcp add` 명령을 만든다(두 헤더).
//     ③ --붙이기 를 주면 그 명령을 실제로 실행한다. 안 주면 명령만 보여 준다(붙여넣기용).
//
//   쓰는 법:
//     node 설치도우미.mjs <토큰>              → 붙여넣을 mcp add 명령을 보여 준다
//     node 설치도우미.mjs <토큰> --붙이기      → 바로 붙인다(claude mcp add 실행)
//     node 설치도우미.mjs <토큰> --서버 <URL>  → 서버 주소를 직접 준다(기본은 아래 상수)
//
//   ★SERVER_URL 은 배포 뒤 실제 주소로 채운다(관리자). 지금은 비어 있으면 --서버 로 준다.
import { spawnSync } from "node:child_process";
import { deviceId } from "./기기.mjs";

const SERVER_URL = ""; // 예: https://youstudio-mcp.<계정>.workers.dev — 배포 뒤 채운다

const argv = process.argv.slice(2);
const token = argv.find((a) => !a.startsWith("--"));
const urlArg = (() => { const i = argv.indexOf("--서버"); return i !== -1 ? argv[i + 1] : null; })();
const 붙이기 = argv.includes("--붙이기");

const URL_ = (urlArg ?? SERVER_URL).trim();

if (!token) {
  console.error("토큰이 필요합니다.  node 설치도우미.mjs <관리자에게-받은-토큰> [--붙이기]");
  process.exit(1);
}
if (!URL_) {
  console.error("서버 주소가 없습니다. 관리자에게 주소를 받아 --서버 <URL> 로 주거나, SERVER_URL 을 채우세요.");
  process.exit(1);
}

const dev = deviceId();
const args = [
  "mcp", "add", "--transport", "http", "--scope", "user", "youstudio", URL_,
  "--header", `Authorization: Bearer ${token}`,
  "--header", `X-Youstudio-Device: ${dev}`,
];

console.log("이 컴퓨터의 설치 id: " + dev + "  (~/.youstudio/device 에 저장됨)");
console.log("");

if (붙이기) {
  console.log("클로드코드에 붙이는 중…");
  const r = spawnSync("claude", args, { stdio: "inherit", shell: process.platform === "win32" });
  if (r.status === 0) {
    console.log("\n붙였습니다. 클로드코드에서 /mcp 로 'youstudio · 연결됨' 을 확인하세요.");
  } else {
    console.error("\n붙이기 실패(종료코드 " + r.status + "). 아래 명령을 직접 붙여넣어 보세요:");
    printCmd();
  }
} else {
  console.log("아래 한 줄을 클로드코드(또는 터미널)에 붙여넣고 엔터:\n");
  printCmd();
}

function printCmd() {
  // 헤더 값에 공백이 있으니 따옴표로 감싼다(윈도우/맥 셸 공통으로 큰따옴표).
  const quoted = args
    .map((a) => (a.includes(" ") || a.includes(":") ? `"${a}"` : a))
    .join(" ");
  console.log("claude " + quoted);
}
