#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구도모의.py <슬러그> [--가림빼기] [--굽기] [--작업 <폴더>] [--출력 <beats.json>] — 굽기(build.cut_and_join)의 «구도 계획만» 무료로 다시 돈다.

★2026-09-29 점심이네 얼굴 추적 수리 — 고친 framing 이 실제 굽기와 «같은 입력»(조각 경계 붙이기·프레임 창·박힌 자막 한계·
  scene_cuts·앞 조각 구도 잇기)으로 어떤 crop 을 내는지 재야 했다. 구도재현.py 는 조각 하나를 prev·틀·자막 한계 없이 돌려
  실제와 달랐다. 여기서는 cut_and_join 을 그대로 부르되 ffmpeg 굽기(_틀굽기·concat)·튐 관문·박힌 자막 관문만 비워
  beats.json(비트·한 장 구도 crop)만 남긴다. 유료 API·영상 굽기 없음. projects/*.json·납품 산출물은 건드리지 않는다
  (조각은 사본으로 돈다 · 캐시 프레임은 --작업 폴더에만).

  --가림빼기  조각의 «가림»(사람이 프레임을 보고 넣은 구도 우회 사각형)을 빼고 돈다 — 가림 없이 구도가 맞는지 재는 용도.
  --굽기      비우지 않고 실제로 cut.mp4 를 굽는다(튐·박힌 자막·얼굴·프레임 수 관문이 모두 산다) — --작업 폴더에만 쓴다.
  배경판 관문(비침관문.판재기 — 말풍선·알림 상자·삽입 그림 테두리가 crop 에 드는가)은 굽지 않아도 실제와 같이 돈다(2026-10-03).
"""
import copy
import json
import os
import sys
import tempfile

RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RUN)
os.environ.setdefault("S2_CONFIG", os.path.expanduser("~/Desktop/스케치코미디/config_누룽지독.json"))


def 모의(slug, 가림빼기=False, work=None, 출력=None, 조용히=True, 조각=None, 굽기=False):
    """조각 = 조각 목록을 바꿔 돌릴 때(시험용 — 예: 사람이 잘라 낸 구간을 되살려 재기).
    굽기=True 면 아무것도 비우지 않고 cut_and_join 을 그대로 돈다(관문 전부 산 채로 · cut.mp4 는 work 폴더에만)."""
    from s2pipe import build, 튐관문, 번인관문, 비침관문
    from s2pipe.cfg import CFG
    proj = json.load(open(os.path.join(CFG["paths"]["projects"], f"{slug}.json"), encoding="utf-8"))
    src = os.path.join(CFG["paths"]["work"], f"{proj['source']['id']}.mp4")
    segs = [copy.deepcopy(x) for x in (조각 if 조각 is not None else proj["segments"]) if x.get("keep", True)]
    if 가림빼기:
        for s in segs:
            s.pop("가림", None)
    호환 = bool(proj.get("asr_words") or proj.get("subs_before_sync")) and not proj.get("asr_격자")
    work = work or tempfile.mkdtemp(prefix=f"_구도모의_{slug}_")
    os.makedirs(work, exist_ok=True)
    if 굽기:
        assert os.path.realpath(work) != os.path.realpath(os.path.join(CFG["paths"]["work"], slug)), "납품 작업 폴더에 굽지 않는다"
        build.cut_and_join(src, segs, os.path.join(work, "cut.mp4"), work, proj["source"].get("fps") or 30.0, 호환=호환)
        log = json.load(open(os.path.join(work, "beats.json"), encoding="utf-8"))
        if 출력:
            json.dump(log, open(출력, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return log, src, segs
    원 = (build._틀굽기, build.run, build.probe_dur, 튐관문.재기, 번인관문.걸림, 비침관문.재기, 비침관문.판재기)
    from s2pipe import framing
    얼굴걸림 = []
    원얼굴관문 = getattr(framing, "얼굴관문", None)
    if 원얼굴관문:                           # 얼굴 관문은 멈추지 않고 모아 둔다(모의는 끝까지 돈다 — 걸림은 결과에 적는다)
        def _모으기(*a, **k):
            r = 원얼굴관문(*a, **k)
            얼굴걸림.extend(r)
            return []
        framing.얼굴관문 = _모으기
    build._틀굽기 = lambda src_, 틀, 영상, p, 겹=False: p
    _run = build.run
    build.run = lambda argv, capture=False: _run(argv, capture) if capture else None   # 재기(ffprobe)는 두고 굽기만 비운다
    build.probe_dur = lambda p: 0.0
    튐관문.재기 = lambda *a, **k: ([], "모의 — 굽지 않음")
    번인관문.걸림 = lambda *a, **k: []
    비침관문.재기 = lambda *a, **k: ([], "모의 — 굽지 않음")       # 구운 cut.mp4 가 없다(2026-10-02 완성본 비침 관문)
    # ★굽기 끝 판 관문도 비운다 — 아래에서 «멈추지 않고» 따로 돌려 결과에 적는다. 비우지 않으면 판이 걸린 편은 cut_and_join 이
    #   AssertionError 로 죽어 beats.json·비트 줄·얼굴 관문 줄이 하나도 안 나왔다(2026-10-03 루키치158 «grep 으로 넘기면 비트·관문 줄이
    #   안 보인다» — 실제로는 판 관문 걸림으로 모의가 중간에 죽은 것이었다. 터미널에선 긴 굽기 출력 끝 오류만 보여 «조용한» 것처럼 보였다).
    비침관문.판재기 = lambda *a, **k: ([], "모의 — 아래에서 따로 잼")
    _stdout = sys.stdout
    try:
        if 조용히:
            sys.stdout = open(os.devnull, "w")
        build.cut_and_join(src, segs, os.path.join(work, "cut.mp4"), work, proj["source"].get("fps") or 30.0, 호환=호환)
    finally:
        if 조용히:
            sys.stdout.close()
        sys.stdout = _stdout
        build._틀굽기, build.run, build.probe_dur, 튐관문.재기, 번인관문.걸림, 비침관문.재기, 비침관문.판재기 = 원
        if 원얼굴관문:
            framing.얼굴관문 = 원얼굴관문
    log = json.load(open(os.path.join(work, "beats.json"), encoding="utf-8"))
    log["_얼굴관문"] = 얼굴걸림
    # ★배경판 잘림 관문(2026-10-03 루키치163·265·161 — 말풍선·삽입 그림 테두리가 완성본 끝에 비쳤는데 모의가 걸림·비침을 비워 둬서
    #   굽기 전에 못 봤다). 이 관문은 원본 프레임과 beats.json 만 쓰므로 굽지 않고도 실제 굽기 끝과 같은 판정을 낸다.
    try:
        log["_판관문"], log["_판요약"] = 비침관문.판재기(src, log, segs, 출력=lambda m: None)
    except Exception as e:                          # noqa: BLE001 — 모의는 끝까지 돈다(인식기 없음 등은 결과에 적는다)
        log["_판관문"], log["_판요약"] = [], f"판 관문 못 돎 — {e}"
    if 출력:
        json.dump(log, open(출력, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return log, src, segs


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    slug = a[0]
    work = a[a.index("--작업") + 1] if "--작업" in a else None
    out = a[a.index("--출력") + 1] if "--출력" in a else None
    log, _, _ = 모의(slug, "--가림빼기" in a, work, out, 조용히=False, 굽기="--굽기" in a)
    for b in log["beats"]:
        w, h, x, y = b["crop"]
        print(f"조각{b['seg']:2d} {b['t0']:8.3f}~{b['t1']:8.3f} crop {w}x{h}@{x},{y}" + ("  컷" if b.get("at_cut") else ""))
    for f in log.get("frames", []):
        print(f"조각{f['seg']:2d} {f['t0']:8.3f}~{f['t1']:8.3f} {f['kind']} crop {f['crop']}")
    for x in log.get("_얼굴관문", []):
        print(f"★얼굴 관문 걸림 조각{x['조각']} {x.get('종류', '')} {x['t0']}~{x['t1']}초 crop {x['crop']} 얼굴 {x['얼굴'][:3]}")
    print(f"얼굴 관문 걸림 {len(log.get('_얼굴관문', []))}곳")
    from s2pipe import 비침관문 as _비
    for g in log.get("_판관문", []):
        print("★배경판 관문 걸림", _비.판글([g]))
    print(f"배경판 관문 — {log.get('_판요약', '')}", flush=True)
