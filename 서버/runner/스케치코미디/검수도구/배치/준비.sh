#!/bin/bash
# 사용: 준비.sh <NNN|슬러그> [--다시] — 편시작(agy 원본 통째 전사 + 자막띠시각 맞춤) → plan.  돈 안 듦(agy).
#   예) 준비.sh 12 = 싱글벙글 싱글12(기본, 예전과 같음) · 준비.sh 점심이네5 · SERIES=점심이네 준비.sh 5 — 시리즈 변수는 같은 폴더 시리즈.sh
# 2026-09-27 싱글279~270 10편 배치에서 쓰던 임시 스크립트를 저장소로 옮김. 로그는 ~/Desktop/스케치코미디/배치로그/<슬러그>_1편시작.txt·_2plan.txt
# 2026-09-29 시리즈 변수(점심이네 64편 — 누룽지독 템플릿·원제 = 폴더 이름). 기본값은 그대로 싱글벙글·숨은기록.
. "$(dirname "${BASH_SOURCE[0]}")/시리즈.sh"; sk_series "$1" || exit 1
R=~/Desktop/youstudio-mcp/서버/runner/스케치코미디; PY=~/.volcano/venv/bin/python3
[ -f "$CFG" ] || { echo "★설정 파일 없음: $CFG ($SERIES)"; exit 1; }
export S2_CONFIG=$CFG
L=~/Desktop/스케치코미디/배치로그; mkdir -p "$L"
# ★번호 앞 0 허용 (2026-09-28 — 1~9편 폴더는 «01.»~«09.» 라 «^1\.» 로는 못 찾았다. 못 찾으면 F 가 «$S/» 가 돼
#   -d 검사까지 통과해 버렸다). 이름이 비면 멈춘다.
S=$NAS; D="$(ls "$S" | grep -E "^0*$n\." | head -1)"; F="$S/$D"
[ -n "$D" ] && [ -d "$F" ] || { echo "★소재 폴더 없음: $SERIES $n"; exit 1; }
# 하단 원제 — 시리즈가 «폴더» 면 소재 폴더 이름의 «NN.<시리즈>_» 뒤를 편시작에 준다(편시작 기본은 mp4 이름의 «_» 뒤)
TITLE_ARG=()
if [ "$TITLE_FROM" = 폴더 ]; then
  case "$D" in *_*) TITLE_ARG=(--원제 "${D#*_}");; *) echo "★소재 폴더 이름에 «_» 가 없어 원제를 못 뗀다: $D"; exit 1;; esac
fi
cd "$R"
st=$(date +%s)
# ★--다시 는 원본 전사 캐시(work/<슬러그>.ko.vtt)도 버린다 (2026-09-28 싱글146 — 끝이 빠진 전사를 그대로 다시 씀)
REDO=""; [ "$2" = "--다시" ] && REDO="--다시전사"
if [ ! -f ~/Desktop/스케치코미디/projects/$SLUG.json ] || [ "$2" = "--다시" ]; then
  $PY 편시작_deep.py "$F" --slug $SLUG --채널 "$SERIES" $REDO "${TITLE_ARG[@]}" \
      --로고 "$LOGO" > "$L/${SLUG}_1편시작.txt" 2>&1 \
    || { echo "★편시작 실패 — $L/${SLUG}_1편시작.txt"; tail -5 "$L/${SLUG}_1편시작.txt"; exit 1; }
fi
$PY -m s2pipe.plan $SLUG --slug $SLUG > "$L/${SLUG}_2plan.txt" 2>&1 \
  || { echo "★plan 실패 — $L/${SLUG}_2plan.txt"; tail -5 "$L/${SLUG}_2plan.txt"; exit 1; }
echo "준비 끝 $SLUG $(( $(date +%s)-st ))초"
