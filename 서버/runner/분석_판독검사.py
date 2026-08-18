#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_판독검사.py — 제미나이 판독(gemini.json)이 쓸 만한지 검사하고 요약한다.

  지침서: `분석/지무비/제미나이_지침서.md` · 설계: `설계/분석_지무비.md` (b)
  사람이 AI Studio 에서 받아 저장한 JSON 을 **곧바로** 검사한다 — 형식이 어긋난 판독을 열 편 모은 뒤에
  알면 다시 받는 비용이 크다. 스키마(키·타입·허용값·시간 범위)를 보고, 통과하면 한눈 요약을 찍는다.

사용:
  python 서버/runner/분석_판독검사.py --판독 분석/지무비/01/gemini.json
  python 서버/runner/분석_판독검사.py --폴더 분석/지무비          # 있는 것 전부 검사 + 진행 상황
"""
import argparse, glob, json, os, re, sys

확신값 = {"높음", "보통", "낮음"}
의미유형 = {"숫자", "고유명사", "감정어", "반전어", "의성어", "행위어", "기타"}
붙은자리 = {"컷 전환", "강조 단어", "반전", "장면 시작", "기타"}
전환방식 = {"디졸브", "플래시", "줌", "기타"}
훅유형 = {"질문", "사건 제시", "결말 암시", "인물 소개", "기타"}
마무리유형 = {"여운", "교훈", "반전 재확인", "다음 영상 유도", "기타"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def 검사(doc, 이름="판독"):
    """돌려주는 것: (오류 목록, 경고 목록, 요약 dict). 오류가 있으면 그 편은 쓰지 않는다."""
    E, W = [], []
    def need(cond, msg):
        if not cond: E.append(msg)
    def warn(cond, msg):
        if not cond: W.append(msg)
    def num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)

    need(isinstance(doc, dict), "최상위가 객체가 아니다")
    if E: return E, W, {}
    for k in ("편", "자막_레인", "강조", "효과음", "도입_30초", "결말_60초"):
        need(k in doc, f"필수 키 없음: {k}")
    if E: return E, W, {}

    편 = doc.get("편") or {}
    need(num(편.get("총장_s")) and 편["총장_s"] > 0, "편.총장_s 가 숫자가 아니다(초 단위 숫자여야 한다)")
    dur = 편.get("총장_s") if num(편.get("총장_s")) else None
    warn(bool(편.get("url")), "편.url 이 비었다")
    warn(bool(편.get("제목")), "편.제목 이 비었다")

    def 시각(x, where):
        if x is None: return
        if not num(x): E.append(f"{where}: 시각이 숫자가 아니다({x!r}) — \"1:23\" 표기 금지"); return
        if dur and not (-1 <= x <= dur + 5): W.append(f"{where}: 시각 {x}s 가 총장 {dur}s 밖")

    레인 = doc.get("자막_레인") or []
    need(isinstance(레인, list) and len(레인) >= 1, "자막_레인 이 비었다(최소 1개)")
    for i, r in enumerate(레인 if isinstance(레인, list) else []):
        w = f"자막_레인[{i}]"
        need(isinstance(r, dict), f"{w}: 객체가 아니다")
        if not isinstance(r, dict): continue
        y = r.get("화면_y_비율")
        need(isinstance(y, list) and len(y) == 2 and all(num(v) and 0 <= v <= 1 for v in y), f"{w}.화면_y_비율: [위,아래] 0~1 비율이어야 한다")
        warn(HEX.match(str(r.get("색_HEX", ""))) is not None, f"{w}.색_HEX 가 #RRGGBB 형식이 아니다({r.get('색_HEX')!r})")
        warn(num(r.get("글자높이_화면대비_%")), f"{w}.글자높이_화면대비_% 가 숫자가 아니다")
        need(r.get("확신") in 확신값, f"{w}.확신 은 높음/보통/낮음 중 하나여야 한다({r.get('확신')!r})")
        시각(r.get("예시_시각_s"), w)

    강조 = doc.get("강조") or []
    need(isinstance(강조, list), "강조 가 배열이 아니다")
    for i, g in enumerate(강조 if isinstance(강조, list) else []):
        w = f"강조[{i}]"
        if not isinstance(g, dict): E.append(f"{w}: 객체가 아니다"); continue
        시각(g.get("시각_s"), w)
        need(isinstance(g.get("강조_단어"), list) and len(g["강조_단어"]) >= 1, f"{w}.강조_단어 는 배열(1개 이상)")
        need(g.get("의미_유형") in 의미유형, f"{w}.의미_유형 이 목록 밖이다({g.get('의미_유형')!r})")
        need(g.get("확신") in 확신값, f"{w}.확신 값이 목록 밖({g.get('확신')!r})")
        방식 = g.get("강조_방식") or {}
        warn(HEX.match(str(방식.get("색_HEX", ""))) is not None, f"{w}.강조_방식.색_HEX 형식")
        warn(num(방식.get("크기_배수")), f"{w}.강조_방식.크기_배수 가 숫자가 아니다")
        warn(bool(str(g.get("자막_전문") or "").strip()), f"{w}.자막_전문 이 비었다")
    warn(len(강조) >= 8, f"강조 사례가 {len(강조)}개다 — 지침은 8개 이상(없으면 판독_불가 에 사유)")

    효과음 = doc.get("효과음") or []
    need(isinstance(효과음, list), "효과음 이 배열이 아니다")
    for i, s in enumerate(효과음 if isinstance(효과음, list) else []):
        w = f"효과음[{i}]"
        if not isinstance(s, dict): E.append(f"{w}: 객체가 아니다"); continue
        시각(s.get("시각_s"), w)
        need(s.get("붙은_자리") in 붙은자리, f"{w}.붙은_자리 목록 밖({s.get('붙은_자리')!r})")
        need(s.get("확신") in 확신값, f"{w}.확신 목록 밖")
    warn(len(효과음) >= 5 or any("효과음" in str(x) for x in doc.get("판독_불가") or []),
         f"효과음 사례가 {len(효과음)}개다 — 지침은 5개 이상(없으면 판독_불가 에 사유)")

    for i, t in enumerate(doc.get("전환") or []):
        w = f"전환[{i}]"
        if not isinstance(t, dict): E.append(f"{w}: 객체가 아니다"); continue
        시각(t.get("시각_s"), w)
        need(t.get("방식") in 전환방식, f"{w}.방식 목록 밖({t.get('방식')!r})")

    도입 = doc.get("도입_30초") or {}
    need(도입.get("훅_유형") in 훅유형, f"도입_30초.훅_유형 목록 밖({도입.get('훅_유형')!r})")
    시각(도입.get("훅_끝_s"), "도입_30초.훅_끝_s")
    warn(bool(str(도입.get("나레_첫문장") or "").strip()), "도입_30초.나레_첫문장 이 비었다")
    결말 = doc.get("결말_60초") or {}
    need(결말.get("마무리_유형") in 마무리유형, f"결말_60초.마무리_유형 목록 밖({결말.get('마무리_유형')!r})")
    need(isinstance(결말.get("결말_공개"), bool), "결말_60초.결말_공개 는 true/false")
    warn(isinstance(doc.get("인상_장치"), list) and len(doc["인상_장치"]) >= 3, "인상_장치 가 3개 미만")
    전체 = doc.get("전체_인상") or {}
    warn(num(전체.get("나레_비중_%")), "전체_인상.나레_비중_% 가 숫자가 아니다")

    낮음 = sum(1 for g in 강조 if isinstance(g, dict) and g.get("확신") == "낮음")
    유형 = {}
    for g in 강조:
        if isinstance(g, dict): 유형[g.get("의미_유형")] = 유형.get(g.get("의미_유형"), 0) + 1
    색 = sorted({str((g.get("강조_방식") or {}).get("색_HEX")) for g in 강조 if isinstance(g, dict)} - {"None"})
    자리 = {}
    for s in 효과음:
        if isinstance(s, dict): 자리[s.get("붙은_자리")] = 자리.get(s.get("붙은_자리"), 0) + 1
    요약 = {"제목": 편.get("제목"), "총장_s": dur, "총장_분": round(dur / 60, 1) if dur else None,
            "레인": [(r.get("레인"), r.get("화면_y_비율"), r.get("색_HEX"), r.get("글자높이_화면대비_%")) for r in 레인 if isinstance(r, dict)],
            "강조_수": len(강조), "강조_확신낮음": 낮음, "강조_유형분포": 유형, "강조_색": 색,
            "효과음_수": len(효과음), "효과음_자리분포": 자리, "전환_수": len(doc.get("전환") or []),
            "훅_유형": 도입.get("훅_유형"), "훅_끝_s": 도입.get("훅_끝_s"),
            "마무리_유형": 결말.get("마무리_유형"), "결말_공개": 결말.get("결말_공개"), "CTA": 결말.get("CTA_있음"),
            "나레_비중_%": 전체.get("나레_비중_%"), "판독_불가": doc.get("판독_불가") or []}
    return E, W, 요약


def 한편(path):
    이름 = os.path.basename(os.path.dirname(path)) or os.path.basename(path)
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except Exception as ex:
        print(f"✗ {이름}: JSON 을 읽을 수 없다 — {ex}")
        print("   → 코드블록 안쪽만 복사했는지, UTF-8 로 저장했는지 본다")
        return False
    E, W, 요약 = 검사(doc, 이름)
    for e in E: print(f"  ✗ {e}")
    for w in W: print(f"  ! {w}")
    if not E:
        print(f"✓ {이름} 통과 — {json.dumps(요약, ensure_ascii=False)}")
    else:
        print(f"✗ {이름} 불통 {len(E)}건 (경고 {len(W)}건)")
    return not E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--판독")
    ap.add_argument("--폴더")
    a = ap.parse_args()
    if a.판독:
        sys.exit(0 if 한편(a.판독) else 1)
    if not a.폴더:
        ap.error("--판독 또는 --폴더 중 하나가 필요하다")
    paths = sorted(glob.glob(os.path.join(a.폴더, "*", "gemini.json")))
    print(f"판독 파일 {len(paths)}개 / 표본 10편")
    ok = sum(1 for p in paths if 한편(p))
    print(f"\n통과 {ok} · 불통 {len(paths) - ok} · 아직 없음 {10 - len(paths)}")
    sys.exit(0 if ok == len(paths) and paths else 1)


if __name__ == "__main__":
    main()
