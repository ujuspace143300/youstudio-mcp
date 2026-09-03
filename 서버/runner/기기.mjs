// 기기.mjs — 이 컴퓨터의 «설치 id» 와 유스튜디오 서버에 보낼 인증 헤더.
//   설계: 설계/인증_이메일허가제.md
//
//   인증은 요청마다 두 가지를 본다 (auth.ts):
//     · Authorization: Bearer <토큰>   — 지인이 관리자에게 받은 것 (환경변수 YOUSTUDIO_TOKEN)
//     · X-Youstudio-Device: <설치 id>  — 이 컴퓨터를 가리키는 값 (~/.youstudio/device 에 한 번 만든다)
//
//   ★설치 id 는 하드웨어 값이 아니라 **랜덤 설치 id** 다. 포맷·재설치하면 바뀐다 —
//     그게 자연스럽다(포맷 = 새 기기). 사생활 식별자(맥주소·시리얼)를 쓰지 않는다.
//   ★MCP 연결(claude mcp add)과 러너가 **같은 파일**을 읽어 같은 id 를 보낸다. 그래야
//     한 컴퓨터가 한 자리만 차지한다. 설치도우미.mjs 가 mcp add 전에 이 파일을 만든다.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

const DIR = path.join(os.homedir(), ".youstudio");
const FILE = path.join(DIR, "device");

/** 이 컴퓨터의 설치 id. 없으면 만들어 저장한다(한 번만). */
export function deviceId() {
  try {
    const v = fs.readFileSync(FILE, "utf8").trim();
    if (v) return v;
  } catch {}
  const id = crypto.randomBytes(16).toString("hex");
  try {
    fs.mkdirSync(DIR, { recursive: true });
    fs.writeFileSync(FILE, id, "utf8");
  } catch {}
  return id;
}

/** 서버에 붙일 인증 헤더. 토큰이 없으면(로컬 dev) Authorization 은 뺀다. */
export function authHeaders(env = process.env) {
  const h = { "X-Youstudio-Device": deviceId() };
  const token = (env.YOUSTUDIO_TOKEN ?? "").trim();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}
