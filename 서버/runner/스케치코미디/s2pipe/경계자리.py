# -*- coding: utf-8 -*-
"""조각 경계(t0·t1)를 옮겨도 되는 «자리» — 경계를 고치는 도구(검수도구/경계제안.py · 이음매수리.py)가 함께 쓰는 한 곳.

★2026-10-03 루키치 배치(161~179) — «경계 고침 도구가 샷 전환·로고·암전을 넘고, 말 사이 짧은 골에서 말끝을 자른다» 클래스 수리
  (사장님 승인 2026-10-03 «남은 도구 오류는 지금 개선해»).
  증상: 경계제안이 편마다 7~18곳을 내는데 배치 에이전트가 거의 다 버렸다(173·168·170·172·164·162·161·171) — 샷 전환·로고·
        큰 제목 카드를 넘거나 agy 시각을 믿은 제안. 167 은 «틈 안 더 조용한 자리» 라며 말 사이 0.05초 골에 경계를 놓아
        말끝 «돼» 를 잘라 재굽기 1회. 161 은 이음매수리가 앞 조각 끝을 130.59→131.40 으로 늘리자고 해 화면 전환(130.589)을
        넘어 다음 샷 대사까지 들어올 뻔했다.
  클래스 넷: (가) 샷 전환을 모름 (나) 로고·암전 구간을 모름 (다) agy 시각(1~3초 늦음)을 낱말 시각처럼 믿음
            (라) «조용한 자리» 를 소리 크기만으로 찾아 말 사이 짧은 골(0.05초)에서 말끝을 자름.
            + 문제없는 경계도 «더 조용한 20ms» 로 옮기자고 했다 — 제안 대부분이 이것이었다(납품 경계에도 편마다 십여 곳).
  수리(이 파일 한 곳):
    ① 문제가 있는 경계만 옮긴다 — 문제 = 박힌 자막 카드(문장이 화면에 떠 있는 동안) 한가운데를 가로지르며 잘려 나가는 쪽에
       말소리가 있다 · 경계가 말소리 위(0.1초 넘는 조용한 골 밖)다 · 나레 앞 말끝 여유(화자색.나레덕킹여유)가 모자란다.
    ② 옮길 자리는 «같은 샷 안» 에서만 찾는다 — 샷 전환은 cuts.json(편시작이 잰 것)과 그 둘레 프레임을 다시 본 날카로운 봉우리
       (프레임격자.날카로운 — 흰 벽 인터뷰처럼 scene 0.28 이 놓친 전환도). 샷 전환 «그 자리» 는 좋은 경계라 후보로 쓴다.
       암전(밝기 < 12) 프레임과 원본 아웃트로(build.엔드카드시작 · 조각 _엔드카드시작) 너머로는 가지 않는다.
    ③ 후보는 «조용한 골이 0.25초 이상» (샷 전환 자리는 0.1초 — 화면이 바뀌어 짧은 쉼도 가려진다)이고, 박힌 카드 한가운데에서
       잘려 나가는 쪽에 말이 남지 않는 자리 — 카드가 «어느 문장인가» 를 준다. 경계를 품은 카드의 말이 남는 쪽이 많으면
       그 문장을 통째로 담는 쪽(끝은 뒤로 · 시작은 앞으로)으로, 잘려 나가는 쪽이 많으면 그 문장을 빼는 쪽으로 옮긴다.
       다른 문장(옆 카드)을 새로 끌어들이지 않는다.
    ④ agy 원본 전사 시각은 쓰지 않는다(카드가 없는 소재에서만 «어디쯤» 찾기 창으로).
    ⑤ 자리가 없으면 옮기지 않고 까닭을 말한다(«말이 샷 전환 너머로 이어진다» · «말 사이 골이 짧다 — 빠른 주고받기»).
  왜 예전 검사를 지났나: 제안은 사람이 «받을지» 고르는 단계라 기계 관문이 없었다 — 경계제안은 ④ 이음매 관문(완성본 낱말)이
    나중에 본다고 믿었고, 이음매 관문은 «완성본 안» 의 말만 봐서 샷 넘김·로고·잘려 나간 쪽 말을 못 본다. 그래서 사람이 매 편
    프레임과 소리로 하나하나 걸러 냈다. 이제 검수도구/경계제안시험.py 가 납품 편으로 «제안이 샷·암전·로고를 넘는 수 0» 을 잰다.
"""
import json
import os
import subprocess

import numpy as np

from . import 프레임격자 as G
try:  # ffmpeg·ffprobe 스레드 상한은 ff.명령 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
    from . import ff
except ImportError:  # 단독 실행(python s2pipe/x.py)
    import ff  # type: ignore

최소골 = 0.25        # 조용한 골이 이만큼은 돼야 경계를 놓는다 — 167 빠른 낭독형 말 사이 골 0.05초에서 말끝 «돼» 가 잘렸다
최소골_전환 = 0.10   # 샷 전환 자리는 화면이 바뀌어 짧은 쉼도 가려진다
문제골 = 0.10        # 지금 경계가 이보다 짧은 골(또는 말소리) 위면 «문제»
카드안 = 0.25        # 카드 가장자리 안쪽 이만큼부터 «한가운데»(카드경계검사와 같은 0.3 언저리 · 10fps 카드 시각 여유)
카드말 = 0.15        # 카드 안 잘려 나가는 쪽 말소리가 이만큼 넘으면 문장을 자른 것
닿음 = 3.0           # 경계를 이보다 멀리 옮기지 않는다(그보다 멀면 조각을 다시 짜야 한다 — 사람)
전환여유 = 0.03      # 시각이 샷 전환과 이만큼 안이면 «전환 자리»
_FR = 0.02           # 소리 칸 20ms


def 암전인가(fr):
    """64×36 회색 프레임 한 장이 암전인가 — 밝기 평균 < 12 · 밝은 점(>60) 1% 미만(make·build 검은꼬리 기준을 작은 그림에 맞춤).
    ★2026-10-03 루키치164 — 로고 앞 암전이 «한 프레임»(164.539)뿐이라 0.1초 걸음으로 훑으면 놓친다. 프레임마다 본다."""
    return float(fr.mean()) < 12 and float((fr > 60).mean()) < 0.01


def 암전시각들(src, a, b):
    """원본 [a, b] 안 암전 프레임 시각(프레임마다) — make 결말 절단 주의가 «늘려라» 의 벽으로 쓴다."""
    g = G.얻기(src)
    k0, k1 = max(0, g.번호(a)), min(g.n, g.번호(b) + 1)
    F = G.프레임들(src, g, k0, k1)
    return [g.시작(k0 + j) for j in range(len(F)) if 암전인가(F[j]) and a <= g.시작(k0 + j) <= b]


# ── 결말 벽 — 이야기 끝 뒤로 원본을 더 틀어도 되는 한계 ───────────────────────────────────────────────
# ★2026-10-03 루키치 배치 «프리미어 끝 여운(기본 1.8초)이 원본의 로고 앞 암전·페이드를 넘어 프리미어 끝에 로고·암전이 든다»
#   클래스 수리 (사장님 «남은 도구 오류는 지금 개선해» 연장). 배치 에이전트가 거의 매 편 손으로 «여운: 0» 을 넣고 FROM=7 로
#   다시 지었다(루키치 26편 · 점심이네40 · Deep 3편 등 계획 JSON 29개에 «여운» 손값).
#   증상: 156 은 아웃트로 카드 감지가 274.77 인데 실제로는 274.524 한 프레임 암전 뒤 카드가 밝아지며 들어와(페이드) 여운이
#         암전·페이드를 담았다. 159 는 주황 카드(336.6) 4초 앞 332.58 에 로고가 강 풍경 위로 먼저 떴고, 계획 JSON 의 dur(341.4)가
#         파일 실제 길이(341.357)보다 길어 카드 감지마저 None 이라 여운 1.8초가 로고 위로 그대로 들어갔다.
#         221 은 카드 바탕(주황)이 원형으로 조여 들어오며 로고가 움직여 «정지 카드» 감지가 1.9초 늦었다.
#   클래스: 끝 벽을 «정지 아웃트로 카드 감지» 하나로만 정했다 — 카드 «앞» 의 암전·페이드·로고 겹침·움직이는 카드 바탕을 모른다.
#     (준비의 «여운 안 화면 전환» 상한도 있었지만, 한 장 암전 뒤 카드가 밝아지는 꼴은 «번쩍임»(1~3장 뒤 앞 화면 밝기로 돌아옴)
#      으로 읽혀 전환이 아니게 됐고, 남색 카드 받침은 싱글벙글 색만 봤다 — 그래서 156·164·150 이 지나갔다.)
#   수리: 벽을 이 함수 한 곳에서 정한다 — 준비(여운 상한)·make(결말 «늘려라» 주의)·prproj끝검사(납품 관문)가 모두 부른다.
#     벽 = min(아웃트로 카드 시작, 첫 암전 프레임(프레임마다), 아웃트로 카드의 로고가 먼저 뜬 첫 프레임, 카드 바탕이 먼저 깔린 첫
#          프레임) · 그 벽 화면으로 다가가는 페이드가 있으면 페이드 첫 프레임까지.
#   모의(손값 무시 · 여운 1.8초 · 원본 76편 = 루키치 67 · 싱글 6 · Deep 1 · 점심이네 2): 옛 상한으로 벽을 넘는 편 24 → 0 ·
#     벽이 먼 편(카드까지 1.8초 넘게 남은 편)은 1.793초 그대로.
로고차 = 18.0        # 로고(또는 카드 바탕) 자리 화소가 카드와 이만큼(0~255 평균 차) 안이면 «카드 화면이 떴다»
로고바탕차 = 40.0    # 이야기 마지막 프레임은 그 자리가 카드와 이만큼은 달라야 한다(흰 벽 = 흰 글자 같은 헛걸림 막기)
페이드걸음 = 1.5     # 페이드 = 벽 화면까지의 거리가 프레임마다 이만큼씩 줄어든다
페이드최소 = 2       # 벽 바로 앞 한 걸음 말고도 이만큼 잇단 걸음이어야 페이드(우연한 움직임 한두 장은 아님)


def _색프레임들(src, g, k0, k1, w=96, h=54):
    """원본 프레임 [k0, k1) 을 작은 색 배열로(로고·카드 바탕 대조용 — 회색은 주황 바탕과 풍경을 못 가른다)."""
    k0, k1 = max(0, k0), min(g.n, k1)
    if k1 <= k0:
        return np.zeros((0, h, w, 3), dtype=np.int16)
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", repr(g.경계값(k0)), "-i", src, "-frames:v", str(k1 - k0),
                        "-vf", f"scale={w}:{h}:flags=area", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]), capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    m = len(a) // (w * h * 3)
    return a[:m * w * h * 3].reshape(m, h, w, 3).astype(np.int16)


def 로고틀(src, 아웃트로):
    """아웃트로 카드 한 장(시작 0.2초 뒤)에서 «바탕이 아닌 화소»(로고·글자) 자리 → (카드 그림, 로고 자리) 또는 None.
    바탕색 = 가장자리 화소의 중앙값. 로고 자리가 화면의 0.3%~50% 가 아니면(카드가 사진 등) 쓰지 않는다."""
    g = G.얻기(src)
    k = min(g.n - 1, g.번호(아웃트로 + 0.2))
    C = _색프레임들(src, g, k, k + 1)
    if not len(C):
        return None
    c = C[0]
    테 = np.concatenate([c[0], c[-1], c[:, 0], c[:, -1]])
    틀 = np.abs(c - np.median(테, axis=0)).sum(axis=2) > 90
    if not (0.003 < float(틀.mean()) < 0.5):
        return None
    return c, 틀


def 아웃트로찾기(src, 하한=0.0):
    """원본 꼬리 정지 아웃트로 카드 시작(build.엔드카드시작 — 굽기와 같은 검출) · 없거나 못 재면 None."""
    _설정()
    try:
        from .build import 엔드카드시작
        g = G.얻기(src)
        return 엔드카드시작(src, g.시작(g.n), 하한)
    except (Exception, SystemExit):                       # noqa: BLE001
        return None


결말창 = 4.0        # 이야기 끝 뒤로 «늘» 이만큼 본다 — 부르는 쪽의 여운·관문 창과 무관(아래 2026-10-04 87 수리)
결말카드뒤 = 0.5    # 아웃트로 카드가 창 안이면 카드 시작 이만큼 뒤까지 본다(로고·바탕 «카드와 같아진 장» 이 반드시 창 안에 들게)


def 결말아웃트로(src, 이야기끝, 굽기카드=None):
    """결말 벽에 쓰는 아웃트로 카드 시작 — 준비·make·prproj끝검사가 «같은 인자» 로 정하는 한 곳.
    = min(원본 직접 감지(build.엔드카드시작 · 파일 실제 길이 · 하한 = 이야기끝 − 0.1), 굽기가 계획에 남긴 _엔드카드시작).
    ★2026-10-04 루키치87 — 예전엔 준비는 «계획 dur · 하한 마지막 조각 t0+2 · 굽기 값과 min», prproj끝검사는 «파일 길이 · 하한
      이야기끝 · 굽기 값 모름», make 는 «계획 dur · 하한 0» 으로 세 곳이 따로 정했다. 같은 함수(결말벽)여도 인자가 갈리면 벽이 갈린다."""
    try:
        st = os.stat(src)
        키 = (os.path.abspath(src), st.st_size, int(st.st_mtime), round(float(이야기끝), 4))
    except OSError:
        키 = None
    if 키 is None or 키 not in _아웃트로캐시:              # 감지는 ffmpeg 수십 번(편당 수십 초) — 준비가 관문 둘에서 다시 부른다
        아 = 아웃트로찾기(src, max(0.0, 이야기끝 - 0.1))
        if 키 is None:
            후 = [x for x in (아, 굽기카드) if x is not None]
            return float(min(후)) if 후 else None
        _아웃트로캐시[키] = 아
    아 = _아웃트로캐시[키]
    후 = [x for x in (아, 굽기카드) if x is not None]
    return float(min(후)) if 후 else None


_아웃트로캐시 = {}


def 결말벽판정(src, 이야기끝, 굽기카드=None):
    """결말 벽의 «유일한» 입구 → {"벽", "까닭", "아웃트로", "이야기끝", "굽기카드"}.
    이야기끝 = 여운이 시작하는 원본 시각(준비의 이야기 마지막 프레임 다음 장 시각 = timeline 여운.전_src_end).
    준비(여운 상한 · 굽기 전 관문)·make(결말 «늘려라» 주의)·prproj끝검사(납품 관문)가 모두 이것만 부른다."""
    아 = 결말아웃트로(src, 이야기끝, 굽기카드)
    벽, 까닭 = 결말벽(src, 이야기끝, 아웃트로=아)
    return {"벽": 벽, "까닭": 까닭, "아웃트로": 아, "이야기끝": float(이야기끝),
            "굽기카드": (float(굽기카드) if 굽기카드 is not None else None)}


def 결말벽(src, a, b=None, 아웃트로=None):
    """이야기 끝 a 뒤 «첫 벽» → (경계값, 까닭) · 없으면 (None, "").
    a = 이야기 마지막 조각의 끝(여운이 시작하는 자리). 벽 프레임 k 는 «보이면 안 되는 첫 프레임» 이고, 돌려주는 값은 그 경계값
    (프레임격자.경계값 — 번호()로 되읽으면 k)이다. 여운은 k 앞에서 끝나야 한다.
    아웃트로: 정지 카드 시작(결말아웃트로 값). 주면 그 카드의 로고·바탕이 먼저 뜬 자리도 본다.
    b: ★결과에 쓰지 않는다(2026-10-04). 보는 창은 언제나 [a, a + 결말창](카드가 그 안이면 카드 + 결말카드뒤까지)이다.
       b 가 그보다 멀 때만 창을 b 까지 넓힌다(여운 3.8초 넘는 손값 — 지금 계획 JSON 에 없다).

    ★2026-10-04 루키치87 «같은 함수인데 두 판정이 1장 어긋남» 클래스 수리 (땜질 금지).
      실측: 준비_prproj 는 b = 이야기끝 + 여운 1.8 + 0.2 = 209.83 으로 불러 벽 208.123(«로고 208.125») ·
            prproj끝검사는 b = 프리미어 끝 + 0.05 = 208.007 로 불러 208.039(«아웃트로 카드 208.248 · 페이드 208.041~»).
            여운이 208.123 의 1장 앞(208.08)까지 늘어 납품 관문이 «벽을 1장 넘음» 으로 반려(배치 에이전트가 여운 0.15 손 처리).
      클래스 둘: (가) 창 b 가 결과를 바꿨다 — 로고 판정은 «카드와 같아진 장» 이 창 안에 있어야 서는데, 창이 짧으면(관문) 로고
                 후보가 없고 길면(준비) 있다. 부르는 쪽마다 창이 달라 같은 원본에 벽이 둘. (나) 페이드 되짚기를 «가장 이른 후보» 하나
                 에서만 했다 — 반쯤 뜬 로고 장(208.125)에서 되짚으면 걸음이 2장뿐이라 페이드가 아니고, 카드(208.248)에서 되짚으면
                 208.041 부터 페이드다. 어느 후보가 min 이냐에 따라 페이드가 보였다 안 보였다 했다.
      수리: (가) 창을 부르는 쪽과 무관하게 고정 · (나) 후보마다 페이드를 되짚어 가장 이른 장을 벽으로.
            인자(아웃트로·이야기끝)도 결말벽판정·결말아웃트로 한 곳에서 — 준비가 쓴 인자를 timeline 에 남겨 끝검사가 그대로 다시 잰다.
      왜 37da614 시험을 지났나: 모의 76편은 «준비와 같은 창» 하나로만 재고 «관문 창으로 다시 재서 같은가» 를 안 쟀다.
        이제 검수도구/결말벽시험.py 가 편마다 창 셋(짧게·준비·길게)으로 재서 값이 하나인지 본다."""
    g = G.얻기(src)
    끝 = a + 결말창
    if 아웃트로 is not None and a - 0.05 < 아웃트로 <= 끝:
        끝 = 아웃트로 + 결말카드뒤
    if b is not None and b > 끝:
        끝 = b
    ka, kb = max(0, g.번호(a)), min(g.n, g.번호(끝) + 1)
    후보 = []
    if 아웃트로 is not None and 아웃트로 > a - 0.05:
        후보.append((max(ka, g.번호(아웃트로)), f"아웃트로 카드 {아웃트로:.3f}"))
    if kb > ka:
        F = G.프레임들(src, g, ka, kb)
        d = next((j for j in range(len(F)) if 암전인가(F[j])), None)
        if d is not None:
            후보.append((ka + d, f"암전 {g.시작(ka + d):.3f}"))
        틀 = 로고틀(src, 아웃트로) if 아웃트로 is not None else None
        if 틀 is not None:
            c, m = 틀
            Fc = _색프레임들(src, g, ka - 1, kb)          # 맨 앞 = 이야기 마지막 프레임(기준)
            # 로고 자리(m)와 바탕 자리(~m) 둘 다 본다 — 로고가 풍경 위로 먼저 뜨는 끝(159)과, 카드 바탕이 먼저 깔리고 로고가
            #   움직여 «정지 카드» 감지가 늦게 잡는 끝(221 — 원형으로 조여 드는 주황 바탕)
            for 자리, 이름 in ((m, "로고"), (~m, "카드 바탕")):
                차 = [float(np.abs(f - c)[자리].mean()) for f in Fc]
                if not 차 or 차[0] <= 로고바탕차:
                    continue
                j = next((j for j in range(1, len(차)) if 차[j] < 로고차), None)
                if j is None:
                    continue
                while j - 1 >= 1 and 차[j - 1] < 0.85 * 차[0]:      # 섞여 드는 첫 장부터(159 332.582 = 반쯤 뜬 로고)
                    j -= 1
                후보.append((ka - 1 + j, f"{이름} {g.시작(ka - 1 + j):.3f}(카드와 {차[j]:.0f})"))
    if not 후보:
        return None, ""
    # 페이드 — 후보마다 벽 화면으로 다가가는 걸음을 거꾸로 걷는다(a 앞으로는 안 간다). 카드로 섞여 드는 디졸브(162·173·145)를 잡는다.
    #   ★후보 하나(가장 이른 것)에서만 되짚으면 반쯤 뜬 장에서 걸음이 모자라 페이드를 놓친다(87) — 모두 되짚어 가장 이른 장.
    안쪽 = [(kw, 까) for kw, 까 in 후보 if kw > ka]
    if 안쪽:
        k0 = max(ka, min(kw for kw, _ in 안쪽) - int(5 * g.fps))   # 페이드는 5초 안(벽이 먼 편에서 수백 장을 읽지 않게)
        k1 = max(kw for kw, _ in 안쪽) + 1
        F = G.프레임들(src, g, k0, k1)
        if len(F) == k1 - k0:
            되짚음 = []
            for kw, 까 in 안쪽:
                f0 = max(k0, kw - int(5 * g.fps))
                거리 = [float(np.abs(F[k - k0] - F[kw - k0]).mean()) for k in range(f0, kw + 1)]
                j = len(거리) - 1
                while j - 1 >= 0 and 거리[j - 1] > 거리[j] + 페이드걸음:
                    j -= 1
                if (len(거리) - 1) - j >= 페이드최소 + 1:
                    되짚음.append((f0 + j, 까 + f" · 페이드 {g.시작(f0 + j):.3f}~"))
            후보 += 되짚음
    kw, 까닭 = min(후보)
    return g.경계값(kw), 까닭


def 여운관문(src, 기록, 프리미어끝):
    """만들 결과(이야기 끝 ~ 프리미어 끝)를 timeline «여운» 기록 그대로 다시 잰다 → {"재", "탈", "글", "벽"}.
    준비_prproj 가 timeline 을 쓰기 «전에»(굽기·조립 전) 같은 기록으로 이걸 부르고, prproj끝검사(납품)가 다시 부른다 —
    두 판정이 같은 함수·같은 인자라 값이 같다. 새 기록(«굽기카드» 칸이 있는 것)은 적힌 벽과 다시 잰 벽이 같은 장인지도 본다(어긋나면 탈).
    기록: {"전_src_end", "벽", "굽기카드"(없으면 None — 2026-10-04 전 timeline)}."""
    g = G.얻기(src)
    a = float(기록["전_src_end"])
    끝 = float(프리미어끝)
    판 = 결말벽판정(src, a, 기록.get("굽기카드"))
    벽, 까닭 = 판["벽"], 판["까닭"]
    글 = (f"원본 결말 벽 {'%.3f' % 벽 if 벽 is not None else '없음'}"
         f"{(' (' + 까닭 + ')') if 까닭 else ''} · 프리미어 끝 = 원본 {끝:.3f}s")
    탈 = False
    if "굽기카드" in 기록:                          # 2026-10-04 뒤 기록만 — 그 전 기록의 벽은 옛 판정(창에 따라 갈림)으로 적혔다
        적힌 = 기록.get("벽")
        같음 = (적힌 is None and 벽 is None) or (적힌 is not None and 벽 is not None and g.번호(적힌) == g.번호(벽))
        if not 같음:
            탈 = True
            글 += f" ★준비가 적은 벽 {적힌} 과 다름(두 판정 어긋남 — 인자·창이 갈렸다)"
    if 끝 - a >= 0.02 and 벽 is not None and g.번호(벽) < g.번호(끝):
        탈 = True
        글 += f" ★벽을 {g.번호(끝) - g.번호(벽)}장 넘음"
    if 끝 - a < 0.02:
        글 += " · 여운 없음"
    return {"재": True, "탈": 탈, "글": 글, "벽": 벽}


def _설정():
    if not os.environ.get("S2_CONFIG"):
        p = os.path.expanduser("~/Desktop/스케치코미디/config.json")
        if os.path.isfile(p):
            os.environ["S2_CONFIG"] = p


class 원본자리:
    """원본 한 편의 소리·샷 전환·박힌 카드·암전·아웃트로 — 경계 후보를 판정한다."""

    def __init__(self, src, proj=None, log=None):
        self.src = src
        self.log = log or (lambda *_: None)
        r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]),
                           capture_output=True, check=True)
        x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
        FR = 320
        n = len(x) // FR
        f = np.fft.rfftfreq(FR, 1 / 16000)
        sel = (f > 300) & (f < 3500)
        spec = np.abs(np.fft.rfft(x[:n * FR].reshape(n, FR) * np.hanning(FR), axis=1))[:, sel].sum(axis=1)
        self.E = 20 * np.log10(spec + 1e-9)                    # 20ms 마다 말대역 dB
        self.n = n
        self.dur = n * _FR
        # 조용 = 둘레 6초 바닥(20% 백분위) + 6dB 아래 — 이음매수리·카드경계검사·이음매관문._원본조용 과 같은 기준
        pad = np.pad(self.E, 150, mode="edge")
        win = np.lib.stride_tricks.sliding_window_view(pad, 301)[:n]
        self.Q = self.E < np.percentile(win, 20, axis=1) + 6.0
        self.g = G.얻기(src)
        cj = os.path.splitext(src)[0] + ".cuts.json"
        try:
            self.cuts = G.컷맞춤(self.g, json.load(open(cj, encoding="utf-8")))
        except (OSError, ValueError):
            self.cuts = []
        self.cards = []
        try:
            from . import 번인관문
            self.cards = sorted(번인관문.확인된카드들(src))
        except Exception as e:                                # noqa: BLE001 — 카드 없이도 돈다(소리·샷만)
            self.log(f"  (박힌 카드 못 읽음 — 소리·샷만으로: {e})")
        self.outro = None
        ends = [s.get("_엔드카드시작") for s in (proj or {}).get("segments", []) if s.get("_엔드카드시작")]
        if ends:
            self.outro = float(min(ends))
        else:
            try:
                _설정()
                from .build import 엔드카드시작
                self.outro = 엔드카드시작(src, self.g.시작(self.g.n))
            except (Exception, SystemExit):                    # noqa: BLE001 — 못 재면 암전만 본다
                self.outro = None
        self._창 = {}

    # ── 화면 ─────────────────────────────────────────────────────
    def _프레임창(self, a, b):
        """[a, b] 프레임(64×36 회색) · 차이열 — 샷 전환·암전 둘 다 여기서."""
        k0, k1 = max(0, self.g.번호(a) - 5), min(self.g.n, self.g.번호(b) + 6)
        key = (k0, k1)
        if key not in self._창:
            F = G.프레임들(self.src, self.g, k0, k1)
            self._창[key] = (k0, F, G.차이열(F))
        return self._창[key]

    def 전환들(self, a, b, 최소=12.0):
        """[a, b] 안 샷 전환 시각(경계값 — 새 샷 첫 프레임 − 0.002). cuts.json ∪ 프레임 날카로운 봉우리."""
        out = {c for c in self.cuts if a - 0.01 <= c <= b + 0.01}
        k0, F, D = self._프레임창(a, b)
        for j in range(1, len(D)):
            if G.날카로운(D, j, 최소=최소, F=F):
                t = self.g.경계값(k0 + j)
                if a - 0.01 <= t <= b + 0.01:
                    out.add(t)
        # 같은 전환을 두 자로 잰 것(±반 프레임)은 하나로
        res = []
        for t in sorted(out):
            if not res or t - res[-1] > 0.03:
                res.append(t)
        return res

    def 암전들(self, a, b):
        """[a, b] 안 암전 프레임 시각 — 밝기 평균 < 12 · 밝은 점(>60) 1% 미만(make·build 검은꼬리와 같은 기준)."""
        k0, F, _D = self._프레임창(a, b)
        out = []
        for j in range(len(F)):
            if 암전인가(F[j]):
                t = self.g.시작(k0 + j)
                if a <= t <= b:
                    out.append(t)
        return out

    # ── 소리 ─────────────────────────────────────────────────────
    def _i(self, t):
        return int(round(t / _FR))

    def 골(self, t):
        """t 를 품은 조용한 골 (시작, 끝) — t 자리(±1칸)가 말소리면 None."""
        i = self._i(t)
        cand = [j for j in (i, i - 1, i + 1) if 0 <= j < self.n and self.Q[j]]
        if not cand:
            return None
        j = cand[0]
        a = j
        while a > 0 and self.Q[a - 1]:
            a -= 1
        b = j
        while b + 1 < self.n and self.Q[b + 1]:
            b += 1
        return a * _FR, (b + 1) * _FR

    def 말초(self, a, b):
        i0, i1 = max(0, self._i(a)), min(self.n, self._i(b))
        return float((~self.Q[i0:i1]).sum()) * _FR if i1 > i0 else 0.0

    def 골들(self, a, b):
        """[a, b] 안 조용한 골들 (시작, 끝) — 창 가장자리에서 잘린 골도 그대로(가장자리 = 샷 전환이면 그 자리가 후보)."""
        i0, i1 = max(0, self._i(a)), min(self.n, self._i(b))
        out, s = [], None
        for i in range(i0, i1):
            if self.Q[i] and s is None:
                s = i
            elif not self.Q[i] and s is not None:
                out.append((s * _FR, i * _FR))
                s = None
        if s is not None:
            out.append((s * _FR, i1 * _FR))
        return out

    # ── 카드 ─────────────────────────────────────────────────────
    def 품은카드(self, t):
        return next(((cs, ce) for cs, ce in self.cards if cs < t < ce), None)

    def 카드자름(self, t, k):
        """t 가 카드 한가운데이고 잘려 나가는 쪽(t1 이면 뒤 · t0 이면 앞) 카드 안에 말소리가 남는가 → (cs, ce, 말초) 또는 None."""
        for cs, ce in self.cards:
            if cs + 카드안 < t < ce - 카드안:
                말 = self.말초(t, ce) if k == "t1" else self.말초(cs, t)
                if 말 > 카드말:
                    return cs, ce, 말
        return None

    # ── 판정 ─────────────────────────────────────────────────────
    def 샷창(self, t, k):
        """경계 t 가 옮겨 다닐 수 있는 [lo, hi] — 같은 샷 안 · 암전·아웃트로 앞 · ±닿음. (lo, hi, lo가전환, hi가전환)"""
        a, b = max(0.0, t - 닿음), min(self.dur - 0.05, t + 닿음)
        T = self.전환들(a, b)
        at = next((c for c in T if abs(c - t) <= 전환여유), None)
        if at is not None and k == "t1":            # 샷 끝에 맞춘 끝 — 앞 샷 안에서만
            앞 = [c for c in T if c < at - 전환여유]
            lo, hi, lo전, hi전 = (앞[-1] if 앞 else a), at, bool(앞), True
        elif at is not None:                         # 샷 머리에 맞춘 시작 — 뒤 샷 안에서만
            뒤 = [c for c in T if c > at + 전환여유]
            lo, hi, lo전, hi전 = at, (뒤[0] if 뒤 else b), True, bool(뒤)
        else:
            앞 = [c for c in T if c < t]
            뒤 = [c for c in T if c > t]
            lo, hi, lo전, hi전 = (앞[-1] if 앞 else a), (뒤[0] if 뒤 else b), bool(앞), bool(뒤)
        for d in self.암전들(lo, hi):               # 암전 너머로 가지 않는다
            if d >= t + 0.02 and d < hi:
                hi, hi전 = d, False
            elif d <= t - 0.02 and d > lo:
                lo, lo전 = d + self.g.T, False
        if self.outro is not None and self.outro < hi and self.outro > t - 0.02:
            hi, hi전 = self.outro, False
        return lo, hi, lo전, hi전

    def 문제(self, t, k, 나레앞=False):
        """지금 경계의 문제 목록(빈 목록 = 옮길 까닭 없음)."""
        out = []
        c = self.카드자름(t, k)
        if c:
            out.append(f"카드 {c[0]:.1f}~{c[1]:.1f} 한가운데(잘려 나가는 쪽 말 {c[2]:.1f}초)")
        g = self.골(t)
        # 소리만으로 «문제» 를 부르는 자리 — 샷 전환 자리는 말이 바뀌는 자연스러운 경계라 소리로는 부르지 않는다(카드로만).
        #   카드가 있는 소재는 «카드 가장자리 0.5초 안» 에서만 소리를 본다: 카드 밖 말대역 소리는 배경음·효과음이 대부분이고,
        #   카드 안쪽은 위 카드자름이 문장 단위로 본다. 카드 사이 짧은 골(문장이 바뀌는 자리)은 문제가 아니다.
        #   ★2026-10-03 납품 167 — 소리만 보면 납품 경계 12곳 중 7곳이 «말소리 위·골 0.06초» 로 걸렸다(샷 전환 = 화자 전환
        #   자리 · 조각 머리 0.03초 뒤 말 시작 — 사람이 듣고 받은 자리). 카드 가장자리·샷 전환 규칙으로 가짜를 뺀다.
        전환자리 = any(abs(x - t) <= 전환여유 for x in self.전환들(t - 0.1, t + 0.1))
        if not 전환자리:
            if self.cards:
                가장자리 = any(cs - 0.5 < t < ce + 0.5 for cs, ce in self.cards) and not self.품은카드(t) or \
                    any(cs < t < cs + 카드안 or ce - 카드안 < t < ce for cs, ce in self.cards)
                if g is None and 가장자리:
                    out.append("카드 가장자리 말소리 위")
            elif g is None:
                out.append("말소리 위")
            elif g[1] - g[0] < 문제골:
                out.append(f"말 사이 골 {g[1] - g[0]:.2f}초 위")
        if 나레앞 and k == "t1":
            from .화자색 import 나레덕킹여유
            if g is not None and t - g[0] < 나레덕킹여유 and self.말초(max(0, g[0] - 0.3), g[0]) > 0.06:
                out.append(f"나레 앞 — 말끝 {g[0]:.2f} 뒤 {t - g[0]:.2f}초(덕킹 여유 {나레덕킹여유}초 모자람)")
        return out

    def _자리(self, p, k, 전환, 나레앞):
        """후보 p 가 경계로 괜찮은가 → 까닭(None = 괜찮음)."""
        if self.카드자름(p, k):
            return "카드 한가운데"
        g = self.골(p)
        # 샷 전환 자리가 문장 바뀌는 자리(어느 카드 안쪽도 아님)면 소리가 이어져도 된다 — 한 사람 말끝에 다른 사람 말이 붙는
        #   주고받기에서 화면 전환 = 화자 전환이다(161 130.59 · 167 106.90 — 사람이 듣고 받은 자리). 문제() 의 샷 전환 규칙과 같다.
        if 전환 and not any(cs + 0.1 < p < ce - 0.1 for cs, ce in self.cards) and self.cards:
            g = g or (p, p)
            if 나레앞 and k == "t1":
                from .화자색 import 나레덕킹여유
                if self.말초(max(0, p - 나레덕킹여유), p) > 0.06:
                    return "나레 덕킹 여유 모자람"
            return None
        if g is None:
            return "말소리 위"
        if g[1] - g[0] < (최소골_전환 if 전환 else 최소골):
            return f"골 {g[1] - g[0]:.2f}초 짧음"
        if 나레앞 and k == "t1":
            from .화자색 import 나레덕킹여유
            if p - g[0] < 나레덕킹여유 and self.말초(max(0, g[0] - 0.3), g[0]) > 0.06:
                return "나레 덕킹 여유 모자람"
        return None

    def 찾기(self, t, k, 나레앞=False, 쪽=None):
        """경계 t 를 옮길 자리 → (새 값, 까닭) · 자리가 없으면 (None, 까닭).
        쪽: None = 카드로 정한다 · "담기"(끝은 뒤·시작은 앞) · "빼기"(끝은 앞·시작은 뒤)."""
        lo, hi, lo전, hi전 = self.샷창(t, k)
        C = self.품은카드(t)
        정한쪽 = 쪽
        if 쪽 is None:
            쪽 = "담기"
            if C:
                남 = self.말초(C[0], t) if k == "t1" else self.말초(t, C[1])
                잘 = self.말초(t, C[1]) if k == "t1" else self.말초(C[0], t)
                if 잘 > 남 and 남 < 0.6:              # 문장 대부분이 잘려 나가는 쪽 — 그 문장을 뺀다
                    쪽 = "빼기"
        # 다른 문장(옆 카드)을 새로 끌어들이지 않는 창
        앞카드끝 = max([ce for cs, ce in self.cards if ce <= (C[0] if C else t) + 0.01] + [-1e9])
        뒤카드시작 = min([cs for cs, ce in self.cards if cs >= (C[1] if C else t) - 0.01] + [1e9])
        if C is None and 정한쪽 is None:
            a, b = 앞카드끝 - 0.3, 뒤카드시작 + 0.05
        elif C is None:                               # 쪽을 정해 준 때(이음매수리 «담기») — 그쪽으로만
            뒤로 = (k == "t1") == (쪽 == "담기")
            a, b = (t, 뒤카드시작 + 0.05) if 뒤로 else (앞카드끝 - 0.05, t)
        elif (k == "t1") == (쪽 == "담기"):          # 끝을 뒤로(담기) · 시작을 뒤로(빼기) — C 뒤 틈
            a, b = C[1] - 0.3, 뒤카드시작 + 0.05
        else:                                         # 끝을 앞으로(빼기) · 시작을 앞으로(담기) — C 앞 틈
            a, b = 앞카드끝 - 0.05, C[0] + 0.3
        a, b = max(a, lo), min(b, hi)
        if self.outro is not None:
            b = min(b, self.outro)
        # 쪽이 정해지면 그 방향으로만 — «담기» 인데 끝을 앞으로 당기면 말끝을 더 자른다
        #   (★2026-10-03 시험: 카드 끝 −0.3 부터 찾다 이음매 «담기» 가 149.06 → 148.94 로 거꾸로 갔다)
        if C is not None or 정한쪽 is not None:
            if (k == "t1") == (쪽 == "담기"):
                a = max(a, t)
            else:
                b = min(b, t)
        후보 = []
        for 전 in [x for x, ok in ((lo, lo전), (hi, hi전)) if ok and a - 0.01 <= x <= b + 0.01]:
            if abs(전 - t) > 0.02 and self._자리(전, k, True, 나레앞) is None:
                후보.append((전, True))
        for ga, gb in self.골들(a, b):
            L = gb - ga
            if L < 최소골:
                continue
            m = min(max(0.12, L * 0.4), 0.3)
            if 나레앞 and k == "t1":
                from .화자색 import 나레덕킹여유
                m = max(m, 나레덕킹여유 + 0.02)
            p = ga + m if k == "t1" else gb - m
            if not (ga + 0.05 <= p <= gb - 0.05):
                continue
            p = self.g.맞춤(p)
            if abs(p - t) > 0.02 and a <= p <= b and self._자리(p, k, False, 나레앞) is None:
                후보.append((p, False))
        if not 후보:
            if C and ((k == "t1" and 쪽 == "담기" and hi < C[1] - 0.1) or (k == "t0" and 쪽 == "담기" and lo > C[0] + 0.1)):
                return None, f"말이 샷 전환({hi if k == 't1' else lo:.2f}) 너머로 이어진다 — 샷 안에 고칠 자리 없음(사람이)"
            if C is None and 앞카드끝 > -1e8 and 뒤카드시작 < 1e8 and 뒤카드시작 - 앞카드끝 < 최소골 + 0.1:
                return None, f"문장 사이 틈 {max(0, 뒤카드시작 - 앞카드끝):.2f}초 — 빠른 주고받기, 샷 전환 자리로 다시 짜라(사람이)"
            return None, f"샷 안({lo:.2f}~{hi:.2f}) {'·'.join([쪽])} 쪽에 {최소골}초 넘는 조용한 골이 없다(사람이)"
        best = min(후보, key=lambda c: abs(c[0] - t))
        전환후보 = [c for c in 후보 if c[1] and abs(c[0] - t) <= abs(best[0] - t) + 0.6]
        if 전환후보:
            best = min(전환후보, key=lambda c: abs(c[0] - t))
        p, 전 = best
        if C is None and 정한쪽 is None:              # 카드 밖 소리만의 문제 — 양쪽을 다 봤다, 실제로 간 쪽을 적는다
            쪽 = "담기" if (p > t) == (k == "t1") else "빼기"
        return round(p, 4),("샷 전환 자리" if 전 else f"조용한 골({최소골}초↑)") + f" · {쪽}"

    def 판정(self, t, k, 나레앞=False):
        """(문제 목록, 새 값 또는 None, 까닭). 문제가 없으면 ([], None, "")."""
        if self.outro is not None and t > self.outro + 0.02:
            # 경계가 이미 원본 아웃트로(로고 카드) 안 — 옮길 자리를 찾지 않는다(그 뒤는 전부 로고다).
            #   ★2026-10-03 싱글160 plan원본 끝 197.0(아웃트로 192.61) — 「카드 가장자리 말소리」 로 더 뒤 199.16 을 제안했다.
            return ([f"원본 아웃트로 {self.outro:.2f} 뒤"], None,
                    f"아웃트로 앞으로 당겨라(굽기가 아웃트로를 잘라 내지만 계획 경계가 틀렸다)")
        문 = self.문제(t, k, 나레앞)
        if not 문:
            return [], None, ""
        새, 까닭 = self.찾기(t, k, 나레앞)
        # 소리만으로 부른 문제를 0.1초(두세 프레임) 안 샷 끝으로 맞추는 것은 알리지 않는다 — 납품 편 결말 끝(로고 앞 1~2프레임)
        #   에 이런 «헛제안» 이 15곳 나왔다(2026-10-03 시험). 사람이 받은 경계를 두세 프레임 옮기자는 말은 소음이다.
        if 새 is not None and abs(새 - t) < 0.1 and all(m.startswith(("카드 가장자리", "말소리", "말 사이")) for m in 문):
            return [], None, ""
        return 문, 새, 까닭

    def 말이어짐(self, a, b):
        """a~b 의 절반 넘게 말소리인가 — 이음매수리가 «잘린 쪽에 말이 이어지나» 를 보는 자."""
        i0, i1 = max(0, self._i(a)), min(self.n, self._i(b))
        return int((~self.Q[i0:i1]).sum()) >= max(1, (i1 - i0) // 2)

    def 이음매고침(self, t1, t0, 나레앞=False):
        """④ 이음매 관문이 반려한 이음매(앞 조각 끝 t1 · 뒤 조각 시작 t0) → [(키, 옛값, 새값 또는 None, 까닭)].
        잘린 쪽에 말이 이어지는 쪽만 «담기» 로(끝은 뒤로 · 시작은 앞으로) 같은 샷 안에서 옮긴다. 둘 다 조용하면 빈 목록."""
        out = []
        if self.말이어짐(t1, t1 + 0.25):
            새, 까닭 = self.찾기(t1, "t1", 나레앞=나레앞, 쪽="담기")
            out.append(("t1", t1, 새, "앞 조각 끝 뒤로 말이 이어짐 — " + 까닭))
        if self.말이어짐(t0 - 0.25, t0):
            새, 까닭 = self.찾기(t0, "t0", 쪽="담기")
            out.append(("t0", t0, 새, "뒤 조각 시작 앞에 말 머리 — " + 까닭))
        return out

