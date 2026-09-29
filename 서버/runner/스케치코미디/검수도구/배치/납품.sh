#!/bin/bash
# 사용: 납품.sh <슬러그|NNN> — 검수 일괄(길이·검은띠·이음매·make·마스터효과) 후 NAS 납품(prproj 두 판·소스·완성본 md5 대조).
#   예) 납품.sh 싱글12(기본 시리즈 싱글벙글 — 예전과 같음) · 납품.sh 점심이네5 → NAS «3. 스캐치코미디/점심이네/완성본/점심이네5_<원제>/»
#   시리즈 변수는 같은 폴더 시리즈.sh(설정 S2_CONFIG · NAS 자리). 숫자만 주면 SERIES 환경변수(없으면 싱글벙글).
# 2026-09-27 임시 deliver.sh 를 저장소로 옮김. bash 는 한글 변수명을 못 쓴다 — 변수는 영문.
# 2026-09-29 시리즈 변수(점심이네 64편). 프로젝트 하단 채널(credit.channel)이 시리즈와 다르면 NAS 에 쓰기 전에 멈춘다.
. "$(dirname "${BASH_SOURCE[0]}")/시리즈.sh"; sk_series "$1" || exit 1
S=$SLUG; R=~/Desktop/youstudio-mcp/서버/runner/스케치코미디; PY=~/.volcano/venv/bin/python3
[ -f "$CFG" ] || { echo "★설정 파일 없음: $CFG ($SERIES)"; exit 1; }
export S2_CONFIG=$CFG
PJ=~/Desktop/스케치코미디/projects/$S.json
[ -f "$PJ" ] || { echo "★프로젝트 없음: $PJ"; exit 1; }
cd $R
ORIG=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['credit']['title'])" "$PJ")
CH=$(python3 -c "import json,sys;print((json.load(open(sys.argv[1])).get('credit') or {}).get('channel') or '')" "$PJ")
# ★다른 시리즈 폴더에 납품하지 않는다 (2026-09-29 — 싱글벙글 373편 credit.channel 은 전부 «싱글벙글», 점심이네는 준비.sh 가 «점심이네» 로 넣는다)
[ "$CH" = "$SERIES" ] || { echo "★$S 하단 채널 «${CH}» ≠ 시리즈 «${SERIES}» — 시리즈를 확인하라(NAS 에 안 씀)"; exit 1; }
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
BASE="$OUTBASE"
# ★같은 편 폴더가 이미 있으면 그 폴더에 덮어쓴다 (2026-09-28 싱글369 — 옛 납품(09-10)은 옛 제목으로 폴더 이름이 붙어 있어
#   credit.title 로 새로 만들면 폴더가 둘이 됐다: 옛 폴더 = 글자 보이는 옛 판, 새 폴더 = 수리본, 확인.py 는 옛 폴더를 봤다).
#   «<슬러그>_» 으로 시작하는 폴더를 NFC 로 찾고(맥 SMB 는 NFD 로 준다) 디스크의 실제 이름을 그대로 쓴다.
#   여럿이면 가장 최근 것. 없을 때만 credit.title 로 새로 만든다. 옛 폴더를 지우지는 않는다(NAS 삭제는 사장님 결정).
#   완성본/ 폴더가 아직 없는 시리즈(점심이네 첫 편)는 찾을 것이 없다 — NAS이관_sk.py 가 편 폴더째 만든다.
D=$(python3 - "$BASE" "$S" <<'PYEOF'
import os, sys, unicodedata as u
b, s = sys.argv[1], sys.argv[2]
hit = [n for n in (os.listdir(b) if os.path.isdir(b) else []) if u.normalize("NFC", n).startswith(u.normalize("NFC", s) + "_") and os.path.isdir(os.path.join(b, n))]
hit.sort(key=lambda n: os.path.getmtime(os.path.join(b, n)), reverse=True)
if len(hit) > 1:
    print(f"★{s} 납품 폴더 {len(hit)}개 — 가장 최근 «{u.normalize('NFC', hit[0])}» 에 덮어쓴다", file=sys.stderr)
print(os.path.join(b, hit[0]) if hit else "")
PYEOF
)
[ -z "$D" ] && D="$BASE/${S}_$ORIG"
# 완성본 mp4 도 폴더 안에 하나뿐이면 그 이름 그대로 덮어쓴다(제목이 바뀐 편에서 mp4 가 둘 되지 않게)
MP=$(python3 - "$D" <<'PYEOF'
import os, sys
d = sys.argv[1]
m = [n for n in os.listdir(d) if n.endswith(".mp4") and not n.startswith("._")] if os.path.isdir(d) else []
print(m[0] if len(m) == 1 else "")
PYEOF
)
[ -z "$MP" ] && MP="완성본_$ORIG.mp4"
$PY NAS이관_sk.py ~/Desktop/스케치코미디/프리미어_$S/스케치_$S.prproj "$D" 2>&1 | head -1
cp "$M" "$D/$MP" && [ "$(md5 -q "$M")" = "$(md5 -q "$D/$MP")" ] && echo "완성본 납품 대조 일치 → $D"
