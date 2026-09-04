#!/usr/bin/env bash
# 배포 — typecheck → wrangler deploy → 배포 기록(.last_deploy) → 배포본 health 확인.
# 세션시작 훅이 .last_deploy 와 HEAD 를 비교해 "배포 안 한 코드" 를 잡는다.
set -euo pipefail
cd "$(dirname "$0")"
npm run typecheck
bash 도구/자산스테이징.sh   # 볼트(원본) 자산/유스튜디오/ → 저장소 자산/(배포용 임시 · .gitignore) + _목록.json (길 C)
if [ -n "$(git status --porcelain ..)" ]; then
  echo "⚠ 미커밋 변경이 있다. 배포는 되지만 다른 컴퓨터는 이 코드를 못 받는다 — 끝나면 커밋·푸시하라."
fi
npx wrangler deploy
git rev-parse --short HEAD > .last_deploy
URL="$(npx wrangler deployments list 2>/dev/null | grep -o 'https://[^ ]*workers.dev' | head -1 || true)"
[ -n "$URL" ] || URL="https://youstudio-mcp.youstudio.workers.dev"
echo "health: $(curl -s -m 15 "$URL/health")"
echo "배포 기록: $(cat .last_deploy) → .last_deploy"
