#!/usr/bin/env bash
# 자산 스테이징 — 볼트(원본) 자산/유스튜디오/<프리셋>/ → 저장소 자산/<프리셋>/ (배포·스모크용 임시) + _목록.json.
#   왜: 저작권 자산은 저장소에 안 둔다(공개 예정 · 설계/자산분리_공개전.md). Cloudflare Assets 는 저장소 자산/ 을 읽으므로
#       배포 직전에 볼트에서 복사해 온다. 「볼트가 원본 · 저장소 자산/ 은 배포용 임시(.gitignore)」. 배포.sh·test/dev-smoke.sh 가 부른다.
#   볼트 자리: 환경변수 YOUSTUDIO_VAULT, 없으면 ~/Desktop/유스튜디오-규격서
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # 서버/
VAULT="${YOUSTUDIO_VAULT:-$HOME/Desktop/유스튜디오-규격서}"
SRC="$VAULT/자산/유스튜디오"
DST="$HERE/../자산"
if [ ! -d "$SRC" ]; then
  if [ -d "$DST/린박스" ]; then echo "⚠ 볼트 자산이 없다($SRC) — 저장소 자산/ 을 그대로 쓴다"; node "$HERE/도구/자산목록.mjs"; exit 0; fi
  echo "★볼트 자산이 없다: $SRC — 옵시디언 Sync 가 끝났는지 보라"; exit 1
fi
mkdir -p "$DST"
for d in "$SRC"/*/; do
  p="$(basename "$d")"
  mkdir -p "$DST/$p"
  rsync -a --delete --exclude '_목록.json' "$d" "$DST/$p/"
done
node "$HERE/도구/자산목록.mjs"
echo "자산 스테이징: $SRC → $DST"
