#!/usr/bin/env bash
# ============================================================
#  유스튜디오 한방 설치 (맥) — 지인용. 토큰 하나로 끝낸다.
#
#    bash 한방설치.sh <관리자에게-받은-토큰> [--저장소 <git URL>] [--서버 <URL>] [--자리 <폴더>]
#
#  하는 일 (여러 번 실행해도 안전 — 있는 것은 건너뛴다)
#    1 Homebrew · node · ffmpeg · python · git      2 Claude Code
#    3 코드(러너) 받기 — 공개 GitHub 에서 clone / 이미 있으면 pull
#    4 이 컴퓨터의 설치 id(~/.youstudio/device) + 서버 자산 받기(글꼴 등 · 토큰 있는 사람만 · sha256 확인)
#    5 러너 파이썬 venv(~/.youstudio/venv · pillow numpy opencv)      6 API 키(본인 발급 · ~/.volcano/keys)
#    7 Claude Code 에 유스튜디오 붙이기(claude mcp add · 두 헤더)     8 프리미어 + CEP 확장
#  설계: 설계/인증_이메일허가제.md · 이식원칙 ⑥(길 C — 코드는 공개, 자산은 토큰 인증 서버에서)
# ============================================================
set -u
TOKEN="${1:-}"; shift || true
REPO="https://github.com/ujuspace143300/youstudio-mcp.git"
SERVER="https://youstudio-mcp.youstudio.workers.dev"
DEST="$HOME/Desktop/youstudio-mcp"
PRESET="린박스"
while [ $# -gt 0 ]; do
  case "$1" in
    --저장소) REPO="$2"; shift 2;;
    --서버) SERVER="$2"; shift 2;;
    --자리) DEST="$2"; shift 2;;
    --프리셋) PRESET="$2"; shift 2;;
    *) echo "★모르는 인자: $1"; exit 2;;
  esac
done
say(){ printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok(){ printf '   \033[32m✔ %s\033[0m\n' "$*"; }
warn(){ printf '   \033[33m⚠ %s\033[0m\n' "$*"; }
stop(){ printf '   \033[31m★ %s\033[0m\n' "$*"; exit 1; }
[ -n "$TOKEN" ] || stop "토큰이 필요하다:  bash 한방설치.sh <토큰>   (관리자에게 받는다 · 한 번만 보인다)"

# ── 1. Homebrew · 도구 ───────────────────────────────────────
say "1/8 Homebrew · node · ffmpeg · python · git"
if ! command -v brew >/dev/null 2>&1; then
  echo "   Homebrew 설치 (맥 비밀번호를 물어본다)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
grep -q 'brew shellenv' "$HOME/.zprofile" 2>/dev/null || echo 'eval "$('"$(command -v brew)"' shellenv)"' >> "$HOME/.zprofile"
for p in node ffmpeg python git; do brew list "$p" >/dev/null 2>&1 || brew install "$p"; done
ok "node $(node -v) · $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3) · $(python3 --version)"

# ── 2. Claude Code ───────────────────────────────────────────
say "2/8 Claude Code"
command -v claude >/dev/null 2>&1 || npm install -g @anthropic-ai/claude-code
ok "claude $(claude --version 2>/dev/null | head -1)"

# ── 3. 코드(러너) ────────────────────────────────────────────
say "3/8 코드 받기 → $DEST"
if [ -d "$DEST/.git" ]; then (cd "$DEST" && git pull -q --ff-only && ok "이미 있음 — 최신으로 당김 $(git rev-parse --short HEAD)"); else git clone -q "$REPO" "$DEST" && ok "받았다 $(cd "$DEST" && git rev-parse --short HEAD)"; fi
[ -f "$DEST/서버/runner/기기.mjs" ] || stop "저장소 꼴이 다르다 — 서버/runner/기기.mjs 가 없다"

# ── 4. 설치 id + 자산 ────────────────────────────────────────
say "4/8 설치 id · 서버 자산(글꼴 등 · 토큰으로만 받는다)"
DEV="$(cd "$DEST/서버/runner" && node -e "import('./기기.mjs').then(m=>console.log(m.deviceId()))")"
[ -n "$DEV" ] || stop "설치 id 를 못 만들었다 (~/.youstudio/device)"
ok "설치 id $DEV"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Youstudio-Device: $DEV")
H="$(curl -s -m 20 -o /dev/null -w '%{http_code}' "${AUTH[@]}" "$SERVER/asset/$PRESET/_목록.json")"
case "$H" in
  200) ;;
  401) stop "서버가 거부했다(401) — 토큰이 틀렸거나 만료·차단·기기 초과·프리셋 권한 없음. 관리자에게 «$PRESET 권한» 을 확인하라: $(curl -s -m 20 "${AUTH[@]}" "$SERVER/asset/$PRESET/_목록.json" | cut -c1-160)";;
  *) stop "서버에 못 붙었다(HTTP $H) — 주소 $SERVER 와 인터넷을 확인하라";;
esac
MAN="$(curl -s -m 30 "${AUTH[@]}" "$SERVER/asset/$PRESET/_목록.json")"
ADIR="$DEST/자산/$PRESET"; mkdir -p "$ADIR"
N=0; BAD=0
while IFS=$'\t' read -r rel bytes sha; do
  [ -n "$rel" ] || continue
  out="$ADIR/$rel"; mkdir -p "$(dirname "$out")"
  if [ -f "$out" ] && [ "$(shasum -a 256 "$out" | cut -d' ' -f1)" = "$sha" ]; then N=$((N+1)); continue; fi
  enc="$(python3 -c 'import sys,urllib.parse;print("/".join(urllib.parse.quote(s) for s in sys.argv[1].split("/")))' "$rel")"
  curl -s -m 120 "${AUTH[@]}" -o "$out" "$SERVER/asset/$PRESET/$enc"
  if [ "$(shasum -a 256 "$out" 2>/dev/null | cut -d' ' -f1)" = "$sha" ]; then N=$((N+1)); else BAD=$((BAD+1)); warn "받은 파일이 목록과 다르다: $rel"; rm -f "$out"; fi
done < <(printf '%s' "$MAN" | python3 -c 'import json,sys;[print(f["path"],f["bytes"],f["sha256"],sep="\t") for f in json.load(sys.stdin)["files"]]')
[ "$BAD" -eq 0 ] || stop "자산 $BAD개를 못 받았다 — 다시 돌려라"
ok "자산 $N개 확인 → $ADIR"

# ── 5. 러너 파이썬 ───────────────────────────────────────────
say "5/8 러너 파이썬 ~/.youstudio/venv (pillow · numpy · opencv)"
VENV="$HOME/.youstudio/venv"
[ -x "$VENV/bin/python3" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip pillow numpy opencv-python >/dev/null && ok "venv 준비 ($("$VENV/bin/python3" --version))"
"$VENV/bin/python3" -c "import PIL, numpy, cv2" || stop "venv 모듈이 안 들어갔다"

# ── 6. API 키 ────────────────────────────────────────────────
say "6/8 API 키 (본인이 발급 · ~/.volcano/keys/) — 린박스: speechmatics(전사) · typecast(나레)"
K="$HOME/.volcano/keys"; mkdir -p "$K"
for name in speechmatics typecast; do
  if [ -s "$K/$name" ]; then ok "$name 이미 있음"; continue; fi
  printf '   %s 키 붙여넣고 엔터 (건너뛰려면 그냥 엔터): ' "$name"; read -r val
  if [ -n "$val" ]; then printf '%s\n' "$val" > "$K/$name"; chmod 600 "$K/$name"; ok "$name 저장"; else warn "$name 건너뜀 — 나중에 $K/$name 에 넣으면 된다"; fi
done
printf 'YOUSTUDIO_TOKEN=%s\n' "$TOKEN" > "$HOME/.youstudio/env"; chmod 600 "$HOME/.youstudio/env"
grep -q 'youstudio/env' "$HOME/.zprofile" 2>/dev/null || echo 'set -a; [ -f "$HOME/.youstudio/env" ] && . "$HOME/.youstudio/env"; set +a' >> "$HOME/.zprofile"
ok "토큰 → ~/.youstudio/env (러너가 YOUSTUDIO_TOKEN 으로 읽는다)"

# ── 7. Claude Code 에 붙이기 ─────────────────────────────────
say "7/8 Claude Code ← 유스튜디오 (claude mcp add · 토큰 + 설치 id 헤더)"
(cd "$DEST/서버/runner" && node 설치도우미.mjs "$TOKEN" --서버 "$SERVER" --붙이기) || warn "붙이기 실패 — 위 명령을 직접 붙여넣어라"

# ── 8. 프리미어 + CEP 확장 ───────────────────────────────────
say "8/8 프리미어 · CEP 확장(com.volcano.prproj)"
"$VENV/bin/python3" "$DEST/서버/runner/린박스/도구/프리미어깔기.py" --쓰기 || warn "프리미어 길이 아직 안 열렸다 — 위 ★ 줄을 보라(프리미어가 없으면 설치 뒤 다시)"

say "끝. 이제:  cd \"$DEST\" && claude   →  /mcp 에서 youstudio · 연결됨 확인 → «린박스 EP01 시작» 처럼 말하면 서버가 순서대로 지시한다"
echo "   러너 실행기: $VENV/bin/python3 \"$DEST/서버/runner/린박스/실행기.py\" --url $SERVER --state <상태.json> --source <드라마.mp4> --title <작품> --workdir <드라마 폴더> --ep EP01 --start <초> --end <초> --repo \"$DEST\""
