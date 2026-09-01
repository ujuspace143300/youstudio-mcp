# 자막만 다시 뽑는다. **굽고 나서 반드시 한 번 돌린다.**
#
#   python -m s2pipe.subs projects/<slug>.json
#
# ★★원본 전체가 아니라 **이미 잘라 붙인 cut.mp4** 를 모델에 넣는다. 그러면
#   시각이 숏폼 기준으로 바로 나와 변환할 게 없고, 실제로 완성될 화면만 보므로
#   놓치는 대사가 적다. sketch 실측으로 **18줄 → 74줄**이 됐다.
#
# ★계획 단계(plan)의 자막은 원본 전체를 보고 낸 것이라 **성기고 싱크가 어긋난다.**
#   조각을 잘라 붙이면 시각이 통째로 달라지기 때문이다 — 그래서 이 단계가 있다.
#
# ★나레이션 자막은 여기서 내지 않는다. 그쪽 정본은 `segments[].narration` 이다.
import base64, json, os, sys, time, urllib.request, urllib.error

from . import gem                                        # EvoLink 우선 호출

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from . import cfg
from .cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)
MODELS = CFG.get("gemini", {}).get("models", ["gemini-3.5-flash"])

SCHEMA = {
    "type": "object",
    "properties": {
        "subs": {"type": "array", "items": {
            "type": "object",
            "properties": {"t": {"type": "number"}, "text": {"type": "string"}},
            "required": ["t", "text"]}},
    },
    "required": ["subs"],
}


def prompt(maxc):
    return f"""이 영상의 **모든 대사**를 자막으로 옮겨라. 이 채널은 자막을 읽는 재미로 보는 채널이다.

## 규칙

- `t` 는 그 말이 시작되는 시각(초). 영상 맨 앞이 0 이다.
- 한 줄 **{maxc}자 이내**. 말이 길면 끊어서 여러 줄로 낸다.
- ★**대사가 있는 동안 자막이 비면 안 된다.** 말을 하고 있는데 자막이 없으면 빠뜨린 것이다.
- ★**3초 이상 비는 구간이 없게 하라.**
- ★**대사가 없는 구간에는 상황 자막을 넣어라.** 먹기만 하거나 정적이 흐르는 대목도
  비워 두지 않는다 — 괄호로 상황이나 속마음을 적는다.
  예: `(아구아구)` `(조심스러운 손길)` `(ㅋㅋㅋ)` `(정적)` `(10만원?)`
  레퍼런스가 실제로 그렇게 채운다.
- 구어체 그대로 옮긴다. 다만 너무 빠른 발음이나 뭉갠 말은 읽기 쉽게 다듬는다.
- 속마음·상황 설명은 괄호로: `(ㅋㅋㅋ)` `(10만원?)`
- ★★**구두점 금지(절대 규칙)** — 마침표·쉼표·말줄임(…·...)을 쓰지 마라.
  물음표·느낌표만 허용. 쉼표 자리는 띄어쓰기로.
- 화자 이름은 넣지 않는다. 화면 전환으로 누가 말하는지 알 수 있다.

말이 겹치거나 빠르게 오가면 각각 짧게 끊어서 촘촘히 낸다.
"""


def main():
    if len(sys.argv) < 2:
        print("python -m s2pipe.subs projects/<slug>.json")
        return 1
    pj = sys.argv[1]
    proj = json.load(open(pj, encoding="utf-8"))
    slug = proj["slug"]
    cut = os.path.join(HERE, CFG["paths"]["work"], slug, "cut.mp4")
    if not os.path.exists(cut):
        print(f"잘라 붙인 영상이 없다: {cut}\n  먼저 python -m s2pipe.build 를 한 번 돌려라")
        return 1

    send = gem.shrink_for_inline(cut)   # 인라인 한도 넘으면 판정용 프록시
    b64 = base64.b64encode(open(send, "rb").read()).decode()
    maxc = CFG["layout"]["subtitle"]["max_chars"]
    payload = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "video/mp4", "data": b64}},
        {"text": prompt(maxc)},
    ]}], "generationConfig": {"maxOutputTokens": 16000,
                              "responseMimeType": "application/json",
                              "responseSchema": SCHEMA}}
    print(f"cut.mp4 {os.path.getsize(cut)/1024/1024:.1f}MB — 전사 요청", flush=True)

    # ★EvoLink → 순정 순으로 간다(spipe/gem.py). 큰 영상은 gem 이 알아서 순정으로 보낸다.
    txt, _route, _model = gem.ask(payload, MODELS, timeout=900)
    if txt is None:
        print("모든 경로가 막혔다")
        return 1
    subs = json.loads(txt)["subs"]

    subs = sorted(subs, key=lambda x: x["t"])
    # ★모델 타임코드가 일정 비율로 늘어난다(plan 과 같은 증상 — Deep01 실측 1.52배).
    #   완성 길이를 넘으면 비율로 되돌린다.
    cut_dur = sum(s["t1"] - s["t0"] for s in proj.get("segments", []) if s.get("keep"))
    mx = max((x["t"] for x in subs), default=0)
    if cut_dur and mx > cut_dur * 1.06:
        ratio = cut_dur / mx
        print(f"★자막 타임코드가 {1/ratio:.2f}배 늘어났다 — {ratio:.3f} 로 되돌린다")
        for x in subs:
            x["t"] = round(x["t"] * ratio, 2)
    old = len(proj.get("subs", []))
    proj.pop("subs_before_sync", None)   # 재추출하면 이전 싱크 기준은 무효다
    for x in subs:
        x["kind"] = "line"   # ★나레이션은 segments 가 정본
        x["text"] = cfg.strip_punct(x.get("text"))  # ★절대 규칙 — 구두점 금지(정답지 G-구두점)
    proj["subs"] = subs
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 빈 구간 검사 — 자막이 성글면 여기서 드러난다
    gaps = []
    for i in range(1, len(subs)):
        g = subs[i]["t"] - subs[i-1]["t"]
        if g >= 3.0:
            gaps.append((subs[i-1]["t"], subs[i]["t"], g))
    total = sum(s["t1"] - s["t0"] for s in proj["segments"])
    print(f"\n자막 {old} → {len(subs)}개 ({total/max(len(subs),1):.1f}초당 1줄)")
    if gaps:
        print(f"★3초 이상 비는 구간 {len(gaps)}곳:")
        for a, b, g in gaps[:8]:
            print(f"   {a:5.1f}~{b:5.1f}  ({g:.1f}초)")
    else:
        print("빈 구간 없음")
    print(f"\n저장: {pj}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
