# -*- coding: utf-8 -*-
"""원본에 박힌(번인) 자막 «상자»가 완성본 화면에 들어오지 않게 — 카드마다 잰 한계와 최종 관문.

    python -m s2pipe.번인관문 <원본.mp4> <beats.json> [--proj projects/<슬러그>.json]   # 재기만(종료코드 1 = 걸림)
                                                   # --proj: 조각 «가림» 과 화면 캡션(화면글자)까지 본다

★2026-09-27 전수 점검(배치로그/잔존점검_결과.md) — 싱글266 26.7~27.9초(높이 뜬 한 줄 카드 · 글자 윗선 938 ·
  상자 윗변 918)·싱글188 68.7~71.5초(날짜 캡션 윗선 952)에 원본 자막 글자가, 85편에 반투명 상자 윗단(948)이
  완성본 상자 아래 끝에 비쳤다. 187 은 두 줄 카드(윗선 ≈910)를 편별 설정 safe_pad_px=80 으로 손으로 막았다.
  클래스: build.find_burned_subs 가 원본 전체에서 고르게 10장만 뽑아 «글자» 윗선의 «중앙값» 하나로 편 전체
  crop 한계를 정했다 — 소수 카드(두 줄·높이 뜬 카드·날짜 캡션)는 중앙값에서 버려지고, 글자보다 20px 위에서
  시작하는 반투명 상자는 처음부터 재지 않았다.
  수리: ① 카드(자막띠시각.카드들 — 박힌 자막이 바뀌는 시각)마다 «상자 윗변»을 잰다(카드상자들).
        ② 조각마다 «그 조각과 겹치는 카드 중 가장 높은 상자 윗변 − 여유» 로 한계를 정한다(조각한계).
        ③ 최종 관문 하나(걸림): 굽기(beats.json 의 모든 crop)와 준비(프리미어 컷 상자)가 같은 함수를 부른다.
           픽셀 글자 검출이 아니라 «crop 밑변 vs 카드 상자 윗변» 위치 비교라 옷·소품 글씨 오탐이 없다.
  왜 예전 검사를 통과했나: 준비의 «컷 하단 잔존 번인 자막 0» 은 프리미어 컷 상자만 봤고(납품 mp4 의 crop 은
  아무도 안 봤다), 픽셀 검출 문턱은 글자 윗머리 몇 px·반투명 상자를 원리상 못 잡는다.
한계(알려짐): 카드 검출 띠(높이 80~90% · 가운데 60%) 밖의 캡션(싱글268 좌상단 «2524년 대한민국» 류)은 카드가
  아니다 — 조각 표식 «가림» [[x0,y0,x1,y1,t0,t1], …] 로 사람이 잰 사각형을 넘기면 굽기(framing.가림경계)가 피하고
  같은 관문이 확인한다.
  → ★2026-09-29 이 한계를 사람 손에서 뺐다(점심이네2 «6월 14일→1월 03일» 가운데 캡션이 1차 완성본 9~12초에 나갔다).

★2026-09-29 점심이네 배치 — «박힌 글자 인식이 한 가지 모양만 안다» (s2pipe/화면글자.py 머리 주석에 사례·숫자):
  카드(자막띠시각._카드재기)와 상자 윗변(_한카드)은 «아래 띠 안 · 밝은 픽셀 곁 어두운 픽셀» 모양으로만 글자를 알아서
  (b) 그림자만 있는 흰 자막을 놓치고(점심이네3 «너넨 뒤졌어» 202.0~204.6 — 카드 0장) (c) 밝은 물건 가장자리를 카드로
  잡았다(11 219~222 운동화 · 5 13.3 의자 · 21 20.1 파란 탁자 · 52 247.2 냄비 · 37 식탁·흰 티). (a) 띠 밖의 원본 캡션은
  아예 재지 않았다.
  수리: 글자가 있는지는 글자 인식기(화면글자 — macOS Vision)가 정한다.
    ① 카드상자들: 카드마다 그 시간에 대사 자막 자리 글줄이 읽히는지 본다 — 안 읽히면 «가짜»(캐시엔 남기고 돌려주지 않는다),
       카드가 없는데 자막 글줄이 읽힌 시간은 «글자인식» 카드로 채운다. 글자 윗선을 못 잰 카드는 읽힌 글줄 윗변으로 잰다.
    ② 화면캡션(화면글자.화면캡션 — agy 가 «얹은 글자/장면 글자» 판정): 조각 «가림» 에 «화면캡션» 사각형으로 붙인다
       (캡션붙인조각). 굽기는 framing.가림경계 로 피하고, 굽기·준비·make 가 이 파일의 걸림 으로 같은 사각형을 막는다.
  왜 예전 관문을 지났나: 걸림 은 «카드 상자» 와 사람이 적은 «가림» 만 비교했다 — 띠 밖 캡션은 둘 다 아니라 비교 대상에
    없었다(«겹침 0» 이 참이었다). ⑦ 준비의 «컷 하단 잔존 번인 자막» 은 컷 아래 밴드의 노란·흰 글자 픽셀만 본다.

★2026-10-02 루키치213 — «글자 인식이 카드를 진짜로 확인해 놓고 위치는 픽셀 기하를 믿었다» (한 클래스):
  루키치 원본(두 칸 영상통화 화면 · 흰 글자 + 얇은 그림자 자막)에서 _한카드 가 글자를 못 보고 두 칸 사이 검은 틈(7.5~23.0초 ·
  윗변 911 · 가로 x943~976 = 33px)과 칸 모서리(110.9~120초 · 윗변 991 · x932~943 = 11px)를 «카드 상자» 로 쟀다. 실제 자막 글자
  윗선은 856·859·910. _글자확인 은 그 시간에 자막 글줄이 읽혀 카드를 «진짜» 로 확정했지만 위치는 `gtop None·이상치` 일 때만
  고쳤다 — 잘못 잰 윗변 991 이 그대로 조각한계(굽기 crop 밑변 상한)가 되어 첫 완성본 36.9초(원본 117~119초 «뭐가 쩔어 븅X아»)에
  원본 자막이 비쳤다(가림 [0,840,1920,1080] 땜질로 납품). 납품 89편 감사: 실제 비침 0 · 위치 어긋난 카드 88편(잠재 위험).
  왜 기존 관문을 지났나: 조각한계·굽기 끝 걸림·⑦ 준비가 «모두 같은 카드상자» 로 채점했다 — 잘못 잰 값이 스스로를 통과시켰다
  (자가 채점). 자 하나가 틀리면 모든 관문이 같이 틀린다.
  수리(구조 — 자를 셋으로):
    ① 위치 보정: 글자 인식으로 확인된 카드는 «언제나» 읽힌 «확실한» 글줄 위치로 고친다(화면글자.확실한자막표본 — 자막 자리 가운데
       장면 글자 한 장이 카드를 끌어올려 컵라면·아이스크림을 잘라 내지 않게) — 윗변 = min(카드 윗변, 글줄 윗선 − 상자여유),
       가로 = 합집합. 가로폭이 아주 좁거나(5% 미만) 글자 윗선이 화면 맨 아래 7% 안인 «카드» 는 기하를 버리고 글줄 위치만 쓴다(_위치보정).
    ② 셋째 자 «글줄»: 화면글자가 읽은 대사 자막 글줄 하나하나(시각·글자 상자)를 카드와 따로 boxes 에 실어 돌려준다(출처 «글줄»).
       걸림 은 crop 이 그 시각에 글줄 상자와 만나면 걸림으로 본다(카드 기하와 무관) — 굽기 끝·⑦ 준비·make 가 같은 함수라 함께 산다.
    ③ 넷째 자(완성본 픽셀): s2pipe/비침관문.py — 구운 cut.mp4 를 글자 인식기로 직접 읽어 원본 대사 자막과 같은 글이 보이면 멈춘다.
  회귀(납품 155편 · 새 카드·글줄 자로 납품 crop 다시 재기)에서 나온 가짜 걸림과 그 수리 — 모두 «자가 정확해야 관문이 산다»:
    · 카드 확인 표본 몫: 앞뒤 0.3초 표본이 «다른 카드 안» 이면 그 카드 몫(루키치282 정장 무늬 가짜 카드가 다음 자막 첫 표본으로 확인됨)
    · 위치 = 같은 자막 여러 장의 윗선 중앙값(화면글자._윗선고르기 — 296 한 장만 상자가 24px 위로 흔들림)
    · 확실한 표본이 없는 카드는 못 믿을 기하만 바꾼다(287 못 잰 카드가 보수값 824 로 남음)
    · 글줄 시각 = 실제 프레임 시각(화면글자.훑기시각 — 2fps 표본은 +0.21초 프레임 · 299 조각 끝 뒤에 뜬 자막을 조각 안으로 봄)
"""
import json
import os
import subprocess
import sys

import numpy as np
try:  # ffmpeg·ffprobe 스레드 상한은 ff.명령 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
    from . import ff
except ImportError:  # 단독 실행(python s2pipe/x.py)
    import ff  # type: ignore

판 = 15                    # 잰 방법이 바뀌면 올린다(캐시 무효) — 9: 글자 인식으로 카드 확인·채우기(2026-09-29)
                           #   15: 확인된 카드 위치를 «확실한» 글줄로 보정 · 글줄(셋째 자)을 boxes 에 싣는다(2026-10-02 루키치213)
                           #   (10~14 는 같은 날 시험판 — 그 캐시를 다시 쓰지 않게 건너뛴다)
좁은카드 = 0.05            # 카드 가로폭이 화면의 5% 미만이면 기하를 버린다 — 213 두 칸 틈 33px·칸 모서리 11px(1920 의 1.7%·0.6%).
                           #   진짜 자막 카드 가장 좁은 «어?» 도 63px 지만 그때도 글줄 위치가 같은 자리를 주므로 잃는 것이 없다
맨아래 = 0.93              # 글자 윗선이 화면 93% 아래인 «카드» 는 기하를 버린다 — 213 칸 모서리 gtop 1011(93.6%)
글줄여유 = 4               # 글줄 상자 윗변 여유(px) — Vision 글줄 상자 윗선은 실제 글자 윗선보다 0~4px 아래(213: 860 vs 856)
글줄시각 = 0.02            # 글줄(2fps 표본 한 장)이 crop 과 «같은 시각» 인 범위 — crop [t0−0.02, t1−0.02] 안의 표본만 비교.
                           #   t1 은 배타적 끝 — 조각 끝 116.99 바로 뒤 117.0 표본(다음 샷에 뜬 자막)을 넣으면 가짜 걸림(루키치282).
                           #   0.02 = 훑기 시각과 원본 프레임 시각의 반 프레임 어긋남. 조각한계용 창은 표본 앞뒤 0.25초(훑기 간격 절반)
상자여유 = 20               # 글자 윗선 → 상자 윗변 최소 거리(한 줄 카드 968→948 · 266 높은 카드 938→918 실측)
상자최대 = 45               # 이보다 위로 잰 상자 윗변은 이상치(어두운 장면에서 안/밖 비교가 흐려짐) — 여기서 멈춘다
못잰윗선 = 824              # 카드인데 글자를 못 잰 경우 — 띠 윗끝(864) − 40 (가장 보수적 · 새는 쪽으로 버리지 않는다)
시각여유 = 0.2              # 카드 시각은 10fps 로 잰다 — 앞뒤 0.2초까지 겹친 것으로 본다(굽기 한계)
관문겹침 = 0.1              # 관문: 카드 시각은 10fps 로 재서 끝이 최대 0.1초 늦게 잡힌다 — 그만큼은 겹침이 아니다


def _프레임(src, t, W, H):
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", src, "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"]), capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8)
    return a[:W * H].reshape(H, W).astype(np.int16) if len(a) >= W * H else None


def _글자줄(mn, mx, x0, x1, 밝=185, 어=110):
    """정지 글자 = 최소밝기 ≥185 인 픽셀 가로 3px 안에 최대밝기 ≤110 인 픽셀(글자+외곽선/상자)."""
    br = mn[:, x0:x1] >= 밝
    dk = mx[:, x0:x1] <= 어
    near = np.zeros_like(dk)
    for k in (1, 2, 3):
        near[:, k:] |= dk[:, :-k]
        near[:, :-k] |= dk[:, k:]
    return br & near


def _한카드(src, c0, c1, W, H):
    """(상자윗변, 글자윗선, x0, x1, 잰방법) — 원본 픽셀 좌표.
    ① 카드 안 3장(0.1초 간격)의 최소/최대 밝기로 «정지한 글자» 만 남기고, 카드 앞·뒤 프레임 둘 다에 있던 글자꼴
       (장면 속 정지 무늬 — 후드티 글씨·소파 모서리)은 뺀다(2026-09-27 264·187·188 에서 글자 덩어리가 위 장면 무늬와 붙어
       윗선이 790 까지 튀었다).
    ② 띠(80~90%)에 걸친 줄을 씨앗으로, 위로 «가운데 정렬된 글자 줄»(두 줄·세 줄 카드)만 이어 붙인다.
    ③ 반투명 상자 윗변 = 글자 윗선 위 45px 안에서 «상자 안 밝기 − 상자 밖 밝기» 가 가장 크게 뛰는 줄.
       못 찾으면 글자 윗선 − 20(한 줄 카드 968→948 · 266 높은 카드 938→918 실측 간격). 둘 중 높은 쪽."""
    mid = (c0 + c1) / 2
    d = min(0.1, max(0.0, (c1 - c0) / 2 - 0.05))
    fr = [f for f in (_프레임(src, mid + k * d, W, H) for k in (-1, 0, 1)) if f is not None]
    if not fr:
        return (못잰윗선, None, 0, W, "프레임없음")
    st = np.stack(fr)
    X0, X1 = int(W * 0.12), int(W * 0.88)
    Y0 = int(H * 0.60)
    앞, 뒤 = _프레임(src, c0 - 0.25, W, H), _프레임(src, c1 + 0.25, W, H)
    정지 = None
    if 앞 is not None and 뒤 is not None:
        정지 = _글자줄(앞[Y0:], 앞[Y0:], X0, X1) & _글자줄(뒤[Y0:], 뒤[Y0:], X0, X1)
        z = 정지.copy()
        for k in (1, 2):
            z[k:] |= 정지[:-k]; z[:-k] |= 정지[k:]; z[:, k:] |= 정지[:, :-k]; z[:, :-k] |= 정지[:, k:]
        정지 = z
    mn3, mx3, m1 = st.min(axis=0), st.max(axis=0), st[len(st) // 2]
    두꺼움 = False
    # 앞·뒤에도 같은 글자가 있으면(카드 검출이 한 자막을 둘로 나눔) 정지 무늬 빼기가 글자까지 지운다 — 빼지 않고 다시 잰다
    #   «엄격» = 흰 글자(≥225)·검은 외곽/상자(≤70)만 — 장면 무늬가 자막 줄에 붙어 두꺼워진 카드(싱글187 137초 검은 셔츠)용
    for 방법, mn, mx, 뺌, 문 in (("정지3장", mn3, mx3, 정지, (185, 110)), ("정지3장·무늬포함", mn3, mx3, None, (185, 110)),
                              ("가운데1장", m1, m1, None, (185, 110)), ("정지3장·엄격", mn3, mx3, None, (225, 70))):
        if 방법 == "정지3장" and 정지 is None:
            continue
        g = _글자줄(mn[Y0:], mx[Y0:], X0, X1, *문)
        if 뺌 is not None:
            g = g & ~뺌
        rows = g.sum(axis=1)
        # 줄 덩어리(틈 6px 이하는 한 줄)
        runs, s0, last = [], None, None
        for y in range(len(rows)):
            if rows[y] >= 3:
                if s0 is None:
                    s0 = y
                elif y - last > 6:
                    runs.append((s0, last)); s0 = y
                last = y
        if s0 is not None:
            runs.append((s0, last))
        띠0, 띠1 = int(H * 0.80) - Y0, int(H * 0.90) - Y0
        # 씨앗 = 띠에 걸치거나 그 아래(93% 카드 — 싱글207)의 «한 줄 두께»(10~75px) 덩어리 중 가장 위.
        #   75px 넘는 덩어리는 장면 무늬(후드티 글씨 — 싱글264 42초)라 씨앗이 못 된다.
        걸침 = [r for r in runs if r[1] >= 띠0 and r[0] <= 띠1 + 60 and rows[r[0]:r[1] + 1].sum() >= 40]
        씨 = [r for r in 걸침 if 10 <= r[1] - r[0] <= 75]
        if 걸침 and not 씨:
            두꺼움 = True
        if not 씨:
            continue
        def 어두운바탕(r0, r1, cc):
            return float(np.median(mn[Y0 + r0:Y0 + r1 + 1, X0 + cc[0]:X0 + cc[-1] + 1])) <= 120

        def 폭(r):
            return np.where(g[r[0]:r[1] + 1].any(axis=0))[0]
        # 자막 줄 = 어두운 바탕(반투명 상자·외곽선) 위 밝은 글자. 그런 덩어리가 있으면 그중 가장 위, 없으면(상자 없는
        #   날짜 캡션 — 싱글188) 전체에서 가장 위 — 잘못 골라도 더 자르는 쪽(새는 쪽이 아니다).
        어둠 = [r for r in 씨 if 어두운바탕(r[0], r[1], 폭(r))]
        seed = min(어둠 or 씨, key=lambda r: r[0])

        def 가운데(r):
            cols = np.where(g[r[0]:r[1] + 1].any(axis=0))[0]
            return (X0 + (cols[0] + cols[-1]) / 2, cols[-1] - cols[0]) if len(cols) else (None, 0)
        sc, sw = 가운데(seed)
        top_r = seed
        for _ in range(2):                                   # 위로 두 줄까지(세 줄 카드)
            위 = [r for r in runs if r[1] < top_r[0] and top_r[0] - r[1] <= 35]
            if not 위:
                break
            r = max(위, key=lambda r: r[1])
            c, w_ = 가운데(r)
            if c is None or abs(c - W / 2) > W * 0.10 or abs(c - sc) > W * 0.10 or rows[r[0]:r[1] + 1].sum() < 40 \
                    or not (10 <= r[1] - r[0] <= 75):
                break
            # 자막 줄은 어두운 바탕(상자·외곽선) 위 밝은 글자다 — 밝은 바탕 위 어두운 글씨(후드티 «ORIGINALS»)는 아니다
            #   두 줄 사이 틈도 상자 안이라 어둡다(후드티·셔츠 무늬와 자막 사이는 옷감이라 밝다)
            cc = 폭(r)
            if not 어두운바탕(r[0], r[1], cc) or not 어두운바탕(r[1] + 1, max(r[1] + 1, top_r[0] - 1), 폭(top_r)):
                break
            top_r = r
        gtop = Y0 + top_r[0]
        cols = np.where(g[top_r[0]:seed[1] + 1].any(axis=0))[0]
        x0 = X0 + int(np.percentile(cols, 1))
        x1 = X0 + int(np.percentile(cols, 99)) + 1
        if gtop < 못잰윗선 + 상자여유:
            return (못잰윗선, gtop, x0, x1, 방법 + "·이상치")
        a = st.mean(axis=0)
        in0, in1 = x0 + 20, x1 - 20
        o0, o1 = (max(0, x0 - 90), max(0, x0 - 40)), (min(W, x1 + 40), min(W, x1 + 90))
        box = gtop - 상자여유
        if in1 - in0 > 20 and (o0[1] - o0[0]) + (o1[1] - o1[0]) > 20:
            p = np.array([np.median(a[y, in0:in1]) for y in range(gtop - 상자최대 - 3, gtop + 1)])
            q = np.array([np.median(np.r_[a[y, o0[0]:o0[1]], a[y, o1[0]:o1[1]]]) for y in range(gtop - 상자최대 - 3, gtop + 1)])
            base = gtop - 상자최대 - 3
            best, by = 0.0, None
            for y in range(gtop - 상자최대, gtop - 2):
                i = y - base
                step = (p[i - 3:i].mean() - p[i:i + 3].mean()) - (q[i - 3:i].mean() - q[i:i + 3].mean())
                if step > best:
                    best, by = step, y
            if by is not None and best >= 12:
                box = min(box, by)
                방법 += "·상자"
        return (int(box), int(gtop), int(x0), int(x1), 방법)
    return (못잰윗선, None, 0, W, "이상치·두꺼운 덩어리뿐" if 두꺼움 else "글자못잼")


def 카드상자들(src, log=None):
    """[{t0,t1,top,gtop,x0,x1,how}] — 박힌 자막 카드마다 상자 윗변(원본 픽셀). `<원본>.카드상자.json` 에 둔다."""
    from . import 자막띠시각 as 띠
    src = os.path.abspath(os.path.expanduser(src))
    cards = 띠.카드들(src)
    st = os.stat(src)
    from . import 화면글자 as _글
    key = f"{st.st_size}:{int(st.st_mtime)}:{len(cards)}:{판}:{'ocr' if _글.인식기() else 'px'}"
    cache = src + ".카드상자.json"
    try:
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("key") == key:
            return [b for b in c["boxes"] if not b.get("가짜")]
    except (OSError, ValueError, KeyError):
        pass
    r = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src]), capture_output=True, text=True)
    W, H = (int(v) for v in r.stdout.strip().split(",")[:2])
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda c: _한카드(src, c[0], c[1], W, H), cards))
    boxes = [{"t0": c[0], "t1": c[1], "top": r_[0], "gtop": r_[1], "x0": r_[2], "x1": r_[3], "how": r_[4]}
             for c, r_ in zip(cards, res)]
    boxes = _글자확인(src, boxes, W, H, log)
    try:
        tmp = cache + f".{os.getpid()}"
        json.dump({"key": key, "W": W, "H": H, "boxes": boxes}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, cache)
    except OSError:
        pass
    if log:
        카 = [b for b in boxes if b.get("출처") != "글줄"]
        n이상 = sum(1 for b in 카 if ("이상치" in b["how"] or "못" in b["how"]) and not b.get("가짜"))
        n가짜 = sum(1 for b in 카 if b.get("가짜"))
        n채움 = sum(1 for b in 카 if b.get("출처") == "글자인식")
        n보정 = sum(1 for b in 카 if not b.get("가짜") and ("글자보정" in b["how"] or "글자위치" in b["how"]))
        참 = [b for b in 카 if not b.get("가짜")]
        log(f"    박힌 자막 카드 {len(참)}장 상자 윗변 잼 — 가장 높은 {min((b['top'] for b in 참), default='-')}"
            f" · 중앙 {sorted(b['top'] for b in 참)[len(참) // 2] if 참 else '-'}"
            + (f" · 보수값/1장 {n이상}장" if n이상 else "")
            + f" · 글자 인식 확인: 가짜 {n가짜}장 뺌 · 놓친 자막 {n채움}장 채움 · 위치 보정 {n보정}장"
            + f" · 글줄(셋째 자) {len(boxes) - len(카)}개")
    return [b for b in boxes if not b.get("가짜")]


def _인식없음():
    """인식기가 없는 컴퓨터(맥 아님) — S2_NO_SCREENTEXT=1 일 때만 옛 방식(픽셀 카드만)으로 간다. 아니면 멈춘다."""
    if os.environ.get("S2_NO_SCREENTEXT") == "1":
        print("    [주의] 화면글자 인식기 없음(S2_NO_SCREENTEXT=1) — 카드 확인·화면 캡션 관문을 건너뛴다(2026-09-29 전 방식)",
              flush=True)
        return True
    return False


def _글자확인(src, boxes, W, H, log=None):
    """★2026-09-29 — 픽셀 모양 카드를 글자 인식으로 확인한다(머리 주석 (b)(c)).
    · 카드 시간(±0.3초)에 대사 자막 자리 글줄이 읽혔으면 «확인». 2fps 훑기에 없으면 카드 가운데(길면 앞·뒤도) 한 장씩 더 읽고,
      그래도 없으면 «가짜» (운동화·탁자·냄비 가장자리 — 글줄이 안 읽힌다).
    · 글자 윗선을 못 잰 카드(보수값 824 · 이상치)는 읽힌 글줄 윗변 − 상자여유 로 잰다.
    · 카드가 덮지 않은 시간에 자막 글줄이 읽혔으면 «글자인식» 카드로 채운다(표본 ±0.5초)."""
    from . import 화면글자 as 글
    if 글.인식기() is None and _인식없음():
        return boxes
    띠 = 글._띠(src)
    c = 글._캐시(src)
    표본 = 글.자막표본(c["frames"], 띠)             # (t, 줄) — 가운데 대사 자막 자리의 «글자 있음» 글줄

    def 안(t, b):
        return b["t0"] <= t < b["t1"]

    def 읽힘(b, 목록):
        # 카드 앞뒤 0.3초 표본도 그 카드 것으로 보되, 다른 카드 «안» 에 든 표본은 그 카드 몫이다(2026-10-02 루키치282 — 정장·넥타이를
        #   잡은 가짜 카드 115.7~117.0 이 다음 카드 117.0~ 의 첫 자막 표본 117.0 으로 «확인» 돼 전체화면 조각이 가짜로 걸렸다).
        #   몫을 뺏긴 카드는 아래에서 카드 안을 한두 장 더 읽어 가린다(진짜 자막이면 거기서 읽힌다).
        return [l for t, l in 목록 if b["t0"] - 0.3 <= t <= b["t1"] + 0.3
                and (안(t, b) or not any(안(t, o) for o in boxes if o is not b))]
    남은 = [b for b in boxes if not 읽힘(b, 표본)]
    시각 = []
    for b in 남은:
        d = b["t1"] - b["t0"]
        ts = [b["t0"] + d / 2] + ([b["t0"] + 0.15, b["t1"] - 0.15] if d > 1.0 else [])
        시각 += [(id(b), t) for t in ts]
    더 = 글.시각들읽기(src, [t for _k, t in 시각]) if 시각 else []
    더본, 더표 = {}, []
    for (k, _t), (t, rows) in zip(시각, 더):
        for _t2, l in 글.자막표본([(t, rows)], 띠):
            더본.setdefault(k, []).append(l)
            더표.append((t, l))
    # 위치를 잴 때는 «확실한» 자막 표본만(화면글자.확실한자막표본 — 자막 자리 가운데 장면 글자 한 장을 뺀다 · 2026-10-02)
    확실 = {id(l) for _t, l in 글.확실한자막표본(표본 + 더표)}
    for b in boxes:
        ls = 읽힘(b, 표본) or 더본.get(id(b), [])
        b["출처"] = "카드"
        if not ls:
            b["가짜"] = True
            b["how"] += "·글자없음"
            continue
        ls확실 = [l for l in ls if id(l) in 확실]
        _위치보정(b, ls확실 or ls, W, H, 합집합=bool(ls확실))
    참 = [b for b in boxes if not b.get("가짜")]
    # 놓친 자막 채우기는 글줄 높이가 그 원본 자막 높이 중앙값의 0.6~1.6배인 표본만(2026-10-02 점심이네32 344.0초 — 흰 티셔츠에
    #   인쇄된 말풍선 «에구궁»(높이 0.112 = 1.7배)을 채운 카드로 잡아 납품 crop 이 가짜로 걸렸다). 흐린 한 장 자막은 그대로 채운다.
    _hs = sorted(l["h"] for _t, l in 표본)
    _med = _hs[len(_hs) // 2] if _hs else 0.0
    빈 = sorted(((t, l) for t, l in 표본 if not any(b["t0"] - 0.3 <= t <= b["t1"] + 0.3 for b in 참)
                and 글.확실높이[0] * _med <= l["h"] <= 글.확실높이[1] * _med), key=lambda x: x[0])
    묶음, 여 = [], 0.5 / 1.0 + 0.01             # 이웃 표본(0.5초 간격)끼리 한 카드
    for t, l in 빈:
        if 묶음 and t - 묶음[-1][-1][0] <= 여:
            묶음[-1].append((t, l))
        else:
            묶음.append([(t, l)])
    for g in 묶음:
        # 윗선 = 확실한 표본이 있으면 그 표본들의 윗선(같은 자막 중앙값 ys)만, 없으면 모든 표본의 부푼 상자 고친 윗선(2026-10-02
        #   점심이네62 221.0초 «아닙니다…» 상자 높이 1.4배 → 윗선 905 · 실제 ≈930)
        gs = [l for _t, l in g if id(l) in 확실]
        gt = int((min(l.get("ys", l["y"]) for l in gs) if gs else min(글.윗선추정(l, _med) for _t, l in g)) * H)
        boxes.append({"t0": round(max(0.0, g[0][0] - 0.5), 2), "t1": round(g[-1][0] + 0.5, 2), "top": gt - 상자여유,
                      "gtop": gt, "x0": int(min(l["x"] for _t, l in g) * W),
                      "x1": int(max(l["x"] + l["w"] for _t, l in g) * W) + 1, "how": "글자인식",
                      "출처": "글자인식", "글": g[0][1]["s"]})
    # ★셋째 자 «글줄» (2026-10-02 루키치213) — 읽힌 대사 자막 글줄 하나하나를 카드와 따로 싣는다. 걸림 은 crop 이 그 «시각» 에
    #   그 글자 상자와 만나는지 본다(카드 기하와 무관 — 카드 위치가 틀려도 이 자는 틀리지 않는다). 조각한계는 앞뒤 0.25초 창으로 쓴다.
    #   2fps 훑기 표본 + 카드 확인용으로 더 읽은 표본(짧은 카드) 중 «확실한» 것만 싣는다(장면 글자 한 장이 crop 을 막지 않게).
    #   시각은 «실제 프레임 시각» — 2fps 훑기 표본은 t+0.21초 프레임이다(화면글자.훑기시각 · 루키치299 149.5 → 149.70).
    #   카드 확인용으로 더 읽은 표본은 -ss 정확 탐색이라 그대로 둔다.
    _fps = 글.원본fps(src)
    실제 = [(글.훑기시각(t, c["fps"], _fps), l) for t, l in 표본 if id(l) in 확실] + [(t, l) for t, l in 더표 if id(l) in 확실]
    for t, l in sorted(실제, key=lambda x: x[0]):
        gt = int(l.get("ys", l["y"]) * H)                      # 한 장 상자 흔들림 대신 같은 자막 윗선 중앙값(루키치296)
        boxes.append({"t0": round(max(0.0, t - 0.25), 3), "t1": round(t + 0.25, 3), "t": round(t, 3),
                      "top": gt - 글줄여유, "gtop": gt, "y1": int((l["y"] + l["h"]) * H) + 1,
                      "x0": int(l["x"] * W), "x1": int((l["x"] + l["w"]) * W) + 1,
                      "how": "글줄", "출처": "글줄", "글": l["s"]})
    boxes.sort(key=lambda b: b["t0"])
    return boxes


def _위치보정(b, ls, W, H, 합집합=True):
    """★2026-10-02 루키치213 — 글자 인식으로 «진짜» 로 확인된 카드의 위치를 읽힌 글줄로 고친다(머리 주석 2026-10-02 ①).
    예전엔 gtop None·이상치 일 때만 고쳐 두 칸 화면 틈(윗변 911 · 폭 33px)·칸 모서리(윗변 991 · 폭 11px)를 잰 «카드» 가 그대로
    한계가 됐다(실제 글자 윗선 856). 글줄 윗선은 카드 시간(±0.3초) 안 모든 표본의 가장 위 — 긴 카드는 여러 자막을 품는다
    (213 110.9~120초 카드 = «어?» 920 · «와 개쩐다» 920 · «뭐가 쩔어 븅X아» 860).
    합집합=False — 그 카드 시간에 «확실한» 표본이 없다(한 장·흐린 표본뿐): 기하를 못 믿을 카드(못 잼·이상치·좁음·맨 아래)만 그 표본
    위치로 바꾸고, 멀쩡한 기하는 장면 글자 한 장으로 끌어올리지 않는다(루키치287 227.9초 — 못 잰 카드가 보수값 824 로 남아 가짜 걸림)."""
    ot = int(min(l.get("ys", l["y"]) for l in ls) * H)        # ys = 같은 자막 여러 장의 윗선 중앙값(화면글자._윗선고르기)
    ox0 = int(min(l["x"] for l in ls) * W)
    ox1 = int(max(l["x"] + l["w"] for l in ls) * W) + 1
    b["글윗선"] = ot
    if b.get("gtop") is None or "이상치" in b["how"] or (b["x1"] - b["x0"]) < W * 좁은카드 or b["gtop"] >= H * 맨아래:
        b["gtop"], b["top"], b["x0"], b["x1"] = ot, ot - 상자여유, ox0, ox1
        b["how"] += "·글자위치"
        return
    if not 합집합:
        return
    새 = (min(b["top"], ot - 상자여유), min(b["gtop"], ot), min(b["x0"], ox0), max(b["x1"], ox1))
    if 새 != (b["top"], b["gtop"], b["x0"], b["x1"]):
        b["top"], b["gtop"], b["x0"], b["x1"] = 새
        b["how"] += "·글자보정"


def 확인된카드들(src):
    """[(t0, t1)] — 글자 인식으로 확인된 «픽셀 카드» 만(가짜 빼고, 채운 카드는 시각이 ±0.5초 어림이라 뺀다).
    카드경계검사·경계제안(경계자리.원본자리)처럼 «문장이 화면에 떠 있는 시각» 이 필요한 곳이 쓴다 — 두 곳이 같은 이 목록을 쓴다.
    한 카드 안에서 읽힌 글줄이 다른 문장으로 바뀌면 그 자리에서 가른다(글줄가르기 — 2026-10-04 루키치67)."""
    boxes = 카드상자들(src)
    return 글줄가르기([(b["t0"], b["t1"]) for b in boxes if b.get("출처", "카드") == "카드"],
                     [(b["t"], b.get("글", ""), b.get("top", 0)) for b in boxes if b.get("출처") == "글줄" and "t" in b])


글줄같음 = 0.5          # 두 글줄의 글 닮음(difflib — 공백·부호 뺌)이 이 이상이면 같은 문장(인식 흔들림 «롤/볼»·«ㅄ/비»)


def 글줄가르기(cards, 글줄):
    """픽셀 카드 [(t0,t1)] 를 그 안에서 읽힌 글줄 [(실제 프레임 시각, 글)] 이 바뀌는 자리에서 가른다.
    ★2026-10-04 루키치67 — 픽셀 카드 검출(자막띠시각.카드들)이 132.6~143.9 를 카드 하나로 뭉쳤는데, 그 안에서 글줄은 «왜 그랬니?» →
      «죄송해요 몰랐습니다» → «아빠 오늘 늦게 들어간다.» → «엄마 자면 연락하도록» → «예 아버지..» 다섯 문장이었다. 경계제안·카드경계검사는
      «경계가 카드 한가운데» 를 문장 자르기로 보는데, 뭉친 카드에서는 문장 사이 경계도 «카드 한가운데» 라 가짜 제안이 나왔다.
      클래스: 카드 끝 = «글자 모양이 바뀐 때» 를 픽셀 한 자로만 쟀다(채팅·밝은 장면에서 모양 변화를 놓침). 글자 인식이 이미 문장을
      읽고 있었다 — 그 자로 가른다. 가르는 자리 = 앞 문장 마지막 표본과 다음 문장 첫 표본의 가운데(2fps · ±0.25초 어림).
    글줄이 한 문장뿐이거나 없으면 카드 그대로."""
    import difflib
    import re
    깨 = re.compile(r"[\s.,!?~…·\"'()\[\]]")
    # 한 장(같은 시각)에 글줄이 여럿이면(두 줄 자막·채팅 목록) 위→아래로 이어 한 글로 본다 — 줄마다 따로 두면 시각순 정렬에서
    #   두 줄이 번갈아 와 «다른 문장» 으로 갈렸다(루키치160 식단 목록 96.3~101.4 가 9조각 · 112·144 같은 말 두 줄)
    장 = {}
    for x in 글줄:
        t, g, y = (x + (0,))[:3] if len(x) == 2 else x
        장.setdefault(round(t, 3), []).append((y, 깨.sub("", g)))
    합친 = [(t, "".join(g for _y, g in sorted(v))) for t, v in 장.items()]
    out = []
    for t0, t1 in cards:
        안 = sorted((t, g) for t, g in 합친 if t0 <= t < t1 and g)
        무리 = []                                         # 같은 문장으로 이어 읽힌 표본 무리 [[(t, 글), …], …]
        for t, g in 안:
            if 무리 and difflib.SequenceMatcher(None, 무리[-1][-1][1], g).ratio() >= 글줄같음:
                무리[-1].append((t, g))
            else:
                무리.append([(t, g)])
        # 한 장뿐인 무리(흐린 장·인식 쓰레기 «10l0곱IC극» · 같은 말 흔들림 «기어세컨드/기아세칸도»)는 가르지 않는다 —
        #   두 장 이상(≥0.5초) 같은 글로 읽힌 문장 사이에서만 가른다(2026-10-04 납품 692편 재기: 한 장 무리까지 가르면 +1254장 중
        #   상당수가 인식 쓰레기·말 흔들림이었다).
        무리 = [m for m in 무리 if len(m) >= 2]
        합 = []                                           # 한 장 무리를 뺀 뒤 이웃이 같은 문장이면 다시 잇는다(가운데 쓰레기 한 장)
        for m in 무리:
            if 합 and difflib.SequenceMatcher(None, 합[-1][-1][1], m[0][1]).ratio() >= 글줄같음:
                합[-1] += m
            else:
                합.append(m)
        무리 = 합
        자리 = []
        for a, b in zip(무리, 무리[1:]):
            m = round((a[-1][0] + b[0][0]) / 2, 2)
            if t0 + 0.1 < m < t1 - 0.1:
                자리.append(m)
        경 = [t0] + 자리 + [t1]
        out += list(zip(경, 경[1:]))
    return out


def 캡션들(src, log=None):
    """원본 화면 캡션(편집자가 얹은 글자 · 대사 자막 자리 밖) — [{t0,t1,x0,y0,x1,y1,글}] 원본 픽셀. s2pipe/화면글자.py."""
    from . import 화면글자 as 글
    if 글.인식기() is None and _인식없음():
        return []
    return 글.화면캡션(src, log=log)


def 캡션붙인조각(seg, 캡션):
    """조각의 «가림» 에 그 조각 시간과 겹치는 화면 캡션 사각형을 붙인 «사본» (원문화면 조각은 그대로 — 화면 글이 내용).
    «글자허용»: ["사조참치", …] 에 든 글(판정키 부분 일치)은 붙이지 않는다(agy 가 장면 글자를 캡션으로 잘못 본 때 사람이 푼다).
    가림 항목 = [x0, y0, x1, y1, t0, t1, "화면캡션:글"] — framing.가림경계 는 앞 여섯 칸만 본다."""
    if seg.get("원문화면") or not 캡션:
        return seg
    from .화면글자 import 판정키
    허용 = [판정키(x) for x in seg.get("글자허용") or [] if 판정키(x)]
    # 조각과 0.1초(관문겹침) 넘게 겹치는 캡션만 — 경계에 몇 ms 걸친 캡션(점심이네29 «4차 이슈 발생» 끝 204.75 · 조각 204.744~)까지
    #   붙이면 굽기가 조각 전체를 그 캡션 밖으로 피하느라 쓸 자리가 반토막 난다
    #   «글자판»(작은 글이 빽빽한 삽입 그림·채팅 캡처 — 2026-10-03 루키치161)은 전체화면 조각에선 통째로 보여 잘리지 않는다 —
    #   그 내용을 보이려고 전체화면으로 둔 조각을 막지 않게 붙이지 않는다(잘림만이 결함이다).
    붙 = [[c["x0"], c["y0"], c["x1"], c["y1"], c["t0"], c["t1"], "화면캡션:" + c["글"]] for c in 캡션
         if min(c["t1"], seg["t1"]) - max(c["t0"], seg["t0"]) > 관문겹침 and not any(h in 판정키(c["글"]) for h in 허용)
         and not (seg.get("전체화면") and c.get("종류") == "글자판")]
    if not 붙:
        return seg
    return dict(seg, 가림=list(seg.get("가림") or []) + 붙)


캡션카드겹침t = 0.5       # 카드 시간의 이 몫 이상을 화면 캡션이 덮고 —
캡션카드겹침x = 0.15      # 카드 가로폭의 이 몫 이상이 캡션 사각형과 겹치며, 카드 시간 안에 읽힌 대사 글줄이 하나도 없으면 «캡션 카드»


def 캡션카드빼기(boxes, 캡션):
    """박힌 자막 «카드» 가운데 사실은 화면 캡션(«다음날»·«4시간 후» 같은 편집 글자)을 잡은 것을 뺀 목록 — 관문(걸림)에 넘길 때만 쓴다.
    ★2026-10-04 루키치64 — 원본 왼쪽 아래 큰 캡션 «다음날»(185.8~187.1 · x21~521 · y837~1022)이 자막 띠에 걸쳐 픽셀 카드
      (186.0~186.9 · x232~1024)로 잡혔고, 카드 끝 0.3초 창 밖 표본(187.2초 다음 자막 «롤그?»)이 «확인» 해 진짜 카드가 됐다.
      그래서 원문화면 조각(화면 글이 내용 — 캡션 검사는 건너뜀)이 «박힌 자막이 보인다» 로 반려됐다.
      클래스: 같은 글자를 두 자(카드 = 박힌 대사 자막 · 화면캡션 = 얹은 글자)가 따로 재 둘 다 «글자 있음» 이라 하면 카드 쪽이 이겼다.
      수리: 캡션이 카드 시간의 절반 이상을 덮고 카드 가로폭 15% 이상 겹치며 카드 시간 «안» 에 읽힌 대사 글줄이 없으면 그 카드는 캡션이다.
      캡션 자체는 다른 길이 막는다 — 원문화면이 아닌 조각은 캡션붙인조각 이 «가림» 으로 붙여 걸림 이 보고, 원문화면 조각은 내용이다.
    재기(2026-10-04 납품 681편 카드상자·화면캡션 캐시): 조건(겹침 x 제외)에 든 카드 9장 — 프레임으로 7장은 캡션만(64 «다음날»·
      «4시간 후» · 117 «다음 날» · 67 «2시간 후» · 71 «5인 톡방» · 74 «오후 8시 50분» · 93 «여자들의 단톡방»), 2장은 진짜 자막
      (153 · 89 — 인식기가 자막 한 줄을 둘로 읽어 오른쪽 조각이 «캡션» 이 됨 · 카드와 가로 겹침 3~4%) → 가로 겹침 15% 로 갈랐다."""
    if not 캡션:
        return boxes
    글줄t = [b["t"] for b in boxes if b.get("출처") == "글줄" and "t" in b]
    out = []
    for b in boxes:
        if b.get("출처") == "카드" and not any(b["t0"] <= t < b["t1"] for t in 글줄t):
            d, w = b["t1"] - b["t0"], b["x1"] - b["x0"]
            if any(min(b["t1"], c["t1"]) - max(b["t0"], c["t0"]) >= 캡션카드겹침t * d
                   and min(b["x1"], c["x1"]) - max(b["x0"], c["x0"]) >= 캡션카드겹침x * w
                   and min(b.get("y1", 10 ** 6), c["y1"]) > max(b["top"], c["y0"]) for c in 캡션):
                continue
        out.append(b)
    return out


def 캡션조각검사(src, segs, box, log=None):
    """make ① 굽기 전 검사 — (반려 목록, 주의 목록). 조각(원문화면 제외)에 원본 화면 캡션이 0.1초 넘게 걸리면:
    전체화면 조각이거나, 굽기(framing.가림경계 — 같은 함수)가 피해도 쓸 세로가 원본 높이 절반이 안 되면(가운데 큰 캡션) 반려,
    아니면 주의(굽기가 피하고 굽기 끝 관문이 다시 본다). ★2026-09-29 점심이네2 «6월 14일→1월 03일»."""
    from . import framing as _fr
    캡 = 캡션들(src, log=log)
    bad, warn = [], []
    if not 캡:
        return bad, warn
    r = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src]), capture_output=True, text=True)
    W, H = (int(v) for v in r.stdout.strip().split(",")[:2])
    ratio = float(box.get("w", 1080)) / float(box.get("h", 908))
    uh = int(H * box.get("sub_zone_top", 0.872))
    for k, s in enumerate(segs):
        if s.get("원문화면"):
            continue
        s2 = 캡션붙인조각(s, 캡)
        붙 = [g for g in (s2.get("가림") or []) if len(g) >= 7 and str(g[6]).startswith("화면캡션:")
             and min(g[5], s["t1"]) - max(g[4], s["t0"]) > 관문겹침]
        if not 붙:
            continue
        글_ = " · ".join(f"«{str(g[6])[5:][:12]}» {max(g[4], s['t0']):.1f}~{min(g[5], s['t1']):.1f}" for g in 붙[:4])
        x0, y0, x1, y1 = _fr.가림경계((0, 0, W, H), s2, s["t0"], s["t1"], uh, ratio)
        ch = min(min(y1, uh) - y0, (x1 - x0) / ratio)
        if s.get("전체화면") or ch < H * 0.5:
            bad.append(f"★조각 {k}({s['t0']:.1f}~{s['t1']:.1f})에 원본 화면 캡션 {글_} — "
                       + ("전체화면이라 그대로 보인다" if s.get("전체화면") else f"피하면 세로 {max(ch, 0):.0f}px 만 남는다(가운데 큰 캡션)")
                       + ". 캡션 샷을 조각에서 빼라(원본 시각을 옮긴다). 장면 속 글자(휴대폰·포장지)면 조각 «글자허용»")
        else:
            warn.append(f"조각 {k}에 원본 화면 캡션 {글_} — 굽기가 가림으로 피한다(세로 {ch:.0f}px)")
    return bad, warn


def 겹친카드(boxes, t0, t1, 여유=시각여유):
    return [b for b in boxes if b["t0"] < t1 + 여유 and b["t1"] > t0 - 여유]


def 조각한계(boxes, t0, t1, 기본, pad):
    """조각 [t0,t1] 에서 crop 이 쓸 수 있는 세로(밑변 y 상한). 카드가 없으면 기본(=sub_zone_top − pad)보다 올리지 않는다."""
    겹 = 겹친카드(boxes, t0, t1)
    if not 겹:
        return 기본, None
    hi = min(겹, key=lambda b: b["top"])
    return min(기본, hi["top"] - pad), hi


def 걸림(boxes, crops, 가림=None):
    """최종 관문 — crops: [{t0,t1,x,y,w,h,이름}] (원본 시각·원본 픽셀). 가림: [{t0,t1,x0,y0,x1,y1}] 사람이 잰 화면 캡션.
    crop 사각형이 겹치는 카드 상자(윗변 아래 전부, 가로는 글자 범위)나 가림 사각형과 만나면 걸림.
    boxes 에 «글줄»(출처 글줄 — 화면글자가 읽은 대사 자막 글자 상자 하나하나 · 2026-10-02)이 있으면 그 시각 crop 과 글자 상자가
    만나는지도 본다(셋째 자 — 카드 기하가 틀려도 이 자는 안 틀린다). 굽기 끝·⑦ 준비·make 가 같은 boxes 를 넘기므로 함께 산다."""
    out = []
    for c in crops:
        bx0, bx1, by0, by1 = c["x"], c["x"] + c["w"], c["y"], c["y"] + c["h"]
        글줄본 = set()
        for b in boxes:
            if b.get("출처") == "글줄":
                # ★셋째 자(2026-10-02 루키치213) — 카드 기하와 무관하게, crop 이 «그 시각» 에 읽힌 자막 글자 상자와 만나는가.
                #   가로 여유 없음(글자 상자가 정확하다) · 같은 crop 에서 같은 글은 한 번만 적는다.
                if not (c["t0"] - 글줄시각 <= b["t"] <= c["t1"] - 글줄시각):
                    continue
                if by1 > b["top"] and by0 < b.get("y1", b["gtop"] + 40) and bx0 < b["x1"] and bx1 > b["x0"] \
                        and b["글"] not in 글줄본:
                    글줄본.add(b["글"])
                    out.append({"이름": c.get("이름"), "t": b["t"], "겹초": 0.5,          # 표본 한 장 = 훑기 간격 0.5초
                                "밑변": by1, "상자윗변": b["top"],
                                "침범px": by1 - b["gtop"], "종류": "글줄", "글자": True, "글": b["글"]})
                continue
            겹초 = min(b["t1"], c["t1"]) - max(b["t0"], c["t0"])
            if 겹초 <= 관문겹침:
                continue
            if by1 > b["top"] and bx0 < b["x1"] + 30 and bx1 > b["x0"] - 30:
                out.append({"이름": c.get("이름"), "t": round(max(b["t0"], c["t0"]), 2), "겹초": round(겹초, 2),
                            "밑변": by1, "상자윗변": b["top"], "침범px": by1 - b["top"], "종류": "카드",
                            # 글자 = crop 밑변이 박힌 글자 윗선까지 내려옴(글자가 보인다). 아니면 반투명 상자 윗단만(띠).
                            #   글자 윗선을 못 잰 카드는 글자로 본다(새는 쪽으로 버리지 않는다).
                            "글자": b.get("gtop") is None or by1 > b["gtop"]})
        for g in 가림 or []:
            겹초 = min(g["t1"], c["t1"]) - max(g["t0"], c["t0"])
            if 겹초 <= 관문겹침:
                continue
            if bx0 < g["x1"] and bx1 > g["x0"] and by0 < g["y1"] and by1 > g["y0"]:
                out.append({"이름": c.get("이름"), "t": round(max(g["t0"], c["t0"]), 2), "겹초": round(겹초, 2),
                            "밑변": by1, "상자윗변": g["y0"], "침범px": None, "종류": g.get("종류", "가림"),
                            "글자": True, **({"글": g["글"]} if g.get("글") else {})})
    return out


def beats_crops(log, W, H):
    """beats.json → crop 목록. 비트 · 한 장 구도(frames) · 전체/원문화면 · 프레임-인-프레임 모두.
    (2026-09-27 이전 beats.json 엔 한 장 구도 crop 이 없다 — 그 조각은 «미기록» 으로 돌려준다)"""
    crops, 미기록 = [], []
    for b in log.get("beats", []):
        w, h, x, y = b["crop"]
        crops.append({"t0": b["t0"], "t1": b["t1"], "x": x, "y": y, "w": w, "h": h, "이름": f"조각{b['seg']} 비트"})
    for f in log.get("frames", []):
        w, h, x, y = f["crop"]
        crops.append({"t0": f["t0"], "t1": f["t1"], "x": x, "y": y, "w": w, "h": h, "이름": f"조각{f['seg']} {f.get('kind', '')}"})
    seen = {f["seg"] for f in log.get("frames", [])}
    for s in log.get("segments", []):
        if s.get("beats", 0) == 0 and s["i"] not in seen:
            미기록.append(s["i"])
    return crops, 미기록


def 가림목록(segs):
    """조각 표식 «가림»: [[x0,y0,x1,y1(,t0,t1)], …] (원본 픽셀·원본 초) — 화면 속 캡션 자리(시각 없으면 조각 전체).
    굽기는 framing.가림경계 로 그 자리를 피하고, 이 관문이 같은 사각형으로 확인한다."""
    out = []
    for s in segs:
        for r in s.get("가림") or []:
            t0, t1 = (r[4], r[5]) if len(r) >= 6 else (s["t0"], s["t1"])
            g = {"t0": t0, "t1": t1, "x0": r[0], "y0": r[1], "x1": r[2], "y1": r[3]}
            if len(r) >= 7 and str(r[6]).startswith("화면캡션:"):
                g["종류"], g["글"] = "화면캡션", str(r[6])[5:]
            if g not in out:                            # 한 캡션이 여러 조각에 붙어도 한 번만
                out.append(g)
    return out


def 멈춤(걸):
    """★2026-09-27 23:50 사장님 결정 — 상자 띠만 있는 옛 납품편(85편)은 다시 굽지 않는다. 옛 편을 다시 조립(⑦~⑨)할 때
    막히지 않게 «준비» 는 글자 노출·화면 캡션만 멈추고 상자 윗단(띠)은 주의로 둔다. 굽기(build)는 새로 정한 한계가
    띠까지 빼므로 둘 다 멈춘다(회귀 감시)."""
    return [g for g in 걸 if g.get("글자")]


def 글(걸):
    return "; ".join(f"{g['이름']} {g['t']}초 밑변 {g['밑변']} > {g['종류']}{('«' + g['글'] + '»') if g.get('글') else ''}"
                     f" 윗변 {g['상자윗변']}" for g in 걸[:6]) \
        + (f" 외 {len(걸) - 6}건" if len(걸) > 6 else "")


if __name__ == "__main__":
    src, bj = sys.argv[1], sys.argv[2]
    boxes = 카드상자들(src, log=print)
    log = json.load(open(bj, encoding="utf-8"))
    r = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src]), capture_output=True, text=True)
    W, H = (int(v) for v in r.stdout.strip().split(",")[:2])
    crops, 미기록 = beats_crops(log, W, H)
    가 = []
    if "--proj" in sys.argv:                       # 조각 «가림» + 화면 캡션까지 (굽기 관문과 같은 재료)
        _pj = json.load(open(sys.argv[sys.argv.index("--proj") + 1], encoding="utf-8"))
        _cap = 캡션들(src, log=print)
        가 = 가림목록([캡션붙인조각(s, _cap) for s in _pj["segments"] if s.get("keep", True)])
        print(f"화면 캡션 {len(_cap)}개 — " + " · ".join(f"«{c['글'][:10]}» {c['t0']}~{c['t1']}" for c in _cap[:12]))
    걸 = 걸림(boxes, crops, 가)
    print(("걸림 " + str(len(걸)) + f"(글자 {len(멈춤(걸))}) — " + 글(걸)) if 걸 else "걸림 0", "· 한장구도 미기록 조각", 미기록)
    sys.exit(1 if 걸 else 0)
