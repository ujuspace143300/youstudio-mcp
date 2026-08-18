#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_집계.py — 제미나이 판독 여러 편을 합쳐 분포를 낸다 (분석 단계 (c) 재료).

  읽는 것: `분석/지무비/NN/gemini.json`(판독) · `NN/_meta.json`(토큰·시간)
  내는 것: `분석/지무비/요약_판독.json` + 사람이 읽는 표(마크다운)

  집계 원칙(사용자 결정 2026-08-18)
    · 편별 **장르는 데이터에 남긴다**(제목·요약에서 추정하고 근거 문자열을 함께 적는다).
    · 어떤 수치가 **장르별로 뚜렷이 갈리면 합산 평균을 내지 않고 갈린 사실을 보고**한다.
      (판정: 두 장르의 중앙값 차이가 전체 폭의 절반을 넘거나, 참/거짓 비율이 정반대일 때)

사용: python 서버/runner/분석_집계.py [--폴더 분석/지무비] [--md 분석/지무비/요약_판독.md]
"""
import argparse, glob, json, os, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
웹툰말 = ("웹툰", "만화", "네이버 웹툰", "카카오웹툰", "원작 웹툰", "애니")
영화말 = ("영화", "드라마", "실사", "감독", "주연")


def 장르추정(doc):
    글 = " ".join([str(doc.get("편", {}).get("제목") or ""),
                   str((doc.get("결말_60초") or {}).get("요약") or ""),
                   str((doc.get("결말_60초") or {}).get("마무리_문장") or ""),
                   str((doc.get("도입_30초") or {}).get("요약") or ""),
                   " ".join(str(x.get("설명") or "") for x in (doc.get("인상_장치") or []))])
    for w in 웹툰말:
        if w in 글: return "웹툰", f"「{w}」 언급"
    for w in 영화말:
        if w in 글: return "영화", f"「{w}」 언급"
    return "미상", "단서 없음"


def 중앙(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(st.median(xs), 2) if xs else None


def 분포(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    if not xs: return None
    ys = sorted(xs)
    q = lambda p: round(ys[min(len(ys) - 1, max(0, int(round((len(ys) - 1) * p))))], 2)
    return {"n": len(ys), "min": ys[0], "p25": q(0.25), "중앙": q(0.5), "p75": q(0.75), "max": ys[-1]}


def 갈림(값들, 장르):
    """장르별로 뚜렷이 갈리는가 — 갈리면 (True, 설명)"""
    A = [v for v, g in zip(값들, 장르) if g == "영화" and isinstance(v, (int, float))]
    B = [v for v, g in zip(값들, 장르) if g == "웹툰" and isinstance(v, (int, float))]
    if len(A) < 2 or len(B) < 2: return False, "표본 부족"
    ma, mb = st.median(A), st.median(B)
    전체 = [v for v in 값들 if isinstance(v, (int, float))]
    폭 = (max(전체) - min(전체)) or 1
    return (abs(ma - mb) > 폭 / 2), f"영화 중앙 {round(ma,2)} vs 웹툰 중앙 {round(mb,2)} (전체 폭 {round(폭,2)})"


def 참비율(값들, 장르, 라벨):
    A = [v for v, g in zip(값들, 장르) if g == "영화" and isinstance(v, bool)]
    B = [v for v, g in zip(값들, 장르) if g == "웹툰" and isinstance(v, bool)]
    if not A or not B: return None
    ra, rb = sum(A) / len(A), sum(B) / len(B)
    갈렸다 = (ra >= 0.75 and rb <= 0.25) or (rb >= 0.75 and ra <= 0.25)
    return {"항목": 라벨, "영화_참비율": round(ra, 2), "웹툰_참비율": round(rb, 2), "뚜렷이_갈림": 갈렸다}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--폴더", default=os.path.join(ROOT, "분석/지무비"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(a.폴더, "요약_판독.json")
    md = a.md or os.path.join(a.폴더, "요약_판독.md")

    편들 = []
    for p in sorted(glob.glob(os.path.join(a.폴더, "*", "gemini.json"))):
        d = json.load(open(p, encoding="utf-8"))
        nn = os.path.basename(os.path.dirname(p))
        meta = {}
        mp = os.path.join(os.path.dirname(p), "_meta.json")
        if os.path.exists(mp): meta = json.load(open(mp, encoding="utf-8"))
        g, 근거 = 장르추정(d)
        # 총장 검증(2026-08-18 실측): 제미나이가 말하는 총장_s 가 **인용 시각보다 작을 때가 있다**(02: 총장 132s 인데 강조 247s).
        #   그때는 총장을 믿지 않는다 — 인용 시각의 최대값을 하한으로 삼고 표시한다. 정확한 총장은 (a) 기계 계측(ffprobe) 몫.
        시각들 = [x.get("시각_s") for x in (d.get("강조") or []) + (d.get("효과음") or []) + (d.get("전환") or []) if isinstance(x.get("시각_s"), (int, float))]
        하한 = max(시각들) if 시각들 else 0
        총장 = (d.get("편") or {}).get("총장_s")
        총장믿음 = isinstance(총장, (int, float)) and 총장 >= 하한 - 1
        레인 = d.get("자막_레인") or []
        나레레인 = next((r for r in 레인 if "나레" in str(r.get("레인"))), {})
        대사레인 = next((r for r in 레인 if "대사" in str(r.get("레인"))), {})
        강조 = d.get("강조") or []
        편들.append({
            "nn": nn, "제목": (d.get("편") or {}).get("제목"), "장르": g, "장르_근거": 근거,
            "총장_s": 총장, "총장_하한_s": round(하한, 1), "총장_믿음": 총장믿음,
            "나레_비중_%": (d.get("전체_인상") or {}).get("나레_비중_%"),
            "강조_수": len(강조), "효과음_수": len(d.get("효과음") or []), "전환_수": len(d.get("전환") or []),
            "훅_유형": (d.get("도입_30초") or {}).get("훅_유형"), "훅_끝_s": (d.get("도입_30초") or {}).get("훅_끝_s"),
            "결말_공개": (d.get("결말_60초") or {}).get("결말_공개"), "CTA": (d.get("결말_60초") or {}).get("CTA_있음"),
            "마무리_유형": (d.get("결말_60초") or {}).get("마무리_유형"),
            "나레_y": 나레레인.get("화면_y_비율"), "나레_크기_%": 나레레인.get("글자높이_화면대비_%"), "나레_색": 나레레인.get("색_HEX"),
            "대사_y": 대사레인.get("화면_y_비율"), "대사_크기_%": 대사레인.get("글자높이_화면대비_%"), "대사_색": 대사레인.get("색_HEX"),
            "강조_색": sorted({str((x.get("강조_방식") or {}).get("색_HEX")) for x in 강조} - {"None"}),
            "강조_크기배수": [(x.get("강조_방식") or {}).get("크기_배수") for x in 강조],
            "강조_유형": [x.get("의미_유형") for x in 강조],
            "효과음_자리": [x.get("붙은_자리") for x in (d.get("효과음") or [])],
            "효과음_종류": [x.get("종류") for x in (d.get("효과음") or [])],
            "토큰": (meta.get("usage") or {}).get("totalTokenCount"), "걸린_s": meta.get("걸린_s"),
        })

    장르 = [x["장르"] for x in 편들]
    def 열(k): return [x.get(k) for x in 편들]
    유형수, 자리수, 종류수, 색수 = {}, {}, {}, {}
    for x in 편들:
        for t in x["강조_유형"]: 유형수[t] = 유형수.get(t, 0) + 1
        for t in x["효과음_자리"]: 자리수[t] = 자리수.get(t, 0) + 1
        for t in x["효과음_종류"]: 종류수[t] = 종류수.get(t, 0) + 1
        for t in x["강조_색"]: 색수[t] = 색수.get(t, 0) + 1
    분당강조 = [round(x["강조_수"] / (x["총장_s"] / 60), 2) if x.get("총장_s") else None for x in 편들]
    분당효과음 = [round(x["효과음_수"] / (x["총장_s"] / 60), 2) if x.get("총장_s") else None for x in 편들]

    요약 = {
        "표본": len(편들), "장르구성": {g: 장르.count(g) for g in set(장르)},
        "총장_못믿는_편": [x["nn"] for x in 편들 if not x["총장_믿음"]],
        "합계": {"토큰": sum(x["토큰"] or 0 for x in 편들), "걸린_s": round(sum(x["걸린_s"] or 0 for x in 편들), 1),
                "총_영상_분": round(sum(x["총장_s"] or 0 for x in 편들) / 60, 1)},
        "D5_자막모양": {"나레_크기_%": 분포(열("나레_크기_%")), "대사_크기_%": 분포(열("대사_크기_%")),
                     "나레_색": {c: 열("나레_색").count(c) for c in set(열("나레_색")) if c},
                     "대사_색": {c: 열("대사_색").count(c) for c in set(열("대사_색")) if c},
                     "나레_y_예": [x["나레_y"] for x in 편들 if x["나레_y"]][:10],
                     "대사_y_예": [x["대사_y"] for x in 편들 if x["대사_y"]][:10]},
        "D6_강조": {"편당_건수": 분포(열("강조_수")), "분당_건수": 분포(분당강조),
                  "의미유형_빈도": dict(sorted(유형수.items(), key=lambda kv: -kv[1])),
                  "색_빈도": dict(sorted(색수.items(), key=lambda kv: -kv[1])),
                  "크기배수": 분포([v for x in 편들 for v in x["강조_크기배수"]])},
        "D8_효과음": {"편당_건수": 분포(열("효과음_수")), "분당_건수": 분포(분당효과음),
                   "붙은자리_빈도": dict(sorted(자리수.items(), key=lambda kv: -kv[1])),
                   "종류_빈도": dict(sorted(종류수.items(), key=lambda kv: -kv[1]))},
        "D10_훅": {"유형_빈도": {t: 열("훅_유형").count(t) for t in set(열("훅_유형")) if t}, "끝_s": 분포(열("훅_끝_s"))},
        "D11_결말": {"결말공개_참": sum(1 for v in 열("결말_공개") if v is True), "CTA_참": sum(1 for v in 열("CTA") if v is True),
                   "마무리유형_빈도": {t: 열("마무리_유형").count(t) for t in set(열("마무리_유형")) if t}},
        "장르_갈림": {
            "나레_비중_%": dict(zip(["갈림", "설명"], 갈림(열("나레_비중_%"), 장르))),
            "총장_s": dict(zip(["갈림", "설명"], 갈림(열("총장_s"), 장르))),
            "분당_강조": dict(zip(["갈림", "설명"], 갈림(분당강조, 장르))),
            "결말_공개": 참비율(열("결말_공개"), 장르, "결말_공개"),
            "CTA": 참비율(열("CTA"), 장르, "CTA"),
        },
        "편": 편들,
    }
    json.dump(요약, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    줄 = ["| NN | 장르 | 제목 | 총장 | 나레% | 강조 | 효과음 | 훅 | 결말공개 | CTA | 토큰 |",
          "| :-- | :-- | :-- | --: | --: | --: | --: | :-- | :-- | :-- | --: |"]
    for x in 편들:
        표시장 = f'{round((x["총장_s"] or 0)/60,1)}분' + ("" if x["총장_믿음"] else f'(?≥{round(x["총장_하한_s"]/60,1)}분)')
        줄.append(f'| {x["nn"]} | {x["장르"]} | {str(x["제목"])[:22]} | {표시장} | {x["나레_비중_%"]} | '
                  f'{x["강조_수"]} | {x["효과음_수"]} | {x["훅_유형"]} | {"○" if x["결말_공개"] else "×"} | {"○" if x["CTA"] else "×"} | {x["토큰"]} |')
    open(md, "w", encoding="utf-8").write("\n".join(줄) + "\n")
    print("\n".join(줄))
    print(f'\n표본 {요약["표본"]} · 장르 {요약["장르구성"]} · 총 토큰 {요약["합계"]["토큰"]} · 총 {요약["합계"]["걸린_s"]}s · 영상 {요약["합계"]["총_영상_분"]}분')
    print("장르 갈림:", json.dumps(요약["장르_갈림"], ensure_ascii=False))
    print("저장:", out, "·", md)


if __name__ == "__main__":
    main()
