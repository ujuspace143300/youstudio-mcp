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
    # ★격자 경계값으로 (2026-09-28 싱글51 1프레임 튐 클래스) — hi 는 «ffmpeg 이 -ss hi(0.01초 반올림)로 준 프레임이 카드»
    #   라는 뜻이다. 그 프레임 번호의 경계값을 돌려야 «가장 가까운 프레임» 규칙(프레임격자.번호)으로 읽어도 카드 첫
    #   프레임 바로 앞에서 끝난다(133.805 를 그대로 두면 가장 가까운 프레임이 카드 앞 한 장이라 내용 한 장을 잃는다).
    from . import 프레임격자 as _G
    _g = _G.얻기(src)
    return _g.경계값(_g.첫프레임(float(f"{max(hi, 0):.2f}")))


def 조각틀(src, s, 호환=False, 앞이어짐=False, 뒤이어짐=False):
    """조각 하나의 «프레임 창» — 굽기(mp4)·준비(프리미어)·관문이 모두 이 값을 쓴다 (2026-09-28 싱글51·47 1프레임 튐).

    돌려주는 값 {"모드", "f0": ffmpeg 이 처음 주는 프레임 번호, "앞멈춤": 첫 실제 프레임을 앞에 더 보여 줄 수,
                 "M": 원본에서 쓰는 실제 프레임 수(f0+앞멈춤 부터), "뒤멈춤": 끝 실제 프레임을 더 보여 줄 수,
                 "N": 총 프레임 수(앞멈춤 + M + 뒤멈춤), "ss": ffmpeg 입력 -ss, "a0": 소리 시작(원본 초), "dur": 조각 길이(초)}
      새  : 경계 = 프레임 격자. f0 = 번호(t0) · N = M = 번호(t1) − f0 — 시각 차 × fps 를 반올림하지 않는다.
            소리는 p_f0 부터(영상 첫 프레임과 같은 순간 — 프리미어 in 점과 같다). 자투리는 cut_and_join 이 경계를
            전환 프레임으로 옮겨 없앤다.
      호환: ④ 가 옛 굽기 시간축으로 자막을 맞춘 편(옛 코드 ② 뒤 새 코드 ⑥). 조각 길이·소리 시작을 옛 값 그대로 둔다
            (N = round((t1−t0)·fps), 소리 t0 부터) — 그래야 자막이 안 밀린다. 영상만 고른다: 가장 가까운 프레임에서
            시작하고(가장 가까운 프레임이 앞 샷 마지막 장이면 옛 굽기처럼 다음 장), 점프 컷 머리 1~2장이 앞 샷이면 그
            자리를 새 샷 첫 장으로 채우고(앞멈춤), 끝 1~2장·t1 너머가 다음 샷이면 끝 장으로 채운다(뒤멈춤) — 1~2프레임
            멈춤은 점프 컷에 가려 안 보이고, 다음·앞 샷 번쩍임은 보인다. 옛 코드는 여기서 다른 샷 장을 넣었다.
    """
    from . import 프레임격자 as G
    g = G.얻기(src)
    t0, t1 = float(s["t0"]), float(s["t1"])
    k0, k1 = g.번호(t0), g.번호(t1)
    if not 호환:
        N = max(1, k1 - k0)
        return {"모드": "새", "f0": k0, "앞멈춤": 0, "M": N, "뒤멈춤": 0, "N": N,
                "ss": g.경계값(k0), "a0": g.시작(k0), "dur": g.길이(k0, k0 + N)}
    N = max(1, int(round((t1 - t0) * g.fps)))
    f0 = k0
    if g.첫프레임(t0) == k0 + 1 and G.전환인가(src, g, k0 + 1):
        f0 = k0 + 1                   # 가장 가까운 프레임이 앞 샷 마지막 장 — 옛 굽기처럼 전환 프레임에서 시작
    A = 0
    if not 앞이어짐:
        c = [x for x in G.전환들(src, g, f0, (1, 2)) if x - f0 < N - 2]
        if c:
            A = max(c) - f0            # 머리 A 장이 앞 샷 — 새 샷 첫 장으로 채운다
    M = N - A
    끝 = f0 + N                        # 실제 프레임 [f0+A, 끝)
    if not 뒤이어짐:
        살필 = sorted(set(range(max(f0 + A + 1, 끝 - 2), 끝)) | set(range(max(f0 + A + 1, k1), 끝)))
        전 = [x for x in G.전환들(src, g, 끝, tuple(x - 끝 for x in 살필))] if 살필 else []
        if 전:
            M = max(1, min(전) - (f0 + A))
    return {"모드": "호환", "f0": f0, "앞멈춤": A, "M": M, "뒤멈춤": N - A - M, "N": N,
            "ss": min(t0, g.경계값(f0)), "a0": t0, "dur": N / g.fps}


def _틀기록(틀, 머리):
    """beats.json 조각 칸에 남길 프레임 창 — 준비(프리미어 in 점)·튐 관문·재기가 같은 값을 읽는다."""
    return {"f0": 틀["f0"], "앞멈춤": 틀["앞멈춤"], "M": 틀["M"], "뒤멈춤": 틀["뒤멈춤"], "N": 틀["N"],
            "a0": round(float(틀["a0"]), 6), "머리": 머리}


def _틀굽기(src, 틀, 영상, p, 겹=False):
    """조각 하나를 «프레임 창» 그대로 굽는다 — 영상 [f0, f0+M) (+끝 멈춤) · 소리 a0 부터 dur. 네 갈래(비트·한 장 구도·
    원문화면·프레임-인-프레임)가 모두 이 길을 지난다(2026-09-28 — 예전엔 갈래마다 -ss/-to/-t 와 round 프레임 수를
    따로 써서 한 갈래만 고쳐도 나머지가 샜다).
      영상 = "[0:v]…[vx]" 꼴 필터(첫 프레임 = f0). 겹=True 면 이미 filter_complex 조각이다."""
    A, M, H, N = 틀["앞멈춤"], 틀["M"], 틀["뒤멈춤"], 틀["N"]
    if A and "[vx]" in 영상 and not 겹:
        # 한 갈래 필터 — ffmpeg 첫 프레임은 f0 라 앞 A 장(앞 샷)을 먼저 버린다(비트 갈래는 비트 창이 이미 f0+A 부터다)
        영상 = 영상.replace("[0:v]", f"[0:v]trim=start_frame={A},setpts=PTS-STARTPTS,", 1)
    끝 = (f"[vx]trim=end_frame={M}" + (f",tpad=start={A}:start_mode=clone" if A else "")
          + (f",tpad=stop={H}:stop_mode=clone" if H else "") + ",setpts=PTS-STARTPTS[vo]")
    소리 = (f"[0:a]atrim=start={max(0.0, 틀['a0'] - 틀['ss']):.6f}:duration={틀['dur']:.6f},"
            f"asetpts=PTS-STARTPTS[ao]")
    fc = f"{영상};{끝};{소리}"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", repr(float(틀["ss"])),
         "-t", f"{max(0.0, 틀['a0'] - 틀['ss']) + 틀['dur'] + 0.5:.4f}", "-i", src,
         "-filter_complex", fc, "-map", "[vo]", "-map", "[ao]", "-t", f"{틀['dur']:.6f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CFG["ffmpeg"]["crf"]),
         "-c:a", "pcm_s16le", "-avoid_negative_ts", "make_zero", "-y", p])
    # ★게이트: 구운 조각의 영상 프레임 수 = N (소리와 프레임 일치 · 2026-09-09 립싱크 실측에서 비트 조각에만 있던 것을 모든 갈래로)
    _nf = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", p],
                         capture_output=True, text=True).stdout.strip()
    assert _nf and int(_nf) == N, f"조각 프레임 {_nf} ≠ 틀 {N} — 영상·소리 프레임 어긋남(립싱크) · {p}"
    return p


def cut_and_join(src, segs, dst, work, fps, 호환=False):
    """구간을 잘라 **여백 없이** 붙인다. crop 은 비트마다 조금씩 움직인다.

    ★경계는 원본 프레임 번호다(s2pipe/프레임격자.py · 2026-09-28 싱글51·47·48). 조각 창은 조각틀() 한 곳이 정하고
      네 갈래 굽기·비트 구도·관문·준비(프리미어)가 같은 값을 쓴다. 호환=True 는 옛 코드 시간축으로 자막을 맞춘 편 —
      조각 길이·소리 시작을 옛 값 그대로 두고 영상만 다음 샷이 안 섞이게 고른다(run_build 가 정한다)."""
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

    # ★조각 경계 = 프레임 격자 (2026-09-28 «화면 전환 자리 1프레임 튐» 클래스 수리)
    #   새 굽기는 경계를 격자 경계값으로 맞추고(계획에 되쓴다 — run_build), 원본에서 이어지지 않는 이음매(점프 컷)는
    #   조각 첫 1~2프레임·끝 1~2프레임에 다른 샷이 끼지 않게 전환 프레임으로 붙인다(자투리 = 1~2프레임 번쩍임 —
    #   싱글126 실측 조각 8 끝 2프레임). 소리 이음매가 최대 2프레임(83ms) 옮겨지므로 ④ 이음매 관문이 다시 본다.
    #   호환 편은 경계·길이를 건드리지 않는다(자막 시간축 보존) — 자투리는 아래 튐 관문이 잡아 알린다.
    from . import 프레임격자 as G
    g = G.얻기(src)
    붙임 = []
    # ★원본에서 이어진 이음매(앞 조각 끝 = 이 조각 시작)가 화면 전환에서 2장 안이면 이음매를 전환으로 옮긴다 — 완성본
    #   내용·소리는 그대로이고(원본에서 이어져 있다) 조각 구분만 바뀐다. 안 옮기면 새 샷 첫 1~2장이 앞 조각 구도로 나가거나
    #   (싱글51 128.545 전환 · 이음매 128.58), 전환 1장 뒤에 다음 조각 구도가 한 번 더 바뀐다. 호환 편은 정확히 프레임
    #   간격의 정수배로 옮겨 두 조각 프레임 수의 합과 소리 이음을 그대로 둔다(자막 시간축 보존).
    for i in range(len(segs) - 1):
        a_, b_ = segs[i], segs[i + 1]
        k = g.번호(a_["t1"])
        if g.번호(b_["t0"]) != k or abs(a_["t1"] - b_["t0"]) > g.T / 2:
            continue
        c = G.전환들(src, g, k, (-2, -1, 1, 2))
        if not c or G.전환인가(src, g, k):
            continue
        c = min(c, key=lambda x: abs(x - k))
        if not (g.번호(a_["t0"]) + 2 < c < g.번호(b_["t1"]) - 2):
            continue
        if 호환:
            a_["t1"] = b_["t0"] = round(a_["t1"] + (c - k) / g.fps, 6)
        else:
            a_["t1"] = b_["t0"] = g.경계값(c)
        붙임.append(f"이어진 이음매 {i}/{i + 1} {c - k:+d}프레임")
    if not 호환:
        for i, s in enumerate(segs):
            k0, k1 = g.번호(s["t0"]), g.번호(s["t1"])
            앞이어짐 = i > 0 and g.번호(segs[i - 1]["t1"]) == k0
            뒤이어짐 = i + 1 < len(segs) and g.번호(segs[i + 1]["t0"]) == k1
            최소 = int(round(0.5 * g.fps))
            if not 앞이어짐:
                c = G.전환들(src, g, k0, (1, 2))
                if c and k1 - max(c) >= 최소:
                    붙임.append(f"조각 {i} 시작 +{max(c) - k0}프레임")
                    k0 = max(c)
            if not 뒤이어짐:
                c = G.전환들(src, g, k1, (-2, -1))
                if c and min(c) - k0 >= 최소:
                    붙임.append(f"조각 {i} 끝 −{k1 - min(c)}프레임")
                    k1 = min(c)
            s["t0"], s["t1"] = g.경계값(k0), g.경계값(k1)
    if 붙임:
        print(f"    조각 경계를 원본 화면 전환 프레임에 붙임 {len(붙임)}곳 — " + " · ".join(붙임), flush=True)
    이음 = [i > 0 and g.번호(segs[i - 1]["t1"]) == g.번호(segs[i]["t0"]) for i in range(len(segs))]
    틀들 = [조각틀(src, s, 호환, 앞이어짐=이음[i], 뒤이어짐=i + 1 < len(segs) and 이음[i + 1])
           for i, s in enumerate(segs)]
    print(f"    조각 창 {'호환(옛 자막 시간축 보존)' if 호환 else '격자'} — 프레임 {sum(t['N'] for t in 틀들)}장"
          + (f" · 멈춤 앞 {sum(t['앞멈춤'] for t in 틀들)}장·끝 {sum(t['뒤멈춤'] for t in 틀들)}장(다른 샷 번쩍임 대신)"
             if any(t['앞멈춤'] or t['뒤멈춤'] for t in 틀들) else ""),
          flush=True)

    parts, log = [], {"segments": [], "beats": [], "frames": [],
                      "격자": {"판": 1, "모드": "호환" if 호환 else "새", "fps": g.fps}}

    def bake_beats(틀, plan):
        """비트마다 다른 crop 을 «프레임 번호» 로 이어 붙인다 — 비트 [f0, f1) 은 조각 첫 프레임에서 센 trim start_frame/
        end_frame 이다(2026-09-28 — 예전 trim=start=초 .3f 는 경계가 프레임 사이에 걸리면 한 장 어긋날 수 있었다)."""
        legs, tags = [], []
        lo_, hi_ = 틀["앞멈춤"], 틀["앞멈춤"] + 틀["M"]         # 실제 프레임 = ffmpeg 첫 프레임(f0)에서 센 [lo_, hi_)
        이음 = lo_
        for j, (bt0, bt1, vf, info) in enumerate(plan):
            s0 = max(lo_, min(hi_, info["f0"] - 틀["f0"]))
            s1 = max(lo_, min(hi_, info["f1"] - 틀["f0"]))
            if j == len(plan) - 1:
                s1 = hi_
            if s1 <= s0:
                continue
            # ★비트는 빈틈·겹침 없이 이어져야 한다 — 계획이 장을 빼먹거나 두 번 쓰면 ffmpeg 전에 멈춘다(2026-09-29)
            assert s0 == 이음, f"비트 창이 안 이어진다 — 비트 {j} 시작 {s0} ≠ 앞 비트 끝 {이음} (framing.plan_beats 경계)"
            이음 = s1
            legs.append(f"[0:v]trim=start_frame={s0}:end_frame={s1},setpts=PTS-STARTPTS,{vf},setsar=1[v{j}]")
            tags.append(f"[v{j}]")
        assert 이음 == hi_, f"비트 창이 조각 끝 {hi_} 에 못 미친다({이음})"
        # ★비트 영상을 소리와 «정확히 같은 프레임 수»로 못 박는다 (2026-09-09 립싱크 실측: 비트 concat 이 마지막 비트에서
        #   1프레임 넘쳐 영상이 소리보다 1프레임 길었다) — 이제 _틀굽기 가 trim=end_frame=M(+끝 멈춤)·프레임 수 관문을 건다.
        #   ★PCM + 프레임 정확 길이(2026-09-03 «순간 배속» 사건) — AAC 꼬리 패딩이 조각마다 +40~60ms 붙어 경계에서 말이
        #   겹쳐 들렸다(46ms 실측). AAC 인코딩은 최종 합칠 때 한 번만.
        # ★concat 뒤 시각을 «장 번호 / fps» 로 다시 매긴다 (2026-09-29 점심이네20 «조각 프레임 309 ≠ 틀 311»).
        #   1장짜리 비트는 concat 이 길이를 0 으로 쳐서 다음 비트 첫 장과 시각이 겹치고, 겹친 장은 뒤 trim·인코더에서 버려진다.
        #   실측(20편 원본 · 굽기와 같은 필터): 비트 [10,1,1,1,1,1,10] → 21장(기대 25) · [5, 1×20, 5] → 11장(기대 30) ·
        #   1장 비트 하나만 있을 때와 2장 비트는 멀쩡했다. 다시 매기면 넷 다 기대 장 수 그대로 나온다.
        영상 = (";".join(legs) + f";{''.join(tags)}concat=n={len(tags)}:v=1:a=0,"
               f"setpts=N/({g.fps:.9f}*TB)[vx]")
        parts.append(_틀굽기(src, 틀, 영상, os.path.join(work, f"seg{len(parts):03d}.mov"), 겹=True))

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
        틀 = 틀들[i]
        # 조각 머리(이음매) — 원본에서 이어지지 않으면 점프 컷(새샷), 이어지면 그 자리가 화면 전환인지(전환) 아닌지(이어짐)
        #   (2026-09-28 싱글48 — 예전엔 모든 조각이 앞 조각 마지막 구도를 끌고 와 점프 컷 뒤 얼굴이 1.2초 가장자리에 걸렸다)
        실0 = 틀["f0"] + 틀["앞멈춤"]                    # 실제 첫 프레임
        앞 = 틀들[i - 1] if i else None
        이어짐 = bool(앞) and 앞["f0"] + 앞["앞멈춤"] + 앞["M"] == 실0 and not 앞["뒤멈춤"] and not 틀["앞멈춤"]
        머리 = ("전환" if G.전환인가(src, g, 실0) else "이어짐") if 이어짐 else "새샷"
        박들 = [_안쪽경계(s["t0"] + (s["t1"] - s["t0"]) * f) for f in (0.25, 0.5, 0.75)]
        if all(박들) and max(abs(박들[0][k] - 박들[j][k]) for j in (1, 2) for k in range(4)) <= 8:
            x, y, w, h = 박들[1]
            vf = (f"crop={w}:{h}:{x}:{y},scale=-2:908,"
                  f"crop=1080:908:(iw-1080)/2:0,setsar=1")
            p = os.path.join(work, f"seg{len(parts):03d}.mov")
            parts.append(_틀굽기(src, 틀, f"[0:v]{vf}[vx]", p))
            prev = None
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0, **_틀기록(틀, 머리)})
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
            parts.append(_틀굽기(src, 틀, vf + "[vx]", p))
            prev = None
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0, **_틀기록(틀, 머리)})
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
        plan = framing.plan_beats(src, s, i, W, H, uh, b, work, cuts, prev,
                                  머리=머리, 틀={"k0": 실0, "k1": 실0 + 틀["M"]})
        if not plan:
            vf, info = framing.plan_frame(src, s, i, W, H, uh, b, work, prev=None if 머리 == "새샷" else prev)
            p = os.path.join(work, f"seg{len(parts):03d}.mov")
            parts.append(_틀굽기(src, 틀, f"[0:v]{vf}[vx]", p))
            prev = info["crop"]
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0, **_틀기록(틀, 머리)})
            log["frames"].append({"seg": i, "t0": s["t0"], "t1": s["t1"], "kind": "한장구도",
                                  "crop": list(info["crop"][:4])})
            continue
        bake_beats(틀, plan)
        prev = plan[-1][3]["crop"]
        log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                "phase": s.get("phase"), "part": parts[-1],
                                "beats": len(plan), **_틀기록(틀, 머리)})
        for a, e, _vf, info in plan:
            log["beats"].append({"seg": i, "t0": a, "t1": e,
                                 "crop": list(info["crop"]),
                                 "시작crop": list(info.get("시작crop") or info["crop"]),
                                 "f0": info.get("f0"), "f1": info.get("f1"),
                                 "at_cut": bool(info["at_cut"])})
        zs = [x[3]["zoom"] for x in plan]
        nf = sum(1 for x in plan if x[3]["face"])
        # ★영구 게이트 (2026-09-21 Deep87 «입이 잘리는 과확대») — 얼굴을 찾은 비트는 그 얼굴이
        #   crop 안에 있어야 한다. 기존 검사는 «얼굴이 검출되는가» 만 봤다. framing.담기 가
        #   보장하지만, 누가 그 관문을 우회하는 경로를 새로 만들면 여기서 걸린다.
        #   face_in=None 은 얼굴이 쓸 수 있는 자리보다 큰 불가피 비트(원본 초근접) — 찍기만 한다.
        밖 = [(round(x[0], 2), x[3]["crop"]) for x in plan if x[3]["face"] and x[3].get("face_in") is False]
        assert not 밖, f"조각 {i}: 얼굴이 crop 밖으로 나간 비트 {밖[:3]} — framing.담기 를 우회했다"
        # ★영구 게이트 (2026-09-29 점심이네20 가스불 — 2장 간격 번쩍임을 전환으로 받아 1~2장 비트 18개가 이어졌고 구도가
        #   2장마다 옮겨졌다): 2장 이하 비트가 셋 넘게 잇달면 번쩍임·깜빡임을 샷 전환으로 본 것이다(진짜 컷 셋이 12분의 1초
        #   간격으로 잇달 일은 없다). 프레임격자.번쩍임 을 우회한 길이 생기면 여기서 먼저 멈춘다.
        _짧, _런 = 0, []
        for x in plan:
            _짧 = _짧 + 1 if x[3]["f1"] - x[3]["f0"] <= 2 else 0
            if _짧 >= 3:
                _런.append(round(x[0], 2))
        assert not _런, (f"조각 {i}: 2장 이하 비트가 셋 넘게 잇달았다(원본 {_런[:4]}초) — 번쩍임을 화면 전환으로 봤다"
                         " (s2pipe/프레임격자.번쩍임 · framing.plan_beats 전환들)")
        # ★영구 게이트 (2026-09-29 점심이네 «가짜 얼굴» — 36곳 가림 우회): 위 관문은 «계획이 고른 얼굴» 만 봐서, 계획이
        #   벽 무늬·흐린 뒤통수를 얼굴로 고르면 통과했다. 검출기가 확신하는 얼굴(점수 0.8↑)이 화면에 있는데 crop 에
        #   0.5초 넘게 하나도 안 들면 멈춘다 — 사람이 완성본 프레임을 보기 전에.
        _얼 = framing.얼굴관문(src, plan, i, work, uh)
        if _얼:
            raise AssertionError(
                f"조각 {i}: 확실한 얼굴이 화면에 있는데 crop 에 안 든 구간 {len(_얼)}곳 — "
                + "; ".join(f"원본 {x['t0']}~{x['t1']}초 crop {x['crop']} 얼굴 {x['얼굴'][:3]}" for x in _얼[:3])
                + "\n  수리: framing.얼굴고르기(가짜·흐린 얼굴 거르기) · plan_beats(주인공 고르기·빈 구도 담기)를 먼저 본다."
                  " 원본이 정말 그 얼굴을 비켜 찍은 샷이면(말하는 사람이 따로 있음) 조각 «가림» 이 아니라 원인을 보고로 남긴다.")
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
    # ★최종 관문 — 경계 1프레임 튐 (2026-09-28 싱글51 72.16초·28.16초 · 싱글47 번쩍임 3곳 · 납품 22편 표본 편마다 4~40곳).
    #   구운 cut.mp4 에서 조각·비트 경계마다 «화면이 두 걸음에 바뀌는가»(겹봉우리)와, 계획 경계가 원본 화면 전환 프레임과
    #   맞는가(자투리·구도 어긋남)를 잰다. ⑦ 컷별 원음 대조는 소리만 봐서 1프레임(42ms) 영상 튐을 원리상 못 잡았고,
    #   위 «조각 프레임 수 = N» 관문은 장 수만 봤지 어느 장인지를 안 봤다. 규칙·지표는 s2pipe/튐관문.py 한 곳.
    from . import 튐관문 as _튐
    _걸, _요 = _튐.재기(work, src, 로그=log)
    if _걸:
        raise AssertionError(f"경계 1프레임 튐 {len(_걸)}곳 — {_요}\n" + _튐.지침(_걸, 호환))
    print(f"    [OK] 경계 튐 관문 — {_요}", flush=True)
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


# ★머리 로고 한 장 — 자리·크기·흰 배경 처리를 여기 한 곳에 둔다(2026-09-29 사장님 결정: 점심이네 64편 = «누룽지독
#   템플릿»). 예전엔 이 계산이 준비_prproj_sk(프리미어)에만 있어서, Deep 은 프리미어 머리만 누룽지독 로고였고
#   납품 mp4 머리는 config channel.* 임시값 «@sketchsample 스케치샘플» 이 찍혀 나갔다(Deep90 mp4 3초 프레임 실측).
#   mp4(draw_frame · config channel.logo_image) 와 프리미어(준비 · work/<슬러그>_로고.png) 가 이 함수 하나를 부른다.
로고_자리 = (0.19928400218486786, 0.069892480969429016)   # 최하연님 작업 Deep prproj 실측 — 로고 중심 (x/폭, y/높이)
로고_비율 = 0.16451612472534                              # 같은 실측 — 프리미어 비율 16.45%(시퀀스 1080 기준)


def 배경맞춤(img, bg):
    """카드·로고의 순백 배경을 껍데기 배경색으로 — 흰 카드 경계가 티 나지 않게 (2026-09-01 사장님).
    (준비_prproj_sk 에서 옮겨 왔다 2026-09-29 — mp4 머리 로고도 같은 처리를 써야 해서. 계산은 그대로)"""
    import numpy as np
    a = np.asarray(img.convert("RGBA")).copy()
    m = (a[:, :, 0] >= 250) & (a[:, :, 1] >= 250) & (a[:, :, 2] >= 250)
    a[m, 0], a[m, 1], a[m, 2] = bg[0], bg[1], bg[2]
    return Image.fromarray(a, "RGBA")


def 로고얹기(im, logo_path, bg):
    """머리 로고 그림을 프리미어 실측 자리·크기로 im 에 얹는다. 순백 배경은 bg(껍데기 배경색)로 바꾼다.

    자리·비율은 config channel.logo_pos · channel.logo_scale 이 있으면 그 값, 없으면 Deep 실측(로고_자리·로고_비율).
    im 이 RGBA(프리미어 껍데기)면 alpha_composite, RGB(mp4 frame)면 알파 마스크로 붙인다 — 불투명 로고면 같은 화소.
    돌려주는 값: (왼쪽 위 x, y), (폭, 높이) — 검사용.
    """
    ch = CFG.get("channel") or {}
    cxr, cyr = ch.get("logo_pos") or 로고_자리
    s_ = float(ch.get("logo_scale") or 로고_비율) * V["w"] / 1080
    logo = 배경맞춤(Image.open(logo_path), bg)
    w_, h_ = int(logo.width * s_), int(logo.height * s_)
    logo = logo.resize((w_, h_))
    cx, cy_ = cxr * V["w"], cyr * V["h"]
    xy = (int(cx - w_ / 2), int(cy_ - h_ / 2))
    if im.mode == "RGBA":
        im.alpha_composite(logo, xy)
    else:
        im.paste(logo, xy, logo)
    return xy, (w_, h_)


def draw_frame(proj, dst):
    """움직이지 않는 층을 한 장으로 — 헤더·제목·출처. 영상과 자막은 ffmpeg 가 얹는다.

    ★껍데기는 sketch 에서 가져왔다. 좌표·글꼴은 「먹기전에」 10편 실측이라 손대지 않는다.
    """
    im = Image.new("RGB", (V["w"], V["h"]), "#" + L["bg"])
    d = ImageDraw.Draw(im)

    h = L["header"]
    ch = CFG["channel"]
    if ch.get("logo_image"):
        # ★머리 = 로고 그림 한 장(누룽지독 템플릿 2026-09-29) — 아이콘·핸들·채널명 글자를 그리지 않는다.
        #   프리미어 껍데기(준비_prproj_sk)와 같은 함수·같은 자리. 그림이 없으면 글자 머리로 떨어지지 말고 멈춘다.
        lp = os.path.join(HERE, ch["logo_image"])
        if not os.path.isfile(lp):
            raise SystemExit(f"channel.logo_image 그림이 없다: {lp} — 머리 로고 없이 굽지 않는다")
        로고얹기(im, lp, tuple(int(L["bg"][i:i + 2], 16) for i in (0, 2, 4)))
    else:
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


def _나레곁창(proj, work, narrs, total):
    """대사 자막을 가를 나레 창 [(시작, 끝)] 과 총길이 — ⑦ 프리미어(준비 → 화자색.대사큐)와 «같은 입력» 을 쓴다:
    나레가 하나면 화자색.나레창(조각 머리 = 굽기 실측 beats.json · 길이 = narrNN.wav 표본 수 · 총길이 = 실측 합).
    나레가 여럿이거나(⑦ 이 멈출 편) 실측이 굽는 자리와 0.1초 넘게 다르면 굽는 자리(narrs)·total 로.
    규격 narration.hide_line_subs 가 꺼져 있으면 창 없음(대사를 가리지 않는다)."""
    if not narrs or not CFG["narration"].get("hide_line_subs", True):
        return [], total
    from . import 화자색 as _HS
    try:
        창 = _HS.나레창(proj, work)
    except Exception:                                    # noqa: BLE001 — beats·wav 를 못 읽으면 굽는 자리로
        창 = None
    if 창 is not None and len(narrs) == 1 and abs(창[0] - narrs[0][0]) < 0.1:
        return [(창[0], 창[1])], 창[2]
    out = []
    for a, wav in narrs:
        try:
            d = probe_dur(wav)
        except Exception:                                # noqa: BLE001
            d = 3.0
        out.append((a, a + d))
    return out, total


def write_ass(proj, dst, total, narrs=(), 색표=None):
    """대사와 나레이션을 **색으로 가른다**(지침서 3장).

    색표 = 화자색.굽기색 결과 {(줄 시각, 글): (r,g,b)|None} — 대사 줄마다 화자 색(프리미어 dlg 큐와 같은 판정).
      «글·시각» 으로 짝을 찾고, 짝이 없거나 None(화자1·판정 없음)이면 기본색(main 스타일 흰색) 그대로.

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
    칠함 = [0, 0, 0]                                     # 화자 색 · 기본색(화자1) · 짝 없음(기본색)
    # ★★나레 곁 대사는 프리미어(⑦ 화자색.대사큐)와 «같은 함수·같은 입력» 으로 정한다 (2026-09-28 저녁 싱글287).
    #   예전 굽기는 여기서 끝을 따로 재고, 아래에서 «나레 창 ±0.2초와 조금이라도 겹치면 줄 통째 감춤» 을 해
    #   나레 바로 앞 대사(«숨겨놓으면 웃기겠다» — 말끝 4.97 · 나레 4.99)가 mp4 에서만 사라졌다. 프리미어는 같은 줄을
    #   나레 앞에서 끊어 보여 줬다(두 산출물 불일치 — 납품 편 대부분이 그랬다: 한편_완주_지침 «도구 주의»).
    #   이제 두 곳 다 화자색.나레곁: 겹치면 자르고(나레 전 시작 → 나레 앞에서 끊음 · 나레 중 시작 → 나레 뒤로 밂),
    #   0.3초도 안 남으면 감춘다. 나레가 뜨는 동안 대사 자막이 안 나오는 것(2026-08-19·09-01)은 그대로다.
    from . import 화자색 as _HS
    창들, 총 = _나레곁창(proj, os.path.dirname(dst), narrs, total)
    pad = float(CFG["narration"].get("duck_pad_sec", 0.15))
    보임 = _HS.나레곁(subs, 창들, 총, pad)
    그대로 = _HS.나레곁(subs, [], 총, pad)                # 나레가 없을 때의 구간 — 잘리거나 밀린 줄을 세려고
    감춤 = sum(1 for v in 보임 if v is None)
    잘림 = sum(1 for v, w in zip(보임, 그대로) if v is not None and v != w)
    for i, cur in enumerate(subs):
        if 보임[i] is None:
            continue
        st, end = round(보임[i][0] / _HS.F, 4), round(보임[i][1] / _HS.F, 4)
        txt = (cur.get("text") or "").replace("\n", " ")
        if len(txt) > hi:                                # 넘치면 화면 밖으로 나간다
            txt = txt[:hi - 1] + "…"
        # ★화자 색 (2026-09-28 사장님 — 완성본에도 프리미어와 같은 화자별 색). 색만 바꾼다: 줄·시각·서식은 그대로.
        색 = (색표 or {}).get((round(cur["t"], 3), cur.get("text")))
        if 색표 is not None:
            칠함[0 if 색 else (1 if (round(cur["t"], 3), cur.get("text")) in 색표 else 2)] += 1
        색태그 = "{\\1c&H%02X%02X%02X&}" % (색[2], 색[1], 색[0]) if 색 else ""
        body.append(f"Dialogue: 0,{_ts(st)},{_ts(end)},main,,0,0,0,,{색태그}{팝}{txt}")

    if 색표 is not None:
        print(f"    대사 색 — 화자 색 {칠함[0]}줄 · 기본색(화자1) {칠함[1]}줄 · 짝 없음(기본색) {칠함[2]}줄", flush=True)
    # ★★나레이션이 뜨는 동안 **대사 자막은 안 나온다** — 둘이 겹치면 자막이 2줄로 뭉친다(2026-08-19). 겹치는 줄은
    #   위 화자색.나레곁 이 나레 앞에서 끊거나 나레 뒤로 밀고, 0.3초도 안 남으면 감춘다(프리미어와 같은 줄).
    if 감춤 or 잘림:
        print(f"    나레이션 곁 대사 자막 — 감춤 {감춤}줄 · 나레 앞에서 끊거나 뒤로 밀어 보인 줄 {잘림}줄 (프리미어와 같은 규칙)",
              flush=True)

    # 나레이션 — 실제로 구운 음성과 **같은 문구·같은 길이**로 얹는다
    seg_narr = {round(a, 3): t for _i, a, t in _HS.나레자리(proj)}
    for a, wav in narrs:
        t = seg_narr.get(round(a, 3))
        if not t:
            continue
        try:
            d = probe_dur(wav)
        except Exception:                                # noqa: BLE001
            d = 3.0
        body.append(f"Dialogue: 0,{_ts(a)},{_ts(a + d)},narr,,0,0,0,,"
                    "{\\fscx86\\fscy86\\t(0,120,\\fscx104\\fscy104)\\t(120,182,\\fscx100\\fscy100)}" + t)

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
    from . import 화자색 as _HS
    out = []
    for i, at, text in _HS.나레자리(proj):
        s = proj["segments"][i]
        span = s["t1"] - s["t0"]
        wav = os.path.join(work, f"narr{i:02d}.wav")
        _p, d = tts.synth(text, n, wav, os.path.join(work, "_tts"))
        if d > span:
            print(f"    ★나레 {i} 가 조각보다 길다 ({d:.1f}초 > {span:.1f}초)"
                  f" — 다음 대사와 겹친다", flush=True)
        print(f"    나레 {i}: {d:.2f}초  {text[:30]}", flush=True)
        out.append((at, wav))
    return out


def pick_sfx(tag, key=""):
    """`@꼬리표` 에서 하나를 고른다. 없으면 None — 조용히 넘기지 않고 알린다.
    ★key(편 이름·조각 번호)로 시드를 건다 (2026-09-28 맥1 — 초이 윈도우 이식 대조 실측: 싱글50 을 같은 코드로 두 번 구우니
      영상 프레임은 디코딩 해시까지 같은데 소리만 달랐다. 시드 없는 random.choice 가 «쿵» 16개 중 굽기마다 다른 것을 골랐다.
      재굽기(FROM=4)·다른 컴퓨터에서 같은 편이 다른 소리로 나가 대조가 안 된다). 편마다 다른 소리는 그대로 — 같은 편만 늘 같다."""
    cat = os.path.join(CFG["paths"]["assets"], "catalog.json")
    if not os.path.isfile(cat) or not tag.startswith("@"):
        return None
    d = json.load(open(cat, encoding="utf-8"))
    cands = [s["file"] for s in d.get("sfx", []) if s.get("tag") == tag[1:]]
    if not cands:
        print(f"    ★효과음 {tag} 이 카탈로그에 없다", flush=True)
        return None
    return os.path.join(HERE, CFG["assets"]["sfx_dir"], random.Random(f"{key}|{tag}").choice(sorted(cands)))


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

    # ★정지 그림 입력은 디코더 스레드 1개 (2026-09-28 04시 100편 배치 — 댓글 카드 12장이 입력마다 코어 수만큼
    #   스레드를 띄워 합성 ffmpeg 하나가 418 스레드, 12편 동시에 부하 142·CPU 유휴 0% 로 한 편 합성이 16분 걸렸다).
    # ★배경 그림을 영상과 같은 프레임 속도로 돌린다 (2026-09-28 «시각 양자화» 클래스) — overlay 는 첫 입력(배경)의 시각표로
    #   프레임을 내는데 -loop 1 그림의 기본값은 25fps 라, 23.976 원본이 25fps 로 다시 떠 약 1초마다 한 장이 두 번 나갔다
    #   (싱글51 완성본 1937장/77.48초 · cut.mp4 1856장 실측). 원본 프레임레이트를 그대로 따른다(config video.fps «source»).
    _r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                         "-of", "csv=p=0", cut], capture_output=True, text=True).stdout.strip() or "30/1"
    ins = ["-threads", "1", "-framerate", _r, "-loop", "1", "-i", frame, "-i", cut]
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
        ins += ["-threads", "1", "-loop", "1", "-i", cp]
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
        + ["-filter_complex_threads", "2", "-filter_complex", fc, "-map", "[v]", "-map", "[ao]",
           "-c:v", "libx264", "-threads", "4", "-preset", CFG["ffmpeg"]["preset"],
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


def run_build(proj, path, 화자색켬=False):
    """화자색켬 — ⑥ 재굽기(한편_sk.sh 가 --화자색 을 준다)에서만 판정한다. ② 첫 굽기는 자막이 ④ 싱크 전이라
    판정이 곧 낡는다(agy 한도만 쓴다) — 그래서 끈다."""
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
    # ★호환 판정 (2026-09-28 프레임 격자 수리) — 완성본 재전사(③)·작표(④)가 «옛 코드로 구운» cut.mp4 시간축으로 자막을
    #   맞춘 편은 조각 길이·소리 시작을 옛 값 그대로 굽는다(자막이 안 밀리게). 재전사가 새 격자 굽기 위에서 됐으면
    #   (asr.py 가 «asr_격자» 를 남긴다) 또는 아직 재전사 전이면 격자 굽기.
    호환 = bool(proj.get("asr_words") or proj.get("subs_before_sync")) and not proj.get("asr_격자")
    전경계 = [(s["t0"], s["t1"]) for s in segs]
    cut = cut_and_join(src, segs, os.path.join(work, "cut.mp4"), work, fps, 호환=호환)
    # ★검은 꼬리 절단이 마지막 조각 t1 을 고쳤으면 계획(proj)에도 되쓴다 (2026-09-07
    #   Deep09 실측: -6.7s 절단이 파일에 안 남아 «완성본 ≠ 계획» 게이트에 걸렸고,
    #   자막·나레 총길이도 절단 전 값으로 구워졌다). 계획 = 실물, 근원은 하나다.
    #   ★격자 굽기가 경계를 프레임 격자에 맞췄으면 그것도 되쓴다(2026-09-28) — 작표·이음매 관문·준비가 계획 길이로
    #   완성본 시각을 셈하므로 계획 = 실제 프레임 수여야 한다.
    새총 = sum(s["t1"] - s["t0"] for s in segs)
    바뀐경계 = sum(1 for s, (a, b) in zip(segs, 전경계) if abs(s["t0"] - a) > 1e-6 or abs(s["t1"] - b) > 1e-6)
    if abs(새총 - total) > 0.01 or 바뀐경계:
        print(f"    절단·격자 반영 — 총길이 {total:.2f}s → {새총:.2f}s · 경계 바뀐 조각 {바뀐경계}개 (계획 저장)", flush=True)
        total = 새총
        json.dump(proj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("2/5 층 그리기", flush=True)
    ov = draw_frame(proj, os.path.join(work, "frame.png"))
    # ★나레이션을 먼저 굽는다 — 자막이 **실제 음성 길이**를 그대로 써야 어긋나지 않는다
    print("3/5 나레이션 (★요금)", flush=True)
    narrs = narrate(proj, work, total)
    print("4/5 자막", flush=True)
    # ★화자 판정은 나레 «뒤»·자막 «앞» (2026-09-28 사장님 설계) — 이 시점엔 새 cut.mp4 와 나레 길이가 있어 ⑦ 프리미어와
    #   같은 재료다. 판정은 저장본(_화자판정캐시.json)에 남고 ⑦ 이 같은 키로 읽는다(두 번 묻지 않는다).
    #   agy 가 전부 멈추면(AgyStop) 여기서 멈춘다 — ⑦ 과 같다. 일부 실패는 표결로 계속.
    색표 = None
    if 화자색켬:
        from . import 화자색 as _HS
        색표 = _HS.굽기색(proj, work, float(CFG["narration"].get("duck_pad_sec", 0.15)))
    ass = write_ass(proj, os.path.join(work, "sub.ass"), total, narrs, 색표)

    sfx_at = []
    if CFG["sfx"].get("enabled"):
        at = 0.0
        for k, s in enumerate(segs):
            if s.get("phase") == 4:                      # Climax — 크래시 줌 자리
                p = pick_sfx(CFG["sfx"]["map"].get("punch", ""), f"{proj.get('slug', '')}|{k}")
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
