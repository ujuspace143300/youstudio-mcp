"""ff.py — 스케치 파이프라인의 ffmpeg·ffprobe 스레드 상한을 한 곳에서 정한다.

★근거 (2026-10-03 18:48 맥1 실측 · 루키치 14편 동시): 부하 150/112/89 · CPU 쉼 0% · 스레드 3416.
  짧은 프레임 뽑기(구도·얼굴·비침·배경판·카드 검사 등)가 -threads 없이 돌아 ffmpeg 하나가
  디코더 프레임 스레드(코어 수만큼) + 필터 스레드(코어 수만큼) + png 인코더 스레드를 띄웠다.
  프레임 한 장 뽑기 30~42 스레드 · 조각 굽기(_틀굽기) 하나 369 스레드(2026-10-04 10시 ps -M 실측).
  14편이 동시에 돌면 그 곱이라 문맥 전환만 하다 CPU 가 녹았다.
  예전엔 호출마다 따로 «-threads 2» 를 붙였다(자막띠시각·튐관문·맞춤평가 · 합성 굽기만) — 새 호출은 늘 빠졌다.
  그래서 모든 호출이 이 함수를 지나게 하고, 검수도구/ffmpeg스레드시험.py 가 안 지난 호출을 잡는다.

정하는 값(환경변수로 바꿀 수 있다 · 이름은 ASCII — bash 는 한글 변수 이름을 export 하지 못한다):
  SKETCH_FF_DECODE  입력마다 디코더 스레드 (기본 2)
  SKETCH_FF_FILTER  -filter_threads · -filter_complex_threads (기본 2)
  SKETCH_FF_ENCODE  출력 인코더 스레드 (기본 4 — 합성 굽기가 2026-09-28 부터 쓰던 값과 같다)
이미 그 자리에 -threads 가 적힌 입력·출력은 건드리지 않는다(정지 그림 입력 -threads 1 등).
"""
import os

_기본 = {"SKETCH_FF_DECODE": 2, "SKETCH_FF_FILTER": 2, "SKETCH_FF_ENCODE": 4}


def 값(이름):
    try:
        n = int(os.environ.get(이름, "") or _기본[이름])
    except ValueError:
        n = _기본[이름]
    return str(max(1, n))


def _이름(a):
    return os.path.basename(str(a))


def 명령(argv):
    """ffmpeg/ffprobe argv 를 받아 스레드 상한을 넣은 새 리스트를 돌려준다(원본은 안 바꾼다)."""
    argv = [str(a) if not isinstance(a, str) else a for a in argv]
    if not argv:
        return argv
    머리 = _이름(argv[0])
    if 머리 == "ffprobe":
        # ffprobe 는 -count_frames 일 때만 통째로 디코드한다 — 입력 옵션 자리(맨 앞)에 디코더 상한
        if "-threads" in argv:
            return list(argv)
        return [argv[0], "-threads", 값("SKETCH_FF_DECODE")] + list(argv[1:])
    if 머리 != "ffmpeg":
        raise ValueError(f"ff.명령 은 ffmpeg/ffprobe 만 받는다: {argv[0]}")
    D, F, E = 값("SKETCH_FF_DECODE"), 값("SKETCH_FF_FILTER"), 값("SKETCH_FF_ENCODE")
    out = [argv[0]]
    if "-filter_threads" not in argv:
        out += ["-filter_threads", F]
    if "-filter_complex" in argv and "-filter_complex_threads" not in argv:
        out += ["-filter_complex_threads", F]
    구역 = []                       # 직전 입력 뒤 ~ 이번 -i 앞 (= 이 입력의 옵션)
    i, 마지막입력끝 = 1, None
    while i < len(argv):
        a = argv[i]
        if a == "-i" and i + 1 < len(argv):
            if "-threads" not in 구역:
                구역 += ["-threads", D]
            out += 구역 + ["-i", argv[i + 1]]
            구역 = []
            i += 2
            마지막입력끝 = len(out)
            continue
        구역.append(a)
        i += 1
    # 남은 구역 = 출력 옵션 + 출력 파일(맨 끝). 출력 옵션에 -threads 가 없으면 출력 파일 바로 앞에 넣는다.
    #   영상 인코더(libx264·libx265)는 E, 그림·rawvideo·소리 출력은 D 로 충분하다(png 인코더도 프레임 스레드를 띄운다).
    if 마지막입력끝 is not None and 구역 and "-threads" not in 구역:
        n = E if any(c in 구역 for c in ("libx264", "libx265")) else D
        구역 = 구역[:-1] + ["-threads", n] + 구역[-1:]
    return out + 구역
