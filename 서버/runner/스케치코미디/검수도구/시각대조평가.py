# 구간 시각 대조 재실측 — 옛 agy 원본 전사를 새 관문(agy_asr._대조)에 넣어 «잡히는가·바로잡히는가» 를 참 시작과 숫자로 잰다.
#
#   python 검수도구/시각대조평가.py 점심이네53 점심이네45 [점심이네3@옛전사.vtt ...] [--본전사=슬러그=경로.vtt] [--창만]
#
# 본 전사: 기본 work/<편>.ko.vtt.맞춤전 (편시작이 남긴 맞춤 전 agy 통째 전사 그대로 — 끝 확인 붙임 포함). --본전사 로 옛 판(예: 점심이네3 첫 전사)을.
# 창 전사: agy 로 40초 창을 묻는다(★agy 호출 — 구독). 답은 ~/.cache/시각대조/<편>/ 에 저장해 다시 돌리면 다시 안 묻는다(work 는 안 건드린다).
# 정답: 검수도구/맞춤평가.참시각 — 납품 편 완성본 Speechmatics 낱말을 keep 조각으로 원본 시각에 되돌린 참 시작(조각 안 줄만).
# 내는 것: 편마다 — 대조 판정·대조율·닻·틀린 닻 · 참 대조(중앙·최대·2초 넘은 줄) 대조 전/후 · 창 전사 자체의 참 대조(창 시각 자가 믿을 만한가).
# 2026-09-29 밤 점심이네 64편 배치(3·10·53 등 통째 전사 시각 틀림을 편시작이 못 잡음)로 만들었다.
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
ROOT = os.path.expanduser("~/Desktop/스케치코미디")
os.environ.setdefault("S2_CONFIG", os.path.join(ROOT, "config.json"))
import 맞춤평가 as M  # noqa: E402
from s2pipe import agy_asr as A, 자막띠시각 as Z  # noqa: E402

CACHE = os.path.expanduser("~/.cache/시각대조")


def 오차(L, 참):
    e = np.array([L[i][0] - v for i, v in 참.items()]) if 참 else np.zeros(0)
    if not len(e):
        return {"n": 0}
    a = np.abs(e)
    return {"n": len(a), "중앙": round(float(np.median(a)), 2), "최대": round(float(a.max()), 2), "2초넘음": int((a > 2).sum())}


def 줄(L):
    return [{"t": t, "e": e, "text": x} for t, e, x in L]


def 평가(slug, 본경로=None, 창만=False, log=print):
    proj = json.load(open(os.path.join(ROOT, "projects", f"{slug}.json"), encoding="utf-8"))
    sid = proj["source"]["id"]
    src = os.path.join(ROOT, "work", f"{sid}.mp4")
    본경로 = 본경로 or os.path.join(ROOT, "work", f"{sid}.ko.vtt.맞춤전")
    _, L0 = Z.읽기(본경로)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                               capture_output=True, text=True).stdout)
    work = tempfile.mkdtemp(prefix="시각대조평가_")
    whole = os.path.join(work, "원본_전체_360p.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-ac", "1", whole], check=True)
    vocab = []
    try:
        from s2pipe.asr import load_vocab
        vocab = load_vocab(sid, channel=json.load(open(os.path.join(ROOT, "work", f"{sid}.info.json"))).get("channel"))
    except Exception:  # noqa: BLE001
        pass
    창목록 = A._창들(dur)
    창답 = A._창전사(whole, dur, vocab, A.MODEL, log, "스케치코미디/시각대조평가", work,
                  캐시=os.path.join(CACHE, sid), 창목록=창목록)
    C = A._창이음(창답)
    # 창 자체의 참 대조
    창참 = M.참시각(proj, [(c["t"], c["e"], c["text"]) for c in C])
    창오차 = 오차([(c["t"], c["e"], c["text"]) for c in C], 창참)
    r = {"편": slug, "원본": round(dur, 1), "창": len(창목록), "창오차": 창오차}
    if 창만:
        return r
    참0 = M.참시각(proj, L0)
    def 확인(a0, a1):                                   # 두 창 확인 창(★agy — 캐시)
        return A._구간전사(whole, a0, a1, dur, vocab, A.MODEL, log, "스케치코미디/시각대조평가#두창확인", work,
                        캐시=os.path.join(CACHE, sid))
    새, 록 = A._대조(줄(L0), C, dur, 창목록, 확인=확인)
    r["두창확인"] = 록.get("두창확인")
    r["옮긴줄"] = 록.get("옮긴줄")
    L1 = [(x["t"], x["e"], x["text"]) for x in 새]
    참1 = M.참시각(proj, L1)
    r.update(판정=록["판정"], 대조율=록.get("대조율"), 닻=록.get("닻"), 틀린닻=록.get("틀린닻"), 어긋남최대=록.get("어긋남최대"),
             전=오차(L0, 참0), 후=오차(L1, 참1),
             틀린창=[(w["창"][0], w["어긋남중앙"]) for w in 록.get("창별", []) if w.get("닻") and abs(w["어긋남중앙"]) > A.대조틀림])
    # 자막띠시각 맞춤(운영 실행()과 같은 순서 — ①②③ 관문 · ④⑤ 꼬리 · ⑥ 대조관문). 카드는 원본 옆 캐시(<원본>.카드2.json)를 읽기만.
    if 록["판정"] != "다시":
        cards, 정보 = Z.카드들(src, 정보=True)
        폭 = 정보.get("폭")
        if len(cards) >= max(8, len(L1) // 3):
            a, _b, _전, _후, 새줄 = Z.맞춤(L1, cards, 폭=폭)
            ok, 까닭, _q0, _q1 = Z.관문(L1, 새줄, cards, 폭, 배율=a)
            조치 = "거부"
            if ok:
                새줄, 꼬 = Z.꼬리관문(L1, 새줄, cards, 끝확인="닿음", 끝재기=lambda: Z._아웃트로(src))
                ok = 꼬["조치"] not in ("거부", "멈춤")
            if ok:
                대맞 = 오차(새줄, M.참시각(proj, 새줄))
                새줄, 대 = Z.대조관문(L1, 새줄, Z.기본값["대조허용"], Z.기본값["대조비율"])
                ok = 대["조치"] != "거부"
                조치 = f"채택·대조관문 {대['조치']}(되돌린 줄 {대['되돌린줄']})"
                r["맞춤_대조관문전"] = 대맞
            L2 = 새줄 if ok else L1
            r.update(맞춤=조치 if ok else f"거부({조치})", 배율=round(a, 3), 최종=오차(L2, M.참시각(proj, L2)))
    return r


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    본 = {}
    for a in sys.argv[1:]:
        if a.startswith("--본전사="):
            k, v = a[len("--본전사="):].split("=", 1)
            본[k] = v
    창만 = "--창만" in sys.argv
    rows = []
    for s in args:
        p = 본.get(s)
        if "@" in s:                                     # 점심이네3@옛전사.vtt — 같은 편의 옛 판 여러 개를 한 번에
            s, p = s.split("@", 1)
        try:
            r = 평가(s, p, 창만)
            if p:
                r["본전사"] = os.path.basename(p)
        except Exception as e:  # noqa: BLE001
            print(f"{s}: 실패 — {e}")
            continue
        rows.append(r)
        print(json.dumps(r, ensure_ascii=False))
    out = os.path.join(CACHE, "평가_" + "_".join(args)[:80] + ".json")
    os.makedirs(CACHE, exist_ok=True)
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", out)


if __name__ == "__main__":
    main()
