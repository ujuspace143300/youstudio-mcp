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

# ★FROM=<n> 이면 그 번호 앞 단계는 건너뛴다(2026-09-09 — 핀만 반영할 때 ③ 유료 재전사를 다시 사지 않게.
#   ④ 작표는 subs_asr·subs_before_sync 에서 다시 돌려도 같은 결과라(sync.py 머리) FROM=4 가 정본 경로다)
FROM="${FROM:-1}"
# ★UNTIL=<n> 이면 그 번호까지만 돌고 멈춘다(2026-09-26 — 자막 교정을 ④ 뒤에 먼저 하고 ⑤~⑨ 는 한 번만 돌리려고.
#   예전엔 끝까지 돈 뒤 교정 → FROM=4 로 ⑥~⑨ 를 또 돌려 편당 10분씩 더 들었다). 흐름: UNTIL=4 → 대조·핀 → FROM=4.
UNTIL="${UNTIL:-99}"
# ★체인이 도는 동안 프로젝트 파일 잠금 (2026-09-26 싱글284·282·281 — 체인이 돌 때 제목을 바꿨더니, 먼저 읽어 둔 옛
#   내용을 단계들이 끝에 통째로 저장해 제목 변경이 사라졌다). 고침 도구(검수도구/경계제안·이음매수리·계획고침)는
#   이 잠금이 있으면 멈춘다. 체인이 끝나거나 죽으면 풀린다.
LOCK="${PJ}.체인중"
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "★이 편 체인이 이미 돌고 있다(PID $(cat "$LOCK")) — 끝난 뒤 다시"; exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
STEP=0
단계() {  # 단계 <이름> <요약 grep 패턴> <명령...>
  local NAME="$1" PAT="$2"; shift 2
  STEP=$((STEP + 1))
  if [ "$STEP" -lt "$FROM" ]; then echo "── $NAME (건너뜀 FROM=$FROM)"; return 0; fi
  if [ "$STEP" -gt "$UNTIL" ]; then echo "── $NAME (멈춤 UNTIL=$UNTIL)"; return 0; fi
  echo "── $NAME"
  if ! "$@" > "$LOG" 2>&1; then
    echo "★실패 — $NAME. 로그 끝:"; tail -8 "$LOG"; exit 1
  fi
  grep -E "$PAT" "$LOG" || true
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
[ "$UNTIL" -ge 9 ] && echo "── 체인 전부 통과" || echo "── ${UNTIL}단계까지 통과 (UNTIL)"
