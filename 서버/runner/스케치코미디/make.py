# -*- coding: utf-8 -*-
"""한 편을 검사하고 굽는다.

    python make.py projects/<편>.json --check    검사만 (공짜)
    python make.py projects/<편>.json            굽기 (★TTS 요금)

★검사가 이 파이프라인의 핵심이다. sketch 는 「구조가 좋은가」를 사람 눈에 맡겼는데,
  여기서는 **5-Phase 가 기계로 검증된다** — 훅이 약한가, Climax 가 너무 빠른가,
  사람들이 웃은 자리를 빠뜨렸는가. 전부 굽기 전에 잡힌다.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PHASES = {p["no"]: p for p in CFG["edit"]["phases"]}


def _g(path, default):
    """생성 config 의 _정답지(판정 대역)에서 값을 꺼낸다 — 없으면 sketch2 시절 기본값.
    판정의 정본은 서버(sk_check)지만, 이 이중 빗장의 상수도 원천은 정답지 한 곳이다."""
    cur = CFG.get("_정답지", {})
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def check(proj, path):
    """반려 사유와 주의를 낸다. rc 0 이면 통과."""
    e, n, tb = CFG["edit"], CFG["narration"], CFG["layout"]["title"]
    bad, warn = [], []

    segs = [s for s in proj.get("segments", []) if s.get("keep", True)]
    if not segs:
        return ["구간이 하나도 없다"], []

    # ★sketch 대본을 잘못 넣는 것을 먼저 잡는다. 소재가 같아 헷갈리기 쉽다.
    # ★★껍데기(제목 2줄·댓글 층)를 sketch 에서 가져온 뒤로 **겉모습이 거의 같아졌다.**
    #   제목 형식으로도, 댓글 유무로도 못 가른다 — 둘 다 한 번씩 오인해서 자기 대본을
    #   막았다. **남은 확실한 표식은 `phase` 하나뿐이다**(5-Phase 는 sketch2 에만 있다).
    if not any("phase" in s for s in segs):
        return (["★이건 sketch 대본이다 — sketch2 는 다른 채널이다."
                 "\n     조각에 `phase` 가 없으면 저쪽 형식이다(5-Phase 는 여기에만 있다)."
                 "\n     sketch2 는 `python -m s2pipe.plan <URL>` 로 새로 계획한다."], [])
    total = sum(s["t1"] - s["t0"] for s in segs)
    lo, hi = e["target_sec"]

    # ── 길이
    if total > e["max_sec"]:
        bad.append(f"완성 길이 {total:.0f}초 — 상한 {e['max_sec']}초를 넘는다")
    elif not (lo <= total <= hi):
        warn.append(f"완성 길이 {total:.0f}초 — 목표 {lo}~{hi}초 밖이다")

    # ── ★5-Phase 구조. 이 파이프라인이 sketch 와 갈리는 지점이다
    used = [s.get("phase", 0) for s in segs]
    missing = [p for p in (1, 2, 3, 4, 5) if p not in used]
    if missing:
        names = ", ".join(f"{p} {PHASES[p]['name']}" for p in missing)
        bad.append(f"Phase 가 빠졌다 — {names}. 기승전결이 서지 않는다")

    if used != sorted(used):
        bad.append(f"Phase 가 순서대로 배열되지 않았다 — {used}")

    # Hook — 첫 조각이 약하면 3초 안에 스크롤을 못 멈춘다
    p1 = PHASES[1]
    if segs[0].get("phase") != 1:
        bad.append(f"첫 조각이 Phase 1(Hook)이 아니다 — P{segs[0].get('phase')}")
    elif segs[0].get("punch", 0) < p1["min_punch"]:
        bad.append(f"★훅이 약하다 — 첫 조각 punch {segs[0].get('punch')}"
                   f" (Hook 은 {p1['min_punch']} 이상이어야 한다)."
                   f" 상황 설명으로 열지 말고 센 대사를 앞으로 끌어와라")

    # ★★조각끼리 겹치면 **같은 장면이 두 번 나온다.** 되감기처럼 보여 눈에 띈다.
    #   밀도가 100% 를 넘으면 그 신호다 — 겹친 만큼 합이 범위보다 커지기 때문이다.
    order = sorted(segs, key=lambda s: s["t0"])
    for a, b in zip(order, order[1:]):
        ov = a["t1"] - b["t0"]
        if ov > _g("구조.G-조각겹침.겹침_max_sec", 0.05):
            bad.append(f"★조각이 {ov:.1f}초 겹친다 — 원본 {b['t0']:.1f}~{a['t1']:.1f} 이"
                       f" 두 번 나온다. 한쪽 끝을 물러라")

    # ★★★**밀도가 완성도를 가른다.** 완성 길이 ÷ 원본에서 펼친 범위.
    #   넓게 퍼뜨리면 대목 사이 맥락이 끊겨 이야기가 안 이어진다 — 같은 소재로
    #   견줘 46% 인 편이 18% 인 편을 이겼다(구조 딱지는 18% 쪽이 더 정확했는데도).
    lo_d, hi_d = e.get("density", [0.40, 0.75])
    span = max(s["t1"] for s in segs) - min(s["t0"] for s in segs)
    dens = total / span if span > 0 else 1.0
    if dens < lo_d:
        bad.append(f"★밀도 {dens*100:.0f}% — 원본 {span:.0f}초에 걸쳐 {total:.0f}초를"
                   f" 뽑았다. {lo_d*100:.0f}% 이상이어야 한다."
                   f" **넓게 퍼뜨리면 맥락이 끊겨 이야기가 안 이어진다** —"
                   f" 좋은 대목이 몰린 곳으로 범위를 좁혀라")
    elif dens > hi_d:
        warn.append(f"밀도 {dens*100:.0f}% — 한 구간을 통으로 쓴 것에 가깝다."
                    f" 원본의 늘어짐이 그대로 남는다")

    # ★한 Phase 가 편을 통째로 먹는 것만 막는다.
    # ★★**지침서의 시간표(0-3·3-10·10-30·30-45·45-50)는 50초 편의 「예시」이지
    #   강제 비율이 아니다.** 처음에 2.2배로 걸었더니 **완성도가 가장 좋다고 판정된
    #   편이 반려됐다**(Hook 16%·Context 39% — 지침서 몫은 6%·14%). 좋은 편일수록
    #   앞부분이 두툼했다. 그래서 「명백히 비대한 것」만 잡도록 3.5배로 풀었다 —
    #   실제로 막아야 했던 것은 Punchline 이 49% 를 먹은 경우였다.
    span = PHASES[5]["sec"][1] or 50
    for no, p in PHASES.items():
        got = sum(s["t1"] - s["t0"] for s in segs if s.get("phase") == no)
        if not got:
            continue
        want = (p["sec"][1] - p["sec"][0]) / span
        if got / total > want * _g("구조.G-Phase몫.배수_max", 3.5):
            bad.append(f"★P{no} {p['name']} 가 {got:.0f}초({got/total*100:.0f}%)를"
                       f" 차지한다 — 한 칸이 편을 통째로 먹었다."
                       f" 나머지 Phase 가 밀려난다. 짧게 자르거나 쪼개라")

    # Climax 위치 — 앞에 오면 뒤가 무너진다
    at, climax_at = 0.0, None
    for s in segs:
        if s.get("phase") == 4 and climax_at is None:
            climax_at = at
        at += s["t1"] - s["t0"]
    if climax_at is not None and total and climax_at / total < _g("구조.G-Climax위치.min_pos", 0.6):
        bad.append(f"★Climax 가 너무 빠르다 — {climax_at:.0f}초"
                   f"({climax_at/total*100:.0f}% 지점). 전체의 60% 를 지나서 와야 한다")

    if segs[-1].get("phase") != 5:
        bad.append(f"마지막 조각이 Phase 5(Punchline)가 아니다 — P{segs[-1].get('phase')}")
    elif segs[-1].get("punch", 0) < PHASES[5]["min_punch"]:
        warn.append(f"마지막 punch {segs[-1].get('punch')} — 최고 웃음 포인트로 끝나야 한다")

    for s in segs:
        ph = PHASES.get(s.get("phase"))
        if ph and s.get("punch", 0) < ph["min_punch"]:
            warn.append(f"P{s['phase']} {ph['name']} 조각의 punch {s['punch']}"
                        f" — 이 자리는 {ph['min_punch']} 이상이 어울린다")

    # ── ★나레이션 패딩 법칙. 읽을 시간보다 화면이 짧으면 다음 대사가 겹친다
    for i, s in enumerate(segs):
        nr = (s.get("narration") or "").strip()
        if not nr:
            continue
        # ★속도는 목소리마다 다르다 — config 에 실측값을 넣어 둔다(narration.sec_per_char).
        #   어림값을 쓰면 「나레이션이 화면보다 긴가」 판정이 통째로 어긋난다.
        need = len(nr) * n.get("sec_per_char", 0.15)
        if need > n["max_sec"]:
            bad.append(f"조각 {i} 나레이션이 {need:.1f}초짜리다 —"
                       f" {n['max_sec']:.0f}초 이내로 줄여라: {nr[:30]}")
        span = s["t1"] - s["t0"]
        if span < need:
            bad.append(f"★조각 {i} 패딩 부족 — 나레이션은 {need:.1f}초인데"
                       f" 화면은 {span:.1f}초다. 다음 대사가 겹쳐 튀어나온다")
        elif span < need + _g("나레이션.G-나레이션.패딩_여유_soft_sec", 0.5):
            warn.append(f"조각 {i} 패딩이 빠듯하다 (나레 {need:.1f}초 / 화면 {span:.1f}초)")
    nrs = [s for s in segs if (s.get("narration") or "").strip()]
    if not nrs:
        warn.append("나레이션이 하나도 없다 — 이 채널의 핵심 장치다")
    elif len(nrs) > _g("나레이션.G-나레이션.개수_권장", [1, 2])[1] + 1:
        warn.append(f"나레이션 {len(nrs)}개 — 1~2개면 충분하다. 많으면 설명이 된다")
    # ★★나레이션이 나오는 동안 원음이 죽는다. 그러니 **웃음이 터지는 자리에는
    #   얹으면 안 된다** — 훅과 펀치라인은 배우 말이 들려야 산다.
    for s in nrs:
        ph = s.get("phase")
        if ph in (1, 5):
            bad.append(f"★P{ph} {PHASES[ph]['name']} 에 나레이션이 있다 —"
                       f" 그 구간은 원음이 죽는다. **훅과 펀치라인은 배우 말이"
                       f" 들려야 한다**: {s['narration'][:24]}")
        elif s.get("punch", 0) >= 9:
            warn.append(f"punch {s['punch']} 조각에 나레이션이 있다 —"
                        f" 웃음이 터지는 대사를 덮는 것은 아닌지 본다")

    # ── 제목·해시태그
    # ★제목은 **껍데기가 정한 2줄**이다(sketch 템플릿). 후보는 그중 하나를 고르는
    #   것이므로 화면에 박히는 `title` 만 반려하고 나머지는 주의로 둔다.
    title = proj.get("title") or []
    if isinstance(title, str):
        title = [title]
    titles = proj.get("title_candidates") or ([title] if title else [])
    if not title:
        bad.append("제목이 없다")
    else:
        if len(title) != tb["lines"]:
            bad.append(f"제목이 {len(title)}줄 — 이 채널은 항상 {tb['lines']}줄이다:"
                       f" {' / '.join(title)}")
        for ln in title:
            if len(ln) > tb["max_chars"]:
                bad.append(f"제목 한 줄이 {len(ln)}자 — 상한 {tb['max_chars']}자다: {ln}")
        end = CFG["title_formula"]["end_mark"]
        if title and not title[-1].endswith(tuple(end)):
            bad.append(f"★제목 끝이 ? ! ... 이 아니다 — 호기심이 안 남는다:"
                       f" {title[-1]}")
    over = [t for t in titles
            if any(len(ln) > tb["max_chars"] for ln in (t if isinstance(t, list) else [t]))]
    if over:
        warn.append(f"후보 {len(over)}개가 한 줄 {tb['max_chars']}자를 넘는다 — 고를 때 뺀다")
    want = CFG["output"]["titles"]
    if len(titles) < want:
        warn.append(f"제목 후보 {len(titles)}개 — {want}개를 뽑는다")
    if not (proj.get("hashtag") or "").strip():
        warn.append("서브 해시태그가 없다")

    if len(proj.get("hooks") or []) < CFG["output"]["hook_lines"]:
        warn.append(f"후킹 대사 {len(proj.get('hooks') or [])}개 —"
                    f" {CFG['output']['hook_lines']}개를 뽑는다")

    # ── 자막
    subs = sorted(proj.get("subs", []), key=lambda x: x["t"])
    gaps = [(subs[i - 1]["t"], subs[i]["t"]) for i in range(1, len(subs))
            if subs[i]["t"] - subs[i - 1]["t"] >= _g("자막.G-자막공백.빈구간_warn_sec", 3.0)]
    if gaps:
        warn.append(f"자막이 3초 이상 비는 곳 {len(gaps)}군데"
                    f" (예: {gaps[0][0]:.0f}~{gaps[0][1]:.0f}초)")
    mx = CFG["layout"]["subtitle"]["max_chars"]
    longs = [s for s in subs if len(s.get("text", "")) > mx]
    if longs:
        warn.append(f"자막 {len(longs)}줄이 {mx}자를 넘는다")

    # ── 원본·fps
    src = proj.get("source", {})
    if not src.get("fps"):
        bad.append("원본 fps 가 없다 — 마진이 프레임 단위라 fps 없이는 못 굽는다")
    mp4 = os.path.join(HERE, CFG["paths"]["work"], f"{src.get('id')}.mp4")
    if not os.path.exists(mp4):
        bad.append(f"원본 영상이 없다: {mp4}")

    return bad, warn


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    path = args[0] if os.path.isabs(args[0]) else os.path.join(HERE, args[0])
    proj = json.load(open(path, encoding="utf-8"))

    bad, warn = check(proj, path)
    print(f"─ {os.path.basename(path)}")
    for w in warn:
        print(f"  주의  {w}")
    for b in bad:
        print(f"  반려  {b}")
    if bad:
        print(f"\n반려 {len(bad)}건 — 고쳐야 굽는다")
        return 1
    print("  통과" + (" (주의 있음)" if warn else ""))

    if "--check" in sys.argv:
        return 0

    from s2pipe import build
    return build.run_build(proj, path)


if __name__ == "__main__":
    sys.exit(main())
