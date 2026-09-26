#!/bin/bash
# 사용: 납품.sh 싱글NNN — 검수 일괄(길이·검은띠·이음매·make·마스터효과) 후 NAS 납품(prproj 두 판·소스·완성본 md5 대조).
# 2026-09-27 임시 deliver.sh 를 저장소로 옮김. bash 는 한글 변수명을 못 쓴다 — 변수는 영문.
S=$1; R=~/Desktop/youstudio-mcp/서버/runner/스케치코미디; PY=~/.volcano/venv/bin/python3
export S2_CONFIG=~/Desktop/스케치코미디/config_숨은기록.json
PJ=~/Desktop/스케치코미디/projects/$S.json
cd $R
ORIG=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['credit']['title'])" "$PJ")
KEY=$(python3 -c "import json,sys,re;print(re.sub(r'[^0-9A-Za-z가-힣]','',''.join(json.load(open(sys.argv[1]))['title'])))" "$PJ")
M=""
for f in $(ls -t ~/Desktop/스케치코미디/out/*.mp4); do
  N=$(python3 -c "import unicodedata,sys,re;print(re.sub(r'[^0-9A-Za-z가-힣]','',unicodedata.normalize('NFC',sys.argv[1])))" "$(basename "$f")")
  case "$N" in *"$KEY"*) M="$f"; break;; esac
done
[ -z "$M" ] && { echo "★$S 완성본 mp4 를 제목으로 못 찾음 ($KEY)"; exit 1; }
echo "== $S · 제목 $KEY · 완성본 $(basename "$M")"
ffprobe -v error -show_entries stream=width,height:format=duration -of compact "$M" | tr '\n' ' '; echo
$PY 검수도구/검은띠재기.py "$M" 2>&1 | tail -1
$PY -m s2pipe.이음매관문 "$PJ" | tail -1
$PY make.py "$PJ" --check 2>&1 | grep -E "상단 제목|통과|반려 [0-9]" | tail -1
echo "마스터 효과 항목 수: $($PY ~/Desktop/유스튜디오-규격서/스크립트/린박스/키트/도구/마스터효과심기.py ~/Desktop/스케치코미디/프리미어_$S/스케치_$S.prproj --확인만 2>&1 | grep -cE '멀티밴드|선택적 제한')"
D="/Volumes/galaxy/영화자료/3. 스캐치코미디/싱글벙글/완성본/${S}_$ORIG"
$PY NAS이관_sk.py ~/Desktop/스케치코미디/프리미어_$S/스케치_$S.prproj "$D" 2>&1 | head -1
cp "$M" "$D/완성본_$ORIG.mp4" && [ "$(md5 -q "$M")" = "$(md5 -q "$D/완성본_$ORIG.mp4")" ] && echo "완성본 납품 대조 일치 → $D"
