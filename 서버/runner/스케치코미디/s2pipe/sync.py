# -*- coding: utf-8 -*-
"""자막의 **시각만** 실제 발화에 맞춘다. 문구는 건드리지 않는다.
요금이 나가지 않는다 — 이미 받아 둔 ASR 결과를 쓴다.

    python -m s2pipe.asr  projects/<편>.json     먼저 (★ASR 요금)
    python -m s2pipe.sync projects/<편>.json     그다음 (공짜)

■ 왜 필요한가
    모델은 영상을 **보고 시각을 추정한다.** 실측하니 줄마다 -1.1 ~ +1.6초로
    제각각 어긋났다(중앙은 +0.12초라 「전체가 밀린」 것도 아니다). 그래서 보정이
    아니라 **줄 단위로 맞춰야** 한다.

■ 어떻게
    ASR 단어를 이어 붙인 글자열과 자막을 이어 붙인 글자열을 맞대어(difflib),
    각 자막의 첫 글자가 ASR 의 어느 글자에 닿는지 찾고 그 글자가 속한 단어의
    시각을 쓴다. 강제정렬을 글자 단위로 흉내 낸 것이다.

■ ★문구는 ASR 것을 쓰지 않는다
    오인식이 많다 — 실측에서 「잭팟」이 「책팟」, 「지명아」가 「안녕아」로 나왔다.
    읽는 재미가 생명인 채널이라 문구는 모델이 다듬은 것을 그대로 둔다.

■ ★괄호 자막은 ASR 에 없다
    `(샤프 탁)` 같은 상황 자막은 소리로 안 잡히므로 맞출 수가 없다 —
    **앞뒤로 맞춰진 줄 사이에 고르게 끼워 넣는다.**
"""
import difflib
import json
import os
import re
import sys

# ★한 번 맞춘 뒤 다시 돌리면 이미 옮긴 값에 또 맞추게 된다. `subs_before_sync` 가
#   있으면 **거기서부터** 다시 맞춘다 — 그래야 몇 번을 돌려도 같은 결과가 나온다.

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CLEAN = re.compile(r"[\s.,!?~…()（）\[\]\"'·]")


def main():
    if len(sys.argv) < 2:
        print("python -m s2pipe.sync projects/<편>.json")
        return 1
    pj = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    proj = json.load(open(pj, encoding="utf-8"))

    words = proj.get("asr_words") or []
    if not words:
        print("ASR 결과가 없다 — 먼저 `python -m s2pipe.asr` 를 돌려라 (★요금)")
        return 1

    src = proj.get("subs_before_sync") or proj.get("subs", [])
    subs = sorted([dict(s) for s in src if s.get("kind") != "narr"],
                  key=lambda x: x["t"])
    if not subs:
        print("맞출 자막이 없다")
        return 1

    # ASR — 글자마다 시각을 달아 둔다.
    # ★단어 글자는 `w` 키다(`text` 가 아니다). 한 번 틀려서 **0자**가 나왔고,
    #   그대로 진행돼 자막이 통째로 0.8초 간격으로 뭉개졌다 — 아래 안전장치 참고.
    achars, atimes = [], []
    for w in words:
        for ch in CLEAN.sub("", w.get("w") or w.get("text") or ""):
            achars.append(ch)
            atimes.append(w["t"])
    asr_s = "".join(achars)
    if len(asr_s) < 10:
        print(f"★ASR 글자가 {len(asr_s)}자뿐이다 — 단어를 못 읽었다."
              f"\n  키를 확인하라(첫 단어: {json.dumps(words[0], ensure_ascii=False)})")
        return 1

    # 자막 — 각 줄의 첫 글자가 몇 번째인지
    sub_s, heads = "", []
    for s in subs:
        heads.append(len(sub_s))
        sub_s += CLEAN.sub("", s.get("text", ""))

    sm = difflib.SequenceMatcher(None, sub_s, asr_s, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    matched = sum(b.size for b in blocks)
    print(f"ASR {len(words)}단어({len(asr_s)}자) · 자막 {len(subs)}줄({len(sub_s)}자)"
          f" · 맞물린 덩어리 {len(blocks)}개({matched}자, {matched/max(len(sub_s),1)*100:.0f}%)")
    # ★★**안 맞으면 손대지 않는다.** 한 번 매칭 0개인 채로 진행해 자막을 통째로
    #   뭉개 먹었다. 고칠 근거가 없으면 그대로 두는 편이 언제나 낫다.
    if matched < len(sub_s) * 0.25:
        print("★맞물린 글자가 너무 적다 — 자막을 건드리지 않고 멈춘다."
              "\n  ASR 이 다른 영상 것이거나 말이 거의 없는 편일 수 있다.")
        return 1

    def at(pos):
        """자막 글자 위치 → ASR 시각. 못 찾으면 None."""
        for a, b, size in blocks:
            if a <= pos < a + size:
                return atimes[b + (pos - a)]
        nxt = [(a, b) for a, b, _ in blocks if a > pos]
        return atimes[nxt[0][1]] if nxt else None

    # ★★**너무 멀리 옮기는 것은 맞춘 게 아니라 잘못 붙은 것이다.** 대사가 적은 편은
    #   ASR 글자가 짧아 엉뚱한 곳에 매칭된다 — 실측에서 8.85초를 옮기려 한 적이
    #   있다. 그런 줄은 **원래 시각을 지킨다**(모델 추정이 8초 틀릴 리는 없다).
    lim = float(os.environ.get("SYNC_MAX_SHIFT", "2.5"))

    def anchor_size(pos):
        """줄 머리글자가 들어 있는 맞물린 덩어리의 길이 — 정렬 근거의 세기."""
        for a, _b, size in blocks:
            if a <= pos < a + size:
                return size
        return 0

    # ★2026-09-03 Deep02 사건 — 모델 자막표가 통째로(최대 ±9초) 틀린 편에서는
    #   2.5초 제한이 **고쳐야 할 줄 21/24를 되돌려** 싱크가 다 어긋난 채 나갔다.
    #   8글자 이상 연속으로 맞물린 정렬은 우연히 붙을 수 없다 — 그런 줄은 멀리도 옮긴다.
    #   제한은 근거가 약한 줄(머리글자가 덩어리 밖·짧은 덩어리)에만 적용한다.
    강근거 = int(os.environ.get("SYNC_STRONG_ANCHOR", "8"))
    fixed, moved, wild = [], [], 0
    for i, s in enumerate(subs):
        t = at(heads[i])
        if t is not None and abs(t - s["t"]) > lim and anchor_size(heads[i]) < 강근거:
            wild += 1
            t = None
        fixed.append(t)
        if t is not None:
            moved.append(t - s["t"])
    if wild:
        print(f"  ★{lim:.1f}초 넘게 튀었는데 근거도 약해({강근거}자 미만) 되돌린 줄 "
              f"{wild}/{len(subs)} — 그 줄은 원래 시각을 지킨다")

    # 못 맞춘 줄(괄호 자막·되돌린 줄) — ★2026-09-03 개정: 원래 시각을 절대값으로 믿지
    #   않는다. 표가 통째로 틀린 편에서 그대로 두면 강근거 줄과 순서가 꼬여 0.25초
    #   간격으로 뭉개졌다(실측). **이웃 강근거 줄 사이에 원래 간격 비례로 끼워 넣는다.**
    #   (예전에 끼워 넣기가 실패한 것은 강근거 줄까지 되돌리던 시절 얘기다 — 지금은
    #    닻이 믿을 만하다. 표가 멀쩡한 편에서는 이동이 거의 0이라 무해하다.)
    strong = [i for i, t in enumerate(fixed) if t is not None]
    for i in range(len(fixed)):
        if fixed[i] is not None:
            continue
        prev = max((j for j in strong if j < i), default=None)
        nxt = min((j for j in strong if j > i), default=None)
        if prev is not None and nxt is not None:
            o0, o1 = subs[prev]["t"], subs[nxt]["t"]
            r = (subs[i]["t"] - o0) / (o1 - o0) if o1 > o0 else 0.5
            fixed[i] = fixed[prev] + r * (fixed[nxt] - fixed[prev])
        elif prev is not None:
            fixed[i] = subs[i]["t"] + (fixed[prev] - subs[prev]["t"])
        elif nxt is not None:
            fixed[i] = subs[i]["t"] + (fixed[nxt] - subs[nxt]["t"])
        else:
            fixed[i] = subs[i]["t"]

    # 순서가 뒤집히지 않게 — 앞줄보다 뒤로만 간다
    for i in range(1, len(fixed)):
        if fixed[i] <= fixed[i - 1]:
            fixed[i] = fixed[i - 1] + 0.25

    big = 0
    for i, s in enumerate(subs):
        d = fixed[i] - s["t"]
        if abs(d) > 0.3:
            big += 1
            print(f"  {s['t']:6.2f} → {fixed[i]:6.2f}  {d:+.2f}  {s['text'][:22]}")
        s["t"] = round(fixed[i], 2)

    if moved:
        moved.sort()
        n = len(moved)
        print(f"\n  맞춰진 줄 {n}/{len(subs)} · 옮긴 폭 중앙 {moved[n//2]:+.2f}초"
              f" · 최대 {max(abs(moved[0]), abs(moved[-1])):.2f}초")
    print(f"  0.3초 넘게 옮긴 줄 {big}/{len(subs)}")

    # ★손대기 전 자막을 남겨 둔다 — 잘못 맞추면 되돌릴 데가 있고, 다시 돌릴 때
    #   **이미 옮긴 값이 아니라 원본에서부터** 맞추게 된다.
    proj.setdefault("subs_before_sync", [dict(x) for x in src])
    other = [s for s in src if s.get("kind") == "narr"]
    proj["subs"] = sorted(subs + other, key=lambda x: x["t"])
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n저장: {pj}\n★대본이 바뀌었으니 다시 검사해야 제작할 수 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
