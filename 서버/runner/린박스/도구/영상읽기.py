# -*- coding: utf-8 -*-
r"""영상을 회색 프레임으로 읽어 준다 — **어느 파이썬으로 돌리든 된다**.

왜 이게 따로 있는가
  이 컴퓨터에는 파이썬이 둘이고, 서로 가진 것이 다르다.

    · `.volcano/venv/Scripts/python.exe`  — opencv 있음, PyAV 없음  ← 파이프라인이 쓰는 것
    · 시스템 python (3.12)                — PyAV 있음, opencv 없음

  그래서 도구를 한쪽에 맞춰 쓰면 다른 쪽에서 죽는다. 실제로 그렇게 헤맸다.
  여기서 **있는 쪽을 골라 쓴다** — 도구는 이 함수만 부르면 된다.
"""
import numpy as np
from PIL import Image

_방식 = None
try:
    import av as _av
    _방식 = 'av'
except ImportError:
    try:
        import cv2 as _cv2
        _방식 = 'cv2'
    except ImportError:
        pass


def 방식():
    if not _방식:
        raise SystemExit(
            '영상을 읽을 수 없다 — PyAV 도 opencv 도 없다.\n'
            '  파이프라인 파이썬으로 돌려라: '
            'pip install opencv-python  (또는 av)')
    return _방식


def 회색프레임(경로, 잘라=None, 크기=None):
    """(차례, 초, 회색배열) 을 하나씩 내놓는다.

    잘라 : (y0, y1) — 세로로 이 구간만 쓴다 (영상창만 보려고)
    크기 : (가로, 세로) — 이 크기로 줄인다
    """
    방식()
    if _방식 == 'av':
        컨 = _av.open(경로)
        스 = 컨.streams.video[0]
        스.thread_type = 'AUTO'
        fps = float(스.average_rate)
        # ★시각은 **PTS 로** 낸다. `i / fps` 로 세면 스트림 start_time 만큼 어긋난다
        #   (2026-08-27 실측). 포헨즈 1화 10편 구간은 start_time 이 0.783초라
        #   컷 표 전체가 0.75초 일렀고, 서버가 짚은 전환과 어긋났다.
        #   ffmpeg 의 -ss 도, 서버도, 우리 렌더도 전부 **컨테이너 시각**을 쓴다.
        시작 = float(스.start_time * 스.time_base) if 스.start_time is not None else 0.0
        i = 0
        for f in 컨.decode(video=0):
            g = f.to_ndarray(format='gray')
            if f.pts is not None:
                _t = float(f.pts * 스.time_base)
            else:
                _t = 시작 + i / fps
            yield i, _t, _다듬기(g, 잘라, 크기)
            i += 1
        컨.close()
    else:
        cap = _cv2.VideoCapture(경로)
        fps = cap.get(_cv2.CAP_PROP_FPS)
        i = 0
        while True:
            ok, img = cap.read()
            if not ok:
                break
            g = _cv2.cvtColor(img, _cv2.COLOR_BGR2GRAY)
            _ms = cap.get(_cv2.CAP_PROP_POS_MSEC)   # 컨테이너 시각 (위 ★ 참고)
            yield i, (_ms / 1000.0 if _ms and _ms > 0 else i / fps), _다듬기(g, 잘라, 크기)
            i += 1
        cap.release()


def _다듬기(g, 잘라, 크기):
    if 잘라:
        g = g[잘라[0]:잘라[1]]
    if 크기:
        g = np.asarray(Image.fromarray(g).resize(크기, Image.BILINEAR))
    return g.astype(np.float32)


def 초당프레임(경로):
    방식()
    if _방식 == 'av':
        컨 = _av.open(경로)
        r = float(컨.streams.video[0].average_rate)
        컨.close()
        return r
    cap = _cv2.VideoCapture(경로)
    r = cap.get(_cv2.CAP_PROP_FPS)
    cap.release()
    return r
