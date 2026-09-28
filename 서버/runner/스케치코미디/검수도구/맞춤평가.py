# 자막띠시각 맞춤 평가 — agy 원본 전사 줄 시작이 «실제 말 시작» 에서 얼마나 틀렸나를 잰다(돈 안 드는 자료만).
#
#   python 검수도구/맞춤평가.py [싱글249 싱글257 ...]      (없으면 맞춤전 파일이 있는 편 전부)
#   python 검수도구/맞춤평가.py --고르기                    (새 맞춤 벌점 값 고르기 — 짝수 편으로 고르고 홀수 편으로 확인)
#
# 정답: 납품한 편 projects/<편>.json 의 완성본 Speechmatics 낱말(asr_words, 완성본 시각)을 keep 조각
#   (segments — 완성본은 keep 조각을 차례로 이어 붙인 것)으로 원본 시각에 되돌린다. agy 줄 글자를
#   그 낱말 글자열에서 찾아(편집 거리 25% 이하 · 두 번째 후보와 뚜렷이 갈릴 때만) 첫 글자 시각 = 참 시작.
#   조각 안에 통째로 들어간 줄만 정답이 있다. 이웃 정답과 동떨어진(어긋남이 이웃 중앙값에서 1.5초 넘게 벗어난)
#   정답은 잘못 찾은 것으로 보고 버린다.
# 비교: 맞춤 전(work/<id>.ko.vtt.맞춤전 그대로) · 옛 맞춤(검수도구/맞춤_옛판.py — 2026-09-27 운영판 전역 DP, 옛 카드 80~90% 띠)
#   · 새 맞춤(s2pipe.자막띠시각.맞춤 — v2 카드·글자 폭) · 관문 뒤(자막띠시각.관문 이 거부하면 맞춤 전).
# 카드: 원본 옆 캐시(옛 <원본>.카드.json · 새 <원본>.카드2.json)가 맞으면 그것을, 없으면 ~/.cache/맞춤평가/ 에 따로 재 둔다
#   (work 폴더에는 쓰지 않는다).
# 2026-09-27 싱글249 «너희들 다 비키니 입을 거야?» 카드 182.3초가 vtt 에 192.2초로 나간 일로 만들었다.
import json
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.expanduser("~/Desktop/스케치코미디")
CACHE = os.path.expanduser("~/.cache/맞춤평가")
os.environ.setdefault("S2_CONFIG", os.path.join(ROOT, "config.json"))   # 꼬리 관문의 아웃트로 검출(build.엔드카드시작)이 설정을 읽는다
from s2pipe import 자막띠시각 as Z  # noqa: E402


# ── 카드 ────────────────────────────────────────────────────────────────
def 카드(src):
    src = os.path.abspath(src)
    st = os.stat(src)
    key = f"{st.st_size}:{int(st.st_mtime)}:{Z.FPS}:{Z.W}x{Z.H}"
    for p in (src + ".카드.json", os.path.join(CACHE, os.path.basename(src) + ".카드.json")):
        try:
            c = json.load(open(p, encoding="utf-8"))
            if c.get("key") in (key, key + ":0.8-0.9"):          # 운영 캐시 키에는 띠 꼬리가 붙어 있다
                return [tuple(x) for x in c["cards"]]
        except (OSError, ValueError, KeyError):
            pass
    cards = 카드재기_띠만(src)
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"key": key, "cards": cards},
              open(os.path.join(CACHE, os.path.basename(src) + ".카드.json"), "w", encoding="utf-8"))
    return cards


def 새카드(src):
    """v2 카드와 글자 폭 — 원본 옆 <원본>.카드2.json 이 맞으면 그것, 아니면 ~/.cache/맞춤평가/ 에 재 둔다."""
    src = os.path.abspath(src)
    st = os.stat(src)
    key = f"{Z.판}:{st.st_size}:{int(st.st_mtime)}:{Z.FPS}:{Z.W}x{Z.H}"
    mine = os.path.join(CACHE, os.path.basename(src) + ".카드2.json")
    for p in (Z.캐시경로(src), mine):
        try:
            c = json.load(open(p, encoding="utf-8"))
            if c.get("key") == key:
                return [tuple(x) for x in c["cards"]], c.get("폭")
        except (OSError, ValueError, KeyError):
            pass
    cards, 띠, 폭 = Z._카드재기(src)
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"key": key, "cards": cards, "띠": 띠, "폭": 폭}, open(mine, "w", encoding="utf-8"))
    return cards, 폭


def 카드재기_띠만(src):
    """옛 카드(80~90% 고정 띠 — 2026-09-27 운영판 Z._카드재기 와 같은 계산). 띠만 잘라 받아 메모리를 적게 쓴다."""
    W, H, FPS = Z.W, Z.H, Z.FPS
    y0, y1 = int(H * 0.80), int(H * 0.90)
    x0, x1 = int(W * 0.2), int(W * 0.8)
    bw, bh = x1 - x0, y1 - y0
    r = subprocess.run(["ffmpeg", "-v", "error", "-threads", "2", "-i", src, "-vf",
                        f"fps={FPS},scale={W}:{H},format=gray,crop={bw}:{bh}:{x0}:{y0}",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    fr = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(fr) // (bw * bh)
    띠 = fr[:n * bw * bh].reshape(n, bh, bw)
    밝 = 띠 > 190
    어 = 띠 < 90
    곁 = np.zeros_like(어)
    for k in (1, 2, 3):
        곁[:, :, k:] |= 어[:, :, :-k]
        곁[:, :, :-k] |= 어[:, :, k:]
    글자 = 밝 & 곁
    수 = 글자.reshape(n, -1).sum(axis=1)
    있음 = 수 >= 12
    cards, s = [], None
    for i in range(n):
        if 있음[i] and s is None:
            s = i
        elif s is not None:
            바뀜 = False
            if 있음[i]:
                a, b = 글자[i - 1], 글자[i]
                합 = (a | b).sum()
                바뀜 = 합 > 0 and (a & b).sum() / 합 < 0.5
            if not 있음[i] or 바뀜:
                if i - s >= 3:
                    cards.append((round(s / FPS, 2), round(i / FPS, 2)))
                s = i if 있음[i] else None
    if s is not None and n - s >= 3:
        cards.append((round(s / FPS, 2), round(n / FPS, 2)))
    return cards


# ── 정답(참 시작) ────────────────────────────────────────────────────────
def 정규(x):
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", x)


def 글자열(proj):
    """완성본 낱말 → (글자열, 글자마다 원본 시각, 글자마다 조각 번호)."""
    segs = [s for s in proj["segments"] if s.get("keep", True)]
    경계, off = [], 0.0
    for s in segs:
        경계.append((off, off + s["t1"] - s["t0"], s["t0"]))
        off += s["t1"] - s["t0"]
    S, T, K = [], [], []
    for w in proj.get("asr_words") or []:
        if w.get("type", "word") != "word":
            continue
        g = 정규(w["w"])
        if not g:
            continue
        k = next((i for i, (a, b, _) in enumerate(경계) if a - 0.02 <= w["t"] < b), None)
        if k is None:
            continue
        a, b, t0 = 경계[k]
        for n, ch in enumerate(g):
            tt = w["t"] + (w["e"] - w["t"]) * n / len(g)
            S.append(ch)
            T.append(t0 + tt - a)
            K.append(k)
    return "".join(S), np.array(T), np.array(K)


def _반정렬(q, S, 앞고정=False):
    """q 전체를 S 의 어느 조각에 붙였을 때 편집 거리 — 끝 자리마다(D[m][e]). 앞고정이면 S 맨 앞에서 시작."""
    n = len(S)
    Sa = np.frombuffer(S.encode("utf-32-le"), dtype=np.uint32)
    D = np.arange(n + 1, dtype=float) if 앞고정 else np.zeros(n + 1)
    for i, ch in enumerate(q, 1):
        같 = (Sa != ord(ch)).astype(float)
        E = np.empty(n + 1)
        E[0] = i
        E[1:] = np.minimum(D[:-1] + 같, D[1:] + 1)
        idx = np.arange(n + 1)
        E = idx + np.minimum.accumulate(E - idx)
        D = E
    return D


def _시작(q, S, e):
    """S[:e] 끝에 q 를 붙였을 때 가장 좋은 시작 자리."""
    r = _반정렬(q[::-1], S[:e][::-1], 앞고정=True)
    k = int(np.argmin(r))
    return e - k


def 참시각(proj, L):
    """{줄 번호: 참 시작(원본 초)}"""
    S, T, K = 글자열(proj)
    if len(S) < 20:
        return {}
    참 = {}
    for i, (t0, t1, x) in enumerate(L):
        q = 정규(x)
        m = len(q)
        if m < 4:
            continue
        D = _반정렬(q, S)
        e = int(np.argmin(D))
        best = D[e]
        if best > 0.25 * m:
            continue
        D2 = D.copy()
        D2[max(0, e - m):e + m + 1] = 1e9
        if D2.min() < best + 2:
            continue
        st = _시작(q, S, e)
        if st >= len(S) or K[st] != K[e - 1]:
            continue
        참[i] = float(T[st])
    # 이웃과 동떨어진 정답 버리기
    ks = sorted(참)
    d = {i: 참[i] - L[i][0] for i in ks}
    좋은 = {}
    for n, i in enumerate(ks):
        이웃 = [d[j] for j in ks[max(0, n - 3):n] + ks[n + 1:n + 4]]
        if len(이웃) >= 2 and abs(d[i] - float(np.median(이웃))) > 1.5:
            continue
        좋은[i] = 참[i]
    return 좋은


# ── 옛 맞춤(2026-09-27 운영판 전역 DP)과 새 맞춤 ─────────────────────────────────────────
import 맞춤_옛판 as 옛판  # noqa: E402


def 새맞춤(L, cards, 폭=None, 매=None):
    return Z.맞춤(L, cards, 폭=폭, **(매 or {}))


# ── 평가 ───────────────────────────────────────────────────────────────
def 오차(시작들, 참):
    e = np.array([abs(시작들[i] - v) for i, v in 참.items()])
    return {"n": len(e), "중앙": float(np.median(e)), "p90": float(np.percentile(e, 90)),
            "최대": float(e.max()), "2초넘음": float((e > 2).mean())}


def 편자료(slug):
    pj = os.path.join(ROOT, "projects", f"{slug}.json")
    proj = json.load(open(pj, encoding="utf-8"))
    sid = proj["source"]["id"]
    vtt0 = os.path.join(ROOT, "work", f"{sid}.ko.vtt.맞춤전")
    src = os.path.join(ROOT, "work", f"{sid}.mp4")
    if not (os.path.exists(vtt0) and os.path.exists(src) and proj.get("asr_words")):
        return None
    _, L = Z.읽기(vtt0)
    참 = 참시각(proj, L)
    if len(참) < 5:
        return None
    cards2, 폭 = 새카드(src)
    return {"slug": slug, "L": L, "cards": 카드(src), "cards2": cards2, "폭": 폭, "참": 참, "src": src,
            "끝확인": 끝확인(vtt0, slug)}


def 끝확인(vtt0, slug):
    """agy «끝 확인» 판정 — vtt 머리 표시(2026-09-28 저녁부터), 없으면 배치로그 편시작 로그의 «(끝 확인 …)»."""
    v = Z.끝확인표시(open(vtt0, encoding="utf-8").read())
    if v:
        return v
    try:
        m = re.search(r"\(끝 확인 (닿음|붙임|끝없음)\)",
                      open(os.path.join(ROOT, "배치로그", f"{slug}_1편시작.txt"), encoding="utf-8").read())
        return m.group(1) if m else None
    except OSError:
        return None


def 모든편(인자):
    if 인자:
        return 인자
    out = []
    for f in sorted(os.listdir(os.path.join(ROOT, "work"))):
        m = re.match(r"^(.+)\.ko\.vtt\.맞춤전$", f)
        if m and os.path.exists(os.path.join(ROOT, "projects", f"{m.group(1)}.json")):
            out.append(m.group(1))
    return out


def 재기(자료, 매=None):
    """(맞춤 전, 옛 맞춤, 새 맞춤, 관문 뒤, 관문 조치) 오차. 관문 조치 = 채택·부분되돌림·거부·멈춤(운영 자막띠시각.실행 과 같게).
    멈춤이면 편시작이 멈춰 다시 전사하므로 «관문 뒤» 는 맞춤 전 오차를 그대로 둔다(다시 전사한 결과는 여기서 모른다)."""
    L, 참 = 자료["L"], 자료["참"]
    if "옛" not in 자료:
        자료["옛"] = [x[0] for x in 옛판.맞춤(L, 자료["cards"])[4]]
    전 = 오차([l[0] for l in L], 참)
    지 = 오차(자료["옛"], 참)
    a, *_, 새줄 = 새맞춤(L, 자료["cards2"], 자료["폭"], 매)
    새 = 오차([x[0] for x in 새줄], 참)
    ok = Z.관문(L, 새줄, 자료["cards2"], 자료["폭"], 배율=a)[0]      # 2026-09-28 관문 ③(옮긴 줄당 번 비용)까지 — 운영과 같게
    if not ok:
        return 전, 지, 새, 전, "거부"
    # ④⑤ 꼬리 관문(2026-09-28 저녁) — 운영과 같게. 아웃트로 검출은 편마다 한 번만(자료에 담아 둔다)
    def 끝():
        if "끝" not in 자료:
            자료["끝"] = Z._아웃트로(자료["src"])
        return 자료["끝"]
    쓸, 꼬 = Z.꼬리관문(L, 새줄, 자료["cards2"], 끝확인=자료.get("끝확인"), 끝재기=끝)
    조치 = {"없음": "채택"}.get(꼬["조치"], 꼬["조치"])
    return 전, 지, 새, (전 if 조치 in ("거부", "멈춤") else 오차([x[0] for x in 쓸], 참)), 조치


def 표(rows):
    f = lambda o: f"{o['중앙']:4.2f} {o['p90']:5.2f} {o['최대']:5.2f} {o['2초넘음']:4.0%}"
    print(f"{'편':8} {'줄':>3} {'참':>3} | {'맞춤 전 (중앙 p90 최대 >2초)':28} | {'옛 맞춤(운영판 DP)':24} | {'새 맞춤':24} | 관문")
    for slug, n, 전, 지, 새, 뒤, 조치 in rows:
        꼬 = {"채택": "채택", "거부": "거부→맞춤 전", "멈춤": "멈춤(다시 전사)"}.get(조치, f"{조치}→관문 뒤 {f(뒤)}")
        print(f"{slug:8} {n:3d} {전['n']:3d} | {f(전):28} | {f(지):24} | {f(새):24} | {꼬}")


def 점(os_):
    """낮을수록 좋다 — 편마다 (중앙 + p90 + 최대/2 + 5×2초넘음비율) 의 평균."""
    return float(np.mean([o["중앙"] + o["p90"] + o["최대"] / 2 + 5 * o["2초넘음"] for o in os_]))


def 고르기(자료들):
    """짝수 번호 편으로 벌점 값을 고르고, 홀수 번호 편으로 확인한다(과적합 확인)."""
    import itertools
    짝 = [d for d in 자료들 if int(re.sub(r"\D", "", d["slug"]) or 0) % 2 == 0]
    홀 = [d for d in 자료들 if d not in 짝]
    격자 = {"기울": [1.0, 2.0], "점프": [1.5, 3.0], "점프폭": [4.0, 6.0], "못붙": [1.0, 1.5],
            "폭벌": [0.5, 1.0, 1.5], "자리": [1.0, 2.0]}          # 2026-09-28 114편 — 고른 값이 가운데 오게
    keys = list(격자)
    결과 = []
    for vals in itertools.product(*[격자[k] for k in keys]):
        매 = dict(zip(keys, vals))
        결과.append((점([재기(d, 매)[2] for d in 짝]), 매))
    결과.sort(key=lambda x: x[0])
    옛짝 = 점([재기(d)[1] for d in 짝])
    옛홀 = 점([재기(d)[1] for d in 홀])
    print(f"옛 맞춤 점수 — 짝 {옛짝:.2f} · 홀 {옛홀:.2f}")
    for sc, 매 in 결과[:8]:
        print(f"짝 {sc:.2f} · 홀 {점([재기(d, 매)[2] for d in 홀]):.2f}  {매}")
    return 결과[0][1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    자료들 = []
    for s in 모든편(args):
        try:
            d = 편자료(s)
        except Exception as e:  # noqa: BLE001
            print(f"{s}: 건너뜀 — {e}")
            continue
        if d:
            자료들.append(d)
        else:
            print(f"{s}: 정답·자료 모자라 뺌")
    매 = None
    for a in sys.argv[1:]:
        if a.startswith("--값="):                           # 예: --값='{"줄벌": 1.5}'
            매 = json.loads(a[len("--값="):])
    if "--고르기" in sys.argv:
        매 = 고르기(자료들)
        print(f"고른 값: {매}\n")
    rows = []
    for d in 자료들:
        rows.append((d["slug"], len(d["L"]), *재기(d, 매)))
    표(rows)
    for 이름, k in (("전", 2), ("옛", 3), ("새", 4), ("관문뒤", 5)):
        모 = [r[k] for r in rows]
        print(f"{이름:4}: 편 중앙값 평균 {np.mean([o['중앙'] for o in 모]):.2f} · p90 평균 {np.mean([o['p90'] for o in 모]):.2f}"
              f" · 최대 평균 {np.mean([o['최대'] for o in 모]):.2f} · >2초 평균 {np.mean([o['2초넘음'] for o in 모]):.1%}")


if __name__ == "__main__":
    main()
