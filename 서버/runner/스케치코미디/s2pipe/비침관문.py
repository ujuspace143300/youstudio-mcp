# -*- coding: utf-8 -*-
"""완성본(cut.mp4)에 원본 박힌 대사 자막이 «비치는가» — 구운 화면을 글자 인식기로 직접 읽는 관문 (넷째 자).

    python -m s2pipe.비침관문 <cut.mp4> <원본.mp4> <beats.json>     # 재기만(종료코드 1 = 걸림)

★2026-10-02 루키치213 첫 완성본 36.9초 — 원본 117~119초 «뭐가 쩔어 븅X아» 가 완성본 아래 끝에 비쳤다(가림 땜질로 납품).
  번인관문의 조각한계·굽기 끝 걸림·⑦ 준비가 모두 «같은 카드상자»(픽셀 기하로 잰 카드 위치)로 채점해, 두 칸 화면 틈·칸 모서리를
  카드로 잘못 잰 값(윗변 911·991 — 실제 글자 856)이 스스로를 통과시켰다(번인관문 머리 주석 2026-10-02).
  클래스: «crop 이 박힌 자막을 담는가» 를 모든 관문이 «원본 쪽 기하 계산» 한 갈래로만 판정했다 — 계산(카드 재기·crop 기록·
    좌표 환산) 어디에 구멍이 나도 같은 계산으로 채점하니 아무도 못 본다.
  수리: 기하와 무관한 자 — 실제로 구운 cut.mp4 화면(우리 자막·틀을 얹기 전)을 4fps 로 읽어, 원본 대사 자막과 «같은 것» 이
    읽히면 멈춘다. 같은 것인지는 원본 글자 인식(화면글자 캐시 — 같은 시각 원본 화면 전체 글줄)에 비춰 정한다. 비교 대상 원본
    자막은 «확실한» 표본만(화면글자.확실한자막표본 — 이웃 표본이 있거나 확신 0.9↑ · 높이가 그 원본 자막 높이 0.6~1.6배):
      A 자리 — 완성본 글줄을 그 순간 crop 으로 원본 좌표에 되돌리면 원본 자막 글줄과 윗선이 같다(±0.02 · ±0.75초 · 가로 둘레 3%)
               — 비침은 crop 밑변에 아래만 잘리고 윗선은 그대로다(213 실측 차 0.008)
      B 글   — 원본 자막 글줄과 글이 같고(한글·숫자 절반 이상) 윗선 차 0.05 안(비트 움직임 환산 어긋남까지)
      C 모름 — 원본 어느 글줄과도 글이 안 맞는(원본 훑기가 못 읽은) 온전한 한 줄이 대사 자막 자리 가운데(±0.06)에 자막 높이로
    A·B 는 되돌린 높이가 원본 자막의 1.6배를 넘으면 아니다(포장지 큰 글씨). 같은 글줄이 이어진 표본 2장(0.25초) 이상이면 걸림.
    ★오탐 실측(2026-10-02 납품 155편 첫 회귀 — 셋 다 장면 글자): 점심이네46 아이스크림 «빵빠레»(B · 원본 «빵빽» 한 장 0.3)·
      59 컵라면 «쌀짬뽕»(A · 원본 «쌀짬뽈» 한 장 0.5)·35 게임 화면 «스킬이 아직 준비되지…»(A · 자막 윗선보다 0.043 위)
      → 위 «확실한 표본»·«윗선 맞춤»·«높이 1.6배» 로 셋 다 빠지고 213 비침은 그대로 잡힌다.
  왜 기하 관문과 따로인가: 카드가 틀려도·crop 기록이 틀려도·환산이 틀려도 «화면에 실제로 보인 글» 은 틀리지 않는다.
  시각: 완성본·원본 훑기 표본은 모두 «실제 프레임 시각»(화면글자.훑기시각 — fps 필터가 간격 안 마지막 프레임을 내서 2fps 는
    +0.21초 · 4fps 는 +0.08초 늦은 프레임이다)으로 고쳐 맞댄다.
한계(알려짐): 글자 윗머리 몇 px 만 걸친 비침(글자로 안 읽힘)은 못 본다 — 그건 번인관문(카드·글줄 기하)이 본다.
  인식기(macOS Vision)가 없는 컴퓨터는 화면글자 규칙 그대로 멈춘다(S2_NO_SCREENTEXT=1 일 때만 건너뛴다).
"""
import json
import os
import re
import subprocess
import sys

FPS = 4.0                  # 완성본 훑기 — 짧은 자막(«어?» 0.5초)도 두 장 이상 걸리게(77초 cut ≈ 6초)
폭 = 1080                  # cut.mp4 원래 폭 그대로 읽는다(확대된 crop 이라 원본 훑기보다 글자가 크다)
확신 = 0.3                 # 완성본 글줄 확신 하한 — 비친 자막은 아래 끝에 잘려 확신이 낮다(213 실측 «뭐가 쩝» 0.5 · «미기저» 0.3)
잇달음 = 2                 # 걸림 = 의심 글줄이 이어진 표본 수(4fps · 0.25초 간격)
시각창 = 0.75              # 원본 글줄을 찾는 시각 범위(±초) — 원본 훑기 2fps + 조각 앞멈춤·호환 시간축 어긋남
자리둘레 = 0.03            # A 자리: 원본 자막 글줄 가로 둘레 여유(화면 비율)
윗선차 = 0.02              # A 자리: 되돌린 윗선 − 원본 자막 윗선 허용(213 비침 0.008 · 점심이네35 게임 UI 0.043)
윗선차글 = 0.05            # B 글: 글이 같을 때 윗선 허용(비트 움직임 환산 어긋남까지)
글겹침 = 0.5               # B 글: 완성본 글줄 글자의 이 비율 이상이 원본 글줄에 있으면 같은 글
높이배 = (0.6, 1.6)        # 완성본 글줄을 원본 크기로 되돌린 높이 ÷ 원본 자막 글줄 높이 — A·B 는 위 끝만(잘린 비침은 낮다), C 는 둘 다


def _글자들(s):
    return re.findall(r"[가-힣0-9]", s or "")


def _같은글(a, b):
    """완성본 글 a 의 한글·숫자 중 원본 글 b 에 있는 비율(중복 셈) — a 가 비면 0."""
    ca = _글자들(a)
    if not ca:
        return 0.0
    cb = _글자들(b)
    n = 0
    for ch in ca:
        if ch in cb:
            cb.remove(ch)
            n += 1
    return n / len(ca)


def _crop_at(log, T, W, H, bw, bh):
    """완성본 시각 T → (원본 시각, 환산 함수 f(x,y)→(원본 x,y) 비율, 종류). 못 찾으면 None."""
    seg = None
    for e in log.get("segments", []):
        if e.get("out_t0") is not None and e["out_t0"] <= T < e["out_t0"] + e.get("out_dur", 0):
            seg = e
            break
    if seg is None:
        return None
    ts = seg["t0"] + (T - seg["out_t0"])
    for b in log.get("beats", []):
        if b["seg"] == seg["i"] and b["t0"] - 1e-3 <= ts < b["t1"] + 1e-3:
            w, h, x1, y1 = b["crop"]
            _w, _h, x0, y0 = b.get("시작crop") or b["crop"]
            u = min(max((ts - b["t0"]) / max(b["t1"] - b["t0"], 1e-3), 0.0), 1.0)
            e_ = u * u * (3 - 2 * u)                     # framing.plan_beats 의 smoothstep
            cx, cy = x0 + (x1 - x0) * e_, y0 + (y1 - y0) * e_
            return ts, (lambda nx, ny, cx=cx, cy=cy, w=w, h=h: ((cx + nx * w) / W, (cy + ny * h) / H)), "비트"
    for f in log.get("frames", []):
        if f["seg"] == seg["i"]:
            w, h, x, y = f["crop"]
            if f.get("kind") in ("전체화면", "원문화면"):
                s = bw / W                                # 가로 맞춤 + 위아래 여백(build 원문화면 갈래)
                yo = (bh - H * s) / 2
                return ts, (lambda nx, ny, s=s, yo=yo: (nx * bw / s / W, (ny * bh - yo) / s / H)), f["kind"]
            return ts, (lambda nx, ny, x=x, y=y, w=w, h=h: ((x + nx * w) / W, (y + ny * h) / H)), f.get("kind", "")
    return None


def 재기(cut, src, log, 표본=None):
    """→ (걸림 목록, 요약). 걸림 = [{t0,t1(완성본 초), 원본초, 글, 근거}] · 표본 = 미리 읽은 완성본 [(t, rows)](시험용)."""
    from . import 화면글자 as 화
    if 화.인식기() is None:
        if os.environ.get("S2_NO_SCREENTEXT") == "1":
            return [], "인식기 없음(S2_NO_SCREENTEXT=1) — 건너뜀"
        raise RuntimeError("완성본 비침 관문 — 화면글자 인식기 없음(macOS Vision 전용). 건너뛰지 않는다(S2_NO_SCREENTEXT=1 로만)")
    c = 화._캐시(src)                                     # 원본 글줄(카드상자들이 이미 만든 캐시)
    W, H = c["W"], c["H"]
    띠 = 화._띠(src)
    # 시각은 모두 «실제 프레임 시각» 으로(화면글자.훑기시각 — fps 필터는 간격 안 마지막 프레임을 낸다 · 2fps 원본 +0.21초)
    sf = 화.원본fps(src)
    자막 = {}                                             # 원본 시각 → «확실한» 대사 자막 글줄(장면 글자 한 장 뺌)
    전표본 = 화.자막표본(c["frames"], 띠)
    for t, l in 화.확실한자막표본(전표본):
        자막.setdefault(화.훑기시각(t, c["fps"], sf), []).append(l)
    _hs = sorted(l["h"] for _t, l in 전표본)
    자막높이 = _hs[len(_hs) // 2] if _hs else 0.05          # 이 원본 대사 자막 글줄 높이 중앙값(화면 비율)
    원 = [(화.훑기시각(t, c["fps"], sf), [화._줄(r) for r in rows]) for t, rows in c["frames"]]
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", cut], capture_output=True, text=True)
    bw, bh = (int(v) for v in r.stdout.strip().split(",")[:2])
    if 표본 is not None:
        frames = 표본
    else:
        cf = 화.원본fps(cut)
        frames = [(화.훑기시각(t, FPS, cf), rows) for t, rows in 화.훑기(cut, fps=FPS, width=폭)]
    의심 = []                                             # (k, t, 원본초, 글, 근거)
    n한 = 0                                               # 읽힌 한글 글줄 수(장면 글자 포함 — 관문이 «보고 있음» 의 증거)
    for k, (t, rows) in enumerate(frames):
        m = _crop_at(log, t, W, H, bw, bh)
        if m is None:
            continue
        ts, f, _종류 = m
        for row in rows:
            l = 화._줄(row)
            if l["c"] < 확신 or l["한"] < 1:
                continue
            n한 += 1
            x0, y0 = f(l["x"], l["y"])
            x1, y1 = f(l["x"] + l["w"], l["y"] + l["h"])
            ml = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            근처자막 = [s for tt, ss in 자막.items() if abs(tt - ts) <= 시각창 for s in ss]
            근거 = None
            # 비친 자막은 아래가 잘려 «낮아질» 수는 있어도 원본 자막보다 크게 커지지는 않는다(포장지 큰 글씨 — 점심이네46 1.8배)
            # 윗선 맞춤: 비친 자막은 crop 밑변에 아래가 잘릴 뿐 윗선은 원본 자막 윗선 그대로다(213 실측 차 0.008). 그 위에 뜬 다른
            #   글(게임 화면 UI «스킬이 아직 준비되지…» — 점심이네35 · 원본 자막 윗선보다 0.043 위)은 자막이 아니다.
            for s in 근처자막:                            # A 자리
                if s["x"] - 자리둘레 <= mx <= s["x"] + s["w"] + 자리둘레 and abs(y0 - s.get("ys", s["y"])) <= 윗선차 \
                        and ml["h"] <= 높이배[1] * s["h"]:
                    근거 = f"A 자리(원본 «{s['s'][:16]}»)"
                    break
            if 근거 is None and my >= 띠[0] - 화.자막위:   # B 글
                hit = max(근처자막, key=lambda s: _같은글(l["s"], s["s"]), default=None)
                if hit is not None and _같은글(l["s"], hit["s"]) >= 글겹침 and ml["h"] <= 높이배[1] * hit["h"] \
                        and abs(y0 - hit.get("ys", hit["y"])) <= 윗선차글:
                    근거 = f"B 글(원본 «{hit['s'][:16]}»)"
            # C 모름 — 원본 훑기가 못 읽은 자막: 온전히 보이는 한 줄만(가운데 ±0.06 · 확신 0.5↑ · 높이가 이 원본 자막 높이 0.6~1.6배).
            #   게임 화면 UI «레벨 업! +1»(점심이네35 · 가운데 −0.11 · 높이 0.3배) 같은 장면 글자를 뺀다.
            if 근거 is None and 화.자막자리(ml, 띠) and abs(mx - 0.5) <= 화.자막가운데 and l["c"] >= 0.5 \
                    and 높이배[0] * 자막높이 <= ml["h"] <= 높이배[1] * 자막높이:
                근처 = [x for tt, ls in 원 if abs(tt - ts) <= 시각창 for x in ls]
                if not any(_같은글(l["s"], x["s"]) >= 글겹침 for x in 근처):
                    근거 = "C 모름(원본 글줄에 없는 글 · 대사 자막 자리)"
            if 근거:
                의심.append((k, t, ts, l["s"], 근거))
    # 이어진 표본 묶기
    걸, 묶 = [], []
    for v in 의심:
        if 묶 and v[0] - 묶[-1][0] <= 1:
            if v[0] != 묶[-1][0]:
                묶.append(v)
            continue
        if len({x[0] for x in 묶}) >= 잇달음:
            걸.append(묶)
        묶 = [v]
    if len({x[0] for x in 묶}) >= 잇달음:
        걸.append(묶)
    out = [{"t0": g[0][1], "t1": g[-1][1], "원본초": round(g[0][2], 2), "글": " / ".join(dict.fromkeys(x[3] for x in g)),
            "근거": g[0][4]} for g in 걸]
    요 = f"완성본 {len(frames)}장 읽음 · 한글 글줄 {n한}개 · 의심 글줄 {len(의심)}장 · 걸림 {len(out)}곳"
    return out, 요


def 글(걸):
    return "; ".join(f"완성본 {g['t0']:.2f}~{g['t1']:.2f}초(원본 {g['원본초']}초) «{g['글'][:30]}» [{g['근거']}]" for g in 걸[:6]) \
        + (f" 외 {len(걸) - 6}곳" if len(걸) > 6 else "")


def 지침(걸):
    return ("  수리: 원본 박힌 자막이 crop 안에 들었다 — 번인관문(카드·글줄 기하)이 놓친 것이다. 먼저 `python -m s2pipe.번인관문"
            " <원본> <beats.json> --proj <계획>` 으로 그 시각 카드·글줄 상자(카드상자.json)를 보고, 카드 위치가 틀렸으면"
            " 번인관문._위치보정·_한카드 를 고친다(조각 «가림» 땜질 금지 — 2026-10-02 루키치213).\n"
            "  장면 글자(휴대폰·간판)를 자막으로 잘못 본 것이면 원본 화면글자 캐시에 그 글이 «자막 자리 밖» 으로 읽히는지 보고"
            " s2pipe/비침관문.py 의 판정(A 자리·B 글·C 모름)을 실측으로 고친다.")


# ───────────────────────── 다섯째 자: 화면 캡션 «배경판» 이 crop 에 비치는가 ─────────────────────────
# ★2026-10-03 루키치163(완성본 40.4~41.2초 오른쪽 끝 · 흰 말풍선 테두리)·265(회색 말풍선)·161(39.2초 왼쪽 끝 · 삽입 일정표 테두리).
#   굽기(framing.가림경계)와 굽기 끝 관문(번인관문.걸림)이 «같은 사각형»(그때는 글자 상자 ±6px)으로 피하고 채점해서, 글자보다 큰
#   말풍선 판·그림 테두리가 crop 끝에 남아도 «겹침 0» 이 참이었다(자가 채점). 위 넷째 자(재기)는 «대사 자막 글» 만 읽어 글 없는
#   테두리는 원리상 못 본다. 구도모의는 걸림·비침을 비워 둬서 미리보기에서도 안 보였다.
#   이 자는 crop 이 실제로 움직이는 대로(비트 시작crop → crop 부드럽게) 모든 프레임에서 판(그림자 포함)과 맞대, 판이 crop 안으로
#   3px 이상 들어오면 걸림이다. 굽기 끝(build)과 구도모의(굽기 없이 미리보기)가 같은 함수를 부른다 — 원본 프레임과 beats.json 만 있으면 된다.
#   대상 = 화면 캡션 자취(overlay 판정 · 글자판·판무리 포함 — 화면글자.캡션자취들). 전체화면·원문화면 조각은 원본을 통째로 보여 판이
#   잘리지 않으므로 보지 않는다(그 조각의 캡션은 번인관문.캡션조각검사·걸림 이 본다). 조각 «글자허용» 글은 뺀다.
# ★2026-10-03 오후 루키치158 — 판을 «다시» 재던 것을 그만둔다(클래스 «한 물체 두 자»): 굽기는 캐시 판(표본 4장 · 71.5초 한 장만 판으로
#   잡혀 [943,27,1115,183])을 피했는데 이 관문은 crop 이 지나는 69.0초 장을 다시 재 [799,34,1107,175] 로 걸었다 — 굽기는 피했다고 여기는
#   데 관문이 걸고, 사람이 샷을 빼야 했다(정현 노래 67.8~73.5초). 판은 화면글자.캡션판 한 곳에서 자취의 모든 표본을 한 번 재고,
#   굽기는 그 «피할 사각형» 합을, 이 관문은 같은 측정의 «잰 판» 합(피할 사각형보다 늘 3px↑ 안쪽)을 쓴다. 판 재기가 틀리면 둘이 같이
#   틀리므로 그 자는 시험으로 지킨다(검수도구/배경판시험.py — 158 재생판 · 160 카톡 알림판 · 163·265·161 · 판 없는 글자).
#   판을 못 잰 캡션(판 아님)은 건너뛴다 — 글자 상자 자체는 번인관문.걸림 이 본다.
판침범 = 3                 # 판이 crop 안으로 들어온 깊이(px · 가로·세로 둘 다) — 이보다 얕으면 그림자 끝 한두 줄이다


def _비트crop(b, ts):
    """비트 b 의 원본 시각 ts 순간 crop (x0,y0,x1,y1) — framing.plan_beats 의 smoothstep 그대로(시작crop → crop)."""
    w, h, x1, y1 = b["crop"]
    _w, _h, x0, y0 = b.get("시작crop") or b["crop"]
    u = min(max((ts - b["t0"]) / max(b["t1"] - b["t0"], 1e-3), 0.0), 1.0)
    e = u * u * (3 - 2 * u)
    cx, cy = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e
    return cx, cy, cx + w, cy + h


def 판재기(src, log, segs=None, 출력=print):
    """→ (걸림 목록, 요약). 걸림 = [{조각, t0, t1(원본 초), 글, 판(x0,y0,x1,y1), crop, 침범}] — 화면 캡션 배경판이 crop 에 든 곳."""
    from . import 화면글자 as 화
    from .번인관문 import 관문겹침
    import math
    if 화.인식기() is None:
        if os.environ.get("S2_NO_SCREENTEXT") == "1":
            return [], "인식기 없음(S2_NO_SCREENTEXT=1) — 건너뜀"
        raise RuntimeError("판 잘림 관문 — 화면글자 인식기 없음(macOS Vision 전용). 건너뛰지 않는다(S2_NO_SCREENTEXT=1 로만)")
    후 = 화.캡션자취들(src, log=출력)                       # 판정(agy · 캐시)을 먼저 — 캐시는 그 뒤에 읽는다(화면캡션 주석)
    c = 화._캐시(src)
    sf = 화.원본fps(src)
    자취, n판없음 = [], 0
    for a in 후:
        e0, e1 = 화._가장자리(src, c, a)
        판 = 화.캡션판(src, c, a)["판"]                    # 굽기(화면캡션 → 가림)와 같은 한 번 잰 결과
        if 판:
            자취.append((a, e0, e1, 판))
        else:
            n판없음 += 1
    if not 자취:
        return [], f"화면 캡션 {len(후)}개 · 판 있는 캡션 없음"
    crops = []                                              # (조각, t0, t1, 첫 프레임, 끝 프레임(제외), crop 함수)
    for b in log.get("beats", []):
        crops.append((b["seg"], b["t0"], b["t1"], b.get("f0", round(b["t0"] * sf)), b.get("f1", round(b["t1"] * sf)),
                      lambda ts, b=b: _비트crop(b, ts)))
    for f in log.get("frames", []):
        if f.get("kind") in ("전체화면", "원문화면"):
            continue
        w, h, x, y = f["crop"]
        crops.append((f["seg"], f["t0"], f["t1"], round(f["t0"] * sf), round(f["t1"] * sf),
                      lambda ts, r=(x, y, x + w, y + h): r))
    의심, n잰 = [], 0
    for seg, c0, c1, n0, n1, cf in crops:
        sg = segs[seg] if segs and 0 <= seg < len(segs) else {}
        if sg.get("원문화면"):
            continue
        허용 = [화.판정키(x) for x in sg.get("글자허용") or [] if 화.판정키(x)]
        for a, e0, e1, 판 in 자취:
            k = 화.판정키(a["글"])
            if any(h in k for h in 허용):
                continue
            w0, w1 = max(c0, e0), min(c1, e1)
            if w1 - w0 <= 관문겹침:                           # 굽기·걸림 과 같은 자 — 0.1초 이하로 스친 비트는 겹침이 아니다
                continue
            na, nb = max(n0, math.ceil(w0 * sf - 1e-6)), min(n1 - 1, math.floor(w1 * sf + 1e-6))
            for n in range(na, nb + 1):                     # crop 은 계산으로 나온다 — 모든 프레임을 본다(그림은 안 읽는다)
                ts = n / sf
                X0, Y0, X1, Y1 = cf(ts)
                n잰 += 1
                ix = min(판[2], X1) - max(판[0], X0)
                iy = min(판[3], Y1) - max(판[1], Y0)
                if ix >= 판침범 and iy >= 판침범:
                    변 = [n_ for n_, v in (("왼", X0 - 판[0]), ("오", 판[2] - X1), ("위", Y0 - 판[1]), ("아래", 판[3] - Y1)) if v > 0]
                    의심.append({"조각": seg, "t": ts, "글": a["글"], "판": [int(v) for v in 판],
                                 "crop": [int(X0), int(Y0), int(X1), int(Y1)], "침범": f"{int(ix)}×{int(iy)}px",
                                 "잘림": "crop " + "·".join(변) + " 끝에 판이 잘림" if 변 else "판 전체가 crop 안"})
    걸 = []
    for v in sorted(의심, key=lambda v: (v["조각"], v["글"], v["t"])):
        if 걸 and 걸[-1]["조각"] == v["조각"] and 걸[-1]["글"] == v["글"] and v["t"] - 걸[-1]["t1"] <= 1.0:
            걸[-1]["t1"] = v["t"]
            continue
        걸.append(dict(v, t0=v["t"], t1=v["t"]))
    return 걸, (f"화면 캡션 {len(후)}개(판 {len(자취)} · 판 없음 {n판없음}) · crop 프레임 {n잰}장 맞댐 · 걸림 {len(걸)}곳")


def 판글(걸):
    return "; ".join(f"조각{g['조각']} 원본 {g['t0']:.2f}~{g['t1']:.2f}초 «{g['글'][:16]}» 판 {g['판']} vs crop {g['crop']}"
                     f" ({g['침범']} · {g['잘림']})" for g in 걸[:6]) + (f" 외 {len(걸) - 6}곳" if len(걸) > 6 else "")


def 판지침(걸):
    return ("  수리: 원본 화면 캡션의 배경판(말풍선·알림 상자·삽입 그림)이 crop 안에 든다. 굽기는 화면글자.화면캡션 의 판 사각형을"
            " 가림으로 피한다 — 먼저 `python -m s2pipe.화면글자 <원본> --판정` 으로 그 캡션의 «판» 이 잡혔는지 본다(판 크기가"
            " 실제 판보다 작으면 화면글자.배경판 을 실측으로 고치고 검수도구/배경판시험.py 에 표본을 넣는다). 판이 맞는데 걸리면 비트 사이 움직임"
            " (시작crop→crop)이 판을 지나간 것이다 — 그 조각을 나누거나 샷을 옮긴다. 장면 글자면 조각 «글자허용»."
            " 조각 «가림» 손 땜질 금지(2026-10-03 루키치163).")


if __name__ == "__main__":
    if "--판" in sys.argv:                                  # python -m s2pipe.비침관문 --판 <원본.mp4> <beats.json> [projects/<슬러그>.json]
        a = [x for x in sys.argv[1:] if x != "--판"]
        lg = json.load(open(a[1], encoding="utf-8"))
        sg = [s for s in json.load(open(a[2], encoding="utf-8"))["segments"] if s.get("keep", True)] if len(a) > 2 else None
        걸, 요 = 판재기(a[0], lg, sg)
        print(요)
        for g in 걸:
            print("  걸림", 판글([g]))
        sys.exit(1 if 걸 else 0)
    cut, src, bj = sys.argv[1:4]
    lg = json.load(open(bj, encoding="utf-8"))
    걸, 요 = 재기(cut, src, lg)
    print(요)
    for g in 걸:
        print("  걸림", 글([g]))
    sys.exit(1 if 걸 else 0)
