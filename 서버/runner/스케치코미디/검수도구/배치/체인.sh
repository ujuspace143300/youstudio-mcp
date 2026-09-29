#!/bin/bash
# 사용: [FROM=n] [UNTIL=n] 체인.sh <NNN|슬러그> — 한편_sk.sh 를 시리즈 설정(S2_CONFIG)으로 돌린다. 로그 ~/Desktop/스케치코미디/배치로그/<슬러그>_체인.txt
#   예) 체인.sh 12 = 싱글벙글 싱글12 · 숨은기록 설정(기본, 예전과 같음) · 체인.sh 점심이네5 = 누룽지독 설정 — 시리즈 변수는 같은 폴더 시리즈.sh
#   흐름(2026-09-27 교훈): FROM=2 UNTIL=4 → 자막대조표 보고 핀 → FROM=4 → 납품.sh.  다시 구우면(FROM=2) 핀은 대조표로 다시 단다.
. "$(dirname "${BASH_SOURCE[0]}")/시리즈.sh"; sk_series "$1" || exit 1
[ -f "$CFG" ] || { echo "★설정 파일 없음: $CFG ($SERIES)"; exit 1; }
cd ~/Desktop/youstudio-mcp/서버/runner/스케치코미디
L=~/Desktop/스케치코미디/배치로그; mkdir -p "$L"
echo "=== $(date +%H:%M:%S) FROM=${FROM:-1} UNTIL=${UNTIL:-99}" >> "$L/${SLUG}_체인.txt"   # 덮어쓰지 않고 이어 쓴다(2026-09-27 — FROM=4 핀 로그가 FROM=7 에 지워졌다)
S2_CONFIG="$CFG" bash 한편_sk.sh $SLUG >> "$L/${SLUG}_체인.txt" 2>&1
rc=$?
echo "종료=$rc" >> "$L/${SLUG}_체인.txt"
tail -12 "$L/${SLUG}_체인.txt"
exit $rc
