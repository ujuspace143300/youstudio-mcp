# 조각을 **원본의 컷 경계에 맞춰** 나눈다.
#
#   python -m spipe.split projects/<slug>.json
#
# 규칙: 원본 4~6초 쓰고 → 중간 컷 하나를 버리고 → 다시 4~6초 …
#
# ★몇 초씩 버릴지 정하지 않는다. **컷이 바뀌는 자리가 경계**이고, 버리는 양은
#   그 컷의 길이가 정한다. 컷 중간을 자르면 화면이 튄다 — 실제로 그렇게 만들었다가
#   "튀는 구간이 많아 어색하다"는 소리를 들었다.
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))


def scene_cuts(src, thr=0.28):
    """원본에서 화면이 바뀌는 시점. 한 번 재면 캐시한다."""
    cache = os.path.splitext(src)[0] + ".cuts.json"
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src,
                        "-filter_complex", f"select='gt(scene,{thr})',metadata=print:file=-",
                        "-an", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ts = sorted(set(round(float(m), 2)
                    for m in re.findall(r"pts_time:([\d.]+)", (p.stdout or "") + (p.stderr or ""))))
    json.dump(ts, open(cache, "w", encoding="utf-8"))
    return ts


def to_origin(subs, segs):
    """숏폼 시각 자막을 원본 시각으로 되돌린다."""
    marks, out, t = [], [], 0.0
    for s in segs:
        marks.append((t, t + (s["t1"] - s["t0"]), s["t0"]))
        t += s["t1"] - s["t0"]
    for x in subs:
        for a, b, o in marks:
            if a <= x["t"] < b:
                out.append({"t": o + (x["t"] - a), "text": x["text"]})
                break
    return out


def to_short(subs_o, segs):
    """원본 시각 자막을 새 조각 배열 기준으로 옮긴다."""
    out, t = [], 0.0
    for s in segs:
        for x in subs_o:
            if s["t0"] <= x["t"] < s["t1"]:
                out.append({"t": round(t + (x["t"] - s["t0"]), 1), "text": x["text"]})
        t += s["t1"] - s["t0"]
    return sorted(out, key=lambda x: x["t"])


def carve(seg, cuts, lo, hi, gmin=2.0):
    """한 덩어리를 컷 경계에 맞춰 「쓰고-버리고」로 나눈다.

    - 조각의 시작과 끝은 **반드시 컷 경계**다. 그래야 화면이 안 튄다
    - 4~6초를 채우면 끊고, 다음 컷 하나를 버린 뒤 다시 시작한다
    - 컷이 성긴 구간(한 컷이 6초 넘음)은 쪼개지 않고 그대로 쓴다
    """
    inside = [c for c in cuts if seg["t0"] < c < seg["t1"]]
    marks = [seg["t0"]] + inside + [seg["t1"]]
    if len(marks) < 4:                       # 컷이 거의 없으면 손대지 않는다
        return [seg], 0

    out, dropped = [], 0
    i, start = 0, marks[0]
    while i < len(marks) - 1:
        # 4초를 넘길 때까지 컷을 이어 붙이고, 6초를 넘기기 전에 끊는다
        j = i + 1
        while j < len(marks) - 1 and marks[j] - start < lo:
            j += 1
        while j < len(marks) - 1 and marks[j] - start > hi and marks[j - 1] - start >= lo:
            j -= 1
        end = marks[j]
        if end - start >= lo * 0.8:
            out.append({**seg, "t0": round(start, 2), "t1": round(end, 2)})
        # ★중간 컷을 버린다. 몇 초일지는 그 컷의 길이가 정한다.
        #   ★단 컷이 짧으면 **gmin 이상 벌어질 때까지 여러 개를 버린다** —
        #   0.3초 버리고 이어 붙이면 자른 게 아니라 그냥 한 조각이다.
        if j + 1 < len(marks) - 1:
            k = j + 1
            while k < len(marks) - 1 and marks[k] - end < gmin:
                k += 1
            dropped += k - j
            start = marks[k]
            i = k
        else:
            break
    return (out or [seg]), dropped


def main():
    if len(sys.argv) < 2:
        print("python -m spipe.split projects/<slug>.json")
        return 1
    pj = sys.argv[1]
    if not os.path.isabs(pj):
        pj = os.path.join(HERE, pj)
    proj = json.load(open(pj, encoding="utf-8"))
    e = CFG["edit"]
    lo, hi = e.get("piece_sec", [4, 6])

    segs = proj["segments"]
    subs_o = to_origin(proj.get("subs", []), segs) if proj.get("subs") else []
    src = os.path.join(HERE, CFG["paths"]["work"], f"{proj['source']['id']}.mp4")
    cuts = scene_cuts(src) if os.path.exists(src) else []
    print(f"원본 컷 전환 {len(cuts)}곳\n")

    gmin = e.get("cut_gap_min", 2.0)
    new, drop = [], 0
    for s in segs:
        got, d = carve(s, cuts, lo, hi, gmin)
        new += got
        drop += d

    # ★조각 사이가 좁으면 **뒤 조각의 시작을 다음 컷까지 민다.**
    #   버린 게 0.3초면 자른 게 아니라 그냥 한 조각이다. 조각 내부만 보는
    #   carve 로는 못 고치는 자리라 여기서 손본다.
    widened, joined = 0, 0
    fixed = [new[0]]
    for s in new[1:]:
        gap = s["t0"] - fixed[-1]["t1"]
        if gap >= gmin:
            fixed.append(s)
            continue
        # 다음 컷까지 밀어 간격을 벌린다
        want = fixed[-1]["t1"] + gmin
        nc = next((c for c in cuts if c >= want and s["t1"] - c >= lo), None)
        if nc:
            fixed.append({**s, "t0": round(nc, 2)})
            widened += 1
        else:
            # 밀 자리가 없으면 합친다 — 붙은 건 어차피 한 조각이다
            fixed[-1] = {**fixed[-1], "t1": s["t1"]}
            joined += 1
    new = fixed
    if widened or joined:
        print(f"간격 손봄 — 시작을 민 조각 {widened}개 · 붙어서 합친 조각 {joined}개\n")

    total = sum(s["t1"] - s["t0"] for s in new)
    span = new[-1]["t1"] - new[0]["t0"]
    lens = sorted(s["t1"] - s["t0"] for s in new)
    proj["segments"] = new
    if subs_o:
        proj["subs"] = to_short(subs_o, new)
    proj["_est_sec"] = round(total, 1)
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"조각 {len(segs)} → {len(new)}개 (중간 컷 {drop}개 버림)\n")
    from . import timeline
    timeline.show(proj)
    print(f"\n저장: {pj}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
