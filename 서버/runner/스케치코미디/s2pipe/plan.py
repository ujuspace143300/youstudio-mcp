# 원본 롱폼을 보고 **5-Phase 로 자른다.** 이 파이프라인의 심장이다.
#
# sketch 와 갈리는 지점: sketch 는 `punch`(웃음의 세기)만 매겨 센 것을 끝에 놓는다.
# 그러면 구조가 평평해진다 — 실제로 punch 7·8·10·10·9·8·7·9·10 이 나왔고 첫 조각이
# 상황 설명이라 훅이 없었다. 여기서는 조각마다 **역할**(phase)을 준다.
#
#   python -m s2pipe.plan <youtube_url> [--slug 이름]
import base64, json, os, re, subprocess, sys, time, urllib.request, urllib.error

from . import gem

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
MODELS = CFG.get("gemini", {}).get("models", ["gemini-3.5-flash"])

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA = {
    "type": "object",
    "properties": {
        "logline": {"type": "string"},
        "hashtag": {"type": "string"},
        "titles": {"type": "array",
                   "items": {"type": "array", "items": {"type": "string"}}},
        "hooks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"t0": {"type": "number"}, "text": {"type": "string"}},
                "required": ["t0", "text"],
            },
        },
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "t0": {"type": "number"},
                    "t1": {"type": "number"},
                    "what": {"type": "string"},
                    "punch": {"type": "integer"},
                    "phase": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "narration": {"type": "string"},
                },
                "required": ["t0", "t1", "what", "punch", "phase", "keep"],
            },
        },
        "subs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"t": {"type": "number"}, "text": {"type": "string"},
                               "kind": {"type": "string"}},
                "required": ["t", "text"],
            },
        },
        "comment_picks": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["logline", "hashtag", "titles", "segments", "subs"],
}


def hot_block(hot):
    if not hot:
        return ""
    lines = "\n".join(f"- **{s//60:02d}:{s%60:02d}** (좋아요 {lk}) {note}"
                      for s, lk, note in hot)
    return f"""## ★★시청자가 실제로 웃은 자리 — 원본 댓글의 타임스탬프

{lines}

★★**이 자리를 빠뜨리면 안 된다.** 손수 시각까지 적어 남길 만큼 강한 대목이라는 뜻이다.
좋아요가 큰 지점은 **반드시 어느 Phase 에든 들어가야 한다.**
(sketch 에서 좋아요 3100짜리 대목을 통째로 버린 적이 있다 — 가장 아까운 실수다.)

★**댓글 시각은 정확하지 않다. 앞뒤로 10초쯤 어긋나는 게 보통이다.**
그 시각 하나만 보지 말고 **±10초를 훑어서 실제 장면을 찾아라.**

★이 시각들은 원본 재생 시각 그대로다 — 네가 매기는 `t0`·`t1` 과 같은 기준이다.
"""


def phase_block():
    rows = "\n".join(
        f"| {p['no']} | {p['name']} | {p['sec'][0]}-{p['sec'][1]}초 | {p['role']} "
        f"| punch {p['min_punch']} 이상 |"
        for p in CFG["edit"]["phases"])
    return f"""| Phase | 이름 | 자리 | 역할 | 세기 |
|---|---|---|---|---|
{rows}"""


def focus_block(focus, win=70):
    """★어느 대목을 쓸지 못박는다 — 같은 원본으로 다른 편을 만들어 견줄 때 쓴다."""
    if focus is None:
        return ""
    lo, hi = max(0, focus - win), focus + win
    return f"""## ★★★이번 편은 **{lo:.0f}~{hi:.0f}초 안에서만** 고른다

그 밖의 대목은 아무리 좋아도 쓰지 마라. 같은 원본으로 **다른 대목의 편**을 따로
만들어 견주려는 것이다. 이 범위 안에서 밀도를 채워라.
"""


def prompt(dur, fps, sub_text, hot=(), focus=None, cands=()):
    e, n, t = CFG["edit"], CFG["narration"], CFG["title_formula"]
    lo, hi = e["target_sec"]
    tf0, tf1 = e["tail_margin_frames"]
    ab0, ab1 = e["action_buffer_frames"]
    br0, br1 = e["breathing_room_sec"]
    pd0, pd1 = n["padding_sec"]
    tb = CFG["layout"]["title"]      # ★껍데기를 sketch 것으로 바꾼 뒤 키가 title 이다
    return f"""이 한국 스케치 코미디 롱폼({dur:.0f}초 · {fps:.3f}fps)을 숏폼 한 편으로 자르려 한다.
「마스터 지침서 3.11」의 규칙을 그대로 따라라.

## ★★기승전결은 5-Phase 다 — 이것이 이 채널의 뼈대다

{phase_block()}

조각마다 `phase` 를 반드시 매겨라. **세기만 보고 고르면 구조가 평평해진다.**

- **Phase 1 (Hook)** — 가장 센 대사를 **맨 앞에 선공개**한다. 상황 설명으로 열지 마라.
  ★**시간순이 아니어도 된다.** 뒤쪽 대목을 앞으로 끌어와도 좋다.
  첫 3초에 스크롤을 멈추게 하지 못하면 나머지는 아무 의미가 없다.
- **Phase 2 (Context)** — 나레이션 한 문장으로 상황을 압축한다. 롱폼에서 1~2분 걸리는
  설명을 여기서 끝낸다.
- **Phase 3 (Ping-Pong)** — 대사를 핑퐁 치듯 주고받는다. 가장 긴 구간이다.
- **Phase 4 (Climax)** — 감정·황당함이 폭발한다. 여기가 최고 punch 여야 한다.
  ★**Climax 가 앞쪽에 오면 안 된다.** 전체의 60% 지점을 지나서 와야 한다.
- **Phase 5 (Punchline)** — 최고 웃음 포인트에서 **여백 없이 칼같이 끝난다.**

### ★★★칸을 억지로 채우지 마라

**딱지는 조각에 붙이는 이름표가 아니라 그 조각이 하는 일이다.**

- ✗**연결 컷에 딱지를 붙이지 마라.** 장면을 넘기려고 스쳐 가는 1~2초짜리, 세기가
  낮은 대목은 **앞 조각에 이어 붙인다.** 실제로 「성적표를 들고 부르는 누나」라는
  1초짜리 연결 컷에 Climax 딱지가 붙은 적이 있다 — punch 4 짜리가 절정일 리 없다.
- ★★**절정과 마무리가 한 대목에 겹치면 그 대목을 둘로 쪼개라.** 감정이 터지는
  앞부분을 Phase 4, 웃음으로 닫는 뒷부분을 Phase 5 로 나눈다. 한 조각이 둘을
  겸하게 두면 Phase 4 자리에 엉뚱한 컷이 들어간다.
- ★**딱지가 붙는 조각은 그 역할에 맞는 세기여야 한다.** 표의 「세기」를 못 채우면
  그 조각은 그 Phase 가 아니다 — 다시 고르거나 쪼개라.

## 규칙

1. **완성 길이 {lo}~{hi}초.** 웃음 타격감이 가장 강한 구간이다(최대 {e['max_sec']}초).
0. ★★★**밀도 {e['density'][0]*100:.0f}~{e['density'][1]*100:.0f}%.**
   고른 조각들의 **첫 시작 ~ 마지막 끝** 범위를 재라. `완성 길이 ÷ 그 범위` 다.
   **이 값이 완성도를 가른다** — 같은 소재로 두 편을 만들어 견줬더니 밀도 46% 인 편이
   18% 인 편을 이겼다(구조는 18% 쪽이 더 정확했는데도).
   **넓게 퍼뜨리면 대목 사이 맥락이 끊겨 이야기가 안 이어진다.**
   ★좋은 대목이 몰려 있는 곳을 찾아 **그 언저리에서** 골라라. 원본 처음부터 끝까지
   훑어 하나씩 집어 오면 밀도가 무너진다.
2. ★**꼬리 마진 {tf0}~{tf1}프레임.** 대사 오디오가 끝난 뒤 그만큼 더 두고 `t1` 을 잡아라.
   짧게 치고 빠지는 대사가 **끝이 잘려 나가는** 것을 막는다. {fps:.0f}fps 기준 약
   {tf1/fps:.2f}초다.
3. ★**시각적 액션 버퍼 {ab0}~{ab1}프레임.** 문이 닫히거나 물건이 놓이는 등 **눈에 보이는
   동작이 끝날 때까지** `t1` 을 더 늘려라. 약 {ab0/fps:.1f}~{ab1/fps:.1f}초다.
4. ★★**숨고르기 {br0}~{br1}초.** 빠른 호흡만 쫓다 내용을 이해 못 하게 만들지 마라.
   상황 설명에 필수적인 핵심 대사, 리얼한 감정 표현(깊은 한숨, 억울함을 호소하는 표정)은
   **잘라내지 말고 늘어뜨려** 시청자가 스토리를 소화할 구간을 준다.
5. ★**나레이션 패딩 {pd0}~{pd1}초.** 나레이션을 넣는 조각은 그 문장을 읽을 시간보다
   **길어야 한다.** 짧으면 다음 대사가 겹쳐 튀어나온다. 나레이션은 {n['max_sec']:.0f}초 이내다.
6. **끝은 하드컷.** 마지막 조각은 대사가 끝나는 바로 그 지점에서 끊는다. 여운 금지.
7. 조각 사이는 여백 없이 붙인다.

## 낼 것

- `logline`: 이 편이 무슨 이야기인지 한 문장
- `titles`: **{CFG['output']['titles']}개.** 화면 상단에 넣을 극강의 어그로 제목.
  ★**각각 정확히 {tb['lines']}줄짜리 배열**로 낸다 — `["첫 줄", "둘째 줄"]`.
  한 줄 **{tb['max_chars']}자 이내**(두 줄 합쳐 {tb['max_chars']*tb['lines']}자까지).
  아래 4가지 공식 중 하나를 골라 쓴다.
  - A형 {t['A']}
  - B형 {t['B']}
  - C형 {t['C']}
  - D형 {t['D']}
  ★★**둘째 줄의 끝은 반드시 `?` `!` `...` 중 하나다.** 「그래서 어떻게 되는데?」라는
  생각을 무조건 하게 만들어야 한다.
- `hashtag`: 서브 해시태그 **1개**. 핵심 갈등이나 희망 힌트를 압축한다.
  예: `#그래서_몇_명이랑_사귄_거야?` `#아니_왜_저기서_저걸_건드려!!!`
- `segments`: 원본을 의미 덩어리로 자른 목록. **버릴 것도 포함해 전부** 낸다.
  - `t0` `t1`: 초 단위. ★**이 영상은 {dur:.0f}초({dur//60:.0f}분 {dur%60:.0f}초)다.
    `t1` 이 {dur:.0f} 를 넘으면 안 된다.**
  - ★★**시각은 반드시 아래 「원본 자막」에 적힌 `분:초` 를 근거로 하라.**
    그 대목의 대사를 자막에서 찾고 그 줄의 시각을 초로 바꿔 쓴다. 영상만 보고 어림하면
    **뒤로 갈수록 밀린다.**
  - ★**한 덩어리는 40초를 넘기지 마라.** 긴 구간은 대사가 바뀌는 자리에서 쪼갠다.
  - ★**덩어리는 원본을 빈틈없이 덮어야 한다.** 첫 `t0` 는 0, 마지막 `t1` 은 끝.
  - `what`: 무슨 일이 벌어지는지
  - `punch`: 웃음의 세기 0~10
  - `phase`: **1~5.** 위 표의 역할에 맞게. 버릴 조각(`keep:false`)은 0 으로.
  - `keep`: 숏폼에 넣을지
  - `narration`: 이 조각에 얹을 나레이션 한 문장(없으면 빈 문자열).
    ★**건조하고 무심한 톤.** 다큐멘터리 성우처럼 객관적으로. 화면 속 인물의 오버하는
    연기와 **대비**를 이뤄야 한다. 감탄사·이모지·구어체 금지.
    ★★**{int(n['max_sec'] * 6.5)}자를 넘기지 마라.** 읽는 데 {n['max_sec']:.0f}초가 넘으면
    다음 대사와 겹친다(한국어 나레이션은 초당 약 6.5자다).
    ★★★**어디에 얹느냐가 아니라 「어디에 얹지 않느냐」가 규칙이다.**
      나레이션이 나오는 동안 그 구간의 **원음은 죽는다.** 그러니
      - ○ **상황 설명 대사** 위에 얹어라 — 그 설명을 나레이션이 대신하므로 잃는 게 없다.
        화면에는 인물이 살아 있어 심심하지 않다.
      - ✗ **웃음이 터지는 대사 위에는 절대 얹지 마라** — 그건 들려야 한다.
        Phase 1(Hook)과 Phase 5(Punchline)에는 넣지 않는다.
      - ✗ **말이 없다는 이유로 고르지 마라.** 대사가 비는 대목은 대개 늘어지는
        대목이라, 소리는 깨끗해도 화면이 죽는다.
    ★주로 **Phase 2(Context)** 에 쓴다. 전체에서 **1~2개면 충분하다.**
  - ★★ **`phase` 가 곧 재생 순서다.** `keep:true` 인 것들을 **Phase 번호 순서대로**
    배열하라 — Phase 1 조각이 배열의 **맨 앞**이다. 그 조각이 원본 뒤쪽에 있어도
    앞으로 끌어온다. **원본 시간순으로 늘어놓고 라벨만 붙이면 훅이 죽는다.**
  - ★ `keep:true` 길이 합이 {lo}~{hi}초가 되게 하라.
- `hooks`: 롱폼 대사 중 **가장 후킹되는 것 3개**를 `t0`(원본 초)와 함께.
  ★**한 글자도 수정하지 마라.** 들린 그대로 적는다.
- `subs`: 넣을 구간의 자막을 **숏폼 시각 기준**으로. 한 줄 {CFG['layout']['subtitle']['max_chars']}자 이내.
  - `kind`: 배우 대사면 `"line"`, 나레이션이면 `"narr"`.
  - ★**대사가 있는 동안 자막이 비면 안 된다.** 3초 이상 비는 구간을 만들지 마라.
- `comment_picks`: 아래 댓글 후보 중 **이 편에 어울리는 것의 번호**를 고른 순서대로.
  ★네가 고른 대목과 맞닿는 반응만. 좋아요가 많아도 상관없는 것은 뺀다.

{focus_block(focus)}
{comment_block(cands)}
{hot_block(hot)}
## 원본 자막 (자동생성이라 부정확하다. 시각 참고용으로만 써라)

{sub_text}
"""


def fetch(url, work):
    """원본 영상·자막·댓글을 받는다. 이미 있으면 건너뛴다."""
    os.makedirs(work, exist_ok=True)
    vid = re.search(r"(?:v=|be/|shorts/)([\w-]{11})", url)
    vid = vid.group(1) if vid else url
    mp4 = os.path.join(work, f"{vid}.mp4")
    if not os.path.exists(mp4):
        for t in range(3):
            p = subprocess.run(["yt-dlp", "--encoding", "utf-8", "--no-progress",
                                "-f", "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b",
                                "--merge-output-format", "mp4",
                                "-o", os.path.join(work, "%(id)s.%(ext)s"), url],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if os.path.exists(mp4):
                break
            why = [ln for ln in (p.stderr or "").splitlines() if "ERROR" in ln]
            print(f"  다운로드 실패 {t+1}/3" + (f" — {why[-1].strip()}" if why else ""),
                  flush=True)
            if why and "403" in why[-1]:
                print("    ★403 이면 yt-dlp 가 낡은 것이다: yt-dlp --update-to nightly",
                      flush=True)
            time.sleep(10)
    subprocess.run(["yt-dlp", "--encoding", "utf-8", "--skip-download",
                    "--write-auto-subs", "--sub-langs", "ko", "--sub-format", "vtt",
                    "-o", os.path.join(work, "%(id)s.%(ext)s"), url],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    info = os.path.join(work, f"{vid}.info.json")
    if not os.path.exists(info):
        subprocess.run(["yt-dlp", "--encoding", "utf-8", "--skip-download",
                        "--write-comments", "--extractor-args",
                        "youtube:comment_sort=top;max_comments=120,120,0,0",
                        "-o", os.path.join(work, "%(id)s.%(ext)s"), url],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return vid, mp4, os.path.join(work, f"{vid}.ko.vtt")


def hot_moments(info_path, n=14):
    """댓글에 박힌 타임스탬프 — 사람들이 실제로 웃은 자리."""
    if not os.path.exists(info_path):
        return []
    try:
        d = json.load(open(info_path, encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        return []
    out = {}
    for c in d.get("comments") or []:
        t = (c.get("text") or "").replace("\n", " ").strip()
        likes = c.get("like_count") or 0
        for m in re.finditer(r"(\d{1,2}):(\d{2})", t):
            sec = int(m.group(1)) * 60 + int(m.group(2))
            if sec not in out or likes > out[sec][0]:
                out[sec] = (likes, t[:70])
    rows = sorted(((s, v[0], v[1]) for s, v in out.items()), key=lambda x: -x[1])
    return sorted(rows[:n])


def fit_comment(t, hi):
    """한 줄에 들어가게 줄인다. 어절 경계에서 끊고 말줄임을 붙인다."""
    if len(t) <= hi:
        return t
    cut = t[:hi - 1]
    sp = cut.rfind(" ")
    if sp >= hi * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,.·") + "…"


# ★★영상 내용과 무관한 댓글을 거른다. 좋아요 순으로만 뽑으면 **채널 공지성 댓글이
#   상위를 차지한다** — 실측에서 「댓글 두 번 터치하면 따봉」 「<뉴발란스 이벤트>」
#   「D-DAY 보고 다시 왔으면 개추」 같은 것이 화면의 절반을 먹었다. 읽는 재미가 없다.
JUNK = re.compile(
    r"개추|추천\s*!|구독|알림\s*설정|좋아요\s*(눌|박)|따봉|고정\s*댓|첫\s*댓|1빠"
    r"|이벤트|협찬|광고|증정|응모|당첨|http|www\.|D-?DAY|디데이"
    r"|다시\s*(왔|보러)|보고\s*(왔|다시)|정주행|알고리즘", re.I)


def is_junk(t):
    if JUNK.search(t):
        return True
    # 이모지·기호만 잔뜩인 것은 읽을 거리가 아니다
    letters = sum(1 for ch in t if ch.isalnum())
    return letters < len(t) * 0.5


def pick_comments(info_path, dur=None, chosen=None):
    """화면에 얹을 댓글을 고른다. ★**긴 것을 버리지 말고 줄여서 쓴다.**

    sketch 실측: 길이로 거르면 120개를 받아도 2개만 남는다(한국어 댓글은 대개 26자를
    넘는다). 그러면 build 가 편 전체에 균등 배치하므로 하나가 37초씩 떠 있어 읽을 게
    없어진다. 개수는 `config.layout.comment.sec_each` 가 정한다.
    """
    if not os.path.exists(info_path):
        return []
    try:
        d = json.load(open(info_path, encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        return []
    cm = CFG["layout"]["comment"]
    hi, each = cm.get("max_chars", 26), cm.get("sec_each", 6.0)
    n = max(6, int((dur or 60) / each)) if each else 6
    out, seen = [], set()
    for c in sorted(d.get("comments") or [], key=lambda x: -(x.get("like_count") or 0)):
        t = (c.get("text") or "").replace("\n", " ").strip()
        if len(t) < 6 or re.search(r"\d+:\d\d", t) or is_junk(t):
            continue
        t = fit_comment(t, hi)
        if t[:12] in seen:
            continue
        seen.add(t[:12])
        out.append({"nick": c.get("author", ""), "text": t,
                    "likes": c.get("like_count") or 0})
    # ★★모델이 **영상을 보고 고른 것**이 있으면 그 순서를 앞세운다. 좋아요만 보면
    #   그 장면과 상관없는 댓글이 뽑힌다 — 어느 대목을 쓰는지는 모델이 안다.
    if chosen:
        pick = {i for i in chosen if 0 <= i < len(out)}
        out = [c for i, c in enumerate(out) if i in pick] + \
              [c for i, c in enumerate(out) if i not in pick]
    return out[:n]


def comment_block(cands):
    """모델에게 댓글 후보를 번호와 함께 보여 준다."""
    if not cands:
        return ""
    lines = "\n".join(f"{i}. ({c['likes']}) {c['text']}"
                      for i, c in enumerate(cands[:40]))
    return f"""## 화면에 얹을 댓글 후보 — **어느 것이 이 편에 어울리나**

{lines}

★**네가 고른 대목과 맞닿는 반응**을 골라라. 좋아요가 많아도 그 장면과 상관없으면
빼라 — 이 채널은 댓글을 읽는 재미로 보는데, 엉뚱한 댓글은 읽을 값어치가 없다.
★번호만 낸다(`comment_picks`). 문구는 고치지 마라.
"""


def vtt_text(path):
    if not os.path.exists(path):
        return "(자막 없음)"
    TAG = re.compile(r"<[^>]+>")
    TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d{3} --> ")
    rows, last, cur = [], None, 0
    for ln in open(path, encoding="utf-8"):
        m = TIME.match(ln)
        if m:
            h, mi, s = m.groups()
            cur = int(h) * 3600 + int(mi) * 60 + int(s)
            continue
        t = TAG.sub("", ln).strip()
        if not t or t == last or t.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        last = t
        if rows and (t.startswith(rows[-1][1]) or rows[-1][1] in t):
            rows[-1] = (rows[-1][0], t)
        else:
            rows.append((cur, t))
    return "\n".join(f"{t//60:02d}:{t%60:02d} {x}" for t, x in rows)


def probe(path):
    """길이와 **프레임레이트**. ★fps 는 마진 계산의 기준이라 반드시 원본값을 쓴다."""
    o = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", "-show_streams", "-select_streams", "v:0",
                        path], capture_output=True, text=True)
    d = json.loads(o.stdout)
    dur = float(d["format"]["duration"])
    r = d["streams"][0].get("avg_frame_rate") or d["streams"][0].get("r_frame_rate")
    try:
        a, b = r.split("/")
        fps = float(a) / float(b)
    except Exception:                                    # noqa: BLE001
        fps = 30.0
    return dur, fps


def origin_of(info_path):
    try:
        d = json.load(open(info_path, encoding="utf-8"))
        return {"channel": d.get("channel") or d.get("uploader") or "",
                "title": d.get("title") or ""}
    except Exception:                                    # noqa: BLE001
        return {"channel": "", "title": ""}


def call(mp4, dur, fps, sub_text, hot, focus=None, cands=()):
    b64 = base64.b64encode(open(mp4, "rb").read()).decode()
    payload = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "video/mp4", "data": b64}},
            {"text": prompt(dur, fps, sub_text, hot, focus, cands)},
        ]}],
        "generationConfig": {"maxOutputTokens": 32000,
                             "responseMimeType": "application/json",
                             "responseSchema": SCHEMA},
    }
    txt, _route, _model = gem.ask(payload, MODELS, timeout=900, tries=6)
    if txt is None:
        raise RuntimeError("모든 경로가 막혔다")
    return json.loads(txt)


def main():
    if len(sys.argv) < 2:
        print("python -m s2pipe.plan <youtube_url> [--slug 이름]")
        return 1
    url = sys.argv[1]
    slug = sys.argv[sys.argv.index("--slug") + 1] if "--slug" in sys.argv else None
    focus = (float(sys.argv[sys.argv.index("--focus") + 1])
             if "--focus" in sys.argv else None)

    work = os.path.join(HERE, CFG["paths"]["work"])
    vid, mp4, vtt = fetch(url, work)
    if not os.path.exists(mp4):
        print("원본을 못 받았다")
        return 1
    slug = slug or vid
    dur, fps = probe(mp4)
    print(f"원본 {dur:.0f}초 · {fps:.3f}fps · {os.path.getsize(mp4)/1024/1024:.1f}MB",
          flush=True)

    info = os.path.join(work, f"{vid}.info.json")
    hot = hot_moments(info)
    if hot:
        print(f"댓글 타임스탬프 {len(hot)}곳 — 사람들이 웃은 자리를 근거로 준다", flush=True)
        for s, lk, note in hot[:8]:
            print(f"   {s//60:02d}:{s%60:02d} ({lk})  {note[:44]}", flush=True)

    if focus is not None:
        print(f"★{focus:.0f}초 언저리에서만 고른다", flush=True)
    # ★댓글 후보를 미리 걸러 모델에게 보여 준다 — **어느 대목을 쓰는지는 모델이 안다**
    cands = pick_comments(info, 9999)
    if cands:
        print(f"댓글 후보 {len(cands)}개 — 어울리는 것을 모델이 고른다", flush=True)
    plan = call(mp4, dur, fps, vtt_text(vtt), hot, focus, cands)

    # ★모델이 원본 길이를 넘는 타임코드를 낸다. 그런데 **일정한 비율로 늘어난다** —
    #   274→412(1.50배) · 416→656(1.58배). 그냥 버리면 뒤쪽 좋은 대목이 통째로
    #   날아가므로 먼저 비율을 되돌리고, 그래도 밖이면 그때 버린다.
    over = max((s["t1"] for s in plan["segments"]), default=0)
    if over > dur * 1.06:
        ratio = dur / over
        print(f"★타임코드가 {1/ratio:.2f}배 늘어났다 — {ratio:.3f} 로 되돌린다", flush=True)
        for s in plan["segments"]:
            s["t0"] = round(s["t0"] * ratio, 1)
            s["t1"] = round(s["t1"] * ratio, 1)
        for h in plan.get("hooks", []):
            h["t0"] = round(h["t0"] * ratio, 1)

    bad = [s for s in plan["segments"] if s["t1"] > dur + 1 or s["t0"] < 0]
    if bad:
        print(f"★원본({dur:.0f}초) 밖 구간 {len(bad)}개를 버렸다", flush=True)
        plan["segments"] = [s for s in plan["segments"] if s not in bad]

    # ★★**Phase 순서로 다시 세운다.** 모델은 Phase 라벨을 붙이라고 하면 붙이지만
    #   **배열은 원본 시간순 그대로 두는 일이 잦다** — 실제로 [2,1,3,3,4,5] 가 나와
    #   Hook 이 15초 지점에 놓였다. 라벨이 곧 재생 순서라는 것이 이 채널의 규칙이므로
    #   코드가 보장한다. 같은 Phase 안에서는 원본 시간순을 지킨다.
    keep = [s for s in plan["segments"] if s.get("keep")]
    before = [s.get("phase", 0) for s in keep]
    keep.sort(key=lambda s: (s.get("phase", 9), s["t0"]))
    after = [s.get("phase", 0) for s in keep]
    if before != after:
        print(f"★Phase 순서로 다시 세웠다 — {before} → {after}", flush=True)
    total = sum(s["t1"] - s["t0"] for s in keep)

    proj = {
        "slug": slug,
        "source": {"url": url, "id": vid, "dur": round(dur, 1), "fps": round(fps, 3)},
        "logline": plan.get("logline", ""),
        "title": (plan.get("titles") or [[""]])[0],
        "title_candidates": plan.get("titles", []),
        "hashtag": plan.get("hashtag", ""),
        "hooks": plan.get("hooks", []),
        "segments": keep,
        "segments_all": plan["segments"],
        "subs": plan.get("subs", []),
        "comments": pick_comments(info, total, plan.get("comment_picks")),
        "comment_picks": plan.get("comment_picks", []),
        "credit": origin_of(info),
        "_est_sec": round(total, 1),
    }
    pdir = os.path.join(HERE, CFG["paths"]["projects"])
    os.makedirs(pdir, exist_ok=True)
    dst = os.path.join(pdir, f"{slug}.json")
    json.dump(proj, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n{proj['logline']}")
    lo, hi = CFG["edit"]["target_sec"]
    print(f"구간 {len(keep)}개 / 전체 {len(plan['segments'])}개 · 예상 {total:.0f}초 "
          + ("OK" if lo <= total <= hi else f"★목표 {lo}~{hi}초 밖"))
    names = {p["no"]: p["name"] for p in CFG["edit"]["phases"]}
    at = 0.0
    for s in keep:
        ph = s.get("phase", 0)
        nr = (s.get("narration") or "").strip()
        print(f"  P{ph} {names.get(ph, '?'):<10} {at:5.1f}초  원본 {s['t0']:7.1f}~{s['t1']:7.1f}"
              f"  punch {s['punch']:2d}  {s['what'][:30]}"
              + (f"\n        나레: {nr[:44]}" if nr else ""))
        at += s["t1"] - s["t0"]
    print(f"\n제목 후보:")
    for t in plan.get("titles", []):
        print(f"  {t}")
    print(f"해시태그: {plan.get('hashtag', '')}")
    print(f"\n저장: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
