# -*- coding: utf-8 -*-
"""한 편을 굽는다. ★나레이션 TTS 요금이 나간다.

sketch 와 갈리는 지점은 **레이아웃**이다. 저쪽은 영상을 가운데 상자에 넣는 5층
구조인데, 여기는 **영상이 화면을 꽉 채우고 그 위에 타이틀바·자막·워터마크를 얹는다**
(지침서 1장). 그래서 crop 비율이 9:16 이고 인물이 훨씬 크게 잡힌다.

순서
    1) 구간을 잘라 붙인다 (framing.plan_beats — 자주·작게)
    2) 오버레이 한 장을 그린다 (타이틀바·해시태그·워터마크)
    3) 자막 ASS — 대사와 나레이션을 **색으로 가른다**
    4) 나레이션을 굽고 제자리에 얹는다 (★요금)
    5) 합성·렌더 + 라우드니스
"""
import json
import os
import random
import subprocess
import sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)
V, L = CFG["video"], CFG["layout"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(argv, capture=False):
    p = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"실패: {' '.join(str(a) for a in argv[:6])}…\n"
                         f"{(p.stderr or '')[-700:]}")
    return p.stdout if capture else ""


def probe_wh(src):
    o = run(["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "default=nw=1", src], capture=True)
    d = dict(x.split("=") for x in o.strip().splitlines() if "=" in x)
    return int(d["width"]), int(d["height"])


def probe_dur(src):
    o = run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", src], capture=True)
    try:
        return float(o.strip())
    except ValueError:
        return 0.0


def find_burned_subs(src, W, H, dur, n=10):
    """원본에 박힌 자막의 윗변. 못 찾으면 None. 우리 자막과 두 겹이 되는 것을 막는다."""
    import numpy as np
    # ★호출마다 전용 임시 폴더 (2026-09-26 — 여러 편 동시 진행 준비): 예전엔 공용 임시 폴더의 고정 이름
    #   _s2burn{i}.png 이라 두 편이 동시에 구우면 서로의 프레임을 덮어써 남의 자막 자리를 읽을 수 있었다.
    _tmp = __import__("tempfile").mkdtemp(prefix="_s2burn_")
    tops = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        p = os.path.join(_tmp, f"_s2burn{i}.png")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss",
                            f"{t:.2f}", "-i", src, "-frames:v", "1", "-y", p],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(p):
            continue
        try:
            a = np.asarray(Image.open(p).convert("RGB")).astype(int)
        except Exception:                                # noqa: BLE001
            continue
        finally:
            pass
        band = a[int(H * 0.75):, :, :]
        g = band.mean(axis=2)
        # ★외곽선 없는 노란 예능자막도 같이 잡는다 (Deep03 실측 2026-09-03)
        노랑 = (band[:, :, 0] >= 200) & (band[:, :, 1] >= 170) & (band[:, :, 2] <= 140)
        y_ok = int(노랑.sum()) >= 1500
        rows = np.where(((g > 200).sum(axis=1) > W * 0.02) |
                        (y_ok & (노랑.sum(axis=1) > 15)))[0]
        if len(rows):
            tops.append(int(H * 0.75) + int(rows[0]))
        try:
            os.remove(p)
        except OSError:
            pass
    if len(tops) < 3:
        return None
    tops.sort()
    return tops[len(tops) // 2]


def 엔드카드시작(src, dur, 하한=0.0):
    """소재 꼬리의 정적 아웃트로 카드(남색 «싱글벙글» 등)가 시작하는 **소재 시각**. 없으면 None.
    ★t1 과 무관하게 카드의 «절대 시작점»을 준다 — 굽기(구간이 카드에 걸치면 트림)와 준비(여운이
    카드 앞에서 멈추게)가 공유한다(2026-09-10 싱글370: t1 이 카드 직전이라 굽기는 안 걸렸는데
    여운이 카드로 1.8s 늘어난 사건 — 검출을 한 곳으로 통일).

    ★2026-09-10 싱글349 «두 장 카드» 클래스 수리 — 땜질 아님:
      옛 검출은 소재 «마지막 한 프레임(fin)»에 앵커해 그와 «같은» 정적 꼬리만 걸었다.
      싱글벙글 소재는 결말 뒤에 [남색 싱글벙글 콜라보 카드] → [스폰서 광고 카드(모바일현금카드 QR)]
      **두 장이 다른 그림**으로 이어지는 경우가 있다. 그러면 fin=스폰서 카드라, 뒤에서 걷어오다가
      스폰서≠남색 경계(≈250s)에서 멈춰 **스폰서 카드 시작(244.9s)**만 돌려줬다. 내 마지막 조각
      t1=238.4 는 남색 카드(237.9s~) 안에 있는데 244.9>238.4 라 트림이 안 걸려 카드가 새어나갔다
      (373~370 등은 우연히 카드가 한 장뿐이라 통과 — 검출 앵커의 구조적 구멍).
      **수리**: 앵커를 버리고 «움직임(motion)»으로 판정한다. 카드는 완전정지(0.4s 뒤 프레임과 평균차
      ≤0.001), 실내용은 정지샷도 ≥0.25 로 차이가 뚜렷하다. 꼬리에서 «정지 사슬»을 걷어오되, 카드
      사이 전이(한두 프레임 튐)는 견디고 **0.6s 이상 지속되는 움직임(=실내용 재진입)**에서만 멈춘다.
      → 두 장이 이어져도 실내용 직전(남색 카드 시작)에서 끊는다. 373·370·372·369·365 등 한 장 편은
      옛 값과 ±2ms 로 동일(무회귀 확인). motion 판정이라 새 스타일 카드도 «검출 술래잡기» 없이 잡는다."""
    import numpy as _np
    def _g(t):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.2f}", "-i", src,
                            "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo",
                            "-pix_fmt", "gray", "-"], capture_output=True)
        a = _np.frombuffer(r.stdout, dtype=_np.uint8)
        return a.astype(_np.int16) if len(a) == 2304 else None
    def _정지(t):
        # 카드=완전정지(0.4s 뒤와 평균차 ≤0.001), 실내용=미세한 손·노이즈로 ≥0.25 → 0.15 로 갈린다
        a, b = _g(t), _g(t + 0.4)
        if a is None or b is None:
            return False
        return float(_np.abs(a - b).mean()) <= 0.15
    시작 = dur - 0.6              # 끝-0.1 은 마지막 키프레임 뒤라 프레임이 안 나온다(2026-09-09 실측)
    if not _정지(시작):           # 꼬리가 정지 카드가 아니면(=실내용으로 끝남) 카드 없음
        return None
    ec, t, 움직임 = 시작, 시작 - 0.15, 0.0
    while t >= 하한:
        if _정지(t):
            ec, 움직임 = t, 0.0
        else:
            움직임 += 0.15
            if 움직임 >= 0.6:      # 0.6s 지속 움직임 = 실내용 재진입 (카드 간 전이 튐은 견딤)
                break
        t -= 0.15
    if ec is None or 시작 - ec < 0.8:                        # 정적 꼬리 0.8s 미만이면 카드 아님
        return None
    lo, hi = ec - 0.15, ec                                   # lo=실내용, hi=카드 — 경계 좁히기
    for _ in range(7):
        mid = (lo + hi) / 2
        if _정지(mid):
            hi = mid
        else:
            lo = mid
    return round(hi, 3)


def cut_and_join(src, segs, dst, work, fps):
    """구간을 잘라 **여백 없이** 붙인다. crop 은 비트마다 조금씩 움직인다."""
    from . import framing
    from . import split as sp

    b = L["video_box"]                           # ★1080x908 상자 (sketch 껍데기)
    W, H = probe_wh(src)
    usable_h = H
    # ★박힌 자막 한계는 «카드마다 잰 상자 윗변»으로 «조각마다» 정한다 (2026-09-27 싱글266·188 글자 노출 · 85편 상자 띠 ·
    #   187 두 줄 카드 — 예전엔 원본 10장 표본의 «글자» 윗선 중앙값 하나(find_burned_subs)로 편 전체를 잘라 소수 카드
    #   (두 줄·높이 뜬 카드·날짜 캡션)와 글자 20px 위의 반투명 상자가 샜다). 규칙과 관문은 s2pipe/번인관문.py 한 곳.
    #   카드 없는 조각은 기본값(sub_zone_top − 여유)보다 더 자르지 않는다(인물 과도 크롭 방지 — 예전 802 같은 과잉).
    from . import 번인관문 as 관
    pad = b.get("safe_pad_px", 8)
    박스들 = []
    기본h = H
    if b.get("avoid_burned_subs"):
        박스들 = 관.카드상자들(src, log=lambda m: print(m, flush=True))
        기본h = int(H * b.get("sub_zone_top", 0.872)) - pad
        if 박스들:
            usable_h = 기본h
            print(f"    원본 자막 카드 {len(박스들)}장 — 조각마다 겹친 카드의 가장 높은 상자 윗변 − {pad} 까지 쓴다"
                  f" (카드 없는 조각 {기본h})", flush=True)
        else:
            # 카드가 하나도 없는 원본(박힌 자막 없음·띠 밖 자막) — 예전 방식 그대로
            top = find_burned_subs(src, W, H, max(s["t1"] for s in segs))
            if top:
                usable_h = top - pad
                print(f"    원본 자막 카드 없음 · 밝은 줄 감지: y={top} ({top/H*100:.1f}%) →"
                      f" 세로 {usable_h}px 만 쓴다", flush=True)
            else:
                usable_h = 기본h
                print(f"    원본 자막 못 찾음 → 기본값으로 세로 {usable_h}px", flush=True)

    cuts = sp.scene_cuts(src) if b.get("follow_face") else []

    # ★마지막 조각의 검은 꼬리 자동 절단 (2026-09-04 사장님 «소리가 남았다고 검은 화면을
    #   출력하는 일은 없어야» — Deep07 아웃트로 암전 2초 실측). 끝에서 0.25s 씩 물러나며
    #   어두운 프레임(평균 밝기 < 12)을 걷어낸다.
    def _어두운가(t):
        # ★죽은 검정만 «어둡다». 검은 배경 위에 글자가 얹힌 카드(블랙아웃 펀치라인 «2주 전이다»)는
        #   평균은 <12 라도 글자 픽셀이 밝다(2026-09-09 Deep61 실측: 카드 평균 0.4·최대 76 —
        #   옛 기준이 카드째 잘라 무한 루프 결말이 «9월 11일 월급날»에서 끊겼다). 밝은 픽셀이 조금이라도
        #   있으면 글자·그림이 있는 것 → 자르지 않는다(mean<12 AND 밝은픽셀 거의 0).
        import numpy as _np
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.2f}", "-i", src,
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True)
        a = _np.frombuffer(r.stdout, dtype=_np.uint8)
        if len(a) == 0:
            return False
        bright = int((a > 60).sum())                 # 글자 획 픽셀 (배경 검정과 확실히 구분)
        return float(a.mean()) < 12 and bright < len(a) * 0.0008
    막 = segs[-1]
    # ★소재 아웃트로 카드 처리 (2026-09-09 사장님 «마지막에 싱글벙글 로고만 떠있고 … 로고 나오게
    #   하지말고 종결지어줘»): 결말 뒤 정적 브랜드 카드(남색 «싱글벙글»)는 검정이 아니라 아래
    #   _어두운가 가 못 잡는다. 카드의 «절대 시작점»을 찾아(엔드카드시작) 조각에 남긴다 — 구간이
    #   카드에 걸치면 트림하고, 안 걸쳐도 그 값으로 준비의 여운이 카드 앞에서 멈춘다(2026-09-10
    #   싱글370: t1 이 카드 직전이라 트림은 없었는데 여운이 카드로 늘던 사건).
    try:
        _srcdur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                        "-of", "csv=p=0", src], check=True,
                                       capture_output=True).stdout.decode().strip())
        _ec = 엔드카드시작(src, _srcdur, 막["t0"] + 2.0)
        if _ec is not None:
            막["_엔드카드시작"] = _ec
            if _ec < 막["t1"]:
                막["t1"] = _ec                                       # 카드 시작 = 배타적 끝(카드 0장)
                print(f"    마지막 조각 아웃트로 카드 절단 → t1={막['t1']} (원본 카드 {_ec:.2f}s~)", flush=True)
            else:
                print(f"    원본 아웃트로 카드 {_ec:.2f}s~ 감지 — 조각은 그 앞({막['t1']})에서 끝나 트림 없음(여운만 제한)", flush=True)
    except Exception as _e:
        print(f"    (아웃트로 카드 감지 건너뜀: {_e})", flush=True)
    깎음 = 0.0
    while 막["t1"] - 막["t0"] > 2.0 and _어두운가(막["t1"] - 0.15):
        막["t1"] = round(막["t1"] - 0.25, 3)
        깎음 += 0.25
    if 깎음:
        print(f"    마지막 조각 검은 꼬리 -{깎음:.2f}s 절단 → t1={막['t1']}", flush=True)

    # ★영구 게이트 (2026-09-10 싱글349 «남색 카드가 새어나간» 사건): 위 트림이 끝난 뒤
    #   **확정된 마지막 소재 프레임이 정지 카드가 아님**을 기계로 못 박는다. 검출/트림에 또
    #   구멍이 나도(새 스타일 카드·두 장 카드) 사람 눈보다 여기서 먼저 멈춘다. 소스 기준으로 잰다
    #   — 결과물엔 비트 팬·줌이 얹혀 카드도 «움직여» 보여 결과 프레임으론 못 잡는다.
    import numpy as _np
    def _소스정지(t):
        def _gg(u):
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(u, 0):.2f}", "-i", src,
                                "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo",
                                "-pix_fmt", "gray", "-"], capture_output=True)
            a = _np.frombuffer(r.stdout, dtype=_np.uint8)
            return a.astype(_np.int16) if len(a) == 2304 else None
        a, b = _gg(t - 0.4), _gg(t)
        return a is not None and b is not None and float(_np.abs(a - b).mean()) <= 0.15
    if 막["t1"] - 막["t0"] > 1.0 and _소스정지(막["t1"] - 0.05):
        raise AssertionError(
            f"마지막 조각 끝({막['t1']:.2f}s)이 정지 카드다 — 엔드카드 검출/트림이 카드를 놓쳤다. "
            f"엔드카드시작({막['t0']+2.0:.1f}~) 반환값과 원본 카드 시작을 대조하라(싱글349 클래스).")

    parts, log = [], {"segments": [], "beats": [], "frames": []}

    def bake_beats(a, bnd, plan):
        legs, tags = [], []
        for j, (bt0, bt1, vf, _) in enumerate(plan):
            cut = (f"trim=start={bt0-a:.3f}"
                   + ("" if j == len(plan) - 1 else f":end={bt1-a:.3f}"))
            legs.append(f"[0:v]{cut},setpts=PTS-STARTPTS,{vf},setsar=1[v{j}]")
            tags.append(f"[v{j}]")
        # ★비트 영상을 소리와 «정확히 같은 프레임 수»로 못 박는다 (2026-09-09 립싱크 실측:
        #   비트 concat 이 마지막 비트에서 1프레임 넘쳐 영상이 소리보다 1프레임 길었다.
        #   조각마다 쌓여 8조각 편 끝에서 ~0.3s 소리가 입보다 앞섰다 — trim=end_frame 으로 자른다.
        #   -t 는 소리에만 걸리고, 영상은 concat 이 -t 를 안 지켜(200프레임 vs 199) 어긋났었다.)
        N = round((bnd - a) * fps)                       # 이 조각의 목표 프레임 수
        fc = ";".join(legs) + f";{''.join(tags)}concat=n={len(plan)}:v=1:a=0,trim=end_frame={N},setpts=PTS-STARTPTS[vo]"
        p = os.path.join(work, f"seg{len(parts):03d}.mov")
        # ★PCM + 프레임 정확 길이(2026-09-03 «순간 배속» 사건) — AAC 꼬리 패딩이 조각마다
        #   +40~60ms 붙어 경계에서 말이 겹쳐 들렸다(46ms 실측). PCM 은 패딩이 없고
        #   -t 로 프레임 단위 길이를 못 박는다. AAC 인코딩은 최종 합칠 때 한 번만.
        d_q = N / fps
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(a),
             "-to", str(bnd), "-i", src, "-filter_complex", fc,
             "-map", "[vo]", "-map", "0:a", "-t", f"{d_q:.5f}",
             "-c:v", "libx264", "-preset", "veryfast",
             "-crf", str(CFG["ffmpeg"]["crf"]), "-c:a", "pcm_s16le",
             "-avoid_negative_ts", "make_zero", "-y", p])
        # ★게이트: 구운 조각의 영상 프레임 수 = 목표 N (소리와 프레임 일치). 어긋나면 립싱크가 밀린다.
        _nf = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", p],
                             capture_output=True, text=True).stdout.strip()
        assert _nf and abs(int(_nf) - N) <= 0, f"비트 조각 프레임 {_nf} ≠ 목표 {N} — 영상·소리 프레임 어긋남(립싱크)"
        parts.append(p)

    def _안쪽경계(t):
        """프레임-인-프레임(원본 아웃트로가 화면을 절반으로 줄이고 검은 테두리) 감지 —
        검은 테두리째 구우면 결과물에 검은 띠가 박힌다(2026-09-07 Deep10 컷7 실측:
        960x540 중앙). 밝기>16 인 실화면 경계를 돌려준다. 테두리가 없으면 None."""
        import numpy as _np
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", src,
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True)
        a = _np.frombuffer(r.stdout, dtype=_np.uint8)
        if len(a) != W * H:
            return None
        m = a.reshape(H, W) > 16
        rows, cols = _np.where(m.any(axis=1))[0], _np.where(m.any(axis=0))[0]
        if not len(rows) or not len(cols):
            return None
        x, y = int(cols[0]), int(rows[0])
        w, h = int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)
        # ★검은 배경 위 작은 글자 카드(블랙아웃 펀치라인 «2주 전이다»)는 프레임-인-프레임이 아니다
        #   — 밝은 영역이 화면의 15% 미만이면 타이틀 카드다. 확대하면 글자가 렌즈처럼 뭉개진다
        #   (2026-09-09 Deep61 실측: 카드를 «전이» 조각으로 확대). 확대하지 않고 원본대로 둔다.
        if w * h < W * H * 0.15:
            return None
        return (x, y, w, h) if w <= W * 0.92 and h <= H * 0.92 else None

    prev = None
    for i, s in enumerate(segs):
        박들 = [_안쪽경계(s["t0"] + (s["t1"] - s["t0"]) * f) for f in (0.25, 0.5, 0.75)]
        if all(박들) and max(abs(박들[0][k] - 박들[j][k]) for j in (1, 2) for k in range(4)) <= 8:
            x, y, w, h = 박들[1]
            vf = (f"crop={w}:{h}:{x}:{y},scale=-2:908,"
                  f"crop=1080:908:(iw-1080)/2:0,setsar=1")
            p = os.path.join(work, f"seg{len(parts):03d}.mov")
            d_q = round((s["t1"] - s["t0"]) * fps) / fps
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(s["t0"]),
                 "-to", str(s["t1"]), "-i", src, "-vf", vf, "-t", f"{d_q:.5f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CFG["ffmpeg"]["crf"]),
                 "-c:a", "pcm_s16le", "-avoid_negative_ts", "make_zero", "-y", p])
            parts.append(p)
            prev = None
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0})
            _vw = min(w, int(1080 * h / 908))                     # 가운데 1080 폭만 보인다
            log["frames"].append({"seg": i, "t0": s["t0"], "t1": s["t1"], "kind": "프레임-인-프레임",
                                  "crop": [_vw, h, x + (w - _vw) // 2, y]})
            print(f"    P{s.get('phase')} 조각 {i} {s['t1']-s['t0']:5.1f}초 → 프레임-인-프레임"
                  f" 감지({w}x{h}@{x},{y}) — 안쪽만 잘라 확대", flush=True)
            continue
        if s.get("원문화면") or s.get("전체화면"):
            # ★전체화면(2026-09-27): 가로 전체만 보이고 자막·잔존 검사는 그대로(박힌 자막 없는 샷 전용).
            # ★원문화면 (2026-09-07 사장님 «결론 빼먹었어» — 결말 명언 카드): 화면 속 글이
            #   내용이라 얼굴 추적·확대 금지. 원본 «가로 전체»를 박스 폭에 맞춰 넣고(글이
            #   잘리면 결이 잘린다) 빈 위아래는 같은 화면의 흐림 배경으로 채운다.
            #   준비(prproj)의 컷 상자도 같은 fit-width 규칙을 쓴다 — 경로마다 따로 금지.
            # setsar=1 필수 — scale 반올림(607.5→608)이 SAR 를 24289:24300 으로 틀어
            # concat 필터가 Invalid argument 로 거부했다(2026-09-07 실측).
            # 빈 위아래는 «페이지색» — 흐림 배경은 어두운 장면에서 검은 띠로 보였다
            # (2026-09-07 사장님 «위아래가 검은색으로 짤리는 게 맞아?»). 준비의 템플릿
            # 원문화면 띠(150px)와 같은 기하·같은 색 = 페이지 위에 카드가 놓인 모양.
            _bg = CFG.get("layout", {}).get("bg", "F7F8FB")
            # ★상자 크기는 설정값(숨은기록 1080x904) — 1080x908 을 박아 두어 다른 조각과 concat 이 «Invalid argument» 로
            #   죽었다(2026-09-27 싱글246 결말 바퀴벌레 샷). 프레임 속도도 원본 fps 로.
            _bw, _bh = int(b.get("w", 1080)), int(b.get("h", 908))
            # pad 로 둘레를 채운다 — color+overlay 는 조각 첫 프레임에 배경만 나오는 1프레임 번쩍임이 있었다(2026-09-27 싱글235)
            vf = (f"[0:v]scale={_bw}:-2,setsar=1,"
                  f"pad={_bw}:{_bh}:(ow-iw)/2:(oh-ih)/2:color=0x{_bg},setsar=1")
            p = os.path.join(work, f"seg{len(parts):03d}.mov")
            d_q = round((s["t1"] - s["t0"]) * fps) / fps
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(s["t0"]),
                 "-to", str(s["t1"]), "-i", src, "-filter_complex", vf, "-t", f"{d_q:.5f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CFG["ffmpeg"]["crf"]),
                 "-c:a", "pcm_s16le", "-avoid_negative_ts", "make_zero", "-y", p])
            parts.append(p)
            prev = None
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0})
            log["frames"].append({"seg": i, "t0": s["t0"], "t1": s["t1"],
                                  "kind": "원문화면" if s.get("원문화면") else "전체화면", "crop": [W, H, 0, 0]})
            print(f"    P{s.get('phase')} 조각 {i} {s['t1']-s['t0']:5.1f}초 → 원문화면"
                  f" fit-width(흐림 배경) — 얼굴 추적 없음", flush=True)
            continue
        # ★조각별 «자막띠무시» (2026-09-27 싱글246 — 결말 반전 그림(바닥을 지나가는 바퀴벌레)이 원본 자막띠 자리
        #   y≈1000~1060 에 있어 자막띠 자르기로 통째 잘렸다). 사람이 «이 조각엔 박힌 자막이 없다» 를 프레임으로 확인한
        #   조각만 세로 전체를 쓴다. 틀리면 ⑦ 준비의 «컷 하단 잔존 번인 자막» 검사가 잡는다.
        uh = usable_h
        if 박스들:
            uh, 높은 = 관.조각한계(박스들, s["t0"], s["t1"], 기본h, pad)
            if 높은 and uh < 기본h:
                print(f"    조각 {i}: 높은 박힌 자막 카드({높은['t0']:.1f}초 · 상자 윗변 {높은['top']}) → 세로 {uh}px 까지", flush=True)
        if s.get("자막띠무시"):
            # 사람 선언보다 측정이 먼저다 — 카드가 겹치면 선언을 무시하고 카드 한계를 쓴다
            if 박스들 and 관.겹친카드(박스들, s["t0"], s["t1"]):
                print(f"    ★조각 {i}: 자막띠무시 표식인데 박힌 자막 카드가 겹친다 — 표식을 무시하고 세로 {uh}px", flush=True)
            else:
                uh = H
                print(f"    조각 {i}: 자막띠무시 — 세로 {H}px 전체를 쓴다(박힌 자막 카드 없음)", flush=True)
        plan = framing.plan_beats(src, s, i, W, H, uh, b, work, cuts, prev)
        if not plan:
            vf, info = framing.plan_frame(src, s, i, W, H, uh, b, work, prev=prev)
            p = os.path.join(work, f"seg{len(parts):03d}.mov")
            d_q = round((s["t1"] - s["t0"]) * fps) / fps
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(s["t0"]),
                 "-to", str(s["t1"]), "-i", src, "-vf", vf, "-t", f"{d_q:.5f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CFG["ffmpeg"]["crf"]),
                 "-c:a", "pcm_s16le", "-avoid_negative_ts", "make_zero", "-y", p])
            parts.append(p)
            prev = info["crop"]
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0})
            log["frames"].append({"seg": i, "t0": s["t0"], "t1": s["t1"], "kind": "한장구도",
                                  "crop": list(info["crop"][:4])})
            continue
        bake_beats(s["t0"], s["t1"], plan)
        prev = plan[-1][3]["crop"]
        log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                "phase": s.get("phase"), "part": parts[-1],
                                "beats": len(plan)})
        for a, e, _vf, info in plan:
            log["beats"].append({"seg": i, "t0": a, "t1": e,
                                 "crop": list(info["crop"]),
                                 "at_cut": bool(info["at_cut"])})
        zs = [x[3]["zoom"] for x in plan]
        nf = sum(1 for x in plan if x[3]["face"])
        # ★영구 게이트 (2026-09-21 Deep87 «입이 잘리는 과확대») — 얼굴을 찾은 비트는 그 얼굴이
        #   crop 안에 있어야 한다. 기존 검사는 «얼굴이 검출되는가» 만 봤다. framing.담기 가
        #   보장하지만, 누가 그 관문을 우회하는 경로를 새로 만들면 여기서 걸린다.
        #   face_in=None 은 얼굴이 쓸 수 있는 자리보다 큰 불가피 비트(원본 초근접) — 찍기만 한다.
        밖 = [(round(x[0], 2), x[3]["crop"]) for x in plan if x[3]["face"] and x[3].get("face_in") is False]
        assert not 밖, f"조각 {i}: 얼굴이 crop 밖으로 나간 비트 {밖[:3]} — framing.담기 를 우회했다"
        불가피 = sum(1 for x in plan if x[3]["face"] and x[3].get("face_in") is None)
        띠 = sum(1 for x in plan if tuple(x[3].get("bounds", (0, 0, W, H))) != (0, 0, W, H))
        if 불가피 or 띠:
            print(f"      (레터박스 비트 {띠}개 — crop 을 띠 안쪽으로 · 초근접 얼굴 비트 {불가피}개 — 최대로 넓힘)",
                  flush=True)
        # ★얼굴 수를 반드시 찍는다. **조용히 실패하는 코드를 만들지 마라** — 모델
        #   (assets/models/yunet.onnx)이 없으면 얼굴을 하나도 못 찾고 확대가 기본값
        #   1.24 로 굳는데, 안 찍으면 그냥 그렇게 구워진다(실제로 한 번 그렇게 나왔다).
        print(f"    P{s.get('phase')} 조각 {i} {s['t1']-s['t0']:5.1f}초 →"
              f" 비트 {len(plan):2d}개(얼굴 {nf}) · 확대 {min(zs):.2f}~{max(zs):.2f}배"
              + ("  ★얼굴을 하나도 못 찾았다" if nf == 0 else ""), flush=True)

    # ★이어붙이기는 «디코드 → concat 필터 → 인코드» 한 번에 (2026-09-03 개정).
    #   조각별 AAC 를 타임스탬프로 이어붙이면(concat demuxer + copy) 조각 경계마다
    #   오디오 틈이 누적돼 컷 4~7에서 150ms~1s 어긋났다(원음 대조 실측). cut.mp4 는
    #   판정·전사용 중간 산물이라 재인코딩 화질 손실은 무해하다.
    ins, fc_in = [], ""
    for j, p in enumerate(parts):
        ins += ["-i", p]
        fc_in += f"[{j}:v][{j}:a]"
    fc = fc_in + f"concat=n={len(parts)}:v=1:a=1[vo][ao]"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", *ins,
         "-filter_complex", fc, "-map", "[vo]", "-map", "[ao]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CFG["ffmpeg"]["crf"]),
         "-c:a", "aac", "-b:a", CFG["ffmpeg"]["audio_bitrate"], "-y", dst])

    off = 0.0
    for e in log["segments"]:
        d = probe_dur(e["part"])
        e["out_t0"], e["out_dur"] = round(off, 3), round(d, 3)
        off += d
    log["out_dur"] = round(off, 3)
    json.dump(log, open(os.path.join(work, "beats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # ★최종 관문 (2026-09-27 싱글266·188 글자 노출 · 85편 상자 띠) — 구운 crop 전부(비트·한 장 구도·전체/원문화면·
    #   프레임-인-프레임)를 카드 상자·사람이 잰 화면 캡션(조각 «가림»)과 위치로 비교한다. 준비(프리미어 컷 상자)도 같은
    #   함수를 부른다. 예전엔 납품 mp4 의 crop 을 보는 관문이 없었다(준비는 프리미어 상자만 봤다).
    if b.get("avoid_burned_subs"):
        crops, _ = 관.beats_crops(log, W, H)
        걸 = 관.걸림(박스들, crops, 관.가림목록(segs))
        if 걸:
            raise AssertionError(f"박힌 자막이 crop 안에 든다 {len(걸)}건 — {관.글(걸)} (s2pipe/번인관문.py)")
        print(f"    [OK] 박힌 자막 관문 — crop {len(crops)}개 · 카드 {len(박스들)}장 겹침 0", flush=True)
    return dst


# ★글꼴을 못 찾으면 **반드시 진짜 글꼴로 떨어져야 한다.** `load_default()` 는 고정 크기
#   비트맵이라 **size 가 통째로 무시된다** — 헤더 글자가 아무리 키워도 작게 나온 이유가
#   이것이었다. 사다리 끝까지 못 찾으면 조용히 굽지 말고 **멈춘다**(맥 이식 2026-08-28).
FALLBACK = [
    r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",  # 윈도우
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",                      # 맥 — 맑은 고딕 대응
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
]


def _font(rel, px):
    # ★rel 이 빈 문자열이면 os.path.join 이 폴더를 돌려준다 — isfile 로 걸러야 한다.
    for p in ([os.path.join(HERE, rel)] if rel else []) + FALLBACK:
        if p and os.path.isfile(p):
            try:
                return ImageFont.truetype(p, px)
            except OSError:
                continue
    raise SystemExit(f"글꼴을 못 찾았다 (rel={rel!r}) — load_default 는 size 를 무시하므로 쓰지 않는다. FALLBACK 사다리를 확인하라.")


def draw_frame(proj, dst):
    """움직이지 않는 층을 한 장으로 — 헤더·제목·출처. 영상과 자막은 ffmpeg 가 얹는다.

    ★껍데기는 sketch 에서 가져왔다. 좌표·글꼴은 「먹기전에」 10편 실측이라 손대지 않는다.
    """
    im = Image.new("RGB", (V["w"], V["h"]), "#" + L["bg"])
    d = ImageDraw.Draw(im)

    h = L["header"]
    ch = CFG["channel"]
    icon = os.path.join(HERE, ch.get("icon", "") or "")
    if ch.get("icon") and os.path.isfile(icon):
        # ★투명 코너를 살려 합성한다(2026-09-09 숨은기록 원형 로고 — RGB 로 붙이면 코너가 검게 나온다)
        ic = Image.open(icon).convert("RGBA").resize((h["icon_size"], h["icon_size"]))
        im.paste(ic, (h["icon_x"], h["y0"] + 8), ic)
    else:
        d.ellipse([h["icon_x"], h["y0"] + 8,
                   h["icon_x"] + h["icon_size"], h["y0"] + 8 + h["icon_size"]],
                  outline="#E23B3B", width=8)
    tx = h["icon_x"] + h["icon_size"] + 26
    hf = _font(h.get("font", ""), h["handle_size"])
    hy = h["y0"] + 10
    d.text((tx, hy), ch.get("handle", ""), font=hf, fill="#111111")
    # ★인증배지 — 핸들 오른쪽에 파란 체크(2026-09-09 숨은기록 템플릿). config channel.badge 있을 때만
    badge = os.path.join(HERE, ch.get("badge", "") or "")
    if ch.get("badge") and os.path.isfile(badge):
        try:
            hw = int(d.textlength(ch.get("handle", ""), font=hf))
        except Exception:
            hw = hf.getbbox(ch.get("handle", ""))[2]
        bs = h.get("badge_size", 44)
        bg_ = Image.open(badge).convert("RGBA").resize((bs, bs))
        by = hy + (h["handle_size"] - bs) // 2 + 4
        im.paste(bg_, (tx + hw + h.get("badge_gap", 14), by), bg_)
    d.text((tx, h["y0"] + 10 + h["handle_size"] + 12), ch.get("name", ""),
           font=_font(h.get("font", ""), h["name_size"]), fill="#111111")

    # 제목 — ★항상 2줄, 가운데 정렬
    t = L["title"]
    tf = _font(t["font"], t["line_h"])
    title = proj.get("title")
    if isinstance(title, str):                           # 옛 형식이면 그대로 한 줄
        title = [title]
    for i, line in enumerate((title or [])[:t["lines"]]):
        y = t["line1_y"] if i == 0 else t["line2_y"]
        w = d.textlength(line, font=tf)
        d.text(((V["w"] - w) / 2, y), line, font=tf, fill="#" + t["color"])

    # 댓글 층 — 유튜브 댓글 UI 를 흉내 낸다(벤치 실측). 고정된 것만 여기 그리고
    # 본문과 좋아요 수는 장면 따라 바뀌므로 ASS 가 얹는다.
    if proj.get("comments"):
        cm = L["comment"]
        cy = cm["y0"] + 6
        d.ellipse([cm["icon_x"], cy,
                   cm["icon_x"] + cm["icon_size"], cy + cm["icon_size"]],
                  fill="#C9CDD4")
        # ★닉네임은 뭉갠다 — 원본 시청자 이름을 그대로 노출하지 않는다
        nx = cm["text_x"]
        d.rounded_rectangle([nx, cm["nick_y"], nx + cm["nick_w"],
                             cm["nick_y"] + cm["nick_h"]], radius=11, fill="#D6D9DE")
        df = _font(cm.get("font", ""), cm["date_size"])
        d.text((nx + cm["nick_w"] + 16, cm["nick_y"] - 2), cm.get("date", ""),
               font=df, fill="#" + cm.get("date_color", "8A8F98"))
        # 좋아요 엄지와 답글 — 실제 댓글처럼 보이게 하는 것이 목적이다
        mf = _font(cm.get("font", ""), cm["meta_size"])
        my = cm["meta_y"]
        d.rectangle([nx, my + 10, nx + 12, my + 26], fill="#8A8F98")
        d.rectangle([nx + 12, my + 4, nx + 26, my + 26], fill="#8A8F98")
        d.text((nx + 150, my), cm.get("reply", "답글"), font=mf,
               fill="#" + cm.get("meta_color", "8A8F98"))

    # 출처 — 설명란이 아니라 화면 안에 박는다
    c = L["credit"]
    cr = proj.get("credit") or {}
    if cr.get("channel") or cr.get("title"):
        txt = c["format"].format(channel=cr.get("channel", ""), title=cr.get("title", ""))
        cf = _font(t["font"], c["size"])
        w = d.textlength(txt, font=cf)
        d.text(((V["w"] - w) / 2, c["y0"]), txt, font=cf, fill="#" + c["color"])

    im.save(dst)
    return dst


def _ts(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(proj, dst, total, narrs=()):
    """대사와 나레이션을 **색으로 가른다**(지침서 3장).

    ★**나레이션 자막은 `subs` 가 아니라 `segments[].narration` 에서 만든다.**
      두 곳에 같은 문구를 두면 한쪽만 고쳤을 때 어긋난다 — 실제로 나레이션을 줄였는데
      화면에는 옛 문구가 그대로 나와 좌우로 넘쳤다. 실제로 **구운 음성의 길이**(narrs)를
      그대로 자막 길이로 쓴다.
    """
    s, ns = L["subtitle"], L["narration_sub"]
    size = int(s["cap_h"] / 0.72)
    nsize = int(ns["cap_h"] / 0.72)

    def bgr(h):
        return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}"

    c = L["comment"]
    # ★Format 줄은 sketch 와 **똑같이** 쓴다. 필드를 줄여 쓰면 libass 가 값을 어긋난
    #   자리에서 읽는다 — 댓글 글꼴·크기가 안 맞던 이유가 여기에도 있었다.
    # ★댓글은 얇은 시스템 글꼴이다 — 자막 글꼴을 쓰면 너무 굵어 댓글로 안 보인다.
    #   윈도우는 맑은 고딕, 맥은 Apple SD Gothic Neo (맥 이식 2026-08-28, 사람 눈 확인 대상).
    cmt_font = c.get("font_name") or ("Malgun Gothic" if os.name == "nt" else "Apple SD Gothic Neo")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {V['w']}
PlayResY: {V['h']}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: main,{s.get('font_name', 'Malgun Gothic')},{size},&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{s['outline_px']},0,2,60,60,{V['h'] - s['baseline_y']},1
Style: narr,{s.get('font_name', 'Malgun Gothic')},{nsize},{bgr(ns['color'])},{bgr(ns.get('outline', '000000'))},&H00000000,-1,0,0,0,100,100,0,0,1,{ns.get('outline_px', 7)},0,2,40,40,{V['h'] - ns['baseline_y']},1
Style: cmt,{cmt_font},{c['text_size']},{bgr(c['color'])},&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,1,0,0,7,{c['text_x']},40,{c['text_y']},1
Style: cmtlike,{cmt_font},{c['meta_size']},{bgr(c.get('meta_color','8A8F98'))},&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,1,0,0,7,{c['text_x'] + 36},40,{c['meta_y']},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    # 대사 — `subs` 에서. 나레이션 몫(kind=narr)은 여기서 빼고 아래에서 다시 만든다.
    subs = sorted([x for x in proj.get("subs", []) if x.get("kind") != "narr"],
                  key=lambda x: x["t"])
    body = []
    hi = s["max_chars"]
    # ★검수용 완성본도 프리미어판과 «동일하게» (2026-09-03 사장님 — 산출물 둘이 다르면
    #   검수가 어긋난다): 아모르 팝(86→104→100 튀기)과 말 끝 종료 시각을 같이 넣는다.
    팝 = "{\\fscx86\\fscy86\\t(0,120,\\fscx104\\fscy104)\\t(120,182,\\fscx100\\fscy100)}"
    for i, cur in enumerate(subs):
        다음t = subs[i + 1]["t"] if i + 1 < len(subs) else total
        if cur.get("t1"):
            end = min(max(cur["t1"] + 0.25, cur["t"] + 1.0), 다음t, total)
        else:
            end = min(다음t, cur["t"] + 3.0, total)
        if end <= cur["t"]:
            continue
        txt = (cur.get("text") or "").replace("\n", " ")
        if len(txt) > hi:                                # 넘치면 화면 밖으로 나간다
            txt = txt[:hi - 1] + "…"
        body.append(f"Dialogue: 0,{_ts(cur['t'])},{_ts(end)},main,,0,0,0,,{팝}{txt}")

    # 나레이션 — 실제로 구운 음성과 **같은 문구·같은 길이**로 얹는다
    seg_narr = {}
    at = 0.0
    for sg in proj["segments"]:
        t = (sg.get("narration") or "").strip()
        if t:
            seg_narr[round(at, 3)] = t
        at += sg["t1"] - sg["t0"]
    spans = []
    for a, wav in narrs:
        t = seg_narr.get(round(a, 3))
        if not t:
            continue
        try:
            d = probe_dur(wav)
        except Exception:                                # noqa: BLE001
            d = 3.0
        spans.append((a, a + d))
        body.append(f"Dialogue: 0,{_ts(a)},{_ts(a + d)},narr,,0,0,0,,"
                    "{\\fscx86\\fscy86\\t(0,120,\\fscx104\\fscy104)\\t(120,182,\\fscx100\\fscy100)}" + t)

    # ★★나레이션이 뜨는 동안 **대사 자막을 감춘다.** 둘이 겹쳐 자막이 2줄로 뭉쳐
    #   나왔다. 그 구간은 원음도 죽였으니 읽을 대사가 없다.
    if spans and CFG["narration"].get("hide_line_subs", True):
        def _sec(v):
            return sum(float(x) * m for x, m in zip(v.split(":"), (3600, 60, 1)))

        keep, cut_n = [], 0
        for ln in body:
            if ",main," not in ln:
                keep.append(ln)
                continue
            p = ln.split(",")
            st, en = _sec(p[1]), _sec(p[2])
            # ★★**구간이 겹치면 감춘다 — 시작 시각만 보면 안 된다.**
            #   나레이션 **전에 시작해서** 그 위로 흘러 들어오는 자막이 그대로
            #   남아 두 줄이 겹쳤다(실측 2026-08-19).
            if any(st < b + 0.2 and en > a - 0.2 for a, b in spans):
                cut_n += 1
                continue
            keep.append(ln)
        if cut_n:
            print(f"    나레이션과 겹쳐 감춘 대사 자막 {cut_n}줄", flush=True)
        body = keep

    # 댓글 — 편 전체에 균등 배치한다. **읽을 게 계속 바뀌어야 지루하지 않다**
    cmts = proj.get("comments", [])
    if cmts:
        cc = L["comment"]
        hi, per = cc["max_chars"], max(1, cc["max_chars"] // cc.get("lines", 2))
        # ★★**길이에 비례해 시간을 나눈다.** 균등하게 주면 51자짜리는 못 읽고
        #   14자짜리는 남아돈다(한국어 묵독은 초당 8~12자다). 짧은 것을 빨리
        #   넘기면 그만큼 긴 것에 줄 수 있어 **같은 시간에 더 많이 담긴다.**
        floor = cc.get("min_sec", 2.2)
        wts = [max(len((c.get("text") or "")), 12) for c in cmts]
        sw = sum(wts) or 1
        spans_c, at_c = [], 0.0
        for w in wts:
            d = max(floor, total * w / sw)
            spans_c.append((at_c, at_c + d))
            at_c += d
        if at_c > total:                             # 최소 시간 때문에 넘치면 줄인다
            k = total / at_c
            spans_c = [(a * k, b * k) for a, b in spans_c]

        def likes(v):
            """유튜브처럼 줄여 쓴다 — 4400 → 4.4천"""
            if v >= 10000:
                return f"{v/10000:.1f}만".replace(".0", "")
            if v >= 1000:
                return f"{v/1000:.1f}천".replace(".0", "")
            return str(v)

        for i, cm in enumerate(cmts):
            t = (cm.get("text") or "").replace("\n", " ")
            if len(t) > hi:                              # 넘치면 화면 밖으로 나간다
                t = t[:hi - 1] + "…"
            # ★두 줄로 나눠 넣는다(\\N). 벤치도 긴 댓글을 2줄로 보여 준다
            if len(t) > per:
                cutp = t.rfind(" ", 0, per + 4)
                cutp = cutp if cutp >= per * 0.5 else per
                t = t[:cutp].rstrip() + "\\N" + t[cutp:].lstrip()
            a, b = _ts(spans_c[i][0]), _ts(spans_c[i][1])
            body.append(f"Dialogue: 0,{a},{b},cmt,,0,0,0,,{t}")
            if cm.get("likes"):
                body.append(f"Dialogue: 0,{a},{b},cmtlike,,0,0,0,,{likes(cm['likes'])}")

    body.sort(key=lambda x: x.split(",")[1])
    open(dst, "w", encoding="utf-8").write(head + "\n".join(body) + "\n")
    return dst


def narrate(proj, work, total):
    """나레이션을 굽고 (시작초, wav) 목록을 준다. ★여기서 요금이 나간다."""
    from . import tts
    n = CFG["narration"]
    if not n.get("enabled") or not n.get("voice_id"):
        return []
    out, at = [], 0.0
    for i, s in enumerate(proj["segments"]):
        span = s["t1"] - s["t0"]
        text = (s.get("narration") or "").strip()
        if text:
            wav = os.path.join(work, f"narr{i:02d}.wav")
            _p, d = tts.synth(text, n, wav, os.path.join(work, "_tts"))
            if d > span:
                print(f"    ★나레 {i} 가 조각보다 길다 ({d:.1f}초 > {span:.1f}초)"
                      f" — 다음 대사와 겹친다", flush=True)
            print(f"    나레 {i}: {d:.2f}초  {text[:30]}", flush=True)
            out.append((round(at, 3), wav))
        at += span
    return out


def pick_sfx(tag):
    """`@꼬리표` 에서 하나를 고른다. 없으면 None — 조용히 넘기지 않고 알린다."""
    cat = os.path.join(CFG["paths"]["assets"], "catalog.json")
    if not os.path.isfile(cat) or not tag.startswith("@"):
        return None
    d = json.load(open(cat, encoding="utf-8"))
    cands = [s["file"] for s in d.get("sfx", []) if s.get("tag") == tag[1:]]
    if not cands:
        print(f"    ★효과음 {tag} 이 카탈로그에 없다", flush=True)
        return None
    return os.path.join(HERE, CFG["assets"]["sfx_dir"], random.choice(sorted(cands)))


def compose(cut, frame, ass, narrs, sfx_at, dst, cmts=()):
    """정적 층 위에 영상 상자를 얹고 자막을 태운 뒤 소리를 섞는다.

    ★입력 0 = 배경(정지 그림, loop) · 1 = 잘라 붙인 영상 · 2.. = 나레이션 · 그 뒤 = 효과음
    ★ass 필터는 시스템 글꼴만 본다 — `fontsdir` 로 우리 폴더를 알려줘야 한다.
      **두 경로 다 콜론을 이스케이프한다**(한쪽만 하면 필터 파싱이 통째로 실패한다).
    """
    n, a, b = CFG["narration"], CFG["audio"], L["video_box"]
    # ★★나레이션이 나오는 동안 **원음을 죽인다.** 안 그러면 배우 말과 겹쳐 둘 다
    #   안 들린다. 앞뒤로 조금 더 죽여야 말꼬리가 안 튄다.
    pad = n.get("duck_pad_sec", 0.15)
    duck = ""
    for at, wav in narrs:
        d = probe_dur(wav)
        duck += (f",volume={10 ** (n.get('duck_db', -30) / 20):.4f}"
                 f":enable='between(t,{max(0, at - pad):.2f},{at + d + pad:.2f})'")
    fontsdir = CFG["assets"]["fonts_dir"].replace("\\", "/").replace(":", "\\:")
    ass_p = ass.replace("\\", "/").replace(":", "\\:")

    ins = ["-loop", "1", "-i", frame, "-i", cut]
    amix = [f"[1:a]volume=1.0{duck}[a0]"]
    labels = ["[a0]"]
    for k, (at, wav) in enumerate(narrs):
        ins += ["-i", wav]
        amix.append(f"[{2+k}:a]adelay={int(at*1000)}|{int(at*1000)},"
                    f"volume={10 ** (n['gain_db'] / 20):.3f}[n{k}]")
        labels.append(f"[n{k}]")
    base = 2 + len(narrs)
    for k, (at, path) in enumerate(sfx_at):
        ins += ["-i", path]
        # ★0.7 → 0.25(-12dB) (2026-09-03 «배속처럼» 사건 — 절정 효과음이 대사 위에 크게
        #   깔려 말이 몰아치게 들렸다). 굽기는 전사 전이라 말 틈을 몰라 볼륨으로 안전하게;
        #   말 틈 스냅 정밀 배치는 프리미어판(준비)이 담당한다.
        amix.append(f"[{base+k}:a]adelay={int(at*1000)}|{int(at*1000)},volume=0.25[s{k}]")
        labels.append(f"[s{k}]")

    # ★댓글 카드 (2026-09-07 자체 검수 실측 — Deep09·10 완성본에 하단 댓글이 없었다.
    #   PNG 카드 방식이 준비(프리미어 템플릿)에만 구현되고 굽기 합성엔 빠져 있었다 —
    #   경로 갈라짐 클래스): 준비와 같은 자리·슬롯 회전으로 시간 창 오버레이.
    base2 = 2 + len(narrs) + len(sfx_at)
    vch, cur = "", "o"
    for j, (cp, a0, a1, x, y) in enumerate(cmts):
        ins += ["-loop", "1", "-i", cp]
        nxt = f"oc{j}"
        vch += (f"[{cur}][{base2 + j}:v]overlay={x}:{y}"
                f":enable='between(t,{a0:.2f},{a1:.2f})'[{nxt}];")
        cur = nxt
    fc = (f"[0:v][1:v]overlay=0:{b['y0']}:shortest=1[o];" + vch
          + f"[{cur}]ass='{ass_p}':fontsdir='{fontsdir}'[v];"
          + ";".join(amix)
          + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0[am];"
          + f"[am]loudnorm=I={a['target_lufs']}:TP={a['true_peak_db']}:LRA={a['lra']}[ao]")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error"] + ins
        + ["-filter_complex", fc, "-map", "[v]", "-map", "[ao]",
           "-c:v", "libx264", "-preset", CFG["ffmpeg"]["preset"],
           "-crf", str(CFG["ffmpeg"]["crf"]), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", CFG["ffmpeg"]["audio_bitrate"],
           "-shortest", "-y", dst])
    return dst


def out_name(proj):
    if proj.get("out_name"):
        return proj["out_name"]
    o = CFG["output"]
    day = datetime.now().strftime(o.get("date_format", "%y%m%d"))
    t = proj.get("title") or proj.get("slug", "out")
    if isinstance(t, list):                              # ★제목은 2줄 배열이다
        t = "".join(t)
    for ch in ' \t:*?"<>|.,!~/\\':
        t = t.replace(ch, "")
    return f"{day}{t[:o.get('title_max', 24)]}.mp4"


def report_cuts(proj, work, src):
    """★원본의 어디를 잘랐는지와 Phase 배치를 남긴다. 굽고 나면 확인할 길이 없다."""
    def mmss(s):
        return f"{int(s)//60}:{s - (int(s)//60)*60:04.1f}"

    segs = [x for x in proj["segments"] if x.get("keep", True)]   # ★keep 필터(2026-09-03 Deep04: 뺀 조각이 구워져 3.7초 어긋남 — 검사기와 같은 기준)
    total = sum(s["t1"] - s["t0"] for s in segs)
    sd = probe_dur(src) if os.path.exists(src) else 0
    names = {p["no"]: p["name"] for p in CFG["edit"]["phases"]}
    print(f"\n── 원본의 어디를 잘랐나"
          + (f" (원본 {mmss(sd)} 중 {total:.1f}초 · {total/sd*100:.0f}%)" if sd else ""))
    at = 0.0
    for i, s in enumerate(segs):
        ph = s.get("phase", 0)
        print(f"  P{ph} {names.get(ph,'?'):<10} 완성본 {mmss(at)}  원본"
              f" {mmss(s['t0'])}-{mmss(s['t1'])} ({s['t1']-s['t0']:4.1f}초)"
              f"  punch {s.get('punch','-'):>2}  {(s.get('what') or '')[:26]}")
        at += s["t1"] - s["t0"]
    order = [s["t0"] for s in segs]
    back = sum(1 for i in range(1, len(order)) if order[i] < order[i - 1])
    print(f"  ★시간을 거스른 자리 {back}곳 — 이 채널은 훅을 위해 일부러 그렇게 한다"
          if back else "  시간 연결: 앞에서 뒤로만 간다")


def run_build(proj, path):
    slug = proj["slug"]
    work = os.path.join(HERE, CFG["paths"]["work"], slug)
    out = os.path.join(HERE, CFG["paths"]["out"])
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)

    src = os.path.join(HERE, CFG["paths"]["work"], f"{proj['source']['id']}.mp4")
    if not os.path.exists(src):
        print(f"원본이 없다: {src}\n  먼저 python -m s2pipe.plan <url>")
        return 1

    segs = [x for x in proj["segments"] if x.get("keep", True)]   # ★keep 필터(2026-09-03 Deep04: 뺀 조각이 구워져 3.7초 어긋남 — 검사기와 같은 기준)
    total = sum(s["t1"] - s["t0"] for s in segs)
    fps = proj["source"].get("fps") or 30.0
    print(f"구간 {len(segs)}개 · {total:.1f}초 · {fps:.3f}fps", flush=True)

    print("1/5 구간 자르고 붙이기", flush=True)
    cut = cut_and_join(src, segs, os.path.join(work, "cut.mp4"), work, fps)
    # ★검은 꼬리 절단이 마지막 조각 t1 을 고쳤으면 계획(proj)에도 되쓴다 (2026-09-07
    #   Deep09 실측: -6.7s 절단이 파일에 안 남아 «완성본 ≠ 계획» 게이트에 걸렸고,
    #   자막·나레 총길이도 절단 전 값으로 구워졌다). 계획 = 실물, 근원은 하나다.
    새총 = sum(s["t1"] - s["t0"] for s in segs)
    if abs(새총 - total) > 0.01:
        print(f"    절단 반영 — 총길이 {total:.1f}s → {새총:.1f}s (계획 저장)", flush=True)
        total = 새총
        json.dump(proj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("2/5 층 그리기", flush=True)
    ov = draw_frame(proj, os.path.join(work, "frame.png"))
    # ★나레이션을 먼저 굽는다 — 자막이 **실제 음성 길이**를 그대로 써야 어긋나지 않는다
    print("3/5 나레이션 (★요금)", flush=True)
    narrs = narrate(proj, work, total)
    print("4/5 자막", flush=True)
    ass = write_ass(proj, os.path.join(work, "sub.ass"), total, narrs)

    sfx_at = []
    if CFG["sfx"].get("enabled"):
        at = 0.0
        for s in segs:
            if s.get("phase") == 4:                      # Climax — 크래시 줌 자리
                p = pick_sfx(CFG["sfx"]["map"].get("punch", ""))
                if p:
                    sfx_at.append((round(at, 3), p))
            at += s["t1"] - s["t0"]

    # 댓글 카드 — 준비의 폴백(앞 12장)과 같은 선택·자리·슬롯 (2026-09-07 자체 검수:
    # 완성본에만 댓글이 빠져 있었다)
    cmts = []
    try:
        import glob as _g
        from PIL import Image as _I
        카드들 = sorted(_g.glob(os.path.join(HERE, CFG["paths"]["work"], f"{slug}_댓글",
                                             "**", "*.png"), recursive=True))[:12]
        if 카드들:
            Lb = L["video_box"]
            zone0, zone1 = Lb["y1"] + 8, L["credit"]["y0"] - 10
            each = total / len(카드들)
            for i2, cp in enumerate(카드들):
                im = _I.open(cp).convert("RGB")
                w2, h2 = 1080, int(im.height * 1080 / im.width)
                if h2 > zone1 - zone0:
                    w2, h2 = int(im.width * (zone1 - zone0) / im.height), zone1 - zone0
                p2 = os.path.join(work, f"_cmt{i2:02d}.png")
                im.resize((w2, h2)).save(p2)
                cmts.append((p2, i2 * each, (i2 + 1) * each, (1080 - w2) // 2, zone0))
            print(f"    댓글 카드 {len(카드들)}장 → 하단 슬롯 {each:.1f}s씩", flush=True)
    except Exception as e:
        print("    ★댓글 카드 합성 준비 실패:", str(e)[:80])

    print("5/5 합성·렌더", flush=True)
    dst = compose(cut, ov, ass, narrs, sfx_at, os.path.join(out, out_name(proj)), cmts)
    print(f"\n완성: {dst}  ({os.path.getsize(dst)/1024/1024:.1f} MB)")
    report_cuts(proj, work, src)
    return 0

# ★`run` 이라는 이름을 다시 쓰지 마라 — 위의 `run(argv)`(ffmpeg 실행기)를 덮어
#   `capture` 인자에서 죽는다. make.py 는 `run_build` 를 부른다.
