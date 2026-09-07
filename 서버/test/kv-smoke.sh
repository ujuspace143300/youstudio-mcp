#!/bin/bash
# 대장 인증 경로 스모크 — 로컬 KV(--local)로 진짜 대장·프리셋 권한·자산·관리 페이지를 한 바퀴 돈다.
#   dev-smoke.sh 는 KV 없이(인증 없음) 도는 스모크라 «발급 토큰 + 기기 헤더 → /asset 200·sha256» 을 못 잡았다(2026-09-07 지인 테스트에서 자산 404).
#   bash test/kv-smoke.sh        (서버/ 에서)   ·   npm run test:kv
set -u
cd "$(dirname "$0")/.."
bash 도구/자산스테이징.sh >/dev/null || { echo "★자산 스테이징 실패"; exit 1; }
ADMIN="kv-smoke-admin-token"
PORT=8791
rm -rf .wrangler/state/v3/kv
npx wrangler kv key put --binding LICENSES --local TOK_LB '{"email":"a@b.c","issued":"2026-09-04","expires":"2099-01-01","maxDevices":2,"devices":[],"blocked":false,"presets":["린박스"]}' >/dev/null 2>&1
LOG="${TMPDIR:-/tmp}/wrangler-kv-smoke.log"
npx wrangler dev --local --port $PORT --var "ADMIN_TOKEN:$ADMIN" > "$LOG" 2>&1 &
WP=$!
for i in $(seq 1 90); do nc -z 127.0.0.1 $PORT 2>/dev/null && break; sleep 1; done
if ! nc -z 127.0.0.1 $PORT 2>/dev/null; then echo "★dev 서버가 안 떴다 — $LOG"; tail -20 "$LOG"; kill $WP 2>/dev/null; exit 1; fi
MCP_URL="http://127.0.0.1:$PORT" YOUSTUDIO_TOKEN=TOK_LB YOUSTUDIO_DEVICE=devA ADMIN_TOKEN="$ADMIN" node test/kv-smoke.mjs; RC=$?
kill $WP 2>/dev/null; pkill -f "wrangler dev --local --port $PORT" 2>/dev/null; pkill -f workerd 2>/dev/null
rm -rf .wrangler/state/v3/kv
exit $RC
