# -*- coding: utf-8 -*-
"""밀도(정답지 G-밀도) 계산 한 곳 — make.check 가 부르고, 검수도구·재기 스크립트도 이 함수를 그대로 쓴다.

밀도 = 이야기 본체의 완성 길이 ÷ 그 본체가 원본에서 펼친 범위.
  ★왜 재나(2026-08-19 sketch2 실측 · 사장님 판정): 같은 소재·같은 41초에서 밀도 46% 편이 18% 편을 이겼다 —
    원본을 듬성듬성 긁어 붙이면 대목 사이 맥락이 끊겨 이야기가 안 이어진다. 기준값(규격 edit.density 35%)은 그대로다.

«본체» 에서 빼는 것 — 전부 «시청자가 그 사이 이야기를 놓치지 않는» 자리만이다:
  ① 결말 점프(2026-09-01 A안 · 09-09 끝 블록) — 끝의 P5 블록(≤ edit.결말점프_최대_s). 예전 그대로.
  ② 먼 훅(edit.훅_밀도제외 · 2026-09-29) — 첫 P1 조각은 «선공개» 라 원본 어디서 떼 와도 맥락을 끊지 않는다.
     본체에서 큰 간격(>15초) 넘게 떨어진 훅만 범위·길이에서 뺀다. 본체 안·곁의 훅은 그 대목의 일부라 예전처럼 센다
     (곁 훅까지 빼 보니 클러스터 머리를 훅으로 쓴 Deep 편 19개가 통과→반려로 뒤집혔다 — 740개 재기).
     구멍: 예전엔 훅 자리까지 범위에 넣어, 결말 쪽 센 대사를 훅으로 쓰면 ①로 뺀 끝 블록까지 범위가 도로 늘었다(점심이네6 29.8%).
  ③ 광고(edit.광고_밀도제외 · 2026-09-29) — proj["광고구간"] 에 적은 원본 속 광고(PPL)는 이야기가 아니다.
     본체 범위에서 그 길이를 뺀다. 조각이 광고와 겹치면 반려(«다른 회사 광고는 넣지 않는다» 규칙과 같은 자리).
     구멍: 가운데 광고 50초가 범위에 남아 앞 셋업을 못 넣었다(점심이네38 — 아정당 143~193).
  ④ 도입 점프(edit.도입점프_최대_s · 2026-09-29, 0 이면 꺼짐) — 결말 점프의 앞쪽 짝. 훅 바로 뒤에 먼저 나오는
     P2 셋업 블록이 본체와 큰 간격(>15초)으로 떨어져 있고, 그 블록이 한도 이하 · 원본 앞 1/3 안에서 시작 ·
     블록 자체 밀도도 기준 이상이며, proj["도입점프"] = {"근거": "...", "짝": [본체·결말 조각 안 원본 시각, …]} 로
     «이 셋업이 뒤에서 갚힌다» 를 적었을 때만 뺀다. 나머지 본체는 예전 기준(35%)을 그대로 넘어야 한다 —
     그래서 새로 생기는 자유는 «한도 이하 앞 블록 하나» 뿐이다(합성 흩뿌림 안 910개: 선언 없이 통과 0 ·
     거짓 선언으로 통과한 65개도 전부 앞 블록을 빼면 예전 관문을 통과하는 안).
     구멍: 결말 쪽 반전·웃음의 셋업(내기·맹세·첫 질문)이 원본 앞에 있으면 범위가 두 배로 늘어 35% 를 못 넘겼다
     (점심이네10 내기 29% · 13 도입 31% · 28 20대 맹세 30% · 47 25% · 42 20% — 셋업을 빼고 나레로 때웠다).

세 스위치 모두 기본은 꺼짐 = 예전 계산과 같다(재기: projects/ 조각 파일 740개 밀도 값 전부 일치).
켜는 것은 사장님 결정 — 규격 edit.훅_밀도제외·광고_밀도제외·도입점프_최대_s.
"""

큰간격_s = 15.0          # 결말 점프가 쓰는 «끝 장면으로 점프한 자리» 와 같은 값
도입_앞비율 = 1 / 3      # 도입 점프 앞 블록은 원본 앞 1/3 안에서 시작한다


def _길이(s):
    return s["t1"] - s["t0"]


def _합집합(구간들):
    out = []
    for a, b in sorted(구간들):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _겹침(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _결말점프_자리(segs, jump_max):
    """예전 make.check 그대로(2026-09-01 A안 · 09-09 Deep61·Deep55) — 끝 블록이 시작하는 재생 순서 번호."""
    cut_i = len(segs)
    if len(segs) > 1 and segs[-1].get("phase") == 5:
        acc = 0.0
        for i in range(len(segs) - 1, 0, -1):
            acc += _길이(segs[i])
            if acc > jump_max:
                break
            if segs[i]["t0"] - segs[i - 1]["t1"] > 큰간격_s:   # 큰 간격 = 끝 장면으로 점프한 자리
                cut_i = i
                break
        if cut_i == len(segs) and _길이(segs[-1]) <= jump_max:
            cut_i = len(segs) - 1                          # 큰 간격 없음 — 마지막 한 조각만(원래 동작)
    return cut_i


def _광고구간(proj):
    out = []
    for x in proj.get("광고구간") or []:
        if isinstance(x, dict):
            a, b = x.get("t0"), x.get("t1")
        else:
            a, b = (list(x) + [None, None])[:2]
        if a is None or b is None or float(b) <= float(a):
            continue
        out.append((float(a), float(b)))
    return out


def _도입점프(body, 끝, hook, e, proj, lo_d):
    dur = float((proj.get("source") or {}).get("dur") or 0)
    """(앞 블록 조각들, 설명) — 인정되면 앞 블록, 아니면 ([], 이유). 선언이 없으면 ([], None)."""
    한도 = float(e.get("도입점프_최대_s", 0) or 0)
    선언 = proj.get("도입점프")
    if 한도 <= 0 or not 선언:
        return [], None
    if not isinstance(선언, dict) or not str(선언.get("근거", "")).strip():
        return [], "«도입점프» 선언에 근거(무슨 셋업이 뒤 어디서 갚히는가 — agy 파악 «꼭 남길 대사» 등)가 없다"
    짝 = 선언.get("짝") or []
    if not isinstance(짝, list) or not 짝:
        return [], "«도입점프» 선언에 짝(셋업이 갚히는 본체·결말 조각 안 원본 시각)이 없다"
    src = sorted(body, key=lambda s: s["t0"])
    후보 = []
    acc = 0.0
    for k in range(1, len(src)):
        acc += _길이(src[k - 1])
        if acc > 한도 + 1e-6:
            break
        if src[k]["t0"] - src[k - 1]["t1"] > 큰간격_s:
            후보.append(k)
    if not 후보:
        return [], (f"훅 뒤 앞 블록(합 {한도:.0f}초 이하)과 본체 사이에 {큰간격_s:.0f}초 넘는 간격이 없다"
                    f" — 도입 점프가 아니라 본체의 일부다")
    이유 = None
    for k in reversed(후보):                                # 한도 안에서 가장 긴 앞 블록부터
        앞 = src[:k]
        뒤 = src[k:] + 끝
        # 재생 순서: 앞 블록이 훅 바로 뒤에 «먼저» 나와야 셋업이다(뒤에서 되감아 보여 주면 점프가 아니라 뒤섞기)
        if [id(s) for s in body[:k]] != [id(s) for s in sorted(앞, key=lambda s: s["t0"])]:
            이유 = "앞 블록이 훅 바로 뒤에 원본 순서대로 먼저 나오지 않는다"
            continue
        if any(s.get("phase") != 2 for s in 앞):
            이유 = f"앞 블록에 P2(Context) 아닌 조각이 있다 — P{[s.get('phase') for s in 앞]}"
            continue
        # 셋업 = 원본 «도입» — 앞 블록은 원본 앞 1/3 안에서 시작해야 한다(점심이네 셋업 15편 실측: 0.4~123초 · 원본의 0~29%)
        if dur and 앞[0]["t0"] > dur * 도입_앞비율:
            이유 = (f"앞 블록 시작 {앞[0]['t0']:.0f}초가 원본({dur:.0f}초) 앞 {도입_앞비율*100:.0f}% 밖이다"
                    f" — 원본 도입부의 셋업이 아니다")
            continue
        a_span = 앞[-1]["t1"] - 앞[0]["t0"]
        a_dens = sum(_길이(s) for s in 앞) / a_span if a_span > 0 else 1.0
        if a_dens < lo_d:
            이유 = (f"앞 블록 자체 밀도 {a_dens*100:.0f}% — 셋업도 원본 {a_span:.0f}초를 듬성듬성 긁었다"
                    f"({lo_d*100:.0f}% 이상이어야 한다)")
            continue
        못찾음 = [t for t in 짝 if not any(s["t0"] - 0.05 <= float(t) <= s["t1"] + 0.05 for s in 뒤)]
        if 못찾음:
            이유 = f"짝 시각 {못찾음} 이 앞 블록 뒤(본체·결말) 조각 안에 없다 — 셋업이 갚히는 자리를 조각에 넣어라"
            continue
        return 앞, (f"도입 점프 인정 — 앞 블록 {앞[0]['t0']:.1f}~{앞[-1]['t1']:.1f}초"
                    f"({len(앞)}조각 · {sum(_길이(s) for s in 앞):.1f}초 · 블록 밀도 {a_dens*100:.0f}%) ·"
                    f" 짝 {짝} · 근거: {str(선언.get('근거'))[:60]}")
    return [], 이유


def 계산(segs, e, proj=None):
    """segs = keep 조각(재생 순서). e = CFG["edit"]. → dict
    dens·span·c_total(본체 길이) · 뺀 것(목록) · 반려·주의(선언이 틀렸을 때) · 도입점프_이유."""
    proj = proj or {}
    lo_d = e.get("density", [0.40, 0.75])[0]
    jump_max = e.get("결말점프_최대_s", 0)
    out = {"뺀것": [], "반려": [], "주의": [], "도입점프_이유": None}

    cut_i = _결말점프_자리(segs, jump_max)
    끝 = segs[cut_i:]
    본 = segs[:cut_i]
    if 끝:
        out["뺀것"].append(f"결말 점프 {끝[0]['t0']:.1f}~{끝[-1]['t1']:.1f}초")

    머리훅 = 본[0] if len(본) > 1 and 본[0].get("phase") == 1 else None

    # 도입 점프는 훅 뒤 조각들로만 찾는다(훅은 셋업이 아니다)
    뒤본 = [s for s in 본 if s is not 머리훅]
    앞, 이유 = _도입점프(뒤본, 끝, 머리훅, e, proj, lo_d)
    out["도입점프_이유"] = 이유
    if 앞:
        본 = [s for s in 본 if all(s is not a for a in 앞)]
        out["뺀것"].append(이유)
    elif 이유 and proj.get("도입점프"):
        out["주의"].append(f"«도입점프» 선언을 인정하지 않았다 — {이유}")
    elif proj.get("도입점프") and not float(e.get("도입점프_최대_s", 0) or 0):
        out["주의"].append("«도입점프» 를 선언했지만 규격 edit.도입점프_최대_s 가 0(꺼짐)이라 밀도 계산에 쓰지 않았다")

    # ★훅 — 본체(훅 뺀 조각)에서 큰 간격(>15초) 넘게 떨어진 «먼 선공개» 일 때만 뺀다. 본체 안·곁의 훅은 그 대목의
    #   일부라 예전처럼 센다(곁 훅까지 빼면 클러스터 머리를 훅으로 쓴 Deep 편들 값이 내려간다 — 740개 재기 2026-09-29).
    if e.get("훅_밀도제외") and 머리훅 is not None and any(s is 머리훅 for s in 본):
        나머지 = [s for s in 본 if s is not 머리훅]
        n_lo = min(s["t0"] for s in 나머지)
        n_hi = max(s["t1"] for s in 나머지)
        떨어짐 = max(n_lo - 머리훅["t1"], 머리훅["t0"] - n_hi)
        if 떨어짐 > 큰간격_s:
            본 = 나머지
            out["뺀것"].append(f"먼 훅 {머리훅['t0']:.1f}~{머리훅['t1']:.1f}초(본체에서 {떨어짐:.0f}초 떨어짐)")

    lo = min(s["t0"] for s in 본)
    hi = max(s["t1"] for s in 본)
    span = hi - lo
    c_total = sum(_길이(s) for s in 본)

    if e.get("광고_밀도제외"):
        광고 = _합집합(_광고구간(proj))
        if 광고 and not str(proj.get("_광고구간_근거", "")).strip():
            out["반려"].append("«광고구간» 에 근거(_광고구간_근거 — agy 파악 «광고 구간» 답 등)가 없다")
        else:
            for a, b in 광고:
                for k, s in enumerate(segs):
                    if _겹침(a, b, s["t0"], s["t1"]) > 0.05:
                        out["반려"].append(f"★조각 {k}({s['t0']:.1f}~{s['t1']:.1f})이 광고구간 {a:.1f}~{b:.1f}초와 겹친다"
                                          f" — 다른 회사 광고는 넣지 않는다")
            뺌 = sum(_겹침(a, b, lo, hi) for a, b in 광고)
            if 뺌 > 0:
                span -= 뺌
                out["뺀것"].append(f"광고 {뺌:.1f}초({', '.join(f'{a:.0f}~{b:.0f}' for a, b in 광고)})")
                out["주의"].append(f"밀도 범위에서 광고 {뺌:.1f}초를 뺐다 — 근거: {str(proj.get('_광고구간_근거'))[:60]}")

    if 앞:
        out["주의"].append(f"밀도 범위에서 {이유}")
    out.update(span=span, c_total=c_total, lo=lo, hi=hi,
               dens=(c_total / span if span > 0 else 1.0))
    return out
