#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/블롭_바이트대조.py — Source Text 블롭의 **런 서식을 필드 단위로 펼쳐** 대조한다 (5단계 규명).

  왜: 화면에서는 한 줄 안 일부 단어가 빨강인데(렌더 실측 31개 큐), 우리 파서가 읽는 필드(크기·색)는
      런마다 똑같이 보인다. 색이 **우리가 안 읽는 필드**에 있다는 뜻이다(진단일지 §23·§25).
      그래서 StyleTable 의 **모든 vtable 슬롯**을 값으로 펼쳐 놓고, 같은 큐 안 런끼리 무엇이 다른지 본다.

  방법: FlatBuffers vtable 을 직접 걷는다. 슬롯마다 (오프셋·원시 4바이트·u32·i32·f32) 를 찍고,
        값이 버퍼 안을 가리키면 **한 단계 더 들어가** 하위 테이블도 같은 식으로 편다.
  대조: ① 한 큐 안 런 vs 런(강조 큐) ② 강조 큐 vs 단색 큐(대조군)

사용:
  python 서버/runner/블롭_바이트대조.py --item 4076                      # 한 큐 펼쳐 보기
  python 서버/runner/블롭_바이트대조.py --강조큐 분석/도너자막_실측.json   # 31개 큐 전수 대조
"""
import argparse, base64, json, os, re, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "도너"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prproj_lib import Doc, load, param_blob, is_source_text, collect_lineage
from 조립_prproj import 공유계보

도너_기본 = "도너/볼케이노_FullTime_v26_b05_ppro-v45.prproj"


def u32(b, o): return struct.unpack_from("<I", b, o)[0]
def i32(b, o): return struct.unpack_from("<i", b, o)[0]
def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def f32(b, o): return struct.unpack_from("<f", b, o)[0]


def 슬롯들(b, t):
    """테이블 t 의 vtable 슬롯 목록 → [(슬롯번호, 절대위치)] (빈 슬롯은 뺀다)"""
    vt = t - i32(b, t)
    n = (u16(b, vt) - 4) // 2
    out = []
    for i in range(n):
        r = u16(b, vt + 4 + 2 * i)
        if r:
            out.append((i, t + r))
    return out


def 값보기(b, p, 폭=4):
    끝 = min(len(b), p + 폭)
    raw = b[p:끝]
    d = {"위치": p, "hex": raw.hex()}
    if len(raw) >= 4:
        d["u32"] = u32(b, p); d["i32"] = i32(b, p)
        f = f32(b, p)
        d["f32"] = round(f, 4) if -1e9 < f < 1e9 else None
    d["u8"] = raw[0] if raw else None
    return d


def 테이블후보(b, p):
    """이 자리의 u32 를 오프셋으로 읽으면 그럴듯한 테이블인가"""
    try:
        t = p + u32(b, p)
        if not (12 < t < len(b) - 4):
            return None
        vt = t - i32(b, t)
        if not (12 <= vt < len(b) - 4):
            return None
        vs = u16(b, vt)
        if 4 <= vs <= 200 and vs % 2 == 0:
            return t
    except Exception:
        pass
    return None


def 펼치기(b, t, 깊이=1, 이름="StyleTable"):
    """테이블을 슬롯 단위로 펼친다(깊이만큼 하위 테이블도)"""
    out = {"_이름": 이름, "_위치": t, "슬롯": {}}
    for i, p in 슬롯들(b, t):
        d = 값보기(b, p)
        sub = 테이블후보(b, p) if 깊이 > 0 else None
        if sub is not None:
            d["하위"] = 펼치기(b, sub, 깊이 - 1, f"{이름}.f{i}")
        out["슬롯"][i] = d
    return out


def 큐블롭(doc, item):
    공유 = 공유계보(doc)
    ids, _u = collect_lineage(doc, [item], stop=공유)
    st = [i for i in sorted(ids - 공유, key=int) if is_source_text(doc.get(i))][0]
    return base64.b64decode(re.sub(r"\s+", "", param_blob(doc.get(st), doc.xml)))


def 런들(b):
    """[(런번호, 텍스트, StyleTable 위치)]"""
    root = 12 + u32(b, 12)
    p = None
    vt = root - i32(b, root)
    r0 = u16(b, vt + 4)
    p = root + r0
    main = p + u32(b, p)
    슬 = dict(슬롯들(b, main))
    rp = 슬[0]
    vec = rp + u32(b, rp)
    out = []
    for i in range(u32(b, vec)):
        el = vec + 4 + 4 * i
        rt = el + u32(b, el)
        s = dict(슬롯들(b, rt))
        tf = s.get(0)
        n = u32(b, tf + u32(b, tf)) if tf else 0
        text = b[tf + u32(b, tf) + 4: tf + u32(b, tf) + 4 + n].decode("utf-8", "replace") if tf else ""
        stf = s.get(1)
        st = stf + u32(b, stf) if stf else None
        out.append((i, text, st))
    return out


def 대조(b, 런):
    """런들의 StyleTable 을 나란히 놓고 다른 슬롯을 찾는다"""
    표 = []
    for i, text, st in 런:
        표.append((i, text, 펼치기(b, st) if st else None))
    슬롯번호 = sorted({k for _i, _t, d in 표 if d for k in d["슬롯"]})
    다름 = []
    for k in 슬롯번호:
        vals = [(_i, (d["슬롯"].get(k) or {}).get("hex") if d else None) for _i, _t, d in 표]
        if len({v for _i, v in vals}) > 1:
            다름.append(k)
    return 표, 다름


def 인쇄(표, 다름):
    슬롯번호 = sorted({k for _i, _t, d in 표 if d for k in d["슬롯"]})
    print(f'  {"슬롯":<5}' + "".join(f'런{i}'.ljust(22) for i, _t, _d in 표) + "  판정")
    for k in 슬롯번호:
        줄 = f"  f{k:<4}"
        for _i, _t, d in 표:
            s = (d["슬롯"].get(k) if d else None)
            줄 += (f'{s["hex"]}/{s.get("f32")}'[:20].ljust(22) if s else "-".ljust(22))
        줄 += "  ← 다름" if k in 다름 else ""
        print(줄)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--도너", default=도너_기본)
    ap.add_argument("--item", type=int, action="append")
    ap.add_argument("--강조큐", default=None, help="분석/도너자막_실측.json — 한 줄에 색 둘인 큐 전수 대조")
    ap.add_argument("--단색", type=int, default=0, help="대조군(단색 큐) 몇 개를 함께 볼지")
    a = ap.parse_args()
    doc = Doc(load(a.도너 if os.path.isabs(a.도너) else os.path.join(ROOT, a.도너)))

    대상, 단색 = list(a.item or []), []
    if a.강조큐:
        d = json.load(open(os.path.join(ROOT, a.강조큐) if not os.path.isabs(a.강조큐) else a.강조큐, encoding="utf-8"))
        for c in d["큐"]:
            색 = c["실측"].get("색") or []
            if len(색) > 1 and 색[1]["비율"] >= 0.2:
                대상.append(c["item"])
            elif 색 and 색[0]["비율"] >= 0.98 and len(c["런"]) > 1:
                단색.append(c["item"])
        단색 = 단색[:a.단색]

    통계 = {}
    for it in 대상:
        b = 큐블롭(doc, it)
        런 = 런들(b)
        표, 다름 = 대조(b, 런)
        print(f'\n■ item {it} · 런 {len(런)}개 · 다른 슬롯 {다름 or "없음"}')
        for i, text, st in 런:
            print(f'    런{i} StyleTable@{st} 「{text[:24]}」')
        if len(대상) <= 3:
            인쇄(표, 다름)
        for k in 다름:
            통계.setdefault(k, []).append(it)
    for it in 단색:
        b = 큐블롭(doc, it)
        표, 다름 = 대조(b, 런들(b))
        print(f'\n○ (대조군·단색) item {it} · 다른 슬롯 {다름 or "없음"}')
        for k in 다름:
            통계.setdefault(f"단색_f{k}", []).append(it)
    if 통계:
        print("\n[요약] 런끼리 달랐던 슬롯")
        for k, v in sorted(통계.items(), key=lambda x: -len(x[1])):
            print(f"  f{k}: {len(v)}개 큐 — {v[:8]}")


if __name__ == "__main__":
    main()
