#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/도너_대조.py — 프리미어 왕복 전후의 prproj 두 개를 대조한다 (0단계 무해 왕복 시험).

  왜: 조립기는 도너의 견본을 복제해 쓴다. 프리미어가 저장할 때 ObjectID·UID 를 다시 매기면
      「도너를 직접 고쳐 크기·위치를 바꾸는 길」이 통째로 깨진다. 그 여부를 **재고 나서** 시작한다.

  대조 8항목: ①ObjectID 수·최대 ②ObjectUID 집합 ③견본 자막 ID ④Source Text 파라미터 ID·글자
             ⑤트랙 UID 6개 ⑥시퀀스 UID ⑦자막 총수·폰트 종류 ⑧속성으로 찾기 재현

사용: python 서버/runner/도너_대조.py --전 도너/_도너시험.prproj --후 도너/_도너시험_저장.prproj
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "도너"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prproj_lib import Doc, load, parse_blob, param_blob
from 조립_prproj import SHARED, 견본찾기      # 견본을 속성으로 찾는 규칙은 조립기와 한 벌만 둔다

SPEC = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))
DN = SPEC["조립"]["도너"]
T, S = DN["트랙_UID"], DN["견본"]


def 색인(xml):
    """ObjectID/UID → 블록 본문. 한 번만 훑는다(블록마다 정규식을 다시 돌리면 136개에서 몇 분씩 걸린다)."""
    pos = [(m.group(3), m.start()) for m in re.finditer(r'^	<(\w+) Object(ID|UID)="([^"]+)"', xml, re.M)]
    끝 = [p[1] for p in pos[1:]] + [len(xml)]
    return {k: xml[a:b] for (k, a), b in zip(pos, 끝)}


def 자막블롭들(ix):
    """Source Text 파라미터를 담은 블록 전부 → (파라미터ID, 폰트들, 글자)"""
    out = []
    for oid, blk in ix.items():
        if "<Name>Source Text</Name>" not in blk:
            continue
        try:
            info = parse_blob(param_blob(blk))
        except Exception:
            continue
        out.append((oid, tuple(info.get("fonts") or []), "".join(r["text"] for r in info["runs"])))
    return out


def 견본글자(ix, item):
    """견본 아이템 → (Source Text 파라미터ID, 글자). 색인만 쓰므로 빠르다."""
    try:
        blk = ix[str(item)]
        chain = re.search(r'<Components ObjectRef="(\d+)"', blk).group(1)
        for comp in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', ix[chain]):
            for prm in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', ix[comp]):
                if "<Name>Source Text</Name>" in ix[prm]:
                    info = parse_blob(param_blob(ix[prm]))
                    return prm, "".join(r["text"] for r in info["runs"])
    except Exception:
        pass
    return None, None


def 훑기(path):
    doc = Doc(load(path))
    ix = 색인(doc.xml)
    ids = re.findall(r'^	<\w+ ObjectID="(\d+)"', doc.xml, re.M)
    uids = re.findall(r'^	<\w+ ObjectUID="([0-9a-f-]+)"', doc.xml, re.M)
    subs = 자막블롭들(ix)
    return doc, ix, {"id수": len(ids), "id최대": max(int(x) for x in ids), "uid집합": set(uids),
                     "자막수": len(subs), "폰트": sorted({f for _o, fs, _t in subs for f in fs})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--전", required=True)
    ap.add_argument("--후", required=True)
    a = ap.parse_args()
    for p in (a.전, a.후):
        if not os.path.exists(p):
            print(f"✗ 파일이 없다: {p}"); sys.exit(2)
    d1, ix1, A = 훑기(a.전)
    d2, ix2, B = 훑기(a.후)
    결과 = []

    def 검사(이름, 통과, 상세):
        결과.append((이름, bool(통과), 상세))

    검사("① ObjectID 수·최대", A["id수"] == B["id수"] and A["id최대"] == B["id최대"],
         f'{A["id수"]}개/최대 {A["id최대"]} → {B["id수"]}개/최대 {B["id최대"]}')
    새 = B["uid집합"] - A["uid집합"]; 사라짐 = A["uid집합"] - B["uid집합"]
    검사("② ObjectUID 집합", not 새 and not 사라짐,
         f'{len(A["uid집합"])}개 → {len(B["uid집합"])}개 · 새 {len(새)} · 사라짐 {len(사라짐)}')
    for 이름 in ("자막_대사", "자막_나레"):
        it = int(S[이름]["item"])
        p1, t1 = 견본글자(ix1, it)
        p2, t2 = 견본글자(ix2, it)
        검사(f"③ 견본 {이름} item {it}", t1 is not None and t1 == t2,
             f'글자 「{(t1 or "없음")[:14]}」 → 「{(t2 or "없음")[:14]}」')
        검사(f"④ {이름} Source Text 파라미터", p1 is not None and p1 == p2, f'{p1} → {p2}')
    for 트, uid in T.items():
        있음 = f'ObjectUID="{uid}"' in d2.xml
        검사(f"⑤ 트랙 UID {트}", 있음, uid if 있음 else "없어짐")
    seq = DN.get("시퀀스", {}).get("UID")
    if seq:
        검사("⑥ 시퀀스 UID", f'ObjectUID="{seq}"' in d2.xml, seq)
    검사("⑦ 자막 총수·폰트", A["자막수"] == B["자막수"] and A["폰트"] == B["폰트"],
         f'{A["자막수"]}개/{len(A["폰트"])}종 → {B["자막수"]}개/{len(B["폰트"])}종')
    try:
        f1, f2 = 견본찾기(d1), 견본찾기(d2)
        같음 = all(견본글자(ix1, f1[k]["item"])[1] == 견본글자(ix2, f2[k]["item"])[1]
                  for k in ("자막_나레", "자막_대사"))
        검사("⑧ 속성으로 찾기 재현", 같음,
             " · ".join(f'{k} {f1[k]["item"]}→{f2[k]["item"]}' for k in ("자막_나레", "자막_대사", "컷_비디오", "나레")))
    except Exception as e:
        검사("⑧ 속성으로 찾기 재현", False, f"실행 실패 {e}")

    폭 = max(len(n) for n, _p, _d in 결과)
    for 이름, 통과, 상세 in 결과:
        print(f'  [{"OK" if 통과 else "!!"}] {이름.ljust(폭)}  {상세}')
    불통 = [n for n, p, _d in 결과 if not p]
    치명 = [n for n in 불통 if not n.startswith("⑧")]
    print()
    if not 불통:
        print("전체 통과 — 프리미어 왕복이 ID·UID 를 바꾸지 않는다. 1단계(도너 직접 편집)로 간다.")
    elif not 치명:
        print("⑧만 불통 — 길은 유효하다. 조립기의 견본찾기 규칙을 손보면 된다.")
    else:
        print(f'불통 {len(불통)}개 — 이 길은 종료. 블롭 서식 쓰기로 돌아간다: {", ".join(불통)}')
    sys.exit(1 if 치명 else 0)


if __name__ == "__main__":
    main()
