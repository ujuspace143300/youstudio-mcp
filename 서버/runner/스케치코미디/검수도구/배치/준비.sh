#!/bin/bash
# 사용: 준비.sh NNN — 싱글벙글 NNN 편시작(agy 원본 통째 전사 + 자막띠시각 맞춤) → plan.  돈 안 듦(agy).
# 2026-09-27 싱글279~270 10편 배치에서 쓰던 임시 스크립트를 저장소로 옮김. 로그는 ~/Desktop/스케치코미디/배치로그/
n=$1; R=~/Desktop/youstudio-mcp/서버/runner/스케치코미디; PY=~/.volcano/venv/bin/python3
export S2_CONFIG=~/Desktop/스케치코미디/config_숨은기록.json
L=~/Desktop/스케치코미디/배치로그; mkdir -p "$L"
S="/Volumes/galaxy/영화자료/3. 스캐치코미디/싱글벙글"; F="$S/$(ls "$S" | grep "^$n\." | head -1)"
[ -d "$F" ] || { echo "★소재 폴더 없음: $n"; exit 1; }
cd "$R"
st=$(date +%s)
if [ ! -f ~/Desktop/스케치코미디/projects/싱글$n.json ] || [ "$2" = "--다시" ]; then
  $PY 편시작_deep.py "$F" --slug 싱글$n --채널 싱글벙글 \
      --로고 ~/Desktop/youstudio-mcp/자산/스케치코미디/channel_icon_숨은기록.png > "$L/싱글${n}_1편시작.txt" 2>&1 \
    || { echo "★편시작 실패 — $L/싱글${n}_1편시작.txt"; tail -5 "$L/싱글${n}_1편시작.txt"; exit 1; }
fi
$PY -m s2pipe.plan 싱글$n --slug 싱글$n > "$L/싱글${n}_2plan.txt" 2>&1 \
  || { echo "★plan 실패 — $L/싱글${n}_2plan.txt"; tail -5 "$L/싱글${n}_2plan.txt"; exit 1; }
echo "준비 끝 싱글$n $(( $(date +%s)-st ))초"
