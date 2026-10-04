#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""준비_prproj_sk.py — 조립_prproj_sk 의 입력 한 벌을 만든다.

  ① 납품 폴더(<workdir>/프리미어_<슬러그>/소스/)에 미디어 복사
     원본.mp4(그대로) · 나레_00.wav(모노 48k s16 변환) · 그래픽_템플릿.mov(껍데기, qtrle argb 30fps)
  ② 껍데기 = build.draw_frame(제목 비움) → 영상 상자(y0~y1)에 알파 구멍 → mov
     제목은 굽지 않는다 — V3 텍스트 그래픽으로 들어가 프리미어에서 수정 가능해야 하므로.
  ③ timeline_sk.json — 컷·나레·자막 큐·상자 배치(모션 값)

사용: python 준비_prproj_sk.py <편.json> --config <config.json>
"""
import argparse, json, os, subprocess, sys, wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG  # noqa: E402  (--config 인자를 걷어간다)
from s2pipe import build    # noqa: E402
from s2pipe import ff       # noqa: E402  ffmpeg·ffprobe 스레드 상한 한 곳 (2026-10-04 · 검수도구/ffmpeg스레드시험.py)
from prproj_lib_probe import ffprobe_info  # noqa: E402


def run(argv):
    subprocess.run(argv, check=True, capture_output=True)


def 텍스트검출(rgb, row_min=12, tot_min=80, top=False):
    """외곽선 자막 검출 — 밝은 픽셀(≥210)에 맞닿은 어두운 픽셀(≤90)을 센다. 색 무관.
       ★2026-09-03 재보정(Deep03 «어디가 편하세요?» 실측): 외곽선이 얇고 흐린 자막은
       (200/70) 기준으로 행 8·총 41 뿐이라 문턱(15/40)에 미달했다. (210/90)으로 넓히면
       얇은 자막 행 20~24·총 144+ vs 진짜 무자막 행 ≤5·총 ≤22 — 깨끗이 갈린다(11프레임 실측).
       top=True 면 (검출여부, 검출 최상단 행) 을 돌려준다 — 자막 윗변 실측용."""
    import numpy as np
    g = np.asarray(rgb).astype(int)
    if g.ndim == 3:
        g = g.mean(axis=2)
    bright = g >= 210
    dark = g <= 90
    bd = np.zeros_like(bright)
    bd[1:, :] |= bright[:-1, :]
    bd[:-1, :] |= bright[1:, :]
    bd[:, 1:] |= bright[:, :-1]
    bd[:, :-1] |= bright[:, 1:]
    c = bd & dark
    rows = c.sum(axis=1)

    # ★띠 창 판정 (2026-09-05… 2026-09-03 Deep05 실측) — 자막은 세로 130px 이내의 얇은
    #   띠다. 흰 셔츠×넥타이 같은 고대비 질감은 세로로 넓게 퍼져 창에 안 모인다(컷1 오탐
    #   → 무한 승격 사건). 130px 미끄럼 창에서 최대 합을 찾아 그 창 안에서만 판정한다.
    def 띠검출(rows_, row_min_, tot_min_):
        n = len(rows_)
        cs = np.concatenate([[0], np.cumsum(rows_)])
        W = min(130, n)
        best, bi = -1, 0
        for i0 in range(0, n - W + 1):
            v = int(cs[i0 + W] - cs[i0])
            if v > best:
                best, bi = v, i0
        창 = rows_[bi:bi + W]
        if best >= tot_min_ and int(창.max()) >= row_min_:
            strong = np.where(창 >= max(4, row_min_ // 2))[0]
            return True, bi + (int(strong[0]) if len(strong) else 0)
        return False, None

    후보 = []
    h1, t1_ = 띠검출(rows, row_min, tot_min)
    if h1 and t1_ is not None:
        후보.append(t1_)
    a3 = np.asarray(rgb).astype(int)
    if a3.ndim == 3:
        # 외곽선 없는 노란 예능자막 (Deep03 실측)
        노랑 = (a3[:, :, 0] >= 200) & (a3[:, :, 1] >= 170) & (a3[:, :, 2] <= 140)
        h2, t2_ = 띠검출(노랑.sum(axis=1), row_min, 1500)
        if h2 and t2_ is not None:
            후보.append(t2_)
        # 유채색 자막 전반 (Deep04 «딱 먹고» 실측) — ★문턱 110/170 (2026-09-03 Deep05:
        #   80/150 은 살구 피부·옷을 3만 픽셀 오탐. 110/170 실측 = 피부 0 vs 색자막 5,540+)
        mx3 = a3.max(axis=2)
        채도 = ((mx3 - a3.min(axis=2)) >= 110) & (mx3 >= 170)
        h3, t3_ = 띠검출(채도.sum(axis=1), row_min, 1200)
        if h3 and t3_ is not None:
            후보.append(t3_)
        hit = h1 or h2 or h3
    else:
        hit = h1
    if not top:
        return hit
    return hit, (min(후보) if hit and 후보 else None)


# 카드·로고의 순백 배경을 껍데기 배경색으로 (2026-09-01 사장님) — 정의는 build 한 곳(2026-09-29 옮김:
#   mp4 머리 로고도 같은 처리를 쓴다). 계산은 옮기기 전과 같다.
배경맞춤 = build.배경맞춤


from s2pipe import 화자색  # noqa: E402  대사 큐·화자 판정·색 — ⑥ 굽기와 같은 함수 (2026-09-28)
from s2pipe.화자색 import 화자판정, 화자교정적용  # noqa: E402,F401  (옮김 2026-09-28 — 화자재판정.py 가 여기서 가져간다)


def 댓글선별(pngs, logline, want=(10, 15)):
    """댓글 카드 PNG 중 편 내용과 어울리는 것을 모델이 고른다 (EvoLink 무료 한도).
       ★최소 10장(2026-09-01 사장님). 판정이 실패하면 앞에서 12장을 그대로 쓴다."""
    import base64
    from s2pipe import gem
    from s2pipe.cfg import CFG as _C
    models = _C.get("gemini", {}).get("models", ["gemini-3.5-flash"])
    parts = [{"text": (f"숏폼 내용: {logline}\n아래 번호 붙은 유튜브 댓글 카드 중 이 내용과 어울리는 것을 "
                       f"{want[0]}~{want[1]}개, 어울리는 순서대로 골라라. JSON 만: {{\"picks\":[번호,...]}} (0부터)")}]
    for i, p in enumerate(pngs):
        parts.append({"text": f"[{i}]"})
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(open(p, "rb").read()).decode()}})
    payload = {"contents": [{"role": "user", "parts": parts}],
               "generationConfig": {"maxOutputTokens": 1000, "responseMimeType": "application/json"}}
    import re as _re
    try:
        from agy_gemini import AgyStop as gem_AgyStop
    except Exception:                                    # noqa: BLE001
        class gem_AgyStop(Exception):
            pass
    for 시도 in range(2):                      # ★빈 응답이 잦다(2026-09-03 실측) — 한 번 더 준다
        try:
            txt, _r, _m = gem.ask(payload, models, timeout=300)
            m = _re.search(r"\[[\d,\s]+\]", txt or "")
            picks = [i for i in json.loads(m.group(0) if m else "x") if 0 <= int(i) < len(pngs)]
            picks = list(dict.fromkeys(int(i) for i in picks))
            assert len(picks) >= want[0]
            return [pngs[i] for i in picks[:want[1]]]
        except (Exception, gem_AgyStop) as e:           # ★안전 필터 거절(AgyStop)도 «앞에서 12장» 폴백으로(2026-09-27)
            print(f"댓글 선별 {시도 + 1}차 실패:", str(e)[:60])
    print("댓글 선별 실패 — 앞 12장 사용")
    return pngs[:12]


def main():
    # ★게이트(2026-09-03) — cv2 없는 파이썬으로 돌리면 얼굴 검출이 조용히 기본값(960,430)으로
    #   떨어져 인물 포커싱이 전부 어긋난다(Deep01~03 실측). 러너 venv 로만 돈다.
    try:
        import cv2  # noqa: F401
    except ImportError:
        sys.exit("★cv2 없음 — 러너 venv 로 실행하라: ~/.volcano/venv/bin/python3 준비_prproj_sk.py …")
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    a = ap.parse_args()
    proj = json.load(open(a.project, encoding="utf-8"))
    slug = proj["slug"]
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(a.project)))
    wdir = os.path.join(workdir, "work", slug)
    src_orig = os.path.join(workdir, "work", proj["source"]["id"] + ".mp4")
    out_root = os.path.join(workdir, f"프리미어_{slug}")
    sdir = os.path.join(out_root, "소스")
    os.makedirs(sdir, exist_ok=True)

    segs = [s for s in proj["segments"] if s.get("keep")]
    total = sum(s["t1"] - s["t0"] for s in segs)
    # ★끝맺음 여운(2026-09-01 사장님: 하드컷이 너무 급하다) — 마지막 컷을 원본에서 연장.
    #   ★반드시 템플릿 굽기·댓글 슬롯 계산 «앞»에서 늘린다 — 뒤에서 늘렸다가 템플릿 mov 가
    #   여운만큼 짧아 끝 0.8초에 껍데기가 통째로 비었다(2026-09-02 사장님 실측 «템플릿 빠짐»).
    #   ★편별 조절: proj["여운"] — 원본이 결말 직후 엔딩 카드로 넘어가는 소재(Deep04 실측:
    #   301.2s 부터 «This is Fiction» 카드가 깜빡이며 시작)는 0 으로 꺼서 카드 침범을 막는다.
    # ★여운 상한 — 원본 아웃트로 카드 앞에서 멈춘다(2026-09-09 사장님 «마지막에 싱글벙글 로고만
    #   떠있고 … 로고 나오게 하지말고 종결지어줘»). 굽기(build.cut_and_join)가 소재 꼬리의 정적
    #   브랜드 카드(남색 «싱글벙글»)를 감지해 마지막 조각 t1 을 그 앞에서 끊고 «_엔드카드시작» 을
    #   조각에 남긴다(계획 JSON 에 저장 → 준비가 읽는다). 카드가 있으면 여운을 0 으로 — 여운은
    #   원본을 앞으로 더 재생하는데 그 앞이 곧 카드라 늘리면 카드가 다시 뜬다.
    _막 = segs[-1]
    # ★프리미어 컷 창 = 굽기 창 (2026-09-28 «경계 1프레임 튐» 클래스) — 컷 in 점·길이·여운을 굽기와 같은 원본 프레임
    #   번호로 정한다(s2pipe/프레임격자.py · build.조각틀). 예전엔 in 점 = 조각 t0(초) 그대로라, t0 가 프레임보다 조금
    #   앞(p−0.002 — 배치 에이전트가 손으로 넣던 꼴)이면 컷 첫 화면이 앞 샷 마지막 프레임이었다(프리미어는 in 점이 든
    #   프레임을 보여 준다 — 추정, 확인은 프리미어에서 컷 첫 프레임 보기).
    from s2pipe import 프레임격자 as _G
    _격 = _G.얻기(src_orig)
    _bj0 = None
    try:
        _bj0 = json.load(open(os.path.join(wdir, "beats.json"), encoding="utf-8"))
        if not (len(_bj0.get("segments", [])) == len(segs) and all(
                abs(e["t0"] - s_["t0"]) < 0.01 for e, s_ in zip(_bj0["segments"], segs))):
            _bj0 = None
    except Exception:                                      # noqa: BLE001
        _bj0 = None
    컷창 = []                                              # 컷마다 (원본 첫 프레임, 프레임 수)
    for _i, _s in enumerate(segs):
        _e = (_bj0 or {}).get("segments", [None] * len(segs))[_i] if _bj0 else None
        if _e and "f0" in _e:
            _A, _M, _N = _e.get("앞멈춤", 0), _e["M"], _e["N"]
            _r = _e["f0"] + _A                                 # 실제 첫 프레임
            _f0 = _r - _A
            if _N > _M:
                # 호환 굽기가 머리·끝 장을 멈춰(같은 장을 더 보여) 다른 샷 번쩍임을 막은 컷 — 프리미어는 멈춤을 못 하니
                #   실제 프레임 앞뒤로 «같은 샷» 프레임을 채워 N 장 창을 만든다. mp4 와 가장 가깝게(앞 x 장 · 뒤 N−M−x 장).
                def _됨(x):
                    앞 = all(not _G.전환인가(src_orig, _격, k) for k in range(_r - x + 1, _r + 1)) if x else True
                    뒤 = not _G.전환들(src_orig, _격, _r + _M, tuple(range(0, _N - _M - x))) if _N - _M - x else True
                    return 앞 and 뒤
                _후 = sorted(range(0, _N - _M + 1), key=lambda x: abs(x - _A))
                _x = next((x for x in _후 if _됨(x)), None)
                assert _x is not None, (
                    f"컷{_i + 1:02d}: 호환 굽기(옛 자막 시간축)가 앞 {_A}장·끝 {_e.get('뒤멈춤', 0)}장을 멈춰 다른 샷 번쩍임을 막은 컷인데 "
                    f"앞뒤가 모두 화면 전환이라 프리미어에선 막을 수 없다 — 조각 t0/t1 을 전환 프레임 시각으로 고친 뒤 FROM=2 로 "
                    f"다시 구워라(③ 재전사 유료)")
                _f0 = _r - _x
                print(f"  컷{_i + 1:02d}: 호환 굽기 멈춤(앞 {_A}·끝 {_e.get('뒤멈춤', 0)}장) → 프리미어는 같은 샷 {_x}장 앞부터"
                      + (f" (mp4 보다 {_A - _x:+d}장 — 이 컷 소리·자막 {(_A - _x) * 1000 / _격.fps:+.0f}ms)" if _x != _A else ""))
        else:
            _f0 = _격.번호(_s["t0"])
            _N = int(round((_e["out_dur"] if _e else (_s["t1"] - _s["t0"])) * _격.fps))
        컷창.append((_f0, _N))
    _여운전끝 = 컷창[-1][0] + 컷창[-1][1]                  # 이야기 마지막 프레임 다음 번호(여운이 시작하는 자리)
    # 여운이 원본을 앞으로 더 재생하는데 그 앞에 아웃트로 카드가 있으면 카드가 다시 뜬다. 카드의
    #   절대 시작점을 직접 구해 여운을 그 앞에서 멈춘다(굽기가 트림 안 한 경우도 안전 — 2026-09-10).
    # ★끝 벽 = 아웃트로 카드 «앞» 의 암전·페이드·로고 겹침까지 (2026-10-03 루키치156·159·164·273 — 카드 감지 하나로만 벽을 정해
    #   여운이 한 장 암전·밝아지는 카드·풍경 위 로고를 담았다. 배치 에이전트가 거의 매 편 손으로 «여운: 0» 을 넣었다).
    # ★판정은 s2pipe/경계자리.결말벽판정 한 곳 «같은 인자» 로 (2026-10-04 루키치87 — 37da614 는 함수만 하나로 했고 인자는 부르는
    #   쪽마다 달랐다: 준비는 창 끝 = 이야기끝+여운+0.2 · 계획 dur · 하한 t0+2 로 아웃트로를 쟀고, prproj끝검사는 창 끝 = 프리미어 끝
    #   +0.05 · 파일 길이 · 하한 이야기끝. 같은 원본에서 준비 208.123(로고) · 끝검사 208.039(페이드) — 여운이 1장 넘어 납품 반려).
    #   이제 이야기끝 = 컷창으로 정한 «여운이 시작하는 프레임» 시각(= timeline 여운.전_src_end), 굽기카드 = 계획의 _엔드카드시작 —
    #   이 둘을 timeline 에 그대로 적고 끝검사가 같은 함수에 같은 값으로 다시 잰다. 아래 «여운관문» 이 굽기·조립 전에 끝검사와
    #   같은 판정을 미리 돌려, 어긋나면 여기서 멈춘다.
    from s2pipe import 경계자리 as _벽
    _이야기끝 = _격.시작(_여운전끝)
    _굽기카드 = float(_막["_엔드카드시작"]) if _막.get("_엔드카드시작") else None
    _결말판 = _벽.결말벽판정(src_orig, _이야기끝, _굽기카드)
    결말벽, 결말벽까닭 = _결말판["벽"], _결말판["까닭"]
    if 결말벽 is not None:
        print(f"  결말 벽 {결말벽:.3f}s — {결말벽까닭} (이야기 끝 {_이야기끝:.3f}s · 여운은 그 1프레임 앞까지)")
    여운_상한 = 결말벽 if 결말벽 is not None else (proj["source"]["dur"] - 0.3)
    # ★결말확인 편(스토리가 원본 끝보다 앞에서 완결 — 뒤는 무관한 다른 스킷)은 여운을 끈다:
    #   여운은 원본을 앞으로 더 재생하는데 그 뒤가 다른 스킷이면 엉뚱한 장면이 붙는다
    #   (2026-09-10 싱글369: 합의금 결말 160.7s 뒤 바로 택시 꼰대 스킷 162s).
    여운 = 0.0 if proj.get("결말확인") else float(proj.get("여운", 1.8))
    assert 여운 + 0.2 <= _벽.결말창, (
        f"여운 {여운}초가 결말 벽 창({_벽.결말창}초)보다 길다 — 벽을 다 못 본다. s2pipe/경계자리.결말창을 늘려라")
    ext = max(0.0, min(여운, 여운_상한 - _막["t1"]))
    # ★받침: 엔드카드 검출이 놓쳐도 여운 안에 남색 «싱글벙글» 카드 프레임이 있으면 그 앞에서 멈춘다
    #   (2026-09-27 100편 배치 — 싱글201·212·246 프리미어 끝에 로고 카드가 0.1~1.8초 붙었다. 카드 평균색 실측
    #   RGB≈(40,43,87)). 0.1초 간격으로 보고 첫 남색 프레임 0.05초 앞에서 끊는다.
    if ext:
        _t = _막["t1"]
        while _t < _막["t1"] + ext:
            _r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{_t:.2f}", "-i", src_orig, "-frames:v", "1",
                                 "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]),
                                capture_output=True).stdout
            _k = len(_r) // 3
            if _k:
                # (이름 _적·_녹·_청 — _G 는 위에서 불러온 프레임격자다. 이 받침을 컷창 뒤로 옮기며 _G 를 덮어써 죽은 것 2026-10-04)
                _적, _녹, _청 = sum(_r[0::3]) / _k, sum(_r[1::3]) / _k, sum(_r[2::3]) / _k
                if _적 < 70 and _녹 < 70 and _청 > 70 and _청 - _적 > 25:
                    ext = max(0.0, _t - 0.05 - _막["t1"])
                    print(f"  여운 안 {_t:.2f}s 에 남색 로고 카드 — 여운 {ext:.2f}s 로 줄임")
                    break
            _t += 0.1
    if ext and 결말벽 is not None:
        # 벽 프레임 «1장 앞» 까지만 — 벽 바로 앞 한 장은 암전·카드로 섞여 드는 첫 장일 수 있다(안전 여유 1프레임)
        _벽장 = _격.번호(결말벽) - _여운전끝 - 1
        if int(ext * _격.fps + 1e-6) > _벽장:
            ext = _격.길이(_여운전끝, _여운전끝 + _벽장) if _벽장 > 0 else 0.0
    if ext:
        # ★여운은 프레임 단위로, 마지막 샷 안에서만 (2026-09-28) — 여운이 화면 전환을 넘으면 «마지막 컷 연장» 이 아니라
        #   다른 샷이 붙고, 끝 1~2장에 걸리면 번쩍임이다. 전환 프레임 앞에서 끝낸다.
        _k1 = 컷창[-1][0] + 컷창[-1][1]
        _n = int(ext * _격.fps + 1e-6)
        _전 = _G.전환들(src_orig, _격, _k1, tuple(range(0, _n + 1))) if _n > 0 else []
        if _전:
            print(f"  여운 안 원본 {_격.시작(min(_전)):.3f}s 에 화면 전환 — 여운 {_n}장 → {min(_전) - _k1}장 (마지막 샷 안에서만)")
            _n = min(_전) - _k1
        ext = _격.길이(_k1, _k1 + _n) if _n > 0 else 0.0
    # 관문: 여운 끝 ≤ 결말 벽 − 1프레임 (위 상한이 뒤에서 다른 길로 풀리면 여기서 멈춘다 — 2026-10-03 156·159)
    if 결말벽 is not None:
        _여운장 = int(round(ext * _격.fps)) if ext else 0
        assert _여운전끝 + _여운장 <= _격.번호(결말벽) - 1 or _여운장 == 0, (
            f"여운 끝(원본 {_격.시작(_여운전끝 + _여운장):.3f}s)이 결말 벽 {결말벽:.3f}s({결말벽까닭})를 넘는다 — "
            f"s2pipe/경계자리.결말벽 상한이 풀렸다")
    # ★관문(2026-10-04 루키치87): 납품 관문(prproj끝검사)과 «같은 함수·같은 기록» 으로 미리 잰다 — timeline 에 적을 여운 기록
    #   그대로 경계자리.여운관문을 부른다. 두 판정의 벽이 다르거나(인자·창이 갈림) 여운 끝이 벽을 넘으면 템플릿 굽기·조립 «전» 에
    #   멈춘다(87 은 ⑧ 조립·납품까지 가서야 반려됐다). 아래 timeline 쓰기 직전에 컷 목록으로 한 번 더 잰다.
    _여운기록 = {"전_src_end": round(_이야기끝, 4), "초": round(ext, 4), "벽": 결말벽, "까닭": 결말벽까닭,
               "굽기카드": _굽기카드, "원본": os.path.abspath(src_orig)}
    _여관 = _벽.여운관문(src_orig, _여운기록, _격.시작(_여운전끝 + (int(round(ext * _격.fps)) if ext else 0)))
    print(("  [OK] " if not _여관["탈"] else "  [X] ") + "여운 관문(납품 끝검사와 같은 자) — " + _여관["글"])
    assert not _여관["탈"], (f"결말 벽 판정이 납품 관문과 어긋나거나 여운이 벽을 넘는다 — {_여관['글']} · "
                          f"s2pipe/경계자리.결말벽판정·여운관문을 보라(손으로 «여운» 을 넣지 말 것)")
    if ext:
        segs[-1] = dict(segs[-1], t1=segs[-1]["t1"] + ext, _여운전t1=segs[-1]["t1"])
        total = round(total + ext, 4)
        print(f"끝맺음 여운 +{ext:.1f}s → 총 {total:.1f}s")

    # ① 미디어 — ★프리미어가 읽는 코덱만 넣는다 (2026-09-01 실측: 유튜브 AV1 원본 → 비디오만
    #   미디어 오프라인, 소리(AAC)는 정상. 경로·메타가 아니라 코덱이 원인이었다)
    지원코덱 = {"h264", "hevc", "prores", "qtrle", "mpeg4", "mjpeg", "dnxhd"}

    def vcodec(path):
        out = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=codec_name", "-of", "csv=p=0", path]),
                             check=True, capture_output=True)
        return out.stdout.decode().strip()

    dst_src = os.path.join(sdir, "원본.mp4")
    if os.path.exists(dst_src) and vcodec(dst_src) not in 지원코덱:
        os.remove(dst_src)                     # 이전에 복사된 미지원 코덱본 폐기
    if not os.path.exists(dst_src):
        if vcodec(src_orig) in 지원코덱:
            import shutil
            shutil.copy2(src_orig, dst_src)
        else:
            print(f"원본 코덱 {vcodec(src_orig)} — 프리미어 미지원 → H.264 변환 (수 분)")
            subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", src_orig,
                            "-vf", "fps=24000/1001", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "16", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst_src]), check=True)
    assert vcodec(dst_src) in 지원코덱, "원본 변환 실패 — 코덱 " + vcodec(dst_src)
    dst_nar = os.path.join(sdir, "나레_00.wav")
    # ★나레 wav 이름은 나레가 붙은 조각 번호를 따른다(narr01·narr02…) — 하드코딩 금지
    #   (2026-09-03 Deep04: 나레가 2번째 조각이라 narr02.wav 였는데 narr01 을 찾다 죽었다)
    import glob as _gl
    # ★나레가 붙은 조각이 둘 이상이면 멈춘다 — 아래 prproj 조립은 나레 한 줄만 싣는다. 예전엔 첫째만 싣고 둘째를
    #   조용히 버려 완성본 mp4(나레 2)와 프리미어(나레 1)가 달랐는데 체인은 «통과» 였다 (2026-09-27 싱글186).
    #   이름도 glob 첫째가 아니라 «나레 조각 번호» 로 정확히 집는다 — 나레를 다른 조각으로 옮겨 다시 구우면
    #   옛 narrNN.wav 가 남아 glob 첫째가 낡은 나레일 수 있다.
    _나레조각 = [i for i, s_ in enumerate(proj["segments"]) if (s_.get("narration") or "").strip()]
    assert len(_나레조각) == 1, (f"나레가 붙은 조각이 {len(_나레조각)}개({_나레조각}) — 프리미어는 나레 1줄만 싣는다. "
                                 "plan 에서 나레를 한 조각에만 남기고 다시 구워라")
    나레들 = [os.path.join(wdir, f"narr{_나레조각[0]:02d}.wav")]
    assert os.path.isfile(나레들[0]), f"나레 wav 가 없다: {나레들[0]} — make 굽기를 먼저 돌려라"
    run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", 나레들[0],
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", dst_nar]))
    # ★나레도 내용 지문 이름 — 같은 이름 제자리 교체는 프리미어 캐시와 섞인다
    #   (2026-09-03 템플릿 화면 뒤섞임 사건과 같은 함정)
    import hashlib as _hl0
    _hn = _hl0.md5(open(dst_nar, "rb").read()).hexdigest()[:8]
    _새nar = os.path.join(sdir, f"나레_00_{_hn}.wav")
    os.replace(dst_nar, _새nar)
    for _fn in os.listdir(sdir):
        if _fn.startswith("나레_00") and _fn != os.path.basename(_새nar):
            try:
                os.remove(os.path.join(sdir, _fn))
            except OSError:
                pass
    dst_nar = _새nar

    # ② 껍데기 — 제목 «없는» frame → 알파 구멍 → mov
    #   ★제목은 껍데기에 굽지 않는다(2026-09-08 사장님 A안 — «프리미어에서 수정할 수 있어야 해»).
    #   보이는 제목은 V3 텍스트 그래픽이 담당한다: 조립기가 도너 견본 서식(노랑 112·Paperlogy)을
    #   규격(S-CoreDream-7ExtraBold·96·#111111·잉크 y305/422)으로 갈아 끼우고 위치를 화면 안에 박는다.
    #   (2026-09-01 «정위치·검은색 보장» 굽기는 서식 교체를 못 풀어 증상만 가린 것이었다.)
    #   ★Deep 흐름(work/<슬러그>_로고.png 존재): 헤더는 사장님 지정 로고 이미지로 갈고
    #   (배치는 최하연님 작업 prproj 실측 — 위치 0.1993:0.0699 · 비율 16.45% · 값은 build.로고_자리·로고_비율 한 곳),
    #   댓글 카드 PNG 를 선별해 슬롯 순환으로 굽는다(위치 0.5:0.8126 · 폭 1020 = 실측).
    from PIL import Image
    import copy as _copy
    import re as _re
    p_draw = _copy.deepcopy(proj)
    p_draw["title"] = []          # 제목은 V3 텍스트 그래픽이 그린다 — 껍데기에서 뺀다 (2026-09-08 A안)
    cr = p_draw.get("credit") or {}
    if cr.get("title"):
        import unicodedata as _ud
        # ★NFD(맥 파일명 자모 분해)·이모지는 폰트가 못 그린다 — 출처 줄이 «#띱 Deep -» 에서 끊긴 실측
        cr["title"] = _ud.normalize("NFC", cr["title"])
        cr["title"] = _re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]", "", cr["title"]).strip()
    frame_png = os.path.join(sdir, "_frame.png")
    build.draw_frame(p_draw, frame_png)
    im = Image.open(frame_png).convert("RGBA")
    b = CFG["layout"]["video_box"]
    L = CFG["layout"]
    bg = tuple(int(L["bg"][i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    logo_p = os.path.join(wdir, os.pardir, f"{slug}_로고.png")
    logo_p = os.path.normpath(logo_p)
    deep = os.path.exists(logo_p)
    # ★헤더 전체(로고+핸들+파란 배지+채널명)를 config 로 그리는 채널(숨은기록: channel.handle +
    #   header.font 있음)은 draw_frame 헤더가 정본이다 — MP4 와 같은 소스. 아래 «로고만» 교체는
    #   옛 Deep(최하연 스캐치독: 헤더가 로고 이미지 하나뿐)용이라, 숨은기록에 돌리면 hidden_story·
    #   배지·숨은기록 글씨를 배경색으로 덮어 지운다(2026-09-09 사장님 «로고 옆 문구·로고인증 반영
    #   안 됨» — MP4 엔 있는데 prproj 엔 없던 진짜 원인: 헤더 소스가 MP4·prproj 로 갈렸다).
    #   ★머리를 로고 그림 한 장으로 그리는 채널(config channel.logo_image — 누룽지독 템플릿 2026-09-29)도
    #   draw_frame 이 이미 같은 함수(build.로고얹기)·같은 자리로 얹었다 — 여기서 다시 갈지 않는다.
    _설정로고 = CFG["channel"].get("logo_image")
    헤더전체 = bool(_설정로고 or (CFG["channel"].get("handle") and L["header"].get("font")))
    if _설정로고 and deep:
        # ★편시작 --로고 와 설정 로고가 다른 그림이면 멈춘다 — mp4·프리미어 머리는 설정 그림으로 그려지므로
        #   다른 그림을 준 편은 사장님이 뜻한 로고가 어느 쪽인지 모른다(2026-09-29 점심이네 = 누룽지독 고정).
        _a = Image.open(logo_p).convert("RGBA")
        _b = Image.open(os.path.join(build.HERE, _설정로고)).convert("RGBA")
        if _a.size != _b.size or _a.tobytes() != _b.tobytes():
            raise SystemExit(f"★편시작 --로고({logo_p}) 가 설정 channel.logo_image({_설정로고}) 와 다른 그림이다 — "
                             "mp4·프리미어 머리는 설정 그림으로 그린다. 어느 로고인지 사장님께 여쭙고 "
                             "편시작을 그 로고로 다시(또는 설정을 고쳐) 돌려라")
    if deep and not 헤더전체:
        hd = L["header"]
        im.paste(Image.new("RGBA", (1080, hd["y1"] - hd["y0"] + 40), bg), (0, hd["y0"] - 20))
        build.로고얹기(im, logo_p, bg)                # 자리·비율 = 최하연 실측(build.로고_자리·로고_비율)
    if deep:
        # ★댓글 영역을 배경색으로 비운다 — draw_frame 이 그린 가짜 댓글 UI(아이콘·닉·날짜)를 지우고
        #   진짜 댓글 카드 PNG 를 그 자리에 얹기 위해. 헤더 방식과 무관하게 댓글 카드가 있으면 돈다
        #   (2026-09-09 헤더/댓글 분리 — 숨은기록도 카드를 쓴다).
        cm = L["comment"]
        im.paste(Image.new("RGBA", (1080, cm["y1"] - cm["y0"] + 40), bg), (0, cm["y0"] - 20))
    hole = Image.new("RGBA", (b["w"], b["y1"] - b["y0"]), (0, 0, 0, 0))
    im.paste(hole, (0, b["y0"]))
    rgba = os.path.join(sdir, "_frame_hole.png")
    im.save(rgba)
    dst_tpl = os.path.join(sdir, "그래픽_템플릿.mov")
    cmt_overlays = []
    if deep:
        import glob as _g
        pngs = sorted(_g.glob(os.path.join(wdir, os.pardir, f"{slug}_댓글", "**", "*.png"), recursive=True))
        # 댓글 선별도 같은 까닭으로 저장본을 쓴다(댓글 파일·로그라인이 같으면 답이 같다)
        import hashlib as _hl2
        _댓키 = _hl2.sha1(json.dumps([[os.path.basename(p_), os.path.getsize(p_)] for p_ in pngs] +
                                    [proj.get("logline", "")], ensure_ascii=False).encode()).hexdigest()
        _댓캐 = os.path.join(wdir, "_댓글선별캐시.json")
        try:
            _dc = json.load(open(_댓캐, encoding="utf-8"))
        except Exception:                                # noqa: BLE001
            _dc = {}
        if _댓키 in _dc and all(os.path.exists(p_) for p_ in _dc[_댓키]):
            picked = _dc[_댓키]
            print(f"댓글 선별 — 저장본 사용 · {len(picked)}장")
        else:
            picked = 댓글선별(pngs, proj.get("logline", ""))
            json.dump({_댓키: picked}, open(_댓캐, "w", encoding="utf-8"), ensure_ascii=False)
        slots = max(len(picked), 1)
        each = total / slots
        # 댓글 자리 = 영상 상자 아래 ~ 출처 위 (침범 금지 · 좌우 꽉차게 — 2026-09-01 사장님)
        zone0, zone1 = b["y1"] + 8, L["credit"]["y0"] - 10
        zone_h = zone1 - zone0
        for i, p in enumerate(picked):
            c = 배경맞춤(Image.open(p), bg)
            w2, h2 = 1080, int(c.height * 1080 / c.width)
            if h2 > zone_h:                              # 긴 카드는 자리 높이에 맞춰 줄인다
                w2, h2 = int(c.width * zone_h / c.height), zone_h
            c = c.resize((w2, h2))
            cp = os.path.join(sdir, f"_cmt{i:02d}.png")
            c.save(cp)
            # ★상단 정렬(2026-09-01 사장님) — 영상 바로 아래 붙이되(침범 없음) 세로 중앙이 아니라 위로
            cmt_overlays.append((cp, i * each, (i + 1) * each, (1080 - w2) // 2, zone0))
        print(f"댓글 {len(picked)}장 → 슬롯 {each:.1f}초씩 · 자리 y{zone0}~{zone1}")
    # ★원문화면 띠 (2026-09-07 사장님 «위아래가 검은색으로 짤리는 게 맞아?» — fit-width
    #   컷의 상자 위아래 빈 띠가 프리미어에선 시퀀스 검정으로 보였다): 그 구간만 템플릿이
    #   띠를 페이지색으로 덮는다 → 페이지 위에 카드가 놓인 모양. 띠 높이 = (상자 908 −
    #   카드 608)/2 = 150px, 굽기(compose)의 페이지색 채움과 같은 기하.
    카드h = 608          # 1080×(1080/1920)=607.5 → ffmpeg scale -2 와 같은 짝수 올림
    띠h = (b["y1"] - b["y0"] - 카드h) // 2
    누c = 0.0
    띠png = None
    for s in (x for x in proj.get("segments", []) if x.get("keep", True)):
        a0, a1 = 누c, 누c + s["t1"] - s["t0"]
        누c = a1
        if not (s.get("원문화면") or s.get("전체화면")):
            continue
        if 띠png is None:
            띠png = os.path.join(sdir, "_원문띠.png")
            Image.new("RGB", (1080, 띠h), bg[:3]).save(띠png)
        cmt_overlays.append((띠png, a0, a1, 0, b["y0"]))
        cmt_overlays.append((띠png, a0, a1, 0, b["y1"] - 띠h))
        print(f"  원문화면 띠 {a0:.1f}~{a1:.1f}s — 상자 위아래 {띠h}px 페이지색")
    if cmt_overlays:
        args = ff.명령(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", rgba])
        for cp, *_r in cmt_overlays:
            args += ["-loop", "1", "-i", cp]
        fc, cur = "", "[0]"
        for i, (_cp, a0, a1, x, y) in enumerate(cmt_overlays):
            nxt = f"[v{i}]"
            fc += f"{cur}[{i + 1}]overlay={x}:{y}:enable='between(t,{a0:.2f},{a1:.2f})'{nxt};"
            cur = nxt
        fc = fc[:-1]
        args += ["-filter_complex", fc, "-map", cur, "-t", f"{total + 1:.3f}",
                 "-r", "30", "-c:v", "qtrle", "-pix_fmt", "argb", dst_tpl]
        run(args)
    else:
        run(ff.명령(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", rgba, "-t", f"{total + 1:.3f}",
             "-r", "30", "-c:v", "qtrle", "-pix_fmt", "argb", dst_tpl]))
    # 되읽기 게이트(2026-09-02) — 템플릿이 총길이보다 짧으면 끝에서 껍데기가 빈다
    tpl_dur = float(subprocess.run(ff.명령(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", dst_tpl]), check=True, capture_output=True).stdout)
    assert tpl_dur >= total, f"템플릿 {tpl_dur:.2f}s < 총길이 {total:.2f}s — 껍데기가 끝에서 빈다"
    # ★파일명에 내용 지문(2026-09-03 사장님 «화면 뒤섞임» 캡쳐) — 같은 이름으로 제자리
    #   교체를 반복하면 프리미어가 옛 미디어 캐시 조각과 섞어 그린다(파일 자체는 멀쩡함을
    #   프레임 추출로 실측). 내용이 바뀌면 이름이 바뀌어 항상 새 미디어로 읽힌다.
    import hashlib as _hl
    _h = _hl.md5()
    with open(dst_tpl, "rb") as _f:
        for _chunk in iter(lambda: _f.read(1 << 20), b""):
            _h.update(_chunk)
    _새tpl = os.path.join(sdir, f"그래픽_템플릿_{_h.hexdigest()[:8]}.mov")
    os.replace(dst_tpl, _새tpl)
    for _fn in os.listdir(sdir):
        if _fn.startswith("그래픽_템플릿") and _fn != os.path.basename(_새tpl):
            try:
                os.remove(os.path.join(sdir, _fn))
            except OSError:
                pass
    dst_tpl = _새tpl
    print(f"템플릿 = {os.path.basename(dst_tpl)} (내용 지문 이름 — 프리미어 캐시 충돌 차단)")

    # ③ timeline — ★조각 길이는 계획값이 아니라 **굽기 실측(beats.json)** 을 쓴다
    #   (2026-09-03 근본 수리: 조각마다 인코딩 꼬리 +0.04~0.06s 가 붙어 누적 0.3s 밀렸다.
    #    실측으로 짜면 완성본·자막·프리미어 배치가 정의상 같은 시간축이다.)
    실측세그 = None
    beats_p = os.path.join(wdir, "beats.json")
    if os.path.exists(beats_p):
        _bj = json.load(open(beats_p, encoding="utf-8"))
        if len(_bj.get("segments", [])) == len(segs) and all(
                abs(e["t0"] - s["t0"]) < 0.01 for e, s in zip(_bj["segments"], segs)):
            실측세그 = _bj["segments"]
            print("조각 길이 = 굽기 실측(beats.json) 기준")
    picture, cum = [], 0.0
    for i, s in enumerate(segs):
        d = s["t1"] - s["t0"]
        if 실측세그:
            d = 실측세그[i]["out_dur"]
            if i == len(segs) - 1 and ext > 0:
                # ★여운 몫은 ext 그대로(굽기의 검은 꼬리 절단분을 여운으로 오인하던 계산 폐기,
                #   2026-09-04) — 그리고 여운 끝 프레임이 암전이면 여운을 0 으로 한다.
                import numpy as _np2
                _r = subprocess.run(ff.명령(["ffmpeg", "-v", "error",
                                     "-ss", f"{실측세그[i]['t1'] + ext - 0.1:.2f}", "-i", dst_src,
                                     "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"]),
                                    capture_output=True)
                _a = _np2.frombuffer(_r.stdout, dtype=_np2.uint8)
                if len(_a) and float(_a.mean()) < 12:
                    print("  여운 끝이 암전 — 여운 0 처리 (검은 화면 출력 금지)")
                else:
                    d += ext
        # in 점 = 컷창 첫 프레임의 표시 시각(+1µs — int(초×TPS) 내림이 한 틱 앞 = 앞 프레임으로 떨어지지 않게)
        picture.append({"t0": round(cum, 4), "t1": round(cum + d, 4), "src_in": _격.시작(컷창[i][0]) + 1e-6,
                        "name": f'{i + 1:02d} P{s["phase"]} {s["what"][:24]}'})
        cum += d
    if 실측세그:
        total = round(cum, 4)                             # 총길이도 실측 기준으로 갱신
    # (끝맺음 여운은 위 — 템플릿 굽기 전 — 로 옮겼다. 2026-09-02)

    # ★게이트(2026-09-03 Deep02 사건 — 싱크 단계를 건너뛰어 자막이 통째로 어긋났다)
    #   자막은 완성본 재전사(s2pipe.asr)와 단어 정렬(s2pipe.sync)을 거쳐야 믿을 수 있다.
    assert proj.get("subs_before_sync"), (
        "★자막 싱크 단계를 안 거쳤다 — 먼저:\n"
        "  python -m s2pipe.asr projects/<슬러그>.json   (★유료 · 완성본 재전사)\n"
        "  python -m s2pipe.sync projects/<슬러그>.json")
    # ★컷별 원음 대조 게이트 (2026-09-03 사장님 «근본적으로 고쳐라» — _synccheck 계승)
    #   완성본(cut.mp4)의 각 컷 소리가 원본의 계획 지점과 150ms 안에서 맞아야 한다.
    #   keep 누락·경계 밀림·낡은 굽기 등 **어떤 원인이든** 여기서 걸린다.
    cut_mp4 = os.path.join(wdir, "cut.mp4")
    if os.path.exists(cut_mp4):
        import numpy as _np
        def _조각소리(path, t0, d):
            # ★t0 가 0 보다 앞이면 그만큼 앞을 무음으로 채운다 — 0 으로 끌어올리면 창이 밀려 어긋남이 가짜로
            #   나온다(2026-09-27 싱글244: 조각 시작 0.3초 · 창 −0.65 → 가짜 −0.35초로 ⑦ 이 멈췄다).
            앞 = max(0.0, -t0)
            r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{max(t0,0):.3f}", "-i", path,
                                "-t", f"{max(d - 앞, 0.01):.3f}", "-vn", "-ac", "1", "-ar", "16000",
                                "-f", "s16le", "-"]), capture_output=True)
            x = _np.frombuffer(r.stdout, dtype=_np.int16).astype(float)
            return _np.concatenate([_np.zeros(int(round(앞 * 16000))), x]) if 앞 else x
        어긋난컷 = []
        for k, pc in enumerate(picture):
            # ★다점 표본 + 일관성 판정 (2026-09-07 Deep13 실측 — 전화 장면처럼 같은 대사가
            #   근처에서 반복되는 소리는 한 점 상관이 이웃 반복에 끌려 -0.9s 오검출을 냈다.
            #   프레임 대조로 컷은 정확함을 확인. 진짜 밀림은 컷 «전체»가 같은 값으로 밀리므로
            #   세 점이 «같은 방향·같은 크기»로 어긋날 때만 실패다.)
            offs = []
            for f in (0.25, 0.5, 0.75):
                mc = pc["t0"] + (pc["t1"] - pc["t0"]) * f
                ms = pc["src_in"] + (mc - pc["t0"])
                a = _조각소리(cut_mp4, mc - 0.4, 0.8)
                bb = _조각소리(dst_src, ms - 1.6, 3.2)
                if len(a) < 6000 or len(bb) < 12000 or a.std() < 50:
                    continue                               # 무음 표본 — 판정 불가
                c = _np.correlate(bb - bb.mean(), a - a.mean(), "valid")
                i = int(_np.argmax(c))
                if i in (0, len(c) - 1):
                    continue                               # 창 끝 퇴화(무신호) — 판정 불가
                offs.append((i / 16000) - 1.2)
            if len(offs) >= 2 and all(abs(o) > 0.15 for o in offs) \
                    and max(offs) - min(offs) <= 0.1:
                어긋난컷.append((k + 1, round(sum(offs) / len(offs), 3)))
            # ★경계 겹침(더블어택) 감시 — 컷 시작 직후 80ms 넘게 어긋나면 실패
            #   (2026-09-03 «순간 배속»: 조각 꼬리 패딩이 46ms 겹쳐 들렸다)
            a2 = _조각소리(cut_mp4, pc["t0"] + 0.10, 0.5)
            bb2 = _조각소리(dst_src, pc["src_in"] - 0.65, 2.0)
            if len(a2) >= 4000 and len(bb2) >= 8000 and a2.std() >= 50:
                # ★정규화 상관 (2026-09-21 띱 7차 — Deep77·80·92·93 네 편 오탐, 실측은 전부 0ms):
                #   맨 상관(내적)은 원본 창 안의 «더 시끄러운 자리»에 끌린다. 컷 시작 직후가 조용하면
                #   (무음에 가까운 0.5초) 봉우리가 제자리(어긋남 0)가 아니라 앞뒤의 큰 소리로 가서
                #   ±0.15~0.36s 가짜 값이 나왔다 — 원본 소리만으로 같은 값이 재현됐다(경계게이트모의).
                #   창마다 원본 쪽 에너지로 나눠 «모양이 같은 자리»를 찾는다. 같은 소리면 제자리에서 1.0.
                #   봉우리가 0.5 에 못 미치면 닮은 자리가 없는 것 — 판정 불가로 넘긴다(3점 대조가 받친다).
                a0, b0 = a2 - a2.mean(), bb2 - bb2.mean()
                c2 = _np.correlate(b0, a0, "valid")
                n2 = len(a0)
                cs = _np.concatenate([[0.0], _np.cumsum(b0 * b0)])
                en = _np.sqrt(_np.maximum(cs[n2:] - cs[:-n2], 1e-9) * float((a0 * a0).sum()))
                c2 = c2 / en[:len(c2)]
                i2 = int(_np.argmax(c2))
                if c2[i2] < 0.5:
                    i2 = 0                                 # 닮은 자리 없음 — 아래에서 판정 불가로 빠진다
                if i2 not in (0, len(c2) - 1):             # 창 끝 퇴화는 판정 불가(-0.75 실측)
                    off2 = (i2 / 16000) - 0.75
                    # 이 검사의 표적은 수십 ms 겹침(더블어택) — 0.5s 넘는 값은 겹침이
                    # 아니라 상관 실패다(웃음 구간 -0.74 실측, 2026-09-07 Deep18 컷8)
                    if 0.08 < abs(off2) <= 0.5:
                        어긋난컷.append((k + 1, "경계", round(off2, 3)))
        print(("  [OK] " if not 어긋난컷 else "  [X] ") +
              f"컷별 원음 대조(±150ms) — 컷 {len(picture)}개 · 어긋남 {어긋난컷}")
        assert not 어긋난컷, "완성본 컷이 계획 지점과 어긋난다 — make 굽기·조각을 확인하라"

    # ★컷 안 통암전 게이트 (2026-09-07 Deep10 실측 — 컷6 앞 5.8초가 원본의 암전 전환부라
    #   완성본 한복판에 검은 화면이 들어갔다. 기존 암전 게이트는 «끝»(검은 꼬리·여운)만 봤다).
    #   컷마다 1초 간격 표본에서 통암전(밝기<12)이 1.5초 이상 이어지면 미완이다.
    암전컷 = []
    for k, seg in enumerate(segs):
        연속, t = 0, seg["t0"] + 0.5
        끝 = seg.get("_여운전t1", seg["t1"])   # 여운 연장분은 여운 암전 프로브가 따로 판정한다
        while t < 끝:
            r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", dst_src,
                                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"]),
                               capture_output=True)
            # ★검은 배경 위 글자 카드(블랙아웃 펀치라인)는 «통암전» 이 아니다 — 밝은 글자 픽셀이 있다
            #   (2026-09-09 Deep61 «2주 전이다» 카드 평균 0.4·밝은픽셀 3180). build.py 검은꼬리와 같은 기준.
            _밝은 = sum(1 for _x in r.stdout if _x > 60)
            어둠 = len(r.stdout) > 0 and (sum(r.stdout) / len(r.stdout)) < 12 and _밝은 < len(r.stdout) * 0.0008
            연속 = 연속 + 1 if 어둠 else 0
            if 연속 >= 2:
                암전컷.append((k + 1, round(t - 1.0, 1)))
                break
            t += 1.0
    print(("  [OK] " if not 암전컷 else "  [X] ") + f"컷 안 통암전 없음 — 걸린 컷 {암전컷}")
    assert not 암전컷, "컷 안에 통암전 구간이 있다 — 구간을 옮기거나 잘라라 (검은 화면 출력 금지)"

    subs = sorted(proj["subs"], key=lambda x: x["t"])
    nar_seg = next(s for s in segs if s.get("narration"))
    nar_sub = next((x for x in subs if x.get("kind") == "narr"), None)
    w = wave.open(dst_nar)
    nar_dur = w.getnframes() / w.getframerate()
    w.close()
    # ★나레 시작은 «나레가 붙은 조각의 머리» 하나로 정한다 — 굽기(s2pipe/build.py tts)가 나레 wav 를 그 자리에 놓으니
    #   프리미어도 같은 자리여야 완성본 mp4 와 같다. (2026-09-27 100편 배치 — 조각을 다시 짜면 초안 자막의 kind=narr
    #   줄 시각이 낡아 프리미어 나레가 완성본과 최대 14초 어긋났다: 싱글266 32.5 vs 18.11. 초안이 없으면 +0.3 을 더해
    #   0.3초 늦었다: 싱글262.) 초안 줄 시각은 이제 쓰지 않고, 다르면 알리기만 한다.
    nar_t0 = picture[segs.index(nar_seg)]["t0"]
    if nar_sub and abs(nar_sub["t"] - nar_t0) > 0.05:
        print(f"  주의  초안 나레 줄 시각 {nar_sub['t']:.2f} ≠ 조각 머리 {nar_t0:.2f} — 조각 머리(완성본과 같은 자리)를 쓴다")
    narration = [{"t0": round(nar_t0, 3), "t1": round(nar_t0 + nar_dur, 3),
                  "wav": dst_nar, "text": nar_seg["narration"]}]

    # 제목 = V3 텍스트 그래픽, 줄별 1장 · **화면 안 정위치** (2026-09-08 사장님 A안).
    #   위치 환산 근거(신병4 도너 실측): 위치 파라미터 y×1920 = 잉크 세로 중심 − 5.6px
    #   (도너 0.109063→앵커 209.4px vs 완성본_참고.mp4 잉크 중심 215px · Paperlogy 112 기준,
    #    크기 비례로 96px 은 −4.8px). 크기 단위는 픽셀 1:1(도너 112.08 → 잉크 97~99px 실측).
    #   견본 자체는 계속 clone 경로 — 견본을 갈거나 V3 를 비우면 「손상」(2026-09-01 실측 2회).
    # 효과음 (2026-09-02 사장님 승인 — 최소 원칙 3개): 훅=dun · 절정(P4)=dudun · 반전(P5)=gaze.
    #   아모르 팩 mp3 → 모노 48k wav(끝 0.4s 페이드·-6dB). 위치는 이야기 구조(phase 경계)에서 자동.
    sfx_dir = os.path.expanduser("~/Desktop/볼케이노 MCP/린박스_배포키트/자산/sfx_amor")
    sfx = []
    if os.path.isdir(sfx_dir):
        i4 = next((i for i, s_ in enumerate(segs) if s_["phase"] == 4), None)
        i5 = next((i for i, s_ in enumerate(segs) if s_["phase"] == 5), None)
        # ★자리는 s2pipe/효과음자리.자리잡기 한 곳 (2026-10-04 루키치75·140·149·152 — 효과음을 하나씩 따로 말 틈으로 옮겨
        #   절정 dudun(2.6초)과 반전 gaze 가 같은 A3 트랙에서 겹쳤고 ⑧ 조립 verify 에서야 «A3 겹침» 으로 죽었다).
        #   말 틈 스냅(2026-09-03 사장님 «배속처럼 들림» — 절정 dudun 이 대사 위에 통째로 깔려 말이 몰아치는 느낌)은 그대로 —
        #   절정·반전은 ±2.5s 안 «말 틈 + A3 빈 자리» 중 가장 가까운 곳, 말 틈이 없으면 A3 빈 자리 −12dB, 그것도 없으면 뺀다.
        #   훅은 오프닝 임팩트라 제자리.
        from s2pipe import 효과음자리 as _효
        _말들 = [(x["t"], x["e"]) for x in (proj.get("asr_words") or []) if x.get("type") != "punctuation"]
        _재료 = []
        for 이름, 라벨, pi in (("dun", "훅", 0), ("dudun", "절정", i4), ("gaze", "반전", i5)):
            if pi is None:
                continue
            srcm = os.path.join(sfx_dir, 이름 + ".mp3")
            if not os.path.exists(srcm):
                continue
            w = os.path.join(sdir, f"효과음_{라벨}.wav")
            dur0 = float(subprocess.run(ff.명령(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", srcm]), check=True, capture_output=True).stdout)
            run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", srcm, "-ac", "1", "-ar", "48000",
                 "-c:a", "pcm_s16le", "-af", f"afade=t=out:st={max(0, dur0-0.4):.2f}:d=0.4,volume=-6dB", w]))
            _ww = wave.open(w)
            _wl = _ww.getnframes() / _ww.getframerate()
            _ww.close()
            _재료.append({"라벨": 라벨, "이름": 이름, "srcm": srcm, "wav": w, "t0": picture[pi]["t0"], "길이": dur0,
                        "wav길이": _wl, "스냅": 라벨 != "훅"})
        for e, r in zip(_재료, _효.자리잡기(_재료, _말들, total)):
            if r["글"]:
                print("  " + r["글"])
            if r["뺌"]:
                continue
            if r["낮춤"]:
                run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", e["srcm"], "-ac", "1", "-ar", "48000",
                     "-c:a", "pcm_s16le",
                     "-af", f"afade=t=out:st={max(0, e['길이']-0.4):.2f}:d=0.4,volume=-12dB", e["wav"]]))
            sfx.append({"wav": e["wav"], "t0": r["t0"], "t1": r["t1"], "text": f"효과음 {e['라벨']} {e['이름']}",
                        "_wav길이": e["wav길이"]})
        print(f"효과음 {len(sfx)}개: " + " · ".join(s_['text'] for s_ in sfx))

    # 제목 큐 — 줄별 1장(도너와 같은 «1줄 = 1그래픽» — 줄간격을 프리미어 리딩에 안 맡긴다).
    #   위치·크기·색·폰트는 규격 layout.title 에서 온다. 환산 근거는 위 주석(신병4 실측).
    _t = CFG["layout"]["title"]
    from fontTools.ttLib import TTFont as _TTF
    _제목PS = _TTF(_t["font"])["name"].getDebugName(6)          # 예: S-CoreDream-7ExtraBold
    _제목RGB = [int(_t["color"][i:i + 2], 16) for i in (0, 2, 4)]

    def _제목위치(line, line_y):
        """draw_frame 과 같은 조건(PIL·크기 line_h)으로 그 줄의 잉크 세로 중심을 재고,
        프리미어 앵커 오프셋(신병4 실측 5.6px@112, 크기 비례)을 빼 위치 파라미터 값으로."""
        from PIL import ImageFont as _IF, ImageDraw as _ID, Image as _Im
        import numpy as _np
        f_ = _IF.truetype(_t["font"], _t["line_h"])
        im_ = _Im.new("L", (1600, _t["line_h"] * 3), 0)
        _ID.Draw(im_).text((20, _t["line_h"]), line, font=f_, fill=255)
        ys_ = _np.where(_np.array(im_).max(axis=1) > 40)[0]
        assert len(ys_), f"제목 줄 잉크 없음: {line!r}"
        중심 = (int(ys_.min()) + int(ys_.max())) / 2 - _t["line_h"] + line_y
        앵커 = 중심 - 5.6 * _t["line_h"] / 112.0
        return f"0.5:{앵커 / 1920:.6f}"

    cues = [{"lane": "title", "t0": 0.0, "t1": round(total, 3), "text": ln,
             "pos": _제목위치(ln, y_), "size": float(_t["line_h"]),
             "font": _제목PS, "color": _제목RGB, "outline": 0.0}
            for ln, y_ in zip(list(proj["title"])[:2], (_t["line1_y"], _t["line2_y"]))]
    # outline 0.0 — 껍데기 구이는 민짜 검정. 도너 견본 외곽선 6.0 을 안 끄면 검정 테두리가
    # 얹혀 «글씨체가 바뀐» 것처럼 굵어 보인다 (2026-09-08 사장님 지적 실측)
    assert len(cues) == 2, "제목은 2줄이어야 한다 (규격 layout.title.lines)"
    cues.append({"lane": "narr", "t0": narration[0]["t0"], "t1": narration[0]["t1"], "text": nar_seg["narration"]})
    # 대사 큐 — 60fps 격자에서 끝 = min(시작+6초, 다음 시작) 로 겹침 0 을 보장한다.
    # ★나레이션이 뜨는 동안 대사 자막은 감춘다 (규격 narration.hide_line_subs — 2026-09-01 사장님 재확인:
    #   나레이션 중에는 본편 대사 자막이 안 나오는 게 맞다). 겹치면 자르고, 0.3초도 안 남으면 뺀다.
    # ★대사 큐·화자 색은 s2pipe/화자색.py 한 곳 — ⑥ 굽기(mp4 자막 색)와 같은 함수다 (2026-09-28 사장님: mp4 에도 같은 색).
    pad = float(CFG["narration"].get("duck_pad_sec", 0.15))
    lines = [x for x in subs if x.get("kind") != "narr"]
    dlg_cues, _번호, 숨김, 늘어짐, 끝없음 = 화자색.대사큐(subs, narration[0]["t0"], narration[0]["t1"], total, pad)
    cues.extend(dlg_cues)
    if 숨김:
        print(f"나레이션과 겹쳐 감춘 대사 자막 {숨김}줄")
    # ★게이트(2026-09-03 사장님) — 대사가 끝나면 자막도 사라져야 한다.
    if 늘어짐:
        긴 = [d for d in 늘어짐 if d > 0.30]
        print(f"  [{'OK' if max(늘어짐) <= 1.05 else 'X'}] 자막 끝 = 말 끝 — "
              f"{len(늘어짐)}줄 · 0.3s 넘게 남는 줄 {len(긴)}개 · 최대 +{max(늘어짐):.2f}s"
              f" (짧은 외마디의 읽기 보장 1.0s 이내)")
        assert max(늘어짐) <= 1.05, "자막이 말 끝보다 1초 넘게 남는다 — 끝시각 계산 확인"
    if 끝없음:
        print(f"  ★끝시각 없는 대사 줄 {끝없음}개 — sync 를 다시 돌려라 (6s 상한으로 감)")

    # ★화자별 자막 색 (2026-09-02 사장님) — 화자마다 색, 효과자막은 나레와 같은 노랑.
    #   화자1 은 기본색 유지(주인공), 파스텔 팔레트라 눈이 편하다. 나레(V4)는 건드리지 않는다.
    # ★판정은 보통 ⑥ 굽기가 먼저 해서 저장해 둔다 — 여기선 같은 키로 저장본을 읽는다(두 번 묻지 않는다).
    #   저장본 키(2026-09-27 100편 배치 — 다시 돌릴 때마다 영상 3회 판정을 새로 불러 agy 한도가 바닥났다)는
    #   조각(여운 뺀 cut.mp4 구간)·자막 줄·시각. 2026-09-28 전 ⑦ 이 여운 늘인 조각으로 만든 옛 키도 찾아본다.
    #   판정 큐는 ⑥ 과 같은 규칙(여운 뺀 총길이)으로 만든다 — 나레가 영상 끝에 걸린 편에서 키가 갈리지 않게(2026-09-28).
    화자색.프리미어색(dlg_cues, _번호, proj, wdir, pad, 화자색.판정조각(segs), 옛키조각=segs)

    # 상자 배치 — ★원본 번인 자막이 상자 밖으로 잘려나가게 확대하고, 컷마다 얼굴 중심을 맞춘다
    #   (2026-09-01 사장님: 원본 자막과 우리 자막이 겹친다 — 확대+인물 포커싱으로 가리지 말고 잘라내라)
    src_info = ffprobe_info(dst_src)
    box_h = b["y1"] - b["y0"]                       # 908
    from s2pipe import build as B
    from s2pipe import framing as FR
    sub_top = B.find_burned_subs(dst_src, 1920, 1080, src_info["dur"]) or int(1080 * b["sub_zone_top"])

    def grab(t, tag):
        """★frame_at 은 tag 로 캐시한다 — 같은 tag 면 다른 시각도 같은 프레임을 돌려준다(실측).
           캐시를 우회해 ffmpeg 로 직접 뽑는다."""
        import numpy as np
        from PIL import Image as _I
        p = os.path.join(wdir, f"_pv_{tag}.png")
        subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", dst_src,
                        "-frames:v", "1", p]), check=True, capture_output=True)
        return np.asarray(_I.open(p).convert("RGB"))

    def face_center(t0, t1, tag):
        """컷 구간에서 얼굴 중심 실측 (yunet, 3프레임 평균). 못 찾으면 화면 중상단."""
        pts = []
        for f in (0.3, 0.5, 0.7):
            try:
                rgb = grab(t0 + (t1 - t0) * f, f"f{tag}_{int(f*10)}")
                # ★굽기와 같은 얼굴 고르기(2026-09-29 점심이네 «가짜 얼굴») — 예전엔 max(r[4]) 로 골랐는데 r[4] 는 점수가
                #   아니라 «두 눈 중점의 x» 다(framing 이 눈 좌표를 실은 뒤로) — 가장 오른쪽 얼굴(흐린 뒤통수·무늬 포함)이 뽑혔다.
                faces = FR.얼굴고르기(rgb, b, 1080)
                if faces:
                    best = faces[0]
                    x, y, w_, h_ = best[:4]
                    pts.append((x + w_ / 2, y + h_ / 2))
            except Exception:
                pass
        if not pts:
            return 960.0, 430.0
        xs = sorted(p[0] for p in pts)
        ys = sorted(p[1] for p in pts)
        # ★한 컷에 샷이 여러 개면(얼굴 위치 편차 큼) 평균이 아무도 안 맞춘다 — 중앙 크롭이 안전하다
        if len(xs) >= 2 and xs[-1] - xs[0] > 350:
            return 960.0, ys[len(ys) // 2]
        return xs[len(xs) // 2], ys[len(ys) // 2]

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    def seg_has_burned(t0, t1):
        """이 컷 구간의 하단 밴드에 **노란 번인 자막**이 있는가 (이 소재의 번인 자막은 노랑).
           밝기만 보면 하늘·흰 차가 오탐된다(실측 — 결말 컷이 확대돼 중앙 반전 자막이 잘렸다).
           ★없는 컷은 확대하지 않는다 — 중앙 화면 자막이 내용인 컷을 자르면 안 된다."""
        # ★색 하드코딩 금지 — 소재마다 자막 색이 다르다(노랑 소재 다음에 흰 소재가 와서 재발했다,
        #   2026-09-01 사장님 반려 2회). 번인 자막의 공통 속성 = 밝은 글자에 검은 외곽선.
        #   「밝은 픽셀(≥200)과 어두운 픽셀(≤70)이 맞닿은 자리」를 세면 색과 무관하게 잡힌다.
        #   실측: 자막 프레임 행최대 22~35·총 400+ vs 무자막 0~10·총 ≤65.
        #   ★한 순간이라도 검출되면 「있음」이다 — 자막이 드문드문한 컷(컷05 실측: 8샘플 중 1~2개만
        #   강검출)을 「없음」으로 놓치는 것이 오탐보다 치명적이다(사장님 절대 요구).
        #   자막 윗변도 함께 실측한다 — 전역 중앙값(find_burned_subs)만 믿었다가 여운 구간의
        #   더 높은 자막(전역 840 vs 실측 ~830)이 한계선을 뚫었다(잔존 게이트가 잡음, 2026-09-01).
        # ★촘촘히 훑는다(0.5초 간격 · 2026-09-03 Deep04 «딱 먹고» 사건) — 8프레임 성긴
        #   샘플은 순간 떠 있는 큰 예능자막을 놓쳤다. 자막 윗변은 순간마다 다르므로
        #   컷 전체를 훑어 **가장 높은 윗변**을 쓴다.
        band0 = int(1080 * 0.70)
        tops = []
        found = False
        타임들, t = [], t0 + 0.25
        while t < t1 - 0.05 and len(타임들) < 70:
            타임들.append(t)
            t += 0.5
        for j, tt in enumerate(타임들):
            try:
                hit, top = 텍스트검출(grab(tt, f"b{t0:.0f}_{j}")[band0:, :, :], top=True)
                if hit:
                    found = True
                    if top is not None:
                        tops.append(band0 + top)
            except Exception:
                pass
        return found, (min(tops) if tops else None)

    # 1차 — 컷별 번인 유무·자막 윗변 실측 (0.5초 간격 전수)
    burn, 컷탑들 = [], []
    for seg in segs:
        f_, t_ = seg_has_burned(seg["t0"], seg["t1"])
        burn.append(f_)
        컷탑들.append(t_)
    print(f"번인 자막 윗변 — 전역 {sub_top} · 컷별 실측 {[t for t in 컷탑들 if t]}")

    # ★근본 규칙(2026-09-03 사장님 «도대체 몇 번째» — 검출 술래잡기 종결):
    #   이 소재군은 대사에 항상 자막을 굽는다. 그러므로 **말이 있는 컷은 검출 결과와
    #   무관하게 자막 구역을 배제하고 크롭한다.** 검출은 유무 판정이 아니라 구역 높이
    #   실측에만 쓴다. (페이드로 어두워진 자막 등 «검출을 뚫는 새 스타일»이 나와도
    #   말이 있는 한 무조건 잘려나간다.) 예외 = 화면 중앙이 글로 가득한 콘텐츠 컷
    #   (게시글 낭독) — 확대하면 내용이 잘리므로 풀샷 유지.
    말들cut = [(w["t"], w["e"]) for w in (proj.get("asr_words") or [])
               if w.get("type") != "punctuation"]

    def 콘텐츠화면(seg):
        import numpy as np
        표수 = 0
        for f in (0.25, 0.5, 0.75):
            try:
                a = grab(seg["t0"] + (seg["t1"] - seg["t0"]) * f, f"m{seg['t0']:.0f}_{f}")
                중앙 = np.asarray(a).astype(int)[270:648, :, :]
                g = 중앙.mean(axis=2)
                # 게시글 화면 = 밝은 바탕(평균 ≥170) 위 어두운 글줄. 어두운 머리·옷만으로는
                # 콘텐츠가 아니다(2026-09-03 컷8 오판 — 근본 규칙이 안 걸렸다)
                어둠 = g <= 90
                어둠글 = (어둠.sum(axis=1) >= 25).sum()
                # ★글줄은 가로폭 대부분에 퍼진다 — 문틀·기둥 같은 세로 띠는 좁은 열에만
                #   몰린다 (2026-09-04 Deep07 컷1 오판 실측: 흐린 복도가 콘텐츠로 판정돼
                #   번인 배제를 빠져나갔다. 문틀 어둠열 4~27% ↔ 글줄은 35% 이상)
                어둠열 = (어둠.sum(axis=0) >= 10).sum()
                if g.mean() >= 170 and 어둠글 >= 20 and 어둠열 >= g.shape[1] * 0.35:
                    표수 += 1
            except Exception:
                pass
        return 표수 >= 2

    # ★근본 규칙 v2 (2026-09-04 사장님 «수차례 반복» — 문턱 구멍 종결):
    #   원본은 «한 마디» 발화에도 자막을 굽는다 — Deep07 컷1 «아이고 추워»(2마디)가
    #   «말 3마디 이상» 문턱을 지나쳐 번인이 남았다(실측: 완성 1.7s, 원본 195.96s «아이고»).
    #   그러므로 **문턱 없이**, 컷의 원본 구간에 발화가 하나라도 겹치면 배제한다.
    #   판정 근거는 완성본 ASR 이 아니라 **원본 전사(vtt)** — 컷 경계에 걸친 발화·작은
    #   소리도 원본 시간축에 그대로 보이기 때문. vtt 가 없을 때만 완성본 ASR 로 대신한다.
    import re as _re3
    원발화 = []
    _vtt = os.path.join(workdir, "work", proj["source"]["id"] + ".ko.vtt")
    # ★agy 원본 전사(2026-09-26 사장님 결정 B)는 시각이 모델 추정이라 거칠다 — 겹침 판정 여유를
    #   AGY_여유 만큼 더 넓힌다(넓히면 배제가 늘 뿐 번인이 새지는 않는 쪽).
    from s2pipe.agy_asr import 원본전사_출처, AGY_여유
    원여유 = AGY_여유 if 원본전사_출처(_vtt) == "agy" else 0.0
    if os.path.exists(_vtt):
        for m in _re3.finditer(r"(\d+):(\d+):(\d+)\.(\d+) --> (\d+):(\d+):(\d+)\.(\d+)",
                             open(_vtt, encoding="utf-8").read()):
            g = [int(x) for x in m.groups()]
            원발화.append((g[0]*3600 + g[1]*60 + g[2] + g[3]/1000,
                           g[4]*3600 + g[5]*60 + g[6] + g[7]/1000))

    for i, (seg, pc) in enumerate(zip(segs, picture)):
        if burn[i]:
            continue
        if 원발화:
            # 자막은 발화보다 조금 먼저 뜨고 늦게 진다 — 앞뒤 여유를 두고 겹침 판정
            말수 = sum(1 for t_, e_ in 원발화
                       if t_ < seg["t1"] + 0.3 + 원여유 and e_ > seg["t0"] - 0.5 - 원여유)
            근거 = "원본 전사"
        else:
            말수 = sum(1 for t_, e_ in 말들cut if t_ < pc["t1"] and e_ > pc["t0"])
            근거 = "완성본 ASR(vtt 없음)"
        if 말수 >= 1 and not 콘텐츠화면(seg):
            burn[i] = True
            print(f"  컷{i+1:02d}: 발화 {말수}건 겹침({근거}) → 자막 구역 무조건 배제(근본 규칙 v2)")

    # ★원문화면 (2026-09-07 사장님 «결론 어디에 빼먹었어» — Deep09 결말 명언 화면을 번인
    #   취급해 잘라냈다): 화면 속 글이 «내용»인 컷은 사람이 segments 에 "원문화면": true 로
    #   선언한다 → 풀샷 유지·잔존 게이트 면제. 그 구간 우리 대사 자막은 sync 가 뺀다(두 겹 방지).
    for i, seg in enumerate(segs):
        if seg.get("원문화면"):
            burn[i] = False
            print(f"  컷{i+1:02d}: 원문화면 선언 — 화면 속 글이 내용 → 풀샷 유지·잔존 면제")

    # ★확대율은 컷별(2026-09-03 사장님 «고친다고 인물 포커싱 나가면 안 된다») —
    #   그 컷의 자막이 요구하는 만큼만 확대한다. 전역 최솟값으로 다 키우면
    #   멀쩡한 컷의 얼굴까지 커진다.
    유효탑 = {}

    def 상자잡기(i, top_i):
        limit_i = max(560, top_i) - 12
        s_i = min(1.35, max(box_h / limit_i, box_h / 1080) * 1.03)
        # ★cy_lo 공식 수리(2026-09-03 근본 원인) — 원본 좌표는 캔버스에 cy+(Y-540)·s 로
        #   놓이므로, 상자 밑변(b.y1)이 한계선(limit_i)을 넘지 않으려면 기준이 540 이어야
        #   한다. b.y0 을 쓰던 옛 식은 얼굴 낮은 컷에서 자막 구역을 34px 까지 새게 했다.
        cy_lo = b["y1"] - (limit_i - 540) * s_i
        cy_hi = b["y0"] + 540 * s_i
        px_lo, px_hi = 1080 - 960 * s_i, 960 * s_i
        xf, yf = face_center(segs[i]["t0"], segs[i]["t1"], i)
        cy = clamp(970 - (yf - 540) * s_i, cy_lo, cy_hi)
        px = clamp(540 - (xf - 960) * s_i, px_lo, px_hi)
        picture[i]["box"] = {"scale": round(s_i * 100, 3), "pos": f"{px / 1080:.6f}:{cy / 1920:.6f}"}
        return s_i, xf, yf

    def 안쪽경계(seg):
        """검은 테두리 분류 — 판정은 s2pipe/안쪽경계.py «하나»(굽기와 같은 함수)에 있다.
        ('안쪽', bbox)  = 양축 «다» 작음 — 진짜 프레임-인-프레임. 자막은 테두리 밖.
        ('레터박스', bbox) = 한 축만 작음 — 자막이 그림 «안»에 있다! 잔존 면제 금지,
                             테두리만 걷고 일반 번인 배제를 태운다(2026-09-08 Deep14).
        None = 테두리 없음.
        ★2026-10-03 (루키치206·172·171): 예전 이 자리의 판정은 «밝기 16 이하 가장자리 = 테두리»였고, 테두리 없는
        표본(전체 화면)까지 상자로 세어 교집합을 냈다 — 표본 한 장만 어두운 밤 장면이어도 컷 전체가 좁아져
        컷 상자 밑변이 박힌 자막까지 내려왔다(206 밤 운동장 «안쪽 1674x958» · 171 밤 골목 «레터박스 1161x1080»).
        이제 띠는 «디지털 순흑 + 곧은 그림 경계» 둘 다일 때만 인정하고, 테두리 있는 표본끼리만 교집합을 낸다.
        원본 크기도 실제 프레임에서 잰다(1920x960 원본 Deep61 이 1080 기준이라 전 컷 레터박스로 나오던 것)."""
        from s2pipe import 안쪽경계 as 경계판정
        장들 = [경계판정.프레임(dst_src, seg["t0"] + (seg["t1"] - seg["t0"]) * f)
                for f in (0.15, 0.35, 0.5, 0.65, 0.85)]
        if any(a is None for a in 장들):
            return None
        return 경계판정.판정(장들)

    안쪽컷 = set()
    for i, (seg, pic) in enumerate(zip(segs, picture)):
        분류 = 안쪽경계(seg)
        if 분류 and 분류[0] == "안쪽":
            x, y, w, h = 분류[1]
            s_f = max(1080.0 / w, box_h / h)
            cx, cy0 = x + w / 2.0, y + h / 2.0
            px = 540 - (cx - 960) * s_f
            cyv = (b["y0"] + b["y1"]) / 2.0 - (cy0 - 540) * s_f
            pic["box"] = {"scale": round(s_f * 100, 3), "pos": f"{px/1080:.6f}:{cyv/1920:.6f}"}
            # 잔존 게이트 면제 — 원본 자막 밴드는 검은 테두리 쪽이라 안쪽만 자르면 물리적으로
            # 못 들어온다. 검출을 돌리면 옷 글씨(«PUBLIC» 티셔츠)를 자막으로 오인한다(실측).
            안쪽컷.add(i)
            print(f"  컷{i+1:02d}: 프레임-인-프레임 감지({w}x{h}@{x},{y}) → 안쪽만 확대 {s_f*100:.0f}%"
                  f" · 잔존 면제(자막 밴드는 테두리에 있음)")
            continue
        if 분류 and 분류[0] == "레터박스":
            # ★레터박스(2026-09-08 Deep14 캡쳐) — 자막은 그림 «안» 하단에 구워져 있다.
            #   테두리를 걷어낸 안쪽을 화면으로 삼되, 자막 윗변(검출 실측)까지만 보인다.
            #   잔존 검사는 그대로 태운다(면제 금지).
            x, y, w, h = 분류[1]
            자막탑 = min(v for v in (컷탑들[i], sub_top, int(1080 * 0.872)) if v)
            limit = min(y + h, 자막탑) - 12
            유효h = max(limit - y, 200)
            s_f = min(1.6, max(box_h / 유효h, 1080.0 / w) * 1.02)
            xf, yf = face_center(seg["t0"], seg["t1"], i)
            중심y = (y + limit) / 2.0
            cy_lo = b["y1"] - (limit - 540) * s_f
            cy_hi = b["y0"] + (540 - y) * s_f
            cyv = clamp((b["y0"] + b["y1"]) / 2.0 - (중심y - 540) * s_f, cy_lo, cy_hi)
            px = clamp(540 - (xf - 960) * s_f, 1080 - 960 * s_f, 960 * s_f)
            pic["box"] = {"scale": round(s_f * 100, 3), "pos": f"{px/1080:.6f}:{cyv/1920:.6f}"}
            print(f"  컷{i+1:02d}: 레터박스 감지({w}x{h}@{x},{y}) → 테두리·자막밴드(윗변 {자막탑})"
                  f" 제외 확대 {s_f*100:.0f}% · 잔존 검사 유지")
            continue
        if seg.get("원문화면") or seg.get("전체화면"):
            # ★fit-width — 원본 가로 전체가 박스 폭에 들어간다 (굽기의 원문화면 화면꼴과 동일)
            pic["box"] = {"scale": round(1080 / 1920 * 100, 3),
                          "pos": f"0.5:{(b['y0'] + b['y1']) / 2 / CFG['video']['h']:.6f}"}
            print(f"  컷{i+1:02d}: 원문화면 → fit-width (가로 전체, 글 안 잘림)")
            continue
        if not burn[i]:
            pic["box"] = {"scale": round(box_h / 1080 * 100, 3),
                          "pos": f"0.5:{(b['y0'] + b['y1']) / 2 / CFG['video']['h']:.6f}"}
            print(f"  컷{i+1:02d}: 번인 자막 없음 → 풀샷 유지")
            continue
        유효탑[i] = min(v for v in (컷탑들[i], sub_top, int(1080 * 0.872)) if v)
        s_i, xf, yf = 상자잡기(i, 유효탑[i])
        print(f"  컷{i+1:02d}: 번인 자막 있음(윗변 {유효탑[i]}) → 확대 {s_i*100:.0f}% · 얼굴 ({xf:.0f},{yf:.0f})")
    # 미리보기 — 상자에 담길 화면을 컷별 box 값 그대로 잘라 확인용으로 남긴다
    pvdir = os.path.join(out_root, "_미리보기")
    os.makedirs(pvdir, exist_ok=True)

    def 미리보기생성():
      for i, (seg, pic) in enumerate(zip(segs, picture)):
        try:
            sc = pic["box"]["scale"] / 100.0
            pxn, cyn = (float(v) for v in pic["box"]["pos"].split(":"))
            px_, cy_ = pxn * 1080, cyn * 1920
            x0 = clamp(960 + (0 - px_) / sc, 0, 1920 - 1080 / sc)
            y0 = clamp(540 + (b["y0"] - cy_) / sc, 0, 1080 - box_h / sc)
            mid = (seg["t0"] + seg["t1"]) / 2
            subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-ss", f"{mid:.2f}", "-i", dst_src,
                            "-frames:v", "1", "-vf",
                            f"crop={1080/sc:.0f}:{box_h/sc:.0f}:{x0:.0f}:{y0:.0f},scale=540:-2",
                            os.path.join(pvdir, f"컷{i+1:02d}.png")]), check=True)
        except Exception as e:
            print("  미리보기 실패:", e)

    미리보기생성()

    # ★잔존 번인 게이트 (절대 재발 금지 — 2026-09-01 사장님 반려 2회) — 상자에 담길 화면의
    #   하단 40% 에서 외곽선 자막이 검출되면 실패다. 판정이 틀려도 여기서 걸린다.
    #   ★걸린 컷은 자동으로 확대로 승격해 다시 만들고 재검사한다 — 표본 추첨(드문드문한 자막)에
    #   판정이 흔들려도 게이트가 최종 판정자다.
    import numpy as np

    def 컷잔존(i):
        seg, pic = segs[i], picture[i]
        sc = pic["box"]["scale"] / 100.0
        pxn, cyn = (float(v) for v in pic["box"]["pos"].split(":"))
        px_, cy_ = pxn * 1080, cyn * 1920
        x0 = clamp(960 + (0 - px_) / sc, 0, 1920 - 1080 / sc)
        y0 = clamp(540 + (b["y0"] - cy_) / sc, 0, 1080 - box_h / sc)
        # ★기하 우선(2026-09-07 Deep11 컷3 — 노란 배지 «사회화» 글자를 자막으로 오인해
        #   확대 3회에도 계속 걸림, Deep10 «PUBLIC» 티셔츠와 같은 소품 글자 FP 클래스):
        #   크롭 밑변이 실측 자막 밴드 윗변보다 위면 밴드는 «기하학적으로» 이미 배제 —
        #   그 아래서 검출된 글자는 자막일 수 없다. 검출은 밴드가 걸릴 때만 판정한다.
        밴드탑 = min(v for v in (컷탑들[i], sub_top) if v) if (컷탑들[i] or sub_top) else None
        if 밴드탑 and y0 + box_h / sc <= 밴드탑 - 6:
            return False
        타임들, tt = [], seg["t0"] + 0.25
        while tt < seg["t1"] - 0.05 and len(타임들) < 70:   # ★0.5초 간격 전수(성긴 샘플 금지)
            타임들.append(tt)
            tt += 0.5
        for t in 타임들:
            p = os.path.join(wdir, "_gatechk.png")
            subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", dst_src,
                            "-frames:v", "1", "-vf",
                            # 전체화면(fit-width) 컷은 상자가 원본보다 커진다 — 원본 안으로 잘라 넣는다(2026-09-27 싱글246)
                            f"crop={min(1080/sc, 1920):.0f}:{min(box_h/sc, 1080):.0f}:{max(x0, 0):.0f}:{max(y0, 0):.0f}", p]),
                           check=True, capture_output=True)
            a = np.asarray(Image.open(p).convert("RGB"))
            if 텍스트검출(a[int(a.shape[0] * 0.60):, :, :]):
                return True
        return False

    # ★기하 관문 (2026-09-27 싱글266·188 글자 노출 · 85편 상자 띠) — 굽기(build)와 «같은 함수»(s2pipe/번인관문.걸림)로
    #   컷 상자(원본 사각형)를 카드마다 잰 상자 윗변·사람이 잰 화면 캡션(조각 «가림»)과 위치로 비교한다. 픽셀 검출
    #   (컷잔존)은 글자 윗머리 몇 px·반투명 상자를 원리상 못 잡았다. 원문화면·전체화면·프레임-인-프레임 컷도 본다.
    from s2pipe import 번인관문 as 관
    _src카드 = src_orig if os.path.exists(src_orig) else dst_src
    박스들 = 관.카드상자들(_src카드, log=print) if b.get("avoid_burned_subs") else []
    # ★원본 화면 캡션(2026-09-29 점심이네2 «6월 14일→1월 03일») — 굽기와 같은 사각형을 조각 «가림» 에 붙인다(메모리 사본만 —
    #   준비는 계획을 저장하지 않는다). 아래 기하 관문·가림피하기·완성본 crop 관문이 모두 이 가림을 본다.
    캡션 = 관.캡션들(_src카드, log=print)
    segs = [관.캡션붙인조각(s, 캡션) for s in segs]

    def 컷사각(i):
        seg, pic = segs[i], picture[i]
        sc = pic["box"]["scale"] / 100.0
        pxn, cyn = (float(v) for v in pic["box"]["pos"].split(":"))
        px_, cy_ = pxn * 1080, cyn * 1920
        x0 = clamp(960 + (0 - px_) / sc, 0, 1920 - 1080 / sc)
        y0 = clamp(540 + (b["y0"] - cy_) / sc, 0, 1080 - box_h / sc)
        w, h = min(1080 / sc, 1920), min(box_h / sc, 1080)
        return {"t0": pic["src_in"], "t1": pic["src_in"] + (pic["t1"] - pic["t0"]),
                "x": int(max(x0, 0)), "y": int(max(y0, 0)), "w": int(round(w)), "h": int(round(h)), "이름": f"컷{i+1:02d}"}

    def 기하걸림(i):
        return 관.걸림(박스들, [컷사각(i)], 관.가림목록([segs[i]]))

    가림여유 = 6     # 가림 사각형 둘레 여유(px) — 컷 상자는 정수로 반올림돼 경계에 1px 걸칠 수 있다

    def 얼굴상자(i, t0, t1):
        """컷 전체의 얼굴을 합친 상자 (x, y, w, h). 프리미어 컷 상자는 컷 내내 한 자리라, 가림을 피해 crop 이 작아지면
        컷 안 «모든» 샷의 말하는 얼굴이 들어가야 한다(295 실측: 가림 시각 얼굴만 재면 컷 끝 125초 여자 얼굴이 오른쪽에
        반쯤 잘렸다). 9장에서 장마다 가장 큰 얼굴 넓이의 60% 넘는 얼굴만(가장자리에 작게 걸친 얼굴·오검출 제외 — 295 118초 왼끝 안경 남자 0.37배) 합친다. 합친 상자가 쓸 수 있는
        자리보다 크면 담기가 그 가운데에 둔다(얼굴담김=None 으로 알린다)."""
        fs = []
        for k in range(9):
            try:
                rgb = grab(t0 + (t1 - t0) * (0.1 + 0.1 * k), f"g{i}_{k}")
                faces = [f[:4] for f in FR.얼굴고르기(rgb, b, 1080)]     # 가짜·흐린 얼굴 거름(굽기와 같은 곳 · 2026-09-29)
            except Exception:
                faces = []
            if faces:
                큰 = max(f[2] * f[3] for f in faces)
                fs += [f for f in faces if f[2] * f[3] >= 큰 * 0.6]
        if not fs:
            return None
        x0, y0 = min(f[0] for f in fs), min(f[1] for f in fs)
        return (x0, y0, max(f[0] + f[2] for f in fs) - x0, max(f[1] + f[3] for f in fs) - y0)

    def 가림피하기(i, usable_h):
        """★2026-09-28 싱글295 — TV 화면 속 가운데 캡션 «보통 수컷이 1,500회…»(원본 x600~1320·y770~915·121.9~123.4초).
        굽기(framing.가림경계)는 네 쪽(왼·오른·위·아래) 중 crop 을 가장 크게 둘 수 있는 쪽으로 피해 완성본에서 사라졌는데,
        준비는 가림을 «가로로만» 피해(09-27 싱글268 좌상단 캡션 때 넣은 식) 화면 가운데 캡션은 1080 폭 상자로 비킬 자리가
        없어 ⑦ 에서 멈췄다(컷04 밑변 902 > 가림 윗변 770). 가운데·넓은 캡션 전체가 같은 구멍이다.
        → 규칙을 한 곳으로: 굽기와 «같은 함수» framing.가림경계 로 피할 쪽(세로 포함)을 고르고, framing.담기 로 그 안에
          얼굴을 담아 crop 을 정한 뒤 프리미어 상자(scale·pos)로 바꾼다. 세로로 피하면 crop 이 작아지니 확대가 커진다.
          관문은 번인관문.걸림 이 원래 사각형으로 다시 본다(여기서 못 피하면 그대로 멈춘다)."""
        c = 컷사각(i)
        ratio = 1080 / box_h
        s0 = picture[i]["box"]["scale"] / 100.0
        pxn, cyn = (float(v) for v in picture[i]["box"]["pos"].split(":"))
        x0 = 960 - pxn * 1080 / s0
        y0 = 540 + (b["y0"] - cyn * 1920) / s0
        넓힌 = dict(segs[i], 가림=[[r[0] - 가림여유, r[1] - 가림여유, r[2] + 가림여유, r[3] + 가림여유] + list(r[4:])
                                  for r in segs[i].get("가림") or []])
        경계 = FR.가림경계((0, 0, 1920, 1080), 넓힌, c["t0"], c["t1"], usable_h, ratio)
        # 컷 상자 좌표 = 원본(dst_src) 기준 — grab 도 dst_src 를 본다(picture 의 src_in 과 같은 축).
        face = 얼굴상자(i, c["t0"], c["t1"])
        bw, bh, tx, ty, 담김 = FR.담기(1080 / s0, box_h / s0, x0, y0, face, 경계, usable_h, ratio)
        s = 1080.0 / bw
        px = (960 - tx) * s
        cy = b["y0"] + (540 - ty) * s
        picture[i]["box"] = {"scale": round(s * 100, 3), "pos": f"{px / 1080:.6f}:{cy / 1920:.6f}"}
        print(f"  컷{i+1:02d}: 화면 캡션(가림) 피함 — 경계 {tuple(int(v) for v in 경계)} · crop {bw}x{bh}@{tx},{ty}"
              f" · 확대 {s0*100:.0f}%→{s*100:.0f}% · 얼굴 {face} 담김 {담김}")

    # 전체화면 컷은 make ① 이 «박힌 자막 카드 겹침 0» 을 이미 보장한다 — 픽셀 글자 검출은 옷·소품 글씨를 자막으로
    #   오인한다(2026-09-27 싱글226 축구 유니폼 «EA7»). 원문화면처럼 픽셀 검사에서 뺀다(기하 관문은 본다).
    for round_ in range(3):
        기하 = {i: 기하걸림(i) for i in range(len(picture))
                if not (segs[i].get("원문화면") or segs[i].get("전체화면")) and i not in 안쪽컷}
        기하 = {i: v for i, v in 기하.items() if v}
        걸림 = sorted(set(기하) | {i for i in range(len(picture))
                               if not (segs[i].get("원문화면") or segs[i].get("전체화면")) and i not in 안쪽컷
                               and i not in 기하 and 컷잔존(i)})
        if not 걸림:
            break
        print(f"  잔존 게이트 {round_+1}회차 — 컷 {[i+1 for i in 걸림]} 다시 잡는다"
              + (f" (카드 상자 기하 {[i+1 for i in 기하]})" if 기하 else ""))
        for i in 걸림:
            카드윗 = [g["상자윗변"] for g in 기하.get(i, []) if g["종류"] == "카드"]
            if 카드윗:
                유효탑[i] = min(유효탑.get(i, 9999), min(카드윗) - 2)
            elif i not in 기하:
                유효탑[i] = 유효탑.get(i, sub_top or int(1080 * 0.872)) - 45
            _탑 = 유효탑.get(i, sub_top or int(1080 * 0.872))
            상자잡기(i, _탑)
            if 관.걸림([], [컷사각(i)], 관.가림목록([segs[i]])):
                가림피하기(i, max(560, _탑) - 12)
    잔존 = [i + 1 for i in range(len(picture))
            if not (segs[i].get("원문화면") or segs[i].get("전체화면")) and i not in 안쪽컷 and 컷잔존(i)]
    기하전부 = [g for i in range(len(picture)) for g in 기하걸림(i)]
    기하잔존 = 관.멈춤(기하전부)                       # 글자·화면 캡션만 멈춘다 — 상자 윗단(띠)은 주의(사장님 2026-09-27 23:50)
    print(("  [OK] " if not 잔존 else "  [X] ") + f"컷 하단 잔존 번인 자막 0  걸린 컷 {잔존}")
    print(("  [OK] " if not 기하잔존 else "  [X] ") + f"박힌 자막 관문(카드 {len(박스들)}장 · 컷 상자 기하) 글자 겹침 0"
          + (f" — {관.글(기하잔존)}" if 기하잔존 else "")
          + (f" · 주의 상자 윗단만 {len(기하전부) - len(기하잔존)}건" if len(기하전부) > len(기하잔존) else ""))
    assert not 잔존, f"컷 {잔존} 하단에 번인 자막이 남아 있다 — 확대 후에도 남는다"
    assert not 기하잔존, f"컷 상자 안에 박힌 자막 글자가 든다 — {관.글(기하잔존)} (s2pipe/번인관문.py)"
    # 납품 mp4 쪽(굽기 beats.json 의 crop 전부)도 같은 함수로 — 예전 코드로 구운 편(2026-09-27 수리 전)이 여기서 멈춘다
    _bj = os.path.join(wdir, "beats.json")
    if (박스들 or 캡션) and os.path.exists(_bj):
        _log = json.load(open(_bj, encoding="utf-8"))
        _crops, _미 = 관.beats_crops(_log, 1920, 1080)
        _전 = 관.걸림(박스들, _crops, 관.가림목록(segs))
        _걸 = 관.멈춤(_전)                              # 옛 편 재조립이 상자 띠만으로 막히지 않게(글자만 멈춤)
        # 수리 전 코드로 구운 beats.json(«frames» 칸 없음)은 재기만 한다 — 옛 납품편 재조립(나레재조립 등)은 mp4 를 다시
        #   굽지 않으므로 여기서 멈춰도 고칠 길이 없다(사장님 2026-09-27 23:50 «띠만 있는 옛 편은 다시 굽지 않는다»).
        #   카드 상자 재기의 보수값(글자 못 잰 카드 = 824)이 옛 편에서 가짜 «글자» 를 내는 일도 있다(재기표 참고).
        if "frames" not in _log and _걸:
            print(f"  [주의] 수리 전 코드로 구운 완성본 — 글자 겹침 후보 {len(_걸)}건 (멈추지 않음): {관.글(_걸)}")
            _걸 = []
        print(("  [OK] " if not _걸 else "  [X] ") + f"박힌 자막 관문(완성본 crop {len(_crops)}개) 글자 겹침 0"
              + (f" — {관.글(_걸)}" if _걸 else "") + (f" · 주의 상자 윗단만 {len(_전) - len(_걸)}건" if len(_전) > len(_걸) else "")
              + (f" · 한 장 구도 crop 미기록 조각 {_미}" if _미 else ""))
        assert not _걸, (f"완성본(굽기) crop 안에 박힌 자막 글자가 든다 {len(_걸)}건 — {관.글(_걸)}. "
                         f"수리 전 코드로 구운 편이면 FROM=6 으로 다시 구워라 (s2pipe/번인관문.py)")
    미리보기생성()          # 승격된 컷의 미리보기 갱신
    scale = round(box_h / 1080 * 100, 3)
    cy = round((b["y0"] + b["y1"]) / 2 / CFG["video"]["h"], 6)

    tl = {"title": f"스케치 {slug}", "total_s": round(total, 4),
          "source": dst_src, "source_dur_s": src_info["dur"],
          "src_audio_tickrate": src_info["audio_tickrate"],
          "template": dst_tpl,
          "box": {"scale": scale, "pos": f"0.5:{cy}"},
          "picture": picture, "narration": narration, "sfx": sfx, "cues": cues,
          # 여운 기록 — 납품 관문(검수도구/prproj끝검사.py)이 «이야기 끝 ~ 프리미어 끝» 사이만 결말 벽을 다시 잰다(2026-10-03)
          # 굽기카드·원본 = 결말벽판정의 인자 그대로(2026-10-04 87 — 끝검사가 같은 인자로 다시 잰다)
          "여운": _여운기록}
    # ★관문 두 번째(2026-10-04 87) — 끝검사가 읽을 바로 그 컷 목록(마지막 컷 src_in + 길이)으로 다시 잰다. 여운 끝 암전 처리 등으로
    #   컷 길이가 위 계산과 달라져도 납품 관문과 같은 숫자를 본다.
    if picture:
        _pc = picture[-1]
        _여관2 = _벽.여운관문(src_orig, _여운기록, float(_pc["src_in"]) + float(_pc["t1"]) - float(_pc["t0"]))
        print(("  [OK] " if not _여관2["탈"] else "  [X] ") + "여운 관문(컷 목록) — " + _여관2["글"])
        assert not _여관2["탈"], f"timeline 의 마지막 컷이 결말 벽 관문에 걸린다 — {_여관2['글']}"
    # ★관문(2026-10-04 루키치75·140·149·152) — A3 효과음 겹침 0 을 ⑧ 조립 verify 와 같은 자(30fps 격자 · wav 길이 내림 ·
    #   영상 끝 자름)로 여기서 잰다. 예전엔 ⑧ 에서야 «트랙 A3 겹침» 으로 죽었다.
    from s2pipe import 효과음자리 as _효2
    _a3 = [(s_["text"],) + _효2.틀(s_["t0"], s_["t1"], s_.get("_wav길이", s_["t1"] - s_["t0"]), total) for s_ in sfx]
    _a3겹 = _효2.겹침들(_a3)
    print(("  [OK] " if not _a3겹 else "  [X] ") + f"A3 효과음 겹침 0 (조립과 같은 자) — {len(sfx)}개"
          + (f" · 겹침 {_a3겹}" if _a3겹 else ""))
    assert not _a3겹, f"A3 효과음이 겹친다 {_a3겹} — s2pipe/효과음자리.자리잡기를 거치지 않은 길이 있다"
    out = os.path.join(out_root, "timeline_sk.json")
    json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("생성:", out)
    print(f"컷 {len(picture)} · 나레 {len(narration)} · 큐 {len(cues)} (제목2·나레1·대사 {len(lines)} — 제목은 V3 화면 안 텍스트) · 총 {total:.1f}s")
    print(f"상자: scale {scale}% · pos 0.5:{cy}")


if __name__ == "__main__":
    main()
