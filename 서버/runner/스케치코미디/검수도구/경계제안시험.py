#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경계제안시험.py [슬러그 …] [--옛] [--자세히] — 경계제안.py 의 제안을 납품 편으로 채점한다(영구 시험 · 무료 — 원본 소리·프레임만).

  ★2026-10-03 루키치 배치 — 경계제안이 편마다 7~18곳을 냈는데 배치 에이전트가 거의 다 버렸다(샷 전환·로고·큰 제목 카드를
    넘거나 agy 시각을 믿음 · 167 은 말 사이 0.05초 골에서 말끝 «돼» 를 잘라 재굽기). 제안 단계엔 기계 관문이 없어 사람이 매 편
    프레임·소리로 걸렀다. 이 시험이 그 눈을 숫자로 바꾼다. 판정 수리는 s2pipe/경계자리.py.

  재료(편마다): projects/<편>.json(납품 경계 = 사람이 듣고 보고 받은 정답) · 있으면 projects/<편>.json.plan원본(plan 이 낸 첫 경계 —
    경계제안이 실제로 받는 거친 경계) · work/<편>.mp4(원본) · work/<편>.cuts.json · 박힌 카드 캐시.
    원본 mp4 가 NAS 로 옮겨졌으면 «영화자료/3. 스캐치코미디/<시리즈>/<번호>.*/» 바로 아래 mp4 를 work/<편>.mp4 로 복사하고
    수정 시각을 카드 캐시 키(<편>.mp4.카드2.json 의 key 셋째 칸)로 맞춘다(touch) — 안 맞추면 카드를 다시 잰다.

  채점(제안 하나 = 경계 옛값 → 새값):
    샷넘음   경계를 넓혀(끝은 뒤로 · 시작은 앞으로) 다른 샷 프레임이 조각에 들어왔다 — 샷 전환은 cuts.json ∪ 프레임 날카로운
             봉우리(최소 8 — 도구(12)보다 예민하게). 옛 경계가 샷 전환 바로 그 자리였다가 넓힌 것도 넘음이다.
    암전넘음 넓힌 구간에 암전 프레임(밝기 < 12)이 들어왔다
    로고넘음 새값이 원본 아웃트로 시작(조각 _엔드카드시작 · build.엔드카드시작) 너머다
    말자름   새값이 박힌 카드 한가운데(가장자리 0.3초 안쪽)이고 잘려 나가는 쪽 카드 안에 말소리 0.2초↑(카드경계검사와 같은 규칙)
    짧은골   새값 자리 조용한 골이 0.2초 미만(167 «돼» 클래스) — 샷 전환 자리는 빼고 잰다
    («겹침 방지» 제안은 다른 제안의 뒤따름이라 따로 센다)
  납품 경계에 낸 제안은 사람이 이미 받은 경계를 바꾸자는 것이라 그 수 자체도 «헛제안» 으로 센다.
  «이음매» 줄: 이음매수리.py 길(경계자리.이음매고침) — 납품 편의 모든 이음매가 반려됐다고 치고 낸 고침을 같은 자로 채점한다.
    거꾸로   «담기»(끝은 뒤로 · 시작은 앞으로)·«빼기» 라 해 놓고 반대로 옮겼다(말을 더 자름)
  종료코드: 샷·암전·로고 넘음 또는 거꾸로가 하나라도 있으면 1.

  --옛[=<커밋>]: 수리 전 경계제안.py(기본 94e1b4b)를 같은 편에 돌려 같은 자로 채점한다(수리 전후 대조용).

  기록 — 2026-10-03 수리 전후 (납품 20편 루키치161~179·206 · plan원본 있는 9편 · 같은 채점자):
                      제안   넘음(샷·암전·로고)   말자름   짧은골   새값=납품 경계
    경계제안 납품 경계  옛 254 → 새 5     149(59%) → 0       14 → 0    68 → 0      —
    경계제안 plan원본   옛 99  → 새 31     31(31%) → 0        6 → 0    26 → 0     14% → 58%
    이음매수리 길       옛 105 → 새 35     84(80%) → 0       22 → 0     6 → 0      — (고칠 자리 없음 70곳은 사람에게)
    다른 시리즈 4편(Deep87·싱글147·160·172) 납품: 옛 45 제안(넘음 49%) → 새 3(넘음 0).
    새 판 «고칠 자리 없음» 은 옮기지 않고 까닭을 찍는다(납품 경계 438곳 중 7곳 — 대부분 「주의(소리만)」).
    옛 숫자는 `--옛` 으로 다시 잴 수 있다(수리 전 커밋 94e1b4b 의 경계제안.py 를 돌린다 · 다른 판은 `--옛=<커밋>`).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402

from s2pipe import 프레임격자 as G  # noqa: E402

W = os.path.expanduser("~/Desktop/스케치코미디")
HERE = os.path.dirname(os.path.abspath(__file__))


class 채점자:
    """도구(경계자리)와 따로 원본을 읽는다 — 같은 자로 채점하면 틀린 자가 스스로를 통과시킨다(번인관문 213 교훈)."""

    def __init__(self, src, proj):
        self.src = src
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                           capture_output=True, check=True)
        x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
        FR = 320
        n = len(x) // FR
        f = np.fft.rfftfreq(FR, 1 / 16000)
        sel = (f > 300) & (f < 3500)
        E = 20 * np.log10(np.abs(np.fft.rfft(x[:n * FR].reshape(n, FR) * np.hanning(FR), axis=1))[:, sel].sum(axis=1) + 1e-9)
        pad = np.pad(E, 150, mode="edge")
        self.Q = E < np.percentile(np.lib.stride_tricks.sliding_window_view(pad, 301)[:n], 20, axis=1) + 6.0
        self.n = n
        self.g = G.얻기(src)
        try:
            self.cuts = G.컷맞춤(self.g, json.load(open(os.path.splitext(src)[0] + ".cuts.json", encoding="utf-8")))
        except (OSError, ValueError):
            self.cuts = []
        try:
            from s2pipe import 번인관문
            self.cards = 번인관문.확인된카드들(src)
        except Exception:                                    # noqa: BLE001
            self.cards = []
        ends = [s.get("_엔드카드시작") for s in proj.get("segments", []) if s.get("_엔드카드시작")]
        self.outro = float(min(ends)) if ends else None
        if self.outro is None:
            try:
                if not os.environ.get("S2_CONFIG"):
                    os.environ["S2_CONFIG"] = f"{W}/config.json"
                from s2pipe.build import 엔드카드시작
                self.outro = 엔드카드시작(src, self.g.시작(self.g.n))
            except (Exception, SystemExit):                  # noqa: BLE001
                self.outro = None

    def _말(self, a, b):
        i0, i1 = max(0, int(a / 0.02)), min(self.n, int(b / 0.02))
        return float((~self.Q[i0:i1]).sum()) * 0.02

    def _골길이(self, t):
        i = int(round(t / 0.02))
        js = [j for j in (i, i - 1, i + 1) if 0 <= j < self.n and self.Q[j]]
        if not js:
            return 0.0
        a = b = js[0]
        while a > 0 and self.Q[a - 1]:
            a -= 1
        while b + 1 < self.n and self.Q[b + 1]:
            b += 1
        return (b - a + 1) * 0.02

    def 전환(self, lo, hi):
        """[lo, hi] 둘레 샷 전환 시각(새 샷 첫 프레임 − 0.002)과 암전 프레임 시각."""
        k0, k1 = max(0, self.g.번호(lo) - 5), min(self.g.n, self.g.번호(hi) + 6)
        F = G.프레임들(self.src, self.g, k0, k1)
        D = G.차이열(F)
        ts = [c for c in self.cuts if lo - 0.06 <= c <= hi + 0.06]
        ts += [self.g.경계값(k0 + j) for j in range(1, len(D)) if G.날카로운(D, j, 최소=8.0, F=F)
               and lo - 0.06 <= self.g.경계값(k0 + j) <= hi + 0.06]
        암 = [self.g.시작(k0 + j) for j in range(len(F)) if F[j].mean() < 12 and (F[j] > 60).mean() < 0.01]
        return sorted(set(round(t, 3) for t in ts)), 암

    def 채점(self, k, old, new):
        """흠 목록. «넘음» 은 경계를 «넓혀» 다른 샷·암전·로고 프레임을 조각 안으로 들인 것 — 끝(t1)을 뒤로 · 시작(t0)을 앞으로.
        좁히다 샷 전환에 맞추는 것(남의 샷 자투리를 덜어 냄)은 흠이 아니다.
        샷 = 그 시각 앞에 있는 전환 수. 끝은 «마지막으로 담기는 프레임»(값 − 0.02), 시작은 «첫 프레임»(값 + 0.02)의 샷을 본다 —
        옛 경계가 샷 전환 바로 그 자리(경계값)일 때 넓히면 곧바로 다음 샷이 들어오는 것까지 잡는다(170 30.45 → 31.14)."""
        lo, hi = min(old, new), max(old, new)
        ts, 암 = self.전환(lo, hi)
        흠 = []
        넓힘 = (k == "t1" and new > old) or (k == "t0" and new < old)
        e = -0.02 if k == "t1" else 0.02
        샷 = lambda x: sum(1 for c in ts if c <= x + e)                  # noqa: E731
        if 넓힘 and 샷(old) != 샷(new):
            넘 = [c for c in ts if min(old, new) + e < c <= max(old, new) + e]
            흠.append(f"샷넘음({','.join(f'{t:.2f}' for t in 넘[:3])})")
        if 넓힘:
            들어옴 = [d for d in 암 if (old < d < new if k == "t1" else new <= d < old)]
            if 들어옴:
                흠.append(f"암전넘음({들어옴[0]:.2f})")
        if self.outro is not None and new > self.outro + 0.02 and k == "t1":
            흠.append(f"로고넘음({self.outro:.2f})")
        for cs, ce in self.cards:
            if cs + 0.3 < new < ce - 0.3:
                말 = self._말(new, min(ce, new + 1.5)) if k == "t1" else self._말(max(cs, new - 1.5), new)
                if 말 >= 0.2:
                    흠.append(f"말자름(카드 {cs:.1f}~{ce:.1f})")
                    break
        k0 = self.g.번호(new)
        전환자리 = any(abs(c - new) <= 0.03 for c in self.cuts) or bool(G.전환들(self.src, self.g, k0, (-1, 0, 1)))
        if not 전환자리 and self._골길이(new) < 0.2:
            흠.append(f"짧은골({self._골길이(new):.2f}초)")
        return 흠


옛판 = "94e1b4b"      # 수리 전 마지막 커밋(2026-10-03)


def 옛제안(pj):
    """수리 전 경계제안.py(커밋 옛판)를 그 판에 돌려 제안 목록을 읽는다."""
    repo = subprocess.run(["git", "-C", HERE, "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    rel = os.path.relpath(os.path.join(HERE, "경계제안.py"), repo)
    code = subprocess.run(["git", "-C", repo, "show", f"{옛판}:{rel}"], capture_output=True, text=True).stdout
    code = code.replace('pj = f"{W}/projects/{slug}.json"', 'pj = slug if os.sep in slug else f"{W}/projects/{slug}.json"')
    code = code.replace("sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))",
                        f"sys.path.insert(0, {os.path.dirname(HERE)!r})")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fp:
        fp.write(code)
    try:
        out = subprocess.run([sys.executable, fp.name, pj], capture_output=True, text=True).stdout
    finally:
        os.remove(fp.name)
    res = []
    for m in re.finditer(r"조각 (\d+) (t[01]): ([\d.]+) → ([\d.]+)  \((.*)\)", out):
        res.append((int(m.group(1)), m.group(2), float(m.group(3)), float(m.group(4)), m.group(5)))
    return res


def 새제안(proj, src):
    import importlib.util
    spec = importlib.util.spec_from_file_location("경계제안", os.path.join(HERE, "경계제안.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from s2pipe.경계자리 import 원본자리
    바뀜, 메모 = mod.제안(proj, 원본자리(src, proj))
    return 바뀜, 메모


def 이음매제안(proj, src):
    """이음매수리 길 — 납품 편의 모든 이음매가 ④ 에서 반려됐다고 치고 경계자리.이음매고침 이 내는 고침.
    (실제 반려는 몇 곳뿐이지만, 어느 이음매가 반려되든 고침이 샷·암전·로고를 넘지 않아야 한다.)"""
    from s2pipe.경계자리 import 원본자리
    자리 = 원본자리(src, proj)
    segs = [s for s in proj["segments"] if s.get("keep", True)]
    바뀜, 메모 = [], []
    for i, (a, b) in enumerate(zip(segs, segs[1:])):
        if abs(b["t0"] - a["t1"]) < 0.05:
            continue
        for k, 옛, 새, 까닭 in 자리.이음매고침(a["t1"], b["t0"], 나레앞=bool((b.get("narration") or "").strip())):
            j = i if k == "t1" else i + 1
            (메모.append((j, k, 옛, 까닭)) if 새 is None else 바뀜.append((j, k, 옛, 새, 까닭)))
    return 바뀜, 메모


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    global 옛판
    옛 = any(a.startswith("--옛") for a in sys.argv)
    for a in sys.argv:
        if a.startswith("--옛="):
            옛판 = a.split("=", 1)[1]
    자세히 = "--자세히" in sys.argv
    if not args:
        args = sorted(os.path.basename(p)[:-5] for p in os.listdir(f"{W}/projects")
                      if p.startswith("루키치") and p.endswith(".json")
                      and os.path.exists(f"{W}/work/{p[:-5]}.mp4"))
    합 = {}
    넘음 = 0
    for slug in args:
        for 판, pj in (("납품", f"{W}/projects/{slug}.json"), ("plan", f"{W}/projects/{slug}.json.plan원본"),
                       ("이음매", f"{W}/projects/{slug}.json")):
            if 판 == "이음매" and 옛:
                continue
            if not os.path.exists(pj):
                continue
            proj = json.load(open(pj, encoding="utf-8"))
            src = f"{W}/work/{proj['source']['id']}.mp4"
            if not os.path.exists(src):
                print(f"{slug}: 원본 없음 — 건너뜀 ({src})")
                break
            심 = 채점자(src, proj)
            경계수 = sum(2 for s in proj["segments"] if s.get("keep", True))
            if 판 == "이음매":
                바뀜, 메모 = 이음매제안(proj, src)
            elif 옛:
                바뀜, 메모 = 옛제안(pj), []
            else:
                바뀜, 메모 = 새제안(proj, src)
            줄 = []
            c = 합.setdefault(판, {"편": 0, "경계": 0, "제안": 0, "겹침": 0, "넘음": 0, "샷넘음": 0, "암전넘음": 0, "로고넘음": 0,
                                  "말자름": 0, "짧은골": 0, "거꾸로": 0, "흠없음": 0, "자리없음": 0, "납품맞음": 0, "옛맞음": 0})
            # plan 판: 제안이 사람이 끝내 받은 납품 경계(±0.1초)로 갔는가 — 도구와 무관한 정답
            납품값 = []
            if 판 == "plan":
                납품값 = [s[k] for s in json.load(open(f"{W}/projects/{slug}.json", encoding="utf-8"))["segments"]
                        if s.get("keep", True) for k in ("t0", "t1")]
            맞음 = lambda v: bool(납품값) and min(abs(v - x) for x in 납품값) <= 0.1      # noqa: E731
            c["편"] += 1
            c["경계"] += 경계수
            c["자리없음"] += len(메모)
            for i, k, a, b, why in 바뀜:
                if "겹침" in why:
                    c["겹침"] += 1
                    continue
                c["제안"] += 1
                흠 = 심.채점(k, a, b)
                # 방향 — «담기»(끝은 뒤로 · 시작은 앞으로) / «빼기»(그 반대)라 해 놓고 거꾸로 가면 말을 더 자른다
                넓 = (k == "t1" and b > a) or (k == "t0" and b < a)
                if ("담기" in why and not 넓) or ("빼기" in why and 넓):
                    흠.append("거꾸로")
                for h in 흠:
                    c[h.split("(")[0]] += 1
                if not 흠:
                    c["흠없음"] += 1
                if any(h.startswith(("샷넘음", "암전넘음", "로고넘음", "거꾸로")) for h in 흠):
                    넘음 += 1
                    c["넘음"] += 1
                if 판 == "plan":
                    c["납품맞음"] += 맞음(b)
                    c["옛맞음"] += 맞음(a)
                표 = (" · 납품 경계" if 맞음(b) else "") if 판 == "plan" else ""
                줄.append(f"    조각 {i} {k}: {a:.2f} → {b:.2f}  {' · '.join(흠) or '흠 없음'}{표}  [{why[:70]}]")
            print(f"{slug} {판}: 경계 {경계수} · 제안 {len([1 for x in 바뀜 if '겹침' not in x[4]])} · 자리없음 {len(메모)}")
            if 자세히:
                print("\n".join(줄))
    print("\n== 합계 ==" + (" (옛 판)" if 옛 else " (새 판)"))
    for 판, c in 합.items():
        p = c["제안"] or 1
        print(f"  {판}: 편 {c['편']} · 경계 {c['경계']} · 제안 {c['제안']}(겹침 뒤따름 {c['겹침']} 따로) · "
              f"넘음(샷·암전·로고 하나라도) {c['넘음']}({c['넘음'] / p:.0%}) · "
              f"샷넘음 {c['샷넘음']}({c['샷넘음'] / p:.0%}) · 암전넘음 {c['암전넘음']} · 로고넘음 {c['로고넘음']} · "
              f"말자름 {c['말자름']}({c['말자름'] / p:.0%}) · 짧은골 {c['짧은골']}({c['짧은골'] / p:.0%}) · 거꾸로 {c['거꾸로']} · "
              f"흠 없음 {c['흠없음']}({c['흠없음'] / p:.0%}) · 고칠 자리 없음(사람에게) {c['자리없음']}"
              + (f" · 새값이 납품 경계(±0.1초) {c['납품맞음']}({c['납품맞음'] / p:.0%}) — 옛값이 이미 납품 경계였던 것 {c['옛맞음']}"
                 if 판 == "plan" else ""))
    sys.exit(1 if 넘음 else 0)


if __name__ == "__main__":
    main()
