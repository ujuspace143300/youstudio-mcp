#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/맛보기_강조색.py — 완성 prproj 의 **자막 런 색만** 바꿔 맛보기 파일을 만든다 (5단계 검증).

  왜: StyleTable.f2 = 채움색(1바이트 R·G·B)임을 바이트 대조로 규명했다(진단일지 §26).
      「읽은 것이 맞다」는 화면으로 확인해야 확정이다 — 계단 3-d 때처럼 **맛보기 몇 큐**로 먼저 본다.

  하는 일: ① 나레 자막의 런 색을 전부 흰색으로 되돌리고(지금은 견본에서 빨강이 딸려 온다)
           ② 지정한 큐 몇 개만 일부러 색을 넣는다 → 사람이 열어서 그 자리만 색이 바뀌는지 본다.
  안전: 색 표를 버퍼 끝에 새로 붙이고 참조만 돌린다(원본 표는 다른 큐와 공유될 수 있다).

사용:
  python 서버/runner/맛보기_강조색.py --prproj <완성.prproj> --out <맛보기.prproj> \
      --강조 1:1:E60206 --강조 5:0:FEE700 --강조 9:1:00FF00
      (큐번호:런번호:색 — 큐번호는 나레 자막을 시각 순으로 센 1부터)
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "도너"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prproj_lib import (Doc, load, save, track_items, parse_blob, param_blob, param_set_blob,
                        is_source_text, collect_lineage, blob_set_colors, TPS)
from 조립_prproj import 공유계보

흰 = [252, 253, 253]          # 도너 자막의 기본 흰색(실측)


def 자막들(doc, 트랙UID):
    """(시각순) [(item, Source Text 파라미터, 런 목록, t0, t1)]"""
    공유 = 공유계보(doc)
    out = []
    items, _ = track_items(doc, 트랙UID)
    for it in items:
        b = doc.get(it)
        s = re.search(r"<Start>(\d+)</Start>", b); e = re.search(r"<End>(\d+)</End>", b)
        ids, _u = collect_lineage(doc, [it], stop=공유)
        st = [i for i in sorted(ids - 공유, key=int) if is_source_text(doc.get(i))][0]
        runs = parse_blob(param_blob(doc.get(st), doc.xml))["runs"]
        out.append({"item": it, "st": st, "runs": runs,
                    "t0": (int(s.group(1)) / TPS if s else 0.0), "t1": (int(e.group(1)) / TPS if e else 0.0)})
    out.sort(key=lambda c: c["t0"])
    return out


def tc(s):
    return f"{int(s) // 60}:{s % 60:05.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prproj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--트랙", default="V3", help="색을 손볼 트랙(기본 V3 = 나레 자막)")
    ap.add_argument("--강조", action="append", default=[], help="큐번호:런번호:RRGGBB (1부터)")
    ap.add_argument("--기본색", default="FCFDFD", help="나머지 런을 칠할 색(기본 = 도너 흰색)")
    a = ap.parse_args()
    T = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))["조립"]["도너"]["트랙_UID"]
    doc = Doc(load(a.prproj))
    cues = 자막들(doc, T[a.트랙])
    기본 = [int(a.기본색[i:i + 2], 16) for i in (0, 2, 4)]
    지정 = {}
    for x in a.강조:
        c, r, hexcol = x.split(":")
        지정.setdefault(int(c), {})[int(r)] = [int(hexcol[i:i + 2], 16) for i in (0, 2, 4)]

    바뀜 = 0
    보기 = []
    for k, c in enumerate(cues, 1):
        want = [list(기본) for _ in c["runs"]]
        for r, rgb in (지정.get(k) or {}).items():
            if r < len(want): want[r] = rgb
        지금 = [r["color"] for r in c["runs"]]
        if 지금 == want:
            continue
        b64 = param_blob(doc.get(c["st"]), doc.xml)
        새, h, info = blob_set_colors(b64, want)
        blk = param_set_blob(doc.get(c["st"]), 새, h)
        doc.replace(c["st"], blk)
        바뀜 += 1
        if k in 지정:
            보기.append((k, c, want, info))
    save(a.out, doc.xml)

    # 자기검증 — 저장한 파일을 다시 읽어 색을 확인한다
    다시 = 자막들(Doc(load(a.out)), T[a.트랙])
    틀림 = []
    for k, c in enumerate(다시, 1):
        want = [list(기본) for _ in c["runs"]]
        for r, rgb in (지정.get(k) or {}).items():
            if r < len(want): want[r] = rgb
        if [r["color"] for r in c["runs"]] != want:
            틀림.append(k)
    print(f'{a.트랙} 자막 {len(cues)}개 중 {바뀜}개 색을 다시 썼다 → {a.out}')
    print(f'  [{"OK" if not 틀림 else "X"}] 저장본 재파싱 = 넣은 색  불일치 {len(틀림)}개 {틀림[:5]}')
    print("\n사람이 볼 자리:")
    for k, c, want, _info in 보기:
        글 = "".join(r["text"] for r in c["runs"])
        칠 = " · ".join(f'런{i} 「{r["text"]}」 → {want[i]}' for i, r in enumerate(c["runs"]) if want[i] != 기본)
        print(f'  {tc(c["t0"])}~{tc(c["t1"])}  「{글}」')
        print(f'      {칠}')
    print(f'  나머지 {len(cues) - len(보기)}개 큐는 전부 흰색({기본})이어야 한다 — 지금 산출물은 첫 런이 빨강이다')
    sys.exit(1 if 틀림 else 0)


if __name__ == "__main__":
    main()
