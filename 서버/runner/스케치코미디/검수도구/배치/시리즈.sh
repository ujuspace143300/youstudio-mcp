# 시리즈.sh — 준비.sh·체인.sh·납품.sh 가 source 해서 쓰는 시리즈 변수 (직접 실행하지 않는다).
# 2026-09-29 점심이네 64편 — 싱글벙글(숨은기록) 전용으로 박혀 있던 배치 도구를 시리즈 변수로 바꿈.
# ★아무것도 안 주면 예전과 똑같다: 싱글벙글 · config_숨은기록.json · 숨은기록 로고 · 슬러그 싱글NNN · NAS 싱글벙글/.
#
# 시리즈를 알려 주는 길(둘 중 하나):
#   ① 인자에 슬러그 — «점심이네5» 처럼 접두+번호면 접두로 시리즈를 안다(권장: 환경변수를 빠뜨려 다른 시리즈의 같은 번호
#      편을 건드릴 일이 없다 — 싱글5 가 도는 중에 «체인.sh 5» 를 잘못 치면 싱글벙글 5편에 두 번째 체인이 붙는다).
#   ② 환경변수 SERIES=점심이네 + 인자 번호 5.  둘 다 주고 서로 다르면 멈춘다.
# 더 바꿀 때(표에 없는 시리즈는 셋 다 필수): SERIES_PREFIX(슬러그 접두) · SERIES_CONFIG(S2_CONFIG 로 넘길 설정 파일) ·
#   SERIES_LOGO(편시작 --로고) · 선택: SERIES_NAS(NAS 시리즈 폴더 — 번호 폴더들과 완성본/ 이 있는 곳) ·
#   SERIES_TITLE(하단 원제 출처: mp4 = mp4 파일 이름의 «_» 뒤(편시작 기본) · 폴더 = 소재 폴더 이름의 «NN.<시리즈>_» 뒤)
# bash 는 한글 변수명을 못 쓴다 — 변수는 영문, 값은 한글 그대로.
# 결과 변수: SERIES PFX n(번호, 앞 0 뗌) SLUG CFG LOGO NAS OUTBASE(= NAS/완성본) TITLE_FROM

_sk_defaults() {   # $1 = 시리즈 이름 → d_pfx d_cfg d_logo d_title
  d_pfx=""; d_cfg=""; d_logo=""; d_title=mp4
  case "$1" in
    싱글벙글)
      d_pfx=싱글
      d_cfg=$HOME/Desktop/스케치코미디/config_숨은기록.json
      d_logo=$HOME/Desktop/youstudio-mcp/자산/스케치코미디/channel_icon_숨은기록.png ;;
    점심이네)
      # 2026-09-29 사장님 결정 — 템플릿 «누룽지독»(Deep 에 쓰던 틀, 볼트 프리셋/스케치코미디/작품/Deep.md «로고 = 누룽지독(@yellow_dog) 고정»).
      #   하단 «#점심이네 - 원제», 원제 = mp4 파일 이름의 «_» 뒤(전례 — Deep·싱글벙글과 같음. 폴더 이름과는 다를 수 있다: 01 폴더 «내가 너네 운전기사야» · mp4 «…운전기사냐는 진짜 분노»).
      d_pfx=점심이네
      d_cfg=$HOME/Desktop/스케치코미디/config_누룽지독.json
      d_logo=$HOME/Desktop/youstudio-mcp/자산/스케치코미디/channel_logo_누룽지독.png
      [ -f "$d_logo" ] || d_logo=$HOME/Desktop/스케치코미디/work/Deep01_로고.png   # 저장소 자산이 들어오기 전 자리
      d_title=mp4 ;;   # ★2026-09-29 전례대로 mp4 파일 이름(Deep 카드 «파일명 = 하단 원제» 09-01 사장님 · 싱글벙글 credit.title = mp4 이름). 폴더 이름을 쓰려면 SERIES_TITLE=폴더
    루키치)
      # 2026-09-30 사장님 결정 — 채널(템플릿) «누룽지독» · 하단 «#루키치 - 원제» · 원제 = mp4 파일 이름의 «_» 뒤(점심이네와 같음).
      d_pfx=루키치
      d_cfg=$HOME/Desktop/스케치코미디/config_누룽지독.json
      d_logo=$HOME/Desktop/youstudio-mcp/자산/스케치코미디/channel_logo_누룽지독.png
      [ -f "$d_logo" ] || d_logo=$HOME/Desktop/스케치코미디/work/Deep01_로고.png
      d_title=mp4 ;;
  esac
}

sk_series() {   # $1 = 번호(NNN) 또는 슬러그(<접두>NNN). 실패면 ★ 한 줄 찍고 1.
  local a=$1 num="" found="" p s
  if [ -z "$a" ]; then echo "★번호나 슬러그를 준다 (예: 12 · 싱글12 · 점심이네5)"; return 1; fi
  if [[ $a =~ ^[0-9]+$ ]]; then
    num=$a
  else
    if [ -n "$SERIES" ]; then
      _sk_defaults "$SERIES"; p=${SERIES_PREFIX:-$d_pfx}
      if [ -n "$p" ] && [[ $a == "$p"* ]] && [[ ${a#"$p"} =~ ^[0-9]+$ ]]; then found=$SERIES; num=${a#"$p"}; fi
    fi
    if [ -z "$found" ]; then
      for s in 싱글벙글 점심이네 루키치; do
        _sk_defaults "$s"
        if [[ $a == "$d_pfx"* ]] && [[ ${a#"$d_pfx"} =~ ^[0-9]+$ ]]; then found=$s; num=${a#"$d_pfx"}; break; fi
      done
    fi
    if [ -z "$found" ]; then echo "★«${a}» — 번호도 아는 슬러그(싱글NNN·점심이네NNN·루키치NNN)도 아니다. 새 시리즈면 SERIES·SERIES_PREFIX 를 준다"; return 1; fi
    if [ -n "$SERIES" ] && [ "$SERIES" != "$found" ]; then
      echo "★시리즈가 엇갈린다 — 환경변수 SERIES=$SERIES · 슬러그 «${a}» 는 $found"; return 1
    fi
    SERIES=$found
  fi
  SERIES=${SERIES:-싱글벙글}
  _sk_defaults "$SERIES"
  PFX=${SERIES_PREFIX:-$d_pfx}
  CFG=${SERIES_CONFIG:-$d_cfg}
  LOGO=${SERIES_LOGO:-$d_logo}
  TITLE_FROM=${SERIES_TITLE:-$d_title}
  NAS=${SERIES_NAS:-"/Volumes/galaxy/영화자료/3. 스캐치코미디/$SERIES"}
  OUTBASE="$NAS/완성본"
  if [ -z "$PFX" ] || [ -z "$CFG" ] || [ -z "$LOGO" ]; then
    echo "★시리즈 «${SERIES}» 는 표에 없다 — SERIES_PREFIX·SERIES_CONFIG·SERIES_LOGO 를 같이 준다 (검수도구/배치/시리즈.sh)"; return 1
  fi
  case "$TITLE_FROM" in mp4|폴더) ;; *) echo "★SERIES_TITLE 은 mp4 또는 폴더: $TITLE_FROM"; return 1;; esac
  n=$((10#$num))          # 앞 0 뗌 — «05» 도 «5» 와 같은 편(슬러그 점심이네5 · 폴더 05.점심이네_…)
  SLUG=$PFX$n
  return 0
}
