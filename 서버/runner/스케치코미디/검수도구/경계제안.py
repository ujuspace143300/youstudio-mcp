#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경계제안.py <슬러그> [--쓰기] — plan 조각 경계(t0·t1)를 대사 밖 «가장 조용한 자리»로 옮기자고 제안한다.

  2026-09-26 싱글285·286 실측: plan 경계는 대사 한가운데를 자주 자른다(편마다 3~6곳). 사람이 원본 전사와
  말대역 소리 크기를 손으로 재서 옮겼고, 그래도 두 곳은 ④ 이음매 관문(완성본 Speechmatics)에 걸려 다시 구웠다.
  이 도구가 그 손일을 한다:
   · 경계가 원본 전사(agy) 한 줄 «안»에 있으면 — 끝(t1)은 그 줄 끝 뒤로, 시작(t0)은 그 줄 시작 앞으로 넓힌다
     (말을 자르느니 한 줄을 통째로 담는다).
   · 그다음 앞뒤 줄 사이 틈(±0.3초)에서 말대역(300~3500Hz) 소리가 가장 작은 20ms 자리로 맞춘다.
   · 원본에서 맞닿은 이음(앞 조각 t1 = 다음 조각 t0)은 자른 자리가 아니므로 건드리지 않는다.
  agy 시각은 ±0.5초쯤 틀린다 — 그래서 줄 시각은 «어디쯤»만 쓰고, 최종 자리는 소리로 정한다.
  최종 확인은 여전히 ④ 이음매 관문이 완성본 낱말로 한다.
"""
import json, os, re, subprocess, sys
import numpy as np

slug = sys.argv[1]
쓰기 = "--쓰기" in sys.argv
W = os.path.expanduser("~/Desktop/스케치코미디")
pj = f"{W}/projects/{slug}.json"
proj = json.load(open(pj, encoding="utf-8"))

# ★체인이 도는 중이면 고치지 않는다 (2026-09-26 — 도는 체인이 옛 내용을 덮어써 고친 값이 사라진 사건)
def _체인중인가(pj):
    import os as _o
    lk = pj + ".체인중"
    if _o.path.exists(lk):
        try:
            _o.kill(int(open(lk).read().strip()), 0)
            return True
        except (ValueError, OSError):
            return False
    return False
if _체인중인가(pj):
    sys.exit(f"★{os.path.basename(pj)} 체인이 도는 중이다 — 끝난 뒤 고친다(고쳐도 체인이 덮어쓴다)")
src = f"{W}/work/{proj['source']['id']}.mp4"
vtt = f"{W}/work/{proj['source']['id']}.ko.vtt"

줄 = [(int(a) * 3600 + int(b) * 60 + float(c), int(d) * 3600 + int(e) * 60 + float(f), x.strip())
      for a, b, c, d, e, f, x in re.findall(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)\n(.+)",
                                             open(vtt, encoding="utf-8").read())]
줄.sort()
r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                   capture_output=True, check=True)
x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
dur = len(x) / 16000
W20 = 320
f = np.fft.rfftfreq(W20, 1 / 16000)
sel = (f > 300) & (f < 3500)
han = np.hanning(W20)


def 소리(t):
    i = int(t * 16000)
    if i < 0 or i + W20 > len(x):
        return 99.0
    return float(20 * np.log10(np.abs(np.fft.rfft(x[i:i + W20] * han))[sel].sum() + 1e-9))


def 조용한곳(a, b):
    """a~b 사이 20ms 간격으로 소리가 가장 작은 자리."""
    a, b = max(0.0, a), min(dur - 0.05, b)
    if b <= a:
        return round(a, 2)
    ts = np.arange(a, b, 0.02)
    v = [소리(t) for t in ts]
    return round(float(ts[int(np.argmin(v))]), 2)


def 안의줄(t):
    return next((l for l in 줄 if l[0] + 0.05 < t < l[1] - 0.05), None)


def 맞춤(t, 끝인가):
    """경계 t 를 대사 밖 조용한 자리로. (새 값, 까닭)"""
    l = 안의줄(t)
    까닭 = ""
    if l:
        까닭 = f"「{l[2][:14]}」 {l[0]:.1f}~{l[1]:.1f} 한가운데"
        t = l[1] if 끝인가 else l[0]            # 끝은 줄 뒤로, 시작은 줄 앞으로 — 통째로 담는다
    앞 = max([l[1] for l in 줄 if l[1] <= t + 0.05] + [t - 0.6])
    뒤 = min([l[0] for l in 줄 if l[0] >= t - 0.05] + [t + 0.6])
    창a, 창b = (min(앞, t) - 0.3, max(뒤, t) + 0.3) if 끝인가 else (min(앞, t) - 0.3, max(뒤, t) + 0.3)
    if 끝인가:
        창a = max(창a, t - 0.3)                  # 끝을 줄 안쪽으로 되당기지 않는다
    else:
        창b = min(창b, t + 0.3)                  # 시작을 줄 안쪽으로 밀지 않는다
    return 조용한곳(창a, 창b), 까닭


segs = proj["segments"]
# 맞닿음은 «완성본 순서»로 잇닿은 두 조각이 원본에서도 붙어 있을 때만 — 원본에서 붙어 있어도 사이에 다른 조각이
# 끼면(훅 앞당김: 싱글286 훅 116.5~120.5 · 본문 120.5~) 완성본에선 이음매라 말이 잘린다(2026-09-26 시험에서 발견)
살린 = [i for i, s in enumerate(segs) if s.get("keep", True)]
맞닿음 = set()
for a, b in zip(살린, 살린[1:]):
    if abs(segs[b]["t0"] - segs[a]["t1"]) < 0.05:
        맞닿음 |= {(a, "t1"), (b, "t0")}

바뀜 = []
for i, s in enumerate(segs):
    for k in ("t0", "t1"):
        if (i, k) in 맞닿음:
            continue
        새, 까닭 = 맞춤(s[k], k == "t1")
        if abs(새 - s[k]) >= 0.05:
            바뀜.append((i, k, s[k], 새, 까닭 or "틈 안 더 조용한 자리"))
            if 쓰기:
                s[k] = 새

# ★넓히다 두 조각이 원본에서 겹치면 같은 대사가 두 번 나온다(훅 반복 — 2026-09-22 사장님 «훅 반복 금지»).
#   완성본에서 뒤에 나오는 조각의 시작을 앞 조각의 끝으로 민다(싱글286 «왜 부부끼리…» 가 훅·본문 양쪽에 들어갈 뻔).
새값 = {(i, k): 새 for i, k, _a, 새, _w in 바뀜}
def 값(i, k):
    return 새값.get((i, k), segs[i][k])
for a_i, a in enumerate(살린):
    for b in 살린[a_i + 1:]:
        a0, a1, b0, b1 = 값(a, "t0"), 값(a, "t1"), 값(b, "t0"), 값(b, "t1")
        if b0 < a1 <= b1 and a0 <= b0:                     # 뒤 조각 머리가 앞 조각 꼬리와 겹침
            바뀜.append((b, "t0", b0, a1, f"조각 {a} 과 겹침 — 같은 대사 두 번 방지"))
            새값[(b, "t0")] = a1
            if 쓰기:
                segs[b]["t0"] = a1
        elif a0 < b1 <= a1 and b0 <= a0:                   # 뒤 조각 꼬리가 앞 조각 머리와 겹침
            바뀜.append((b, "t1", b1, a0, f"조각 {a} 과 겹침 — 같은 대사 두 번 방지"))
            새값[(b, "t1")] = a0
            if 쓰기:
                segs[b]["t1"] = a0

합 = sum(값(i, "t1") - 값(i, "t0") for i in 살린)
print(f"{slug}: 경계 제안 {len(바뀜)}곳 · 합계 {합:.1f}초" + ("" if 쓰기 else " (재기만 — --쓰기 로 반영)"))
for i, k, a, b, why in 바뀜:
    print(f"  조각 {i} {k}: {a:.2f} → {b:.2f}  ({why})")
def 자막옮김(옛segs, 새segs, subs):
    """초안 자막을 새 경계 시간축으로 옮긴다 — 대사는 원본 시각을 따라가고(없어진 구간 줄은 버림),
    나레는 제 조각 머리에 붙는다(나레 소리는 굽기가 조각 머리에 놓는다 — 어긋나면 소리·자막이 따로 논다)."""
    def 누적(ss):
        out, at = [], 0.0
        for s_ in ss:
            if s_.get("keep", True):
                out.append((at, s_)); at += s_["t1"] - s_["t0"]
            else:
                out.append((None, s_))
        return out
    옛, 새 = 누적(옛segs), 누적(새segs)
    결과 = []
    for x_ in subs:
        for (oa, os_), (na, ns_) in zip(옛, 새):
            if oa is None or na is None:
                continue
            if oa <= x_["t"] < oa + (os_["t1"] - os_["t0"]):
                y = dict(x_)
                if x_.get("kind") == "narr":
                    y["t"] = round(na + (x_["t"] - oa), 2)
                else:
                    원 = os_["t0"] + (x_["t"] - oa)
                    if not (ns_["t0"] <= 원 < ns_["t1"]):
                        break                                  # 새 경계 밖으로 나간 줄 — 버린다(sync 가 다시 짠다)
                    y["t"] = round(na + (원 - ns_["t0"]), 2)
                결과.append(y)
                break
    return sorted(결과, key=lambda z: z["t"])


if 쓰기 and 바뀜:
    옛판 = json.load(open(pj, encoding="utf-8"))
    json.dump(옛판, open(pj + ".경계전", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    proj["subs"] = 자막옮김(옛판["segments"], segs, 옛판.get("subs", []))
    proj["_est_sec"] = round(합, 1)
    proj.setdefault("_경계제안", []).append([(i, k, a, b, why) for i, k, a, b, why in 바뀜])
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  반영 — 이전 판 {os.path.basename(pj)}.경계전")
