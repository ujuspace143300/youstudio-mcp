#!/bin/bash
# 로컬 스모크 한 줄 — wrangler.jsonc 의 KV(LICENSES) id 가 비어 있으면 wrangler dev 가 안 뜨므로
# KV 줄을 뺀 임시 설정으로 dev 서버를 띄우고(단일 토큰 폴백 = 인증 없음) npm test 를 돌린 뒤 끈다.
#   bash test/dev-smoke.sh        (서버/ 에서)
set -u
cd "$(dirname "$0")/.."
python3 - <<'PY'
import io,re
t=io.open('wrangler.jsonc',encoding='utf-8').read()
t2=re.sub(r'\n\s*"kv_namespaces": \[\{[^\]]*\]\s*,?', '\n', t)   # KV 줄(과 뒤 쉼표)만 뺀다 — assets 는 남긴다(자산 시험)
io.open('.wrangler-devtmp.jsonc','w',encoding='utf-8').write(t2)
PY
LOG="${TMPDIR:-/tmp}/wrangler-dev-smoke.log"
npx wrangler dev -c .wrangler-devtmp.jsonc --port 8787 > "$LOG" 2>&1 &
WP=$!
for i in $(seq 1 90); do nc -z 127.0.0.1 8787 2>/dev/null && break; sleep 1; done
if ! nc -z 127.0.0.1 8787 2>/dev/null; then echo "★dev 서버가 안 떴다 — $LOG"; tail -20 "$LOG"; kill $WP 2>/dev/null; rm -f .wrangler-devtmp.jsonc; exit 1; fi
npm test; RC=$?
kill $WP 2>/dev/null; pkill -f "wrangler dev -c .wrangler-devtmp.jsonc" 2>/dev/null; pkill -f workerd 2>/dev/null
rm -f .wrangler-devtmp.jsonc
exit $RC
