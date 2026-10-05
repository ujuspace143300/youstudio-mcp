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
from . import cfg
from .cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)
try:  # ffmpeg·ffprobe 스레드 상한은 ff.명령 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
    from . import ff
except ImportError:  # 단독 실행(python s2pipe/x.py)
    import ff  # type: ignore
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
                    "첫대사": {"type": "string"},   # keep 조각이 담는 첫 원본 자막 줄 — plan관문 ⑦ 이 시각과 맞대 본다(2026-09-29)
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
        "ending": {
            "type": "object",
            "properties": {"type": {"type": "string"}, "desc": {"type": "string"}},
            "required": ["type", "desc"],
        },
    },
    "required": ["logline", "hashtag", "titles", "segments", "subs", "ending"],
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


def 파악_block(파악):
    """agy 파악 답(원본을 통째로 보고 들은 답)을 plan 입력으로 — 줄거리·인물 관계·셋업·결말·로고 시각의 근거.
    (2026-09-29 점심이네 64편 — plan 이 인물 관계를 틀리고(36 친구를 «남매»로) 결말 반전의 셋업을 뺐는데, 같은 원본을 본
     파악 답은 대체로 맞았고 에이전트는 그 답으로 plan 을 바로잡았다. plan 은 그 답을 받은 적이 없었다.)"""
    if not 파악:
        return ""
    return f"""## ★★원본을 통째로 보고 들은 «파악 답» — 줄거리·인물 관계·셋업·결말의 근거

{파악['글'].strip()}

★**인물 관계(친구·남매·연인·선후임)와 결말은 이 답을 따른다.** 네가 영상에서 다르게 짐작했으면 이 답이 맞다.
★★**셋업(결말이 뒤집거나 닫는 약속·내기·경고·질문·거짓말) 대사는 반드시 조각에 넣는다** — 셋업을 빼면 결말이 왜 웃긴지
  알 수 없다(관문이 재고, 빠지면 주의로 알린다 — 같은 구실을 하는 다른 대사가 조각에 있으면 그것으로 된다). «꼭 남길 대사» 도 되도록 담는다.
★**로고(아웃트로 카드)가 나온 뒤의 목소리는 결말이 아니다** — 굽기가 카드에서 조각을 잘라 낸다. 결말은 로고 앞 마지막 대사다.
★이 답의 시각은 ±2초 어림이다. 조각의 t0·t1 은 아래 「원본 자막」 시각으로 잡는다.
"""


_글길_머리 = """## ★★★영상 없이 짠다 — 원본 자막(전사)과 파악 답만 준다
영상을 붙인 요청이 구글 안전 필터에 막혔다. 아래 「원본 자막」(0.1초 시각)과 「파악 답」만으로 조각을 골라라.
- 장면·인물은 파악 답의 흐름과 대화 맥락(질문과 대답, 호칭)으로 판단한다. 아래 글 가운데 «영상을 보고» 는 «자막과 파악 답을 읽고» 로 읽어라.
- ★★**답에 욕설·성적 표현·폭력 낱말을 옮겨 적지 마라** — 그 낱말은 `○` 로 가린다(`hooks.text`·`what`·`logline`·`narration`).
  시각이 정본이다: 훅 대사 글은 코드가 원본 자막에서 다시 채운다(`첫대사` 도 가린 채 적어도 된다).
- ★`subs` 는 **빈 목록** `[]` 으로 낸다 — 초안 자막은 코드가 원본 자막에서 짠다(굽기 뒤 ④ 가 완성본 전사로 다시 짠다).

"""
_줄임 = """

## ★★앞선 답이 출력 한도를 넘어 잘렸다 — 이번에는 짧게
- `subs` 는 **빈 목록** `[]` 으로 낸다(초안 자막은 코드가 원본 자막에서 짠다).
- `segments` 의 `what` 은 25자 이내, 버리는 조각(`keep:false`)은 40초 덩어리로 크게 묶어 몇 개만.
- 생각은 짧게 하고 곧바로 답을 내라.
"""


def prompt(dur, fps, sub_text, hot=(), focus=None, cands=(), 원제="", 파악=None, 글길=False):
    # ★나레 글자 상한은 make 관문과 같은 식(max_sec ÷ sec_per_char)으로 알려 준다 (2026-09-29 — 예전 문구 «3×6.5=19자» 는
    #   make 의 «글자 × 0.161초 > 3초» 반려(18자까지)보다 1자 넉넉해, 점심이네 초안 10편이 정확히 19자 나레로 반려됐다)
    e, n, t = CFG["edit"], CFG["narration"], CFG["title_formula"]
    lo, hi = e["target_sec"]
    tf0, tf1 = e["tail_margin_frames"]
    ab0, ab1 = e["action_buffer_frames"]
    br0, br1 = e["breathing_room_sec"]
    pd0, pd1 = n["padding_sec"]
    tb = CFG["layout"]["title"]      # ★껍데기를 sketch 것으로 바꾼 뒤 키가 title 이다
    # ★원제 = 이 편의 핵심 사연·반전 (2026-09-27 100편 배치 — plan 이 원제의 줄거리·결말을 통째로 빼고 곁가지만
    #   고른 편이 절반 넘게 나왔다: 싱글266·267·241·248 등. 원제를 몰랐다.)
    원제줄 = (f"\n## ★★원제 «{원제}» — 이 편이 무엇에 관한 것인지다\n"
             "원제가 말하는 사연·반전이 들어 있는 대목과, 원본 끝(아웃트로 직전)의 진짜 결말을 **반드시** 담아라. "
             "곁가지 장면만으로 짜지 마라. 원제를 그대로 제목(titles)으로 쓰지는 마라.\n") if 원제 else ""
    return f"""{_글길_머리 if 글길 else ""}이 한국 스케치 코미디 롱폼({dur:.0f}초 · {fps:.3f}fps)을 숏폼 한 편으로 자르려 한다.
「마스터 지침서 3.11」의 규칙을 그대로 따라라.
{원제줄}
## ★★기승전결은 5-Phase 다 — 이것이 이 채널의 뼈대다

{phase_block()}

조각마다 `phase` 를 반드시 매겨라. **세기만 보고 고르면 구조가 평평해진다.**

- **Phase 1 (Hook)** — 가장 센 대사를 **맨 앞에 선공개**한다. 상황 설명으로 열지 마라.
  ★**시간순이 아니어도 된다.** 뒤쪽 대목을 앞으로 끌어와도 좋다.
  첫 3초에 스크롤을 멈추게 하지 못하면 나머지는 아무 의미가 없다.
  ★★★**훅은 반드시 대사다.** 말 없는 먹방·행동 컷은 화면이 좋아도 훅이 아니다 —
  Hook 조각의 구간 안에 `hooks` 1번 대사의 시각이 들어 있어야 한다(게이트가 잰다).
  **제목이 던진 질문을 첫 대사가 받아야 한다** — 전제(이 편이 무슨 상황인지)가 서는 대사를 골라라.
- **Phase 2 (Context)** — 나레이션 한 문장으로 상황을 압축한다. 롱폼에서 1~2분 걸리는
  설명을 여기서 끝낸다.
- **Phase 3 (Ping-Pong)** — 대사를 핑퐁 치듯 주고받는다. 가장 긴 구간이다.
- **Phase 4 (Climax)** — 감정·황당함이 폭발한다. 여기가 최고 punch 여야 한다.
  ★**Climax 가 앞쪽에 오면 안 된다.** 전체의 60% 지점을 지나서 와야 한다.
- **Phase 5 (Punchline)** — 최고 웃음 포인트에서 **여백 없이 칼같이 끝난다.**
  ★★★**절대 지침 — 끝에는 반전 또는 결론이 반드시 있다.** 최고점에서 끊는 것과
  이야기가 끝나는 것은 다르다. 마지막 조각을 보고 「아, 이렇게 끝났구나」가 나와야 한다 —
  상황이 **뒤집히거나(반전) 닫혀야(결론)** 한다. 웃음의 꼭대기일 뿐 이야기를 닫지 못하는
  조각은 Phase 5 가 아니다. 제목이 만든 「그래서 어떻게 되는데?」에 이 조각이 **답한다.**
  ★★**결말이 클러스터에서 멀어도 된다 — 「결말 점프」.** 마지막 조각 하나(10초 이내)는
  원본 어디에 있든 데려올 수 있고 밀도 계산에서 빠진다. 그러니 결말 때문에 좋은
  클러스터를 버리지 마라 — 클러스터는 웃음이 몰린 곳에, 결말은 진짜 결말에.
  없는 결말을 지어내지 마라.

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

1. ★★★**완성 길이 {lo}~{hi}초 — 절대 규칙.** 기승전결을 담을 최소 길이다(상한 {e['max_sec']}초).
   짧으면 반려된다. 클러스터 **안에서** 핑퐁·절정을 더 담아 채워라.
0. ★★★**밀도 {e['density'][0]*100:.0f}~{e['density'][1]*100:.0f}%.**
   고른 조각들의 **첫 시작 ~ 마지막 끝** 범위를 재라. `완성 길이 ÷ 그 범위` 다.
   **이 값이 완성도를 가른다** — 같은 소재로 두 편을 만들어 견줬더니 밀도 46% 인 편이
   18% 인 편을 이겼다(구조는 18% 쪽이 더 정확했는데도).
   **넓게 퍼뜨리면 대목 사이 맥락이 끊겨 이야기가 안 이어진다.**
   ★좋은 대목이 몰려 있는 곳을 찾아 **그 언저리에서** 골라라. 원본 처음부터 끝까지
   훑어 하나씩 집어 오면 밀도가 무너진다.
   ★단 **마지막 결말 조각(결말 점프, 10초 이내)은 범위 계산에서 빠진다** — 결말은
   멀리 있어도 데려와라.
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
   ★단 하드컷은 「어떻게 끊느냐」다 — 「무엇으로 끝나느냐」는 Phase 5 절대 지침(반전·결론)을 따른다.
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
  - `첫대사`: ★`keep:true` 조각마다 **그 조각이 담는 첫 원본 자막 줄을 그대로**(아래 「원본 자막」에서 옮겨 적는다).
    관문이 이 줄을 전사에서 찾아 `t0` 언저리에 있는지 잰다 — 설명과 시각이 다른 장면을 가리키면 반려된다.
  - `punch`: 웃음의 세기 0~10
  - `phase`: **1~5.** 위 표의 역할에 맞게. 버릴 조각(`keep:false`)은 0 으로.
  - `keep`: 숏폼에 넣을지
  - `narration`: 이 조각에 얹을 나레이션 한 문장(없으면 빈 문자열).
    ★**건조하고 무심한 톤.** 다큐멘터리 성우처럼 객관적으로. 화면 속 인물의 오버하는
    연기와 **대비**를 이뤄야 한다. 감탄사·이모지·구어체 금지.
    ★★**공백 포함 {int(n['max_sec'] / n.get('sec_per_char', 0.15))}자를 넘기지 마라(관문이 글자 수로 잰다).** 읽는 데
    {n['max_sec']:.0f}초가 넘으면 다음 대사와 겹친다.
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
  ★★**구두점 금지(절대 규칙)** — 자막·나레이션에 마침표·쉼표·말줄임(…)을 쓰지 마라.
    물음표·느낌표만 허용. 쉼표 자리는 띄어쓰기로.
  - `kind`: 배우 대사면 `"line"`, 나레이션이면 `"narr"`.
  - ★**대사가 있는 동안 자막이 비면 안 된다.** 3초 이상 비는 구간을 만들지 마라.
- `comment_picks`: 아래 댓글 후보 중 **이 편에 어울리는 것의 번호**를 고른 순서대로.
  ★네가 고른 대목과 맞닿는 반응만. 좋아요가 많아도 상관없는 것은 뺀다.
- `ending`: ★★★**이 편이 무엇으로 끝나는지.** 필수다.
  - `type`: `"반전"` 또는 `"결론"` — 마지막 조각에서 상황이 뒤집히면 반전, 닫히면 결론.
  - `desc`: 그 결말을 **한 문장**으로. 마지막 조각(Phase 5)에서 실제로 벌어지는 일이어야
    한다 — 화면에 없는 결말을 적으면 안 된다.
  ★desc 를 한 문장으로 적을 수 없다면 결말이 없는 것이다. 그러면 조각 선택으로 돌아가
    결말이 있는 대목까지 범위를 잡아라.

### ★★관문이 plan 직후에 재는 것 (2026-09-29 — 반려되면 수리 지침과 함께 다시 부른다)
- **훅 대사를 본문에서 또 쓰지 마라** — 훅 조각의 원본 구간이 다른 조각과 겹치거나, 같은 말이 본문 조각에서 또 나오면 반려.
- **나레는 꼭 남길 대사·훅 대사 위에 얹지 마라** — 나레 조각 머리에서 (글자 수 × 0.11초) 동안 원음이 죽는다.
- **로고(아웃트로 카드) 위로 조각을 늘이지 마라** — 카드 뒤 목소리(쿠키 대사)는 결말이 아니다.
- **밀도·Climax 위치·결말 포함·조각 겹침** 은 위 규칙 그대로 잰다.

{파악_block(파악)}
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


def _vtt_큐(path):
    """전사 vtt → [(시작초, 글)] — 시각 검증용(계획 시각이 전사와 맞는지 세는 데 쓴다)."""
    if not os.path.exists(path):
        return []
    T = re.compile(r"^(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?) --> ")
    out, cur = [], None
    for ln in open(path, encoding="utf-8"):
        m = T.match(ln)
        if m:
            cur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
        elif cur is not None and ln.strip() and not ln.startswith("WEBVTT"):
            out.append((cur, re.sub(r"<[^>]+>", "", ln).strip()))
    return out


def _훅맞춤(hooks, 큐, scale, 창=8.0):
    """훅(대사 글+시각)에 scale 을 곱했을 때, 그 언저리(±창) 전사에 글이 실제로 있는 훅의 수.
    글은 공백·부호를 뗀 2글자 조각(bigram)의 절반 이상이 전사 창 안에 있으면 «맞음»."""
    뗀 = lambda s: re.sub(r"[^0-9A-Za-z가-힣]", "", s or "")
    n = 0
    for h in hooks:
        글 = 뗀(h.get("text"))
        if len(글) < 4:
            continue
        t = h.get("t0", 0) * scale
        창글 = 뗀("".join(x for c, x in 큐 if t - 창 <= c <= t + 창))
        조각 = [글[i:i + 2] for i in range(len(글) - 1)]
        if 조각 and sum(1 for g in 조각 if g in 창글) >= len(조각) * 0.5:
            n += 1
    return n


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
    o = subprocess.run(ff.명령(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", "-show_streams", "-select_streams", "v:0",
                        path]), capture_output=True, text=True)
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


def vtt_정밀(path):
    """글 길(영상 없음)용 원본 자막 — 0.1초 시각. 분:초(1초 단위)로는 영상 없이 경계를 못 잡는다."""
    L = _vtt_큐(path)
    return "\n".join(f"[{t:.1f}초] {x}" for t, x in L) if L else "(자막 없음)"


CALLER = "스케치코미디/plan"


def _agy(payload, limit_min, log=print):
    """plan 전용 agy 호출 → 답 글. **EvoLink 로 넘기지 않는다** — 글 길도 영상 판정의 대신이라 막히면 멈춘다
    (2026-09-26 사장님 결정 2번 · 유료 금지). 실패는 judge_run.판정멈춤(SystemExit 3)."""
    jr = gem.judge_run
    resp, 까닭 = jr.agy_먼저(payload, CALLER, limit_min=limit_min, log=log)
    if resp is None:
        jr.기록(CALLER, "agy_fail_stop", 0, "plan — EvoLink 로 안 넘김(멈춤) — " + 까닭)
        raise jr.판정멈춤(f"plan agy 실패 — EvoLink 로 넘기지 않고 멈춘다: {까닭}")
    return gem.agy_gemini.text_of(resp)


def 거절종류(글):
    """판정멈춤 글 → "필터"(구글 안전 필터) · "출력한도"(답이 잘림) · None(그 밖 — 그대로 멈춘다)."""
    if re.search(r"필터 차단|content safety|sensitive words|PROHIBITED_CONTENT|blocked by Gemini", 글, re.I):
        return "필터"
    if re.search(r"출력 토큰 한도|output token limit", 글, re.I):
        return "출력한도"
    return None


def _본문(mp4, 글, schema):
    parts = []
    if mp4:
        parts.append({"inline_data": {"mime_type": "video/mp4",
                                      "data": base64.b64encode(open(mp4, "rb").read()).decode()}})
    parts.append({"text": 글})
    return {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 32000, "responseMimeType": "application/json",
                                 "responseSchema": schema}}


def call(mp4, dur, fps, vtt, hot, focus=None, cands=(), 원제="", 파악=None, 덧="", 길="영상"):
    """plan 한 번 → (답 dict, 길 "영상"|"글", 겪은 일 [글]).

    ★구글 안전 필터 대안 길 (2026-09-29 점심이네4 — 여동생 속옷 택배 장면·«뒤질래» 등으로 영상 plan 이 세 번 거절돼 보류,
      에이전트가 손으로 projects json 을 짜 납품. 싱글벙글7 도 같은 일로 보류). ⑥/⑦ 화자 판정(화자색.py 2026-09-27 싱글233)의
      전례대로, 영상이 필터에 막히면 **글(원본 전사 0.1초 시각 + 파악 답)만으로** 다시 짠다. 거절문이 «모델 출력에 민감한 낱말»
      이라 글 길은 욕설을 ○ 로 가려 적게 하고(훅 글은 코드가 전사로 되채움), 자막 초안은 코드가 전사로 짠다.
    ★출력 한도 초과 (싱글166·159·245·184 — 옛 코드에서 한 번 더 물어 4편 모두 통과) — 되묻지 않고 멈추던 것을, 답을 줄이라는
      지시(자막 초안 빼기 · what 짧게)를 붙여 **한 번만** 다시 묻는다(같은 질문을 되풀이하지 않는다 — agy_gemini.AgyOutputLimit)."""
    jr = gem.judge_run
    겪음, 줄임 = [], False            # 길: 앞 회차가 필터로 글 길에 갔으면 수리 회차도 글 길로(같은 거절을 또 사지 않게)
    while True:
        글 = prompt(dur, fps, vtt_정밀(vtt) if 길 == "글" else vtt_text(vtt), hot, focus, cands, 원제, 파악,
                   글길=(길 == "글")) + (_줄임 if 줄임 else "") + 덧
        try:
            txt = _agy(_본문(mp4 if 길 == "영상" else None, 글, SCHEMA), limit_min=15)
            return json.loads(txt), 길, 겪음
        except jr.판정멈춤 as e:
            k = 거절종류(str(e))
            if k == "필터" and 길 == "영상":
                겪음.append("영상 요청이 구글 안전 필터에 막힘 → 글(전사·파악 답)만으로 다시")
                print("  주의  plan — 영상이 구글 안전 필터에 막힘 → 글(원본 전사 0.1초 · 파악 답)만으로 다시 짠다", flush=True)
                길 = "글"
                continue
            if k == "출력한도" and not 줄임:
                겪음.append("출력 한도 초과 → 줄인 답으로 한 번 더")
                print("  주의  plan — 답이 출력 한도를 넘어 잘림 → 자막 초안을 빼고 짧게 한 번 더", flush=True)
                줄임 = True
                continue
            raise


# ── agy 파악 답 (원본을 통째로 보고 들은 답) ──────────────────────
파악SCHEMA = {
    "type": "object",
    "properties": {
        "요약": {"type": "string"},
        "인물": {"type": "array", "items": {"type": "object", "properties": {
            "이름": {"type": "string"}, "관계": {"type": "string"}}, "required": ["이름", "관계"]}},
        "흐름": {"type": "array", "items": {"type": "object", "properties": {
            "t0": {"type": "number"}, "t1": {"type": "number"}, "무슨일": {"type": "string"},
            "대사": {"type": "array", "items": {"type": "string"}}}, "required": ["t0", "t1", "무슨일"]}},
        "셋업": {"type": "array", "items": {"type": "object", "properties": {
            "t": {"type": "number"}, "대사": {"type": "string"}, "뒤집는것": {"type": "string"}},
            "required": ["t", "대사"]}},
        "결말": {"type": "object", "properties": {
            "t": {"type": "number"}, "대사": {"type": "string"}, "설명": {"type": "string"}}, "required": ["t", "대사"]},
        "로고초": {"type": "number"},
        "광고": {"type": "array", "items": {"type": "object", "properties": {
            "t0": {"type": "number"}, "t1": {"type": "number"}}}},
        "훅후보": {"type": "array", "items": {"type": "object", "properties": {
            "t": {"type": "number"}, "대사": {"type": "string"}}}},
        "꼭남길": {"type": "array", "items": {"type": "object", "properties": {
            "t": {"type": "number"}, "대사": {"type": "string"}}, "required": ["t", "대사"]}},
    },
    "required": ["요약", "인물", "흐름", "셋업", "결말", "로고초", "꼭남길"],
}


def 파악질문(dur):
    return f"""이 영상은 한국 스케치 코미디 한 편({dur:.0f}초)이다. 쇼츠(80초 이하)로 줄이기 위한 «내용 파악»만 한다.
영상을 통째로 한 번 보고 소리를 한 번 듣고 곧바로 답하라. 사진(프레임)을 따로 뽑지 마라 — 정밀한 시각은 우리가 따로 잰다.
시각은 영상 첫머리부터의 초(대략 ±2초면 충분).

- 요약: 누가, 무엇 때문에, 어떻게 끝나는가(결말·반전 포함) 한 문장.
- 인물: 등장인물마다 불리는 이름(모르면 겉모습)과 서로의 관계(친구·남매·연인·선후임 등). ★관계는 대사(호칭·말투)를 근거로.
- 흐름: 큰 장면 5~10개 — t0·t1 · 무슨 일 · 핵심 대사 1~2개(들리는 그대로).
- 셋업: 결말(반전·결론)이 뒤집거나 닫는 **앞선** 대사 — 약속·내기·경고·질문·거짓말. 이 대사가 없으면 결말이 왜 웃긴지
  알 수 없는 것만 1~4개. 각 대사가 결말의 무엇을 받쳐 주는지(뒤집는것).
- 결말: 로고·끝 카드가 나오기 **전** 마지막 결말 대사와 그 시각, 무엇으로 끝나는지 한 문장.
- 로고초: 채널 로고·끝 카드가 처음 화면에 나오는 시각(없으면 -1). ★로고 위에 깔리는 쿠키 대사는 결말이 아니다.
- 광고: 영화·앱·제품 홍보 구간(없으면 빈 목록).
- 훅후보: 첫 3초에 쓸 센 대사 2개와 시각.
- 꼭남길: 80초로 줄일 때 꼭 남길 대사(뜻이 통하는 질문–대답 쌍)와 시각 — 셋업·결말 대사를 포함해 6~12줄.
"""


def 파악정리(j):
    """파악 JSON → plan관문 이 쓰는 모양 {"글", "로고", "꼭남길", "셋업", "결말"}."""
    def 초(t):
        try:
            return float(t)
        except (TypeError, ValueError):
            return None
    줄 = [f"요약: {j.get('요약', '')}"]
    줄 += ["인물: " + " · ".join(f"{x.get('이름', '')}({x.get('관계', '')})" for x in j.get("인물") or [])]
    for x in j.get("흐름") or []:
        줄.append(f"- {초(x.get('t0')) or 0:.0f}~{초(x.get('t1')) or 0:.0f}초 {x.get('무슨일', '')}"
                 + (" — " + " / ".join(f"«{d}»" for d in x.get("대사") or []) if x.get("대사") else ""))
    for x in j.get("셋업") or []:
        줄.append(f"셋업 {초(x.get('t')) or 0:.0f}초 «{x.get('대사', '')}» — {x.get('뒤집는것', '')}")
    ed = j.get("결말") or {}
    줄.append(f"결말 {초(ed.get('t')) or 0:.0f}초 «{ed.get('대사', '')}» — {ed.get('설명', '')}")
    로고 = 초(j.get("로고초"))
    줄.append(f"로고(아웃트로 카드) 처음: {'없음' if 로고 is None or 로고 < 0 else f'{로고:.0f}초'}")
    if j.get("광고"):
        줄.append("광고 구간: " + ", ".join(f"{초(x.get('t0')) or 0:.0f}~{초(x.get('t1')) or 0:.0f}초" for x in j["광고"]))
    줄 += [f"꼭 남길 {초(x.get('t')) or 0:.0f}초 «{x.get('대사', '')}»" for x in j.get("꼭남길") or []]
    return {"글": "\n".join(줄), "로고": 로고 if 로고 is not None and 로고 >= 0 else None,
            "꼭남길": [{"글": x.get("대사", ""), "시각": [초(x.get("t"))] if 초(x.get("t")) is not None else [], "묶음": i}
                     for i, x in enumerate(j.get("꼭남길") or [])],
            "셋업": [{"글": x.get("대사", ""), "시각": [초(x.get("t"))] if 초(x.get("t")) is not None else []}
                   for x in j.get("셋업") or []],
            "결말": {"글": ed.get("대사", ""), "시각": [초(ed.get("t"))] if 초(ed.get("t")) is not None else []} if ed.get("대사") else None}


def 파악얻기(slug, mp4, dur, work, 준것=None):
    """파악 답 — ① --파악 으로 준 파일(.md 배치 답·.json) ② work/<slug>.파악.json(캐시) ③ 없으면 agy 에 원본 영상을 통째로 준다.
    막히면(필터 등) None — plan 은 파악 없이 간다(파악은 plan 의 입력·관문의 근거일 뿐 필수는 아니다)."""
    from . import plan관문
    for p in [준것] if 준것 else []:
        if p and os.path.exists(p):
            if p.endswith(".json"):
                return 파악정리(json.load(open(p, encoding="utf-8"))), p
            return plan관문.파악읽기(p), p
    캐시 = os.path.join(work, f"{slug}.파악.json")
    if os.path.exists(캐시):
        return 파악정리(json.load(open(캐시, encoding="utf-8"))), 캐시
    jr = gem.judge_run
    t0 = time.time()
    try:
        j = json.loads(_agy(_본문(mp4, 파악질문(dur), 파악SCHEMA), limit_min=10))
    except jr.판정멈춤 as e:
        print(f"  주의  파악 답 못 받음({거절종류(str(e)) or '실패'}) — 파악 없이 plan 을 짠다: {str(e)[:120]}", flush=True)
        return None, ""
    json.dump(j, open(캐시, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"파악 답 {time.time() - t0:.0f}초 — {캐시}", flush=True)
    return 파악정리(j), 캐시


def main():
    if len(sys.argv) < 2:
        print("python -m s2pipe.plan <youtube_url> [--slug 이름]")
        return 1
    url = sys.argv[1]
    slug = sys.argv[sys.argv.index("--slug") + 1] if "--slug" in sys.argv else None
    focus = (float(sys.argv[sys.argv.index("--focus") + 1])
             if "--focus" in sys.argv else None)

    work = os.path.join(HERE, CFG["paths"]["work"])
    if os.path.exists(url) or (slug and os.path.exists(os.path.join(work, f"{slug}.mp4"))):
        # ★로컬 소재 (2026-09-01 Deep 흐름) — 편시작_deep.py 가 만든 work 파일을 쓴다.
        #   유튜브 자막 대신 Speechmatics 전사(.ko.vtt), 댓글 텍스트 없음(댓글은 PNG 카드).
        assert slug, "로컬 소재는 --slug 가 필수다"
        vid = slug
        mp4 = os.path.join(work, f"{vid}.mp4")
        vtt = os.path.join(work, f"{vid}.ko.vtt")
        assert os.path.exists(mp4) and os.path.exists(vtt), "편시작_deep.py 를 먼저 돌려라 (mp4·ko.vtt)"
    else:
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
    원제 = origin_of(info).get("title", "")
    판정영상 = gem.shrink_for_inline(mp4)
    # ★파악 답을 plan 의 입력으로 (2026-09-29 점심이네 64편 — plan 초안이 인물 관계·셋업·로고를 틀린 편이 많았고, 같은 원본을
    #   agy 가 통째로 본 파악 답은 대체로 맞았다). --파악 <파일>(배치가 미리 받은 .md·.json) · 없으면 work 캐시 · 없으면 agy 한 번.
    준파악 = sys.argv[sys.argv.index("--파악") + 1] if "--파악" in sys.argv else None
    파악, 파악출처 = 파악얻기(slug, 판정영상, dur, work, 준파악)
    if 파악:
        print(f"파악 답 — {파악출처} (꼭 남길 {len(파악.get('꼭남길') or [])}줄 · 셋업 {len(파악.get('셋업') or [])}줄"
              f" · 로고 {파악.get('로고')})", flush=True)

    # ★plan 직후 관문 (s2pipe/plan관문.py 머리 주석) — 반려면 수리 지침을 붙여 다시 부른다. 가장 반려가 적은 답을 남긴다.
    from . import plan관문, build
    큐 = plan관문.큐읽기(vtt)
    try:
        카드 = build.엔드카드시작(mp4, dur)
    except Exception as e:                               # noqa: BLE001
        카드 = None
        print(f"  (아웃트로 카드 검출 건너뜀: {e})", flush=True)
    if 카드 is not None:
        print(f"원본 아웃트로 카드 {카드:.2f}초~ (정지 카드 — 이 뒤 목소리는 결말이 아니다)", flush=True)
    pdir = os.path.join(HERE, CFG["paths"]["projects"])
    os.makedirs(pdir, exist_ok=True)
    dst = os.path.join(pdir, f"{slug}.json")
    수리회수 = int(CFG.get("edit", {}).get("plan_수리회수", 2))
    # --글길: 처음부터 영상 없이(글 길) — 같은 편이 필터에 거듭 막혀 영상 요청을 또 사지 않으려 할 때(사람이 고른다)
    덧, 길, 회차, 최선 = "", ("글" if "--글길" in sys.argv else "영상"), [], None
    for 회 in range(수리회수 + 1):
        plan, 길, 겪음 = call(판정영상, dur, fps, vtt, hot, focus, cands, 원제, 파악, 덧, 길)
        proj, total = 정리(plan, dur, fps, vtt, 큐, info, url, vid, slug, 길)
        if 회 == 0:
            # 박힌 자막 카드 — ⑦ 설명시각의 시계(2026-10-03 · plan관문.카드줄읽기 주석). 화면글자 캐시는 plan 부르기 안에서 이미 만들어진다
            카드줄 = plan관문.카드줄읽기(mp4)
            print(f"  박힌 자막 카드 {len(카드줄)}장" + ("" if 카드줄 else " — 없음(설명시각은 전사 시계로 잰다)"), flush=True)
        # src: ⑨ 원본검사(문장 자름·원본 순서·통암전·결말 꼬리 — 2026-10-05 수리D5 · plan관문 ⑨ 주석)
        bad, warn, 값 = plan관문.검사(proj, 큐, 파악, 카드, dst, 카드줄=카드줄, src=mp4)
        회차.append({"회": 회 + 1, "길": 길, "겪음": 겪음, "반려": [[d, g] for d, g in bad], "주의": warn, "값": 값})
        print(f"\nplan 관문 {회 + 1}회({길}) — 반려 {len(bad)} · 주의 {len(warn)}", flush=True)
        for d, g in bad:
            print(f"  반려  [{d}] {g}", flush=True)
        for w in warn:
            print(f"  주의  {w}", flush=True)
        if 최선 is None or len(bad) < len(최선[1]):
            최선 = (proj, bad, total)
        if not bad:
            break
        if 회 < 수리회수:
            print(f"  → 수리 지침을 붙여 plan 을 다시 부른다({회 + 2}/{수리회수 + 1})", flush=True)
            덧 = "\n\n" + plan관문.수리지침(bad, warn) + 앞선답(proj)
    proj, bad, total = 최선
    proj["_plan관문"] = {"통과": not bad, "남은반려": [[d, g] for d, g in bad], "회차": 회차,
                       "파악": 파악출처, "엔드카드": 카드}
    json.dump(proj, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    keep = proj["segments"]
    print(f"\n{proj['logline']}")
    ed = proj.get("ending") or {}
    print(f"결말({ed.get('type', '?')}): {ed.get('desc', '— 없음')}")
    lo, hi = CFG["edit"]["target_sec"]
    print(f"구간 {len(keep)}개 / 전체 {len(proj['segments_all'])}개 · 예상 {total:.0f}초 "
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
    for t in proj.get("title_candidates", []):
        print(f"  {t}")
    print(f"해시태그: {proj.get('hashtag', '')}")
    if bad:
        print(f"\n★plan 관문 미통과 — 반려 {len(bad)}건이 남았다(다시 부르기 {len(회차)}회). 고칠 것: "
              + plan관문.요약(bad, []) + " — projects json «_plan관문» · 검수도구/plan점검.py 로 보고 사람이 고친다")
    else:
        print(f"\nplan 관문 통과 ({len(회차)}회째)")
    print(f"\n저장: {dst}")
    return 0


def 앞선답(proj):
    """다시 부를 때 붙이는 앞선 답(keep 조각·훅) — 반려 사유가 없는 조각은 그대로 두게."""
    줄 = [f"- P{s.get('phase')} 원본 {s['t0']:.1f}~{s['t1']:.1f}초 punch {s.get('punch')}"
         + (f" 나레 «{s['narration']}»" if (s.get("narration") or "").strip() else "") + f" — {s.get('what', '')[:40]}"
         for s in proj["segments"]]
    훅 = [f"- {h.get('t0')}초 «{h.get('text', '')}»" for h in proj.get("hooks") or []]
    return "\n## 앞선 답 (keep 조각 — 재생 순서)\n" + "\n".join(줄) + "\n### 앞선 훅\n" + "\n".join(훅) + "\n"


def 초안자막(keep, 큐, maxc):
    """원본 전사 → 숏폼 시각 초안 자막(대사) + 나레 줄. 모델이 subs 를 비운 답(글 길·줄인 답)에서만 쓴다.
    초안은 굽기 뒤 ④ sync 가 완성본 전사로 통째로 다시 짠다 — 여기서는 make ① 이 읽을 초안(14자·구두점 규칙)만 맞춘다."""
    out, at = [], 0.0
    for s in keep:
        if (s.get("narration") or "").strip():
            out.append({"t": round(at, 2), "text": s["narration"], "kind": "narr"})
        for c0, c1, x in 큐:
            if not (s["t0"] <= c0 < s["t1"]):
                continue
            글 = cfg.strip_punct(x)
            if not 글:
                continue
            t = at + (c0 - s["t0"])
            조각 = [글]
            while any(len(g) > maxc and " " in g for g in 조각):
                g = next(g for g in 조각 if len(g) > maxc and " " in g)
                k = min((i for i, ch in enumerate(g) if ch == " "), key=lambda i: abs(i - len(g) / 2))
                i = 조각.index(g)
                조각[i:i + 1] = [g[:k], g[k + 1:]]
            span = max(0.3, min(c1, s["t1"]) - c0)
            합 = sum(len(g) for g in 조각) or 1
            누 = 0
            for g in 조각:
                out.append({"t": round(t + span * 누 / 합, 2), "text": g, "kind": "line"})
                누 += len(g)
        at += s["t1"] - s["t0"]
    return out


def 정리(plan, dur, fps, vtt, 큐3, info, url, vid, slug, 길):
    """모델 답 → projects 모양. (proj, keep 길이 합)."""
    # ★모델이 원본 길이를 넘는 타임코드를 낸다. 그런데 **일정한 비율로 늘어난다** —
    #   274→412(1.50배) · 416→656(1.58배). 그냥 버리면 뒤쪽 좋은 대목이 통째로
    #   날아가므로 먼저 비율을 되돌리고, 그래도 밖이면 그때 버린다.
    over = max((s["t1"] for s in plan["segments"]), default=0)
    ratio = dur / over if over > dur * 1.06 else 1.0
    if ratio < 1.0:
        # ★«늘어났다» 판정은 전사(vtt)로 확인한 뒤에만 한다 (2026-09-21 띱 7차 — Deep73·79·80·89):
        #   이상값 조각 하나(원본 길이 밖 t1)가 «전체가 1.35배 늘어났다» 로 오판돼 **맞던 시각까지**
        #   0.739 를 곱해 버렸다(족발 등장 477s → 352s). 훅은 대사 글과 시각을 같이 갖고 있으니,
        #   «그대로» 와 «되돌린» 두 가설 중 어느 쪽이 전사와 더 맞는지 세어 고른다.
        #   되돌린 쪽이 더 맞을 때만 되돌린다 — 아니면 밖으로 나간 조각만 아래에서 버린다.
        큐 = _vtt_큐(vtt)
        그대로, 되돌림 = _훅맞춤(plan.get("hooks", []), 큐, 1.0), _훅맞춤(plan.get("hooks", []), 큐, ratio)
        if 큐 and 되돌림 <= 그대로:
            print(f"★원본 길이 밖 조각이 있지만 시각은 늘어나지 않았다 — 훅·전사 대조: 그대로 {그대로}개 · "
                  f"되돌리면 {되돌림}개 맞음. 되돌리지 않고 밖 조각만 버린다", flush=True)
            ratio = 1.0
    if ratio < 1.0:
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

    # ★절대 규칙(2026-09-01 사장님) — 나레이션·자막 구두점 걸러내기 (정답지 G-구두점)
    for s in plan["segments"]:
        if s.get("narration"):
            s["narration"] = cfg.strip_punct(s["narration"])
    for x in plan.get("subs", []):
        x["text"] = cfg.strip_punct(x.get("text"))

    # ★글 길·줄인 답은 욕설을 ○ 로 가리고 subs 를 비운다(call 머리 주석) — 훅 글은 전사에서 되채우고 초안 자막은 전사로 짠다
    from . import plan관문
    for h in plan.get("hooks", []):
        if "○" in (h.get("text") or ""):
            # t0 ±6초 안에서 가린 글과 가장 닮은 전사 줄 하나로 (여러 줄을 이으면 앞 줄까지 딸려 온다 — 점심이네4 글 길 시험)
            후보 = [(plan관문.닮음(h["text"].replace("○", ""), x), x) for c0, c1, x in 큐3 if abs(c0 - h.get("t0", 0)) <= 6.0]
            if 후보 and max(후보)[0] >= 0.3:
                h["text"] = max(후보)[1]
    subs = plan.get("subs") or []
    if not subs:
        subs = 초안자막(keep, 큐3, CFG["layout"]["subtitle"]["max_chars"])
        print(f"  초안 자막 {len(subs)}줄 — 원본 전사로 짰다(모델 답에 subs 없음 · ④ 가 완성본 전사로 다시 짠다)", flush=True)

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
        "subs": subs,
        "comments": pick_comments(info, total, plan.get("comment_picks")),
        "comment_picks": plan.get("comment_picks", []),
        "credit": origin_of(info),
        # 절대 지침(정답지 G-결말) — 이 편이 무엇으로 끝나는지. 스키마 필수라 모델이 반드시 낸다
        "ending": plan.get("ending", {}),
        "_est_sec": round(total, 1),
    }
    if 길 == "글":
        proj["_plan길"] = "글(영상이 구글 안전 필터에 막혀 원본 전사·파악 답만으로 짬)"
    return proj, total

if __name__ == "__main__":
    sys.exit(main())
