#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/도너_규격갱신.py — 도너가 바뀌면 규격 「조립.도너」의 실측값을 다시 적는다.

  왜: 조립기는 견본을 **속성으로** 찾으므로 번호가 틀려도 돌아간다. 그래도 규격에 옛 번호가 남아 있으면
      「문서와 실제가 어긋난다」. 도너를 갈아 끼울 때마다 이 스크립트로 값을 다시 재고 적는다.

  재는 것: 원본 mp4 계보 번호 · 견본(컷·나레·자막) 번호 · 자막 견본의 폰트·크기·위치·런 수.
  안 건드리는 것: UID(왕복해도 안 변한다) · 레벨 값 · 안내문.

사용: python 서버/runner/도너_규격갱신.py --도너 도너/도너_2판.prproj [--쓰기]
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "도너"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prproj_lib import Doc, load, track_items, parse_blob, param_blob, is_source_text, 이름인가, collect_lineage
from 조립_prproj import 견본찾기, 딸린ID, 공유계보

규격_경로 = os.path.join(ROOT, "스타일/영화롱폼/규격.json")


def 참조(블록, 태그=None):
    out = re.findall(r'<(\w+)(?: [^>]*?)? ?ObjectRef="(\d+)"/>', 블록)
    return [o for t, o in out if 태그 is None or t == 태그]


def 자막실측(doc, item):
    """자막 견본 하나 → 번호·폰트·크기·위치·런 수"""
    공유 = 공유계보(doc)
    ids, _u = collect_lineage(doc, [item], stop=공유)
    남 = sorted(ids - 공유, key=int)
    blocks = {i: doc.get(i) for i in 남}
    st = [i for i in 남 if is_source_text(blocks[i])][0]
    info = parse_blob(param_blob(blocks[st], doc.xml))
    pos = [i for i in 남 if 이름인가(blocks[i], "Position") or "<Name>위치</Name>" in blocks[i]]
    v = re.search(r"<StartKeyframe>[^,]+,([^,]+),", blocks[pos[0]]) if pos else None
    d = 딸린ID(doc, item)
    return {"item": item, "chain": d["chain"],
            "vfc": int([i for i in 남 if blocks[i].lstrip().startswith("<VideoFilterComponent")][0]),
            "subclip": d["subclip"], "clip": d["clip"],
            "source_text_param": int(st), "position_param": int(pos[0]) if pos else None,
            "position": v.group(1) if v else None,
            "폰트": (info.get("fonts") or [None])[0],
            "크기_px": (lambda v: int(v) if isinstance(v, float) and v.is_integer() else v)(info["runs"][0].get("size") if info["runs"] else None),
            "런": len(info["runs"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--도너", required=True)
    ap.add_argument("--쓰기", action="store_true", help="규격.json 에 실제로 쓴다(기본은 대조만)")
    a = ap.parse_args()
    spec = json.load(open(규격_경로, encoding="utf-8"))
    DN = spec["조립"]["도너"]
    doc = Doc(load(a.도너 if os.path.isabs(a.도너) else os.path.join(ROOT, a.도너)))
    견본 = 견본찾기(doc)
    새 = {"파일": os.path.relpath(os.path.abspath(a.도너), ROOT).replace("\\", "/")}

    # ① 원본 mp4 계보 — UID 는 그대로, 번호만 다시
    M = dict(DN["원본_mp4"])
    md = M["Media_UID"]
    mb = doc.get_uid(md)
    M["VideoStream"] = int(참조(mb, "VideoStream")[0])
    M["AudioStream"] = int(참조(mb, "AudioStream")[0])
    for m in re.finditer(r'^\t<(\w+) ObjectID="(\d+)"', doc.xml, re.M):
        if f'<Media ObjectURef="{md}"/>' in doc.get(int(m.group(2))) and m.group(1) in ("VideoMediaSource", "AudioMediaSource"):
            M[m.group(1)] = int(m.group(2))
    새["원본_mp4"] = M

    # ② 견본 — 컷·나레는 트랙 첫 아이템, 자막은 폰트로 찾은 것
    S = {k: dict(v) for k, v in DN["견본"].items()}
    cv = 견본["컷_비디오"]
    S["컷_비디오"].update({k: cv[k] for k in ("item", "chain", "subclip", "clip")})
    링크 = [m.group(1) for m in re.finditer(r'^\t<Link ObjectID="(\d+)"', doc.xml, re.M)
            if f'ObjectRef="{cv["item"]}"/>' in doc.get(int(m.group(1)))]
    if 링크: S["컷_비디오"]["link"] = int(링크[0])
    M["Markers"] = int((참조(doc.get(cv["clip"]), "Markers") or [M["Markers"]])[0])
    ca = 견본["컷_오디오_덕킹"]
    S["컷_오디오_덕킹"].update({k: ca[k] for k in ("item", "chain", "subclip", "clip", "filter")})
    S["컷_오디오_덕킹"]["level_param"] = int([p for p in 참조(doc.get(ca["filter"]), "Param") if 이름인가(doc.get(int(p)), "Level")][0])
    items, _ = track_items(doc, DN["트랙_UID"]["A1"])
    if items:
        u = 딸린ID(doc, items[0], 오디오=True)
        S["컷_오디오_유니티"]["item"] = u["item"]
        if "filter" in u:
            S["컷_오디오_유니티"]["filter"] = u["filter"]
            S["컷_오디오_유니티"]["level_param"] = int([p for p in 참조(doc.get(u["filter"]), "Param") if 이름인가(doc.get(int(p)), "Level")][0])
    nr = 견본["나레"]
    S["나레"].update({k: nr[k] for k in ("item", "chain", "subclip", "clip")})
    for 이름, 트 in (("자막_대사", "V2"), ("자막_나레", "V3")):
        S[이름].update({k: v for k, v in 자막실측(doc, 견본[이름]["item"]).items() if v is not None})
    새["견본"] = S

    # ③ 대조 출력
    변경 = []
    def 훑(옛, 뉴, 길="조립.도너"):
        for k, v in 뉴.items():
            if isinstance(v, dict):
                훑(옛.get(k, {}), v, f"{길}.{k}")
            elif 옛.get(k) != v:
                변경.append((f"{길}.{k}", 옛.get(k), v))
    훑(DN, 새)
    폭 = max((len(k) for k, _o, _n in 변경), default=10)
    print(f"도너: {새['파일']}")
    for k, o, n in 변경:
        print(f"  {k.ljust(폭)}  {o} → {n}")
    print(f"\n바뀐 값 {len(변경)}개" + ("" if a.쓰기 else " — 쓰려면 --쓰기"))
    # UID 생존 확인
    죽은 = [u for u in re.findall(r'"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', json.dumps(DN))
            if f'ObjectUID="{u}"' not in doc.xml]
    if 죽은: print(f"!! 도너에 없는 UID {len(죽은)}개: {죽은}")
    if a.쓰기:
        def 병합(옛, 뉴):
            for k, v in 뉴.items():
                옛[k] = 병합(옛.get(k, {}), v) if isinstance(v, dict) else v
            return 옛
        병합(DN, 새)
        json.dump(spec, open(규격_경로, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("규격.json 갱신")
    sys.exit(1 if 죽은 else 0)


if __name__ == "__main__":
    main()
