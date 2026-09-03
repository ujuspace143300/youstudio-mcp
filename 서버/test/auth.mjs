/**
 * test/auth.mjs — 발급 대장 판정(순수 로직) 단위 시험. KV·네트워크 없이 돈다.
 *   node test/auth.mjs   (또는 npm run test:auth)
 * decideAuth·isExpired·newLicense 를 src/auth.ts 에서 그대로 가져와 검사한다.
 *   ts 를 node 로 바로 못 읽으니, 시험은 컴파일된 형태를 흉내 내지 않고
 *   auth.ts 의 로직을 여기 mirror 하지 않는다 — 대신 tsc 로 나온 게 아니라
 *   esbuild/tsx 없이 돌도록 로직만 import 하는 얇은 재수출(.mjs)을 쓴다.
 * ★단순화: 여기서는 auth.ts 의 순수 함수를 동적으로 컴파일하지 않고,
 *   Node 22+ 의 ts 타입제거(--experimental-strip-types)를 쓴다.
 */
import { decideAuth, isExpired, newLicense, DEFAULT_MAX_DEVICES, DEVICE_CAP } from "../src/auth.ts";

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass += 1; console.log("  통과  " + name); }
  else { fail += 1; console.log("  ★미통과  " + name); }
}

const NOW = Date.parse("2026-09-03T12:00:00Z");
const DAY = 24 * 60 * 60 * 1000;

// isExpired
ok("만료 전은 유효", !isExpired("2026-12-02", NOW));
ok("만료일 당일은 유효(그 날 끝까지)", !isExpired("2026-09-03", NOW));
ok("만료일 다음날은 만료", isExpired("2026-09-02", NOW));
ok("형식 깨지면 만료 취급", isExpired("망가짐", NOW));

// newLicense
const L = newLicense("친구@example.com", 90, 2, NOW);
ok("발급: 만료 90일 뒤", L.expires === new Date(NOW + 90 * DAY).toISOString().slice(0, 10));
ok("발급: 기기 0대·차단 아님", L.devices.length === 0 && L.blocked === false);
ok("발급: 상한 넘는 maxDevices 는 잘림", newLicense("a@b.c", 90, 999, NOW).maxDevices === DEVICE_CAP);

// decideAuth — 1) 대장에 없음
ok("없는 토큰 거부(-32001)", decideAuth(null, "dev1", NOW).ok === false);

// 2) 차단
ok("차단된 계정 거부(-32003)", decideAuth({ ...L, blocked: true }, "dev1", NOW).code === -32003);

// 3) 만료
ok("만료된 토큰 거부(-32004)", decideAuth({ ...L, expires: "2026-09-01" }, "dev1", NOW).code === -32004);

// 4) 기기 지문 없음
ok("기기 지문 없으면 거부(-32005)", decideAuth(L, "", NOW).code === -32005);

// 첫 기기 등록
const r1 = decideAuth(L, "devA", NOW);
ok("첫 기기 통과+등록(changed)", r1.ok && r1.changed && r1.license.devices.length === 1);

// 같은 기기 재접속 — 등록 안 함
const L1 = r1.ok ? r1.license : L;
const r2 = decideAuth(L1, "devA", NOW);
ok("같은 기기 재접속 통과·등록 안 함", r2.ok && r2.changed === false);

// 두 번째 기기 등록(자리 2)
const r3 = decideAuth(L1, "devB", NOW);
ok("둘째 기기 통과+등록", r3.ok && r3.changed && r3.license.devices.length === 2);

// 세 번째 기기 — 자리 없음(기본 2) 거부
const L2 = r3.ok ? r3.license : L1;
const r4 = decideAuth(L2, "devC", NOW);
ok("셋째 기기 거부(-32006)", r4.ok === false && r4.code === -32006);

// 상한을 3으로 올리면 셋째 통과
const r5 = decideAuth({ ...L2, maxDevices: 3 }, "devC", NOW);
ok("허용대수 3이면 셋째 통과", r5.ok === true);

// 기본값 상수
ok("기본 허용 2대", DEFAULT_MAX_DEVICES === 2);
ok("상한 50", DEVICE_CAP === 50);

console.log(`\n결과: ${pass} 통과 · ${fail} 미통과`);
process.exit(fail ? 1 : 0);
