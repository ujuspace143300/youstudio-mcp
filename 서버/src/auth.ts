/**
 * auth.ts — 이메일 허가제(발급 대장) 인증.
 *
 * 설계: `설계/인증_이메일허가제.md`.
 *   사장님이 이메일을 대장에 등록 → 토큰 발급 → 지인 사용 → 사장님이 목록·차단·연장.
 *   요청마다 6검사: 대장에 있나 → 차단됐나 → 만료됐나 → 기기 자리 있나(이메일당 기본 2·상한 50) → **이 프리셋을 써도 되나**(허용프리셋 · 기본 전부 거부 · 2026-09-04 배포 직전 구현).
 *
 * 저장: Cloudflare KV (바인딩 이름 LICENSES). 키 = 토큰 문자열, 값 = License(JSON).
 *   토큰 자체가 KV 키라 대장에 「토큰 값」을 따로 평문 필드로 두지 않는다(키 보호 규칙).
 *
 * 순수 로직(decideAuth·registerDevice)은 KV 와 분리해 node 로 단위 시험한다
 *   (test/auth.mjs). Worker 쪽은 KV 읽기/쓰기만 하고 판정은 순수 함수에 맡긴다.
 */

/** 대장 한 줄. 토큰은 KV 키이므로 여기 두지 않는다. */
export interface License {
  email: string;
  issued: string;   // YYYY-MM-DD
  expires: string;  // YYYY-MM-DD — 이 날 끝(23:59:59Z)까지 유효
  maxDevices: number; // 이메일당 허용 기기 수 (기본 2 · 상한 50)
  devices: string[];  // 등록된 기기 지문(설치 id)
  blocked: boolean;   // 사장님이 즉시 차단
  /** 허용프리셋 — 이 이메일이 쓸 수 있는 프리셋 이름들. 없거나 비면 **전부 거부**(명시한 것만 허용, 설계 「프리셋별 권한」) */
  presets?: string[];
}

export const DEFAULT_MAX_DEVICES = 2;
export const DEVICE_CAP = 50; // 사장님이 올릴 수 있는 상한

export type AuthResult =
  | { ok: true; license: License; changed: boolean } // changed=true 면 기기 새로 등록됨 → KV 저장 필요
  | { ok: false; code: number; message: string };

/** 만료일(YYYY-MM-DD)이 지났는지 — 그 날 끝까지 유효하게 하루를 더한 자정과 비교. */
export function isExpired(expires: string, nowMs: number): boolean {
  const t = Date.parse(expires + "T00:00:00Z");
  if (Number.isNaN(t)) return true; // 형식이 깨졌으면 안전하게 만료로
  const endOfDay = t + 24 * 60 * 60 * 1000; // 그 날 23:59:59 까지 허용
  return nowMs >= endOfDay;
}

/**
 * 순수 판정. license 는 KV 에서 읽어 온 것(없으면 null), device 는 요청 헤더의 기기 지문.
 * 반환이 ok:true 이고 changed:true 면 호출부가 license.devices 를 KV 에 다시 써야 한다.
 */
export function decideAuth(
  license: License | null,
  device: string,
  nowMs: number,
  preset: string | null = null,
): AuthResult {
  // 1) 대장에 있나
  if (!license) {
    return { ok: false, code: -32001, message: "인증 실패 — 등록되지 않은 토큰이다. 사장님에게 발급을 요청하라." };
  }
  // 2) 차단됐나
  if (license.blocked) {
    return { ok: false, code: -32003, message: "차단된 계정이다 — 사장님에게 문의하라." };
  }
  // 3) 만료됐나
  if (isExpired(license.expires, nowMs)) {
    return { ok: false, code: -32004, message: `토큰이 만료됐다(${license.expires}) — 사장님에게 연장을 요청하라.` };
  }
  // 4) 기기 — 헤더에 지문이 없으면 거부(러너가 반드시 보낸다)
  const dev = (device ?? "").trim();
  if (!dev) {
    return { ok: false, code: -32005, message: "기기 식별자가 없다 — 설치가 온전하지 않다(~/.youstudio/device)." };
  }
  const cap = Math.min(Math.max(1, license.maxDevices || DEFAULT_MAX_DEVICES), DEVICE_CAP);
  // 5) 프리셋 — 요청이 프리셋을 지목했으면(tools/call youstudio_video) 허용프리셋에 있어야 한다. 기본 = 전부 거부.
  //    initialize·tools/list 처럼 프리셋이 없는 요청은 이 검사를 건너뛴다(대장·차단·만료·기기는 이미 봤다).
  const want = (preset ?? "").trim();
  if (want) {
    const allowed = Array.isArray(license.presets) ? license.presets : [];
    if (allowed.indexOf(want) === -1) {
      return { ok: false, code: -32007, message: `이 프리셋(${want})은 권한이 없습니다 — 관리자에게 요청하라. 허용: ${allowed.length ? allowed.join("·") : "없음"}` };
    }
  }
  // 이미 등록된 기기면 그대로 통과
  if (license.devices.indexOf(dev) !== -1) {
    return { ok: true, license, changed: false };
  }
  // 빈 자리 있으면 등록하고 통과
  if (license.devices.length < cap) {
    const next: License = { ...license, devices: license.devices.concat([dev]) };
    return { ok: true, license: next, changed: true };
  }
  // 자리 없음 → 거부(사장님이 대장에서 풀어야 함 — 자동 밀어내기 안 함)
  return {
    ok: false,
    code: -32006,
    message: `등록된 기기 ${cap}대를 초과했다 — 사장님에게 기기 초기화를 요청하라.`,
  };
}

/**
 * MCP 요청 body 에서 프리셋을 뽑는다 — tools/call youstudio_video 의 arguments.preset. 배치(배열)면 전부 모은다.
 * 프리셋이 없는 요청(initialize·tools/list 등)은 빈 배열.
 */
export function presetsInBody(body: unknown): string[] {
  const msgs = Array.isArray(body) ? body : [body];
  const out: string[] = [];
  for (const m of msgs) {
    if (!m || typeof m !== "object") continue;
    const o = m as { method?: unknown; params?: { arguments?: { preset?: unknown } } };
    if (o.method !== "tools/call") continue;
    const p = o.params?.arguments?.preset;
    if (typeof p === "string" && p.trim()) out.push(p.trim());
  }
  return out;
}

/** 요청에서 Bearer 토큰과 기기 지문 헤더를 뽑는다. */
export function readCreds(request: Request): { token: string; device: string } {
  const token = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "").trim();
  const device = (request.headers.get("x-youstudio-device") ?? "").trim();
  return { token, device };
}

/** 새 대장 한 줄을 만든다(발급). 관리 도구·발급 경로가 쓴다. */
export function newLicense(email: string, days: number, maxDevices: number, nowMs: number, presets: string[] = []): License {
  const issued = new Date(nowMs);
  const exp = new Date(nowMs + days * 24 * 60 * 60 * 1000);
  const ymd = (d: Date) => d.toISOString().slice(0, 10);
  return {
    email,
    issued: ymd(issued),
    expires: ymd(exp),
    maxDevices: Math.min(Math.max(1, maxDevices), DEVICE_CAP),
    devices: [],
    blocked: false,
    presets: presets.slice(),
  };
}
