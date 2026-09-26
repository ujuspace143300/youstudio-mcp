# 편집 이음매에서 말이 잘렸는가 — 완성본 Speechmatics 낱말 시각(asr_words)으로 잰다.
#
#   python -m s2pipe.이음매관문 projects/<편>.json      (재기만 한다 · 반려 있으면 종료코드 1)
#
# ★2026-09-26 사장님 결정(B): 원본 전사는 agy(제미나이 flash 3.8)로 한다. agy 시각은 말 끝을
#   0.5~1초 늦게 잡아(Deep90·91·93 실측 — 승인·납품된 편 4개 중 3~4개를 make 가 «발화 중간 절단»으로
#   가짜 반려), 원본 전사로는 이음매 절단을 판정할 수 없다. 그래서 판정을 **정밀 시각이 있는 곳**으로
#   옮긴다 — 완성본 재전사(한편 ③, Speechmatics)는 매 편 어차피 돌고, 잘린 말이 실제로 들어간
#   «완성본» 소리를 낱말 단위로 본다. 원본 추정(make)보다 한 단계 뒤지만 더 정확하다.
#   make 절단 게이트(Deep18·20·27·60 사건)는 agy 전사일 때 «주의» 로 내려가고, 반려는 여기서 한다.
#
# 이음매 = 살린 조각(keep)이 바뀌는 자리(완성본 시각). 원본에서 맞닿은 조각(t1 = 다음 t0)은 이음매가 아니다.
#   반려: ① 뜻 있는 낱말(감탄·숨소리 제외)이 이음매를 가로지른다  ② 영상 끝(결말)에 뜻 있는 마지막 낱말 끝이 붙었다
#   주의: 이음매 앞 말끝이 이음매에 붙었다(<붙음 초 — 꼬리 잘림 의심, 사람이 듣고 판단) · 쉼이 빠듯하다(<빠듯 초)
#         · 이음매 바로 뒤에서 말이 시작한다(말 머리 잘림 의심)
#   ★«붙음» 을 반려로 두지 않는 까닭 — 2026-09-26 납품 20편(Deep73~93) 실측: 완성본 전사는 소리가 뚝 끊긴
#     이음매에서 앞 낱말 끝을 이음매까지 늘려 잡았다(Deep88 「좋아」 −0.01초 · Deep91 「으」 0.07초 — 원본
#     Speechmatics 로는 둘 다 말끝 뒤 0.45·0.66초에서 잘랐다). 반려로 두면 20편 중 3편이 가짜로 멈춘다.
#   예외: proj["이음매허용"] = [완성본 초, …] — 사람이 듣고 괜찮다고 한 자리(±0.3초)
import json
import os
import re
import sys

붙음 = 0.08      # 낱말 끝이 이음매 앞 이만큼 안이면 잘린 꼬리
빠듯 = 0.25      # make 옛 게이트의 «꼬리 빠듯» 여유와 같게
머리 = 0.05      # 이음매 뒤 이만큼 안에 말이 시작하면 머리 잘림 의심
추임새 = re.compile(r"[하호흐히헤아어오우음야에크으읏앗엇]+")


def 뜻말(w):
    """감탄·숨소리가 아닌 낱말인가 — 「크아」「으」 같은 소리는 이음매에 걸쳐도 반려하지 않는다."""
    글 = re.sub(r"[^가-힣]", "", w)
    return len(글) >= 2 and not 추임새.fullmatch(글)


def 이음매(proj):
    """[(완성본 초, 앞 조각 번호, 원본 t1)] — 살린 조각 사이 실제 자른 자리."""
    segs = [s for s in proj.get("segments", []) if s.get("keep", True)]
    out, at = [], 0.0
    for i, s in enumerate(segs):
        at += s["t1"] - s["t0"]
        if i + 1 < len(segs) and abs(segs[i + 1]["t0"] - s["t1"]) >= 0.05:
            out.append((round(at, 3), i, s["t1"]))
    return out, round(at, 3)


def 검사(proj):
    words = [w for w in (proj.get("asr_words") or []) if w.get("type") == "word"]
    bad, warn = [], []
    if not words:
        return bad, ["asr_words 가 없어 이음매를 못 쟀다"]
    허용 = proj.get("이음매허용") or []
    joints, total = 이음매(proj)

    def 허용됨(J):
        return any(abs(J - h) <= 0.3 for h in 허용)

    for J, i, 원t1 in joints:
        tag = f"이음매 {J:.2f}초(조각 {i} 끝 · 원본 {원t1:.1f})"
        걸침 = [w for w in words if w["t"] < J - 0.03 and w["e"] > J + 0.03]
        앞 = [w for w in words if w["e"] <= J + 0.03]
        뒤 = [w for w in words if w["t"] >= J - 0.03]
        if 걸침:
            (warn if 허용됨(J) or not 뜻말(걸침[0]["w"]) else bad).append(f"{tag} — 낱말 「{걸침[0]['w']}」 {걸침[0]['t']:.2f}~{걸침[0]['e']:.2f} 가 이음매를 가로지른다")
            continue
        if 앞:
            p = 앞[-1]
            쉼 = J - p["e"]
            if 쉼 < 붙음 and not 허용됨(J):
                warn.append(
                    f"{tag} — 앞 말 「{p['w']}」 끝 {p['e']:.2f} 가 이음매에 붙었다(쉼 {쉼:.2f}초) — 꼬리 잘림."
                    f" 원본 t1 을 늘리거나(말끝+0.3) 당겨라. 듣고 괜찮으면 이음매허용: [{J:.2f}]")
            elif 쉼 < 빠듯:
                warn.append(f"{tag} — 앞 말 「{p['w']}」 끝과 쉼 {쉼:.2f}초 — 빠듯")
        if 뒤 and 뒤[0]["t"] - J < 머리:
            warn.append(f"{tag} — 뒤 말 「{뒤[0]['w']}」 이 이음매 직후 {뒤[0]['t'] - J:.2f}초에 시작 — 말 머리 잘림 의심")
    # 결말 — 영상 끝에 마지막 말끝이 붙었는가
    last = words[-1]
    쉼 = total - last["e"]
    if 쉼 < 붙음 and last["t"] < total and not 허용됨(total):
        (bad if 뜻말(last["w"]) else warn).append(
            f"결말 {total:.2f}초 — 마지막 말 「{last['w']}」 끝 {last['e']:.2f} 가 영상 끝에 붙었다 — 결말 꼬리 잘림."
            f" 마지막 조각 t1 을 늘려라. 듣고 괜찮으면 이음매허용: [{total:.2f}]")
    elif 쉼 < 빠듯:
        warn.append(f"결말 — 마지막 말 「{last['w']}」 끝과 영상 끝 쉼 {쉼:.2f}초 — 빠듯")
    return bad, warn


def main():
    pj = sys.argv[1]
    proj = json.load(open(pj, encoding="utf-8"))
    bad, warn = 검사(proj)
    joints, total = 이음매(proj)
    for w in warn:
        print(f"  주의  {w}")
    for b in bad:
        print(f"  반려  ★{b}")
    print(f"  [{'OK' if not bad else 'X'}] 이음매 관문 — 이음매 {len(joints)}곳 · 영상 {total:.1f}초 · 반려 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
