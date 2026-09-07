#!/usr/bin/env bash
# 스케치 한 편 체인 — 검사→굽기→재전사→작표→검사→재굽기→준비→조립→주입검사.
# ★어느 단계든 실패하면 그 자리에서 멈춘다. grep 요약은 로그에서 뽑는다 —
#   «명령 | grep || true» 꼴은 실패를 삼킨다(2026-09-07 Deep13 실측: 준비 죽었는데 조립이 돌았다).
set -euo pipefail
cd "$(dirname "$0")"
export S2_CONFIG="${S2_CONFIG:-/Users/yustudio1/Desktop/스케치코미디/config.json}"
PY=~/.volcano/venv/bin/python3
SLUG="$1"
PJ="/Users/yustudio1/Desktop/스케치코미디/projects/${SLUG}.json"
PR="/Users/yustudio1/Desktop/스케치코미디/프리미어_${SLUG}"
LOG="/tmp/한편_${SLUG}.log"
DONOR="/Users/yustudio1/Desktop/볼케이노 MCP/23. 신병4/1편_공유_신병이대답할때마다누군가엎드린다/신병이대답할때마다누군가엎드린다.prproj"
BON="/Users/yustudio1/Desktop/유스튜디오-규격서/스크립트/린박스/키트/스타일/아모르_부품.prproj"

단계() {  # 단계 <이름> <요약 grep 패턴> <명령...>
  local 이름="$1" 패턴="$2"; shift 2
  echo "── $이름"
  if ! "$@" > "$LOG" 2>&1; then
    echo "★실패 — $이름. 로그 끝:"; tail -8 "$LOG"; exit 1
  fi
  grep -E "$패턴" "$LOG" || true
}

단계 "① 검사"       "반려|통과"                                    "$PY" make.py "$PJ" --check
단계 "② 굽기"       "절단|반영|감지|카드|완성:"                     "$PY" make.py "$PJ"
단계 "③ 재전사(유료)" "낱말사전|단어"                                "$PY" -m s2pipe.asr "$PJ"
단계 "④ 작표"       "핀|재정박|병합|갈림|정정|유령|복원|재흐름|겹침 정리|최종 관문|커버리지|원문화면" "$PY" -m s2pipe.sync "$PJ"
단계 "⑤ 재검사"     "반려|통과"                                    "$PY" make.py "$PJ" --check
단계 "⑥ 재굽기"     "완성:"                                        "$PY" make.py "$PJ"
단계 "⑦ 준비"       "여운|원음|통암전|잔존|화자 판정|감지|원문화면"   "$PY" 준비_prproj_sk.py "$PJ"
단계 "⑧ 조립"       "\[X\]|저장|프리미어가|전체"                    "$PY" 조립_prproj_sk.py --timeline "$PR/timeline_sk.json" --donor "$DONOR" --out "$PR/스케치_${SLUG}.prproj"
단계 "⑨ 주입검사"   "전체|탈"                                      python3 "/Users/yustudio1/Desktop/볼케이노 MCP/23. 신병4/ep_0212-0352/주입검사.py" "$PR/스케치_${SLUG}.prproj" --본 "$BON" --기준 "$PR/스케치_${SLUG}.prproj.아모르전"
echo "── 체인 전부 통과"
