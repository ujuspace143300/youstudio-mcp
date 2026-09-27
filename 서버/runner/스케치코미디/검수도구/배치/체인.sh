#!/bin/bash
# 사용: [FROM=n] [UNTIL=n] 체인.sh NNN — 한편_sk.sh 를 숨은기록 설정으로 돌린다. 로그 ~/Desktop/스케치코미디/배치로그/싱글NNN_체인.txt
#   흐름(2026-09-27 교훈): FROM=2 UNTIL=4 → 자막대조표 보고 핀 → FROM=4 → 납품.sh.  다시 구우면(FROM=2) 핀은 대조표로 다시 단다.
n=$1; cd ~/Desktop/youstudio-mcp/서버/runner/스케치코미디
L=~/Desktop/스케치코미디/배치로그; mkdir -p "$L"
echo "=== $(date +%H:%M:%S) FROM=${FROM:-1} UNTIL=${UNTIL:-99}" >> "$L/싱글${n}_체인.txt"   # 덮어쓰지 않고 이어 쓴다(2026-09-27 — FROM=4 핀 로그가 FROM=7 에 지워졌다)
S2_CONFIG=~/Desktop/스케치코미디/config_숨은기록.json bash 한편_sk.sh 싱글$n >> "$L/싱글${n}_체인.txt" 2>&1
rc=$?
echo "종료=$rc" >> "$L/싱글${n}_체인.txt"
tail -12 "$L/싱글${n}_체인.txt"
exit $rc
