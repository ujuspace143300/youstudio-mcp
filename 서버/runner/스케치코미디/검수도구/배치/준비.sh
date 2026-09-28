#!/bin/bash
# 사용: 준비.sh NNN — 싱글벙글 NNN 편시작(agy 원본 통째 전사 + 자막띠시각 맞춤) → plan.  돈 안 듦(agy).
# 2026-09-27 싱글279~270 10편 배치에서 쓰던 임시 스크립트를 저장소로 옮김. 로그는 ~/Desktop/스케치코미디/배치로그/
n=$1; R=~/Desktop/youstudio-mcp/서버/runner/스케치코미디; PY=~/.volcano/venv/bin/python3
export S2_CONFIG=~/Desktop/스케치코미디/config_숨은기록.json
L=~/Desktop/스케치코미디/배치로그; mkdir -p "$L"
# ★번호 앞 0 허용 (2026-09-28 — 1~9편 폴더는 «01.»~«09.» 라 «^1\.» 로는 못 찾았다. 못 찾으면 F 가 «$S/» 가 돼
#   -d 검사까지 통과해 버렸다). 이름이 비면 멈춘다.
S="/Volumes/galaxy/영화자료/3. 스캐치코미디/싱글벙글"; D="$(ls "$S" | grep -E "^0*$n\." | head -1)"; F="$S/$D"
[ -n "$D" ] && [ -d "$F" ] || { echo "★소재 폴더 없음: $n"; exit 1; }
cd "$R"
st=$(date +%s)
# ★--다시 는 원본 전사 캐시(work/싱글NNN.ko.vtt)도 버린다 (2026-09-28 싱글146 — 끝이 빠진 전사를 그대로 다시 씀)
REDO=""; [ "$2" = "--다시" ] && REDO="--다시전사"
if [ ! -f ~/Desktop/스케치코미디/projects/싱글$n.json ] || [ "$2" = "--다시" ]; then
  $PY 편시작_deep.py "$F" --slug 싱글$n --채널 싱글벙글 $REDO \
      --로고 ~/Desktop/youstudio-mcp/자산/스케치코미디/channel_icon_숨은기록.png > "$L/싱글${n}_1편시작.txt" 2>&1 \
    || { echo "★편시작 실패 — $L/싱글${n}_1편시작.txt"; tail -5 "$L/싱글${n}_1편시작.txt"; exit 1; }
fi
$PY -m s2pipe.plan 싱글$n --slug 싱글$n > "$L/싱글${n}_2plan.txt" 2>&1 \
  || { echo "★plan 실패 — $L/싱글${n}_2plan.txt"; tail -5 "$L/싱글${n}_2plan.txt"; exit 1; }
echo "준비 끝 싱글$n $(( $(date +%s)-st ))초"
