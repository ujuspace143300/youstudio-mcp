# 구간마다 **어디를 얼마나 확대해 자를지** 정한다.
#
# 레퍼런스 추적 결과(ref/zoom_track.py):
#   - 확대율이 1.1~1.8배로 **컷마다 바뀐다**. 고정이 아니다
#   - crop 위치가 x 187~1160 으로 움직인다 — **중앙 고정이 아니라 인물을 따라간다**
#   - 좌우반전은 없다 (반전 없이 매칭해 일치도 0.97·0.98 이 나왔다)
import os, subprocess
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .cfg import CFG
MODEL = os.path.join(CFG["paths"]["assets"], "models", "yunet.onnx")

# ★OpenCV 5.0 에서 `cv2.CascadeClassifier` 가 **없어졌다**(AttributeError).
#   haar 로 짰다가 조용히 0개만 잡혀서 한참 헤맸다 — DNN 검출기(YuNet)를 쓴다.
#
# ★★OpenCV 는 **비ASCII 경로를 못 읽는다.** imread 도 ONNX 로더도 마찬가지다.
#   작업 폴더가 `클로드` 라 모델을 그대로는 못 연다 — ASCII 경로로 복사해 쓴다.
def _ascii_copy(src):
    if src.isascii() and os.path.exists(src):
        return src
    if not os.path.exists(src):
        return None
    import shutil, tempfile
    dst = os.path.join(tempfile.gettempdir(), "sketch_models", os.path.basename(src))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        # ★다 복사한 뒤 한 번에 바꿔 단다 (2026-09-26 — 여러 편 동시 진행 때 반쯤 복사된 모델을 읽지 않게)
        tmp = f"{dst}.{os.getpid()}.tmp"
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    return dst if dst.isascii() else None


try:
    import cv2
    # ★OpenCV 는 기본으로 코어 수만큼 스레드를 쓴다 — 굽기 6~12편이 동시에 돌면 스레드가 수백 개로 불어
    #   부하 188·CPU 유휴 0% 가 됐다(2026-09-28 07시 100편 배치). 한 프로세스 2개로 묶는다.
    try:
        cv2.setNumThreads(2)
    except Exception:
        pass
    MODEL_PATH = _ascii_copy(MODEL)
    HAS_YN = hasattr(cv2, "FaceDetectorYN") and bool(MODEL_PATH)
except Exception:
    cv2, HAS_YN, MODEL_PATH = None, False, None


def _read_rgb(path):
    """★cv2.imread 는 한글 경로에서 조용히 None 을 준다. PIL 로 읽는다."""
    try:
        return np.asarray(Image.open(path).convert("RGB"))
    except Exception:
        return None


def _faces_yunet(rgb, score=0.45):
    """★임계 0.6 은 너무 보수적이다 — 2인 씬이 많은 소재에서 **비트의 37% 가
    「얼굴 0개」**로 나왔다(실측 2026-08-19). 0.45 로 낮추면 12%, 0.3 이면 6% 다.
    0.3 은 오탐이 늘어 배경 무늬까지 잡으므로 **0.45 를 기본**으로 한다."""
    global MODEL_PATH
    # ★임시 폴더 모델이 도중에 지워지면 다시 복사한다 (2026-09-28 03:44 100편 배치 — 누군가 $TMPDIR/sketch_models 를
    #   지워 그 시각에 돌던 굽기들이 onnx 읽기 실패로 죽었다(싱글128). 시작 때 한 번만 복사하던 구멍).
    if MODEL_PATH and not os.path.exists(MODEL_PATH):
        MODEL_PATH = _ascii_copy(MODEL) or MODEL_PATH
    det = cv2.FaceDetectorYN.create(MODEL_PATH, "", (rgb.shape[1], rgb.shape[0]),
                                    score_threshold=score, nms_threshold=0.3, top_k=50)
    bgr = rgb[:, :, ::-1].copy()
    _, faces = det.detect(bgr)
    if faces is None:
        return []
    # ★★검출기는 얼굴 상자와 함께 **5점(오른눈·왼눈·코·입 양끝)** 을 준다 —
    #   그동안 상자만 쓰고 버렸다. `f[4]`·`f[5]` 에 **두 눈의 중점**을 실어 보낸다.
    #   상자 중심은 머리 기울기·머리카락에 흔들리는데 눈은 훨씬 덜 흔들린다.
    # ★`f[6]` = 검출 점수 · `f[7]` = 두 눈 사이 거리 (2026-09-29 «가짜 얼굴» 수리 — 얼굴고르기 가 쓴다.
    #   예전엔 점수를 버리고 넓이만 봤다: 흐린 뒤통수·벽 무늬(점수 0.45~0.70)가 진짜 얼굴(0.82~0.94)보다 커서 주인공이 됐다)
    out = []
    for f in faces:
        ex = ey = None
        d = 0.0
        if len(f) >= 8:
            ex = (float(f[4]) + float(f[6])) / 2
            ey = (float(f[5]) + float(f[7])) / 2
            d = float(np.hypot(float(f[6]) - float(f[4]), float(f[7]) - float(f[5])))
        sc = float(f[14]) if len(f) >= 15 else 1.0
        out.append((int(f[0]), int(f[1]), int(f[2]), int(f[3]), ex, ey, sc, d))
    return out


def _선명도(gray, f):
    """얼굴 한 개의 선명도 (얼굴 상자 · 눈 둘레) — 대비로 나눈 라플라시안 분산(대비·크기와 무관하게 «초점» 만 잰다).
    ★2026-09-29 점심이네 실측(몽타주 58개 얼굴): 초점 맞은 말하는 얼굴 상자 0.040~0.222 · 눈 둘레 0.090~0.479,
      초점 밖 앞사람 뒤통수·흐린 뒷사람 상자 0.001~0.017 · 눈 0.012~0.077 (15편 흐린 앞 여친은 머리카락 윤곽 때문에
      상자 0.086 이라 눈 둘레 0.030 으로만 갈린다 — 그래서 둘 다 본다)."""
    import cv2 as _cv
    H, W = gray.shape
    x, y, w, h = f[:4]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0, 0.0
    r = gray[y0:y1, x0:x1].astype(np.float32)
    r = _cv.resize(r, (96, max(8, int(96 * (y1 - y0) / (x1 - x0)))), interpolation=_cv.INTER_AREA)
    상자 = float(_cv.Laplacian(r, _cv.CV_32F).var()) / (float(r.var()) + 25.0)
    눈 = 0.0
    if f[4] is not None and len(f) > 7:
        d = max(8.0, f[7])
        ex0, ex1 = int(max(0, f[4] - d)), int(min(W, f[4] + d))
        ey0, ey1 = int(max(0, f[5] - d * 0.5)), int(min(H, f[5] + d * 0.5))
        if ex1 - ex0 >= 4 and ey1 - ey0 >= 4:
            e = _cv.resize(gray[ey0:ey1, ex0:ex1].astype(np.float32), (64, 32), interpolation=_cv.INTER_AREA)
            눈 = float(_cv.Laplacian(e, _cv.CV_32F).var()) / (float(e.var()) + 25.0)
    return 상자, 눈


def 얼굴고르기(rgb, box, usable_h, score=None):
    """★구도가 따라갈 «자격 있는 얼굴» 목록(넓이 큰 순) — 모든 구도 경로(plan_beats·plan_frame·plan_pan·same_scene·
    준비의 컷 상자)가 이 한 곳을 지난다. 돌려주는 얼굴 튜플 = _faces_yunet 과 같다 (x,y,w,h,눈x,눈y,점수,눈사이).

    ★2026-09-29 점심이네 64편 배치 — 다시 굽기의 대부분이 «가짜 얼굴» 이었다. YuNet 은 점수 0.45 로 흐린 앞사람 뒤통수·
      어깨·팔 깁스·벽·꽃·액자·담요·쿠션 무늬·냉장고 자석을 얼굴로 준다. 그런 상자는 진짜 얼굴보다 «크다»(11편 벽 391194px²
      vs 얼굴 160198 · 23편 흐린 배경 −12,366,534x570 vs 얼굴 411x548). 예전 코드는 넓이순 첫째를 주인공으로 골라
      구도가 그쪽으로 끌려가 말하는 얼굴이 상자 밖·반쯤 잘렸다(가림 없이 다시 재면 가림 시간창 115.4초 중 얼굴 담김 42%).
      에이전트는 완성본 프레임을 눈으로 보고 조각마다 «가림» 사각형을 넣어 우회했다(20편 · 36곳).
    가르는 것(같은 프레임의 다른 얼굴과 «견준다» — 절대 문턱은 어두운 장면·옆얼굴에서 진짜를 버린다):
      ① 점수 — 같은 프레임 최고 점수 − face_score_gap(기본 0.2) 아래는 버린다. 실측: 가짜 0.45~0.70 · 같은 프레임 진짜 0.82~0.94.
      ② 초점 — 점수가 넉넉한(최고 − 0.1 안) 얼굴 중 가장 선명한 값과 견줘 상자 선명도가 face_sharp_ratio(기본 0.18)배 아래거나
         눈 둘레 선명도가 face_eye_sharp_ratio(기본 0.12)배 아래면 버린다. 실측: 흐린 앞사람 상자 0.02~0.15배 · 눈 0.03~0.07배,
         초점 맞은 두 사람 서로 상자 0.23배 이상(36편 283초 소파에 엎드려 웃는 남자 0.23 · 24편 그늘진 여자 0.137 은 빠진다).
         눈 쪽을 더 느슨하게 둔 까닭 — 눈 감은 얼굴은 눈 둘레 결이 적다(5편 157초 기대어 잠든 여자 0.20배 · 상자는 0.57배).
         둘 다 0.25 로 두었을 때 한 쌍 무리에서 진짜 얼굴이 빠졌다(회귀 재기 2026-09-29 에서 잡음).
         흐린 진짜 앞사람(어깨너머 샷 9·15·24·36편)도 여기서 빠진다 — 초점이 가 있는 사람이 이 샷의 주인공이다.
    얼굴이 하나뿐이면 견줄 것이 없어 그대로 둔다(8편 누운 얼굴 0.54 는 진짜다)."""
    if rgb is None or not HAS_YN:
        return []
    box = box or {}
    thr = box.get("face_score", 0.45) if score is None else score
    fs = [q for q in _faces_yunet(rgb, thr) if q[1] + q[3] // 2 < usable_h]
    # ★★배경의 작은 얼굴을 버린다. 지나가는 사람·액자·포스터가 잡히면
    #   구도가 그쪽으로 끌려간다 — 세로가 화면의 6% 도 안 되면 주인공이 아니다.
    fs = [q for q in fs if q[3] >= usable_h * 0.06]
    if len(fs) <= 1:
        return fs
    best = max(q[6] for q in fs)
    fs = [q for q in fs if q[6] >= best - box.get("face_score_gap", 0.2)]
    선명 = {}
    if len(fs) > 1:
        import cv2 as _cv
        gray = _cv.cvtColor(np.ascontiguousarray(rgb), _cv.COLOR_RGB2GRAY)
        sh = [_선명도(gray, q) for q in fs]
        확신 = [s for q, s in zip(fs, sh) if q[6] >= best - 0.1]
        ref상자 = max(s[0] for s in 확신)
        ref눈 = max(s[1] for s in 확신)
        rr = box.get("face_sharp_ratio", 0.18)
        re_ = box.get("face_eye_sharp_ratio", 0.12)
        선명 = {id(q): s[0] for q, s in zip(fs, sh)}
        fs = [q for q, s in zip(fs, sh) if s[0] >= ref상자 * rr and (ref눈 <= 0 or s[1] >= ref눈 * re_)]
    fs.sort(key=lambda q: -q[2] * q[3])
    # ★주인공(fs[0])은 점수가 넉넉한(최고 − 0.1 안) 얼굴 중 가장 큰 것 — 나머지는 넓이순. 점수가 한 단 낮은 큰 상자
    #   (13편 담요 0.70 vs 얼굴 0.92)는 주인공이 못 되고, 크기가 비슷하면 무리로만 함께 담긴다(plan_beats mains).
    #   단 크기가 엇비슷한(45% 이상) 얼굴이 두 배 넘게 선명하면 그쪽이 주인공이다 — 초점이 가 있는 사람이 이 샷의 주인공
    #   (17편 102.7초: 앞의 남자 247x387 선명도 0.034 · 말하는 여자 200x336 0.122 — 넓이만 보면 남자로 걸어가 1초 동안
    #   둘 다 반쯤 잘렸다. 얼굴 관문이 잡았다).
    if len(fs) > 1:
        b_ = max(q[6] for q in fs)
        후보 = [q for q in fs if q[6] >= b_ - 0.1]
        주 = 후보[0]
        또렷 = [q for q in 후보 if q[2] * q[3] >= 주[2] * 주[3] * 0.45
                and 선명.get(id(q), 0) >= 2 * 선명.get(id(주), 0) > 0]
        if 또렷:
            주 = max(또렷, key=lambda q: 선명.get(id(q), 0))
        fs = [주] + [q for q in fs if q is not 주]
    return fs


def _busy_center(rgb, usable_h):
    """얼굴을 못 찾을 때 — 잔무늬가 많은 곳이 인물이다.
    배경(벽·커튼)은 밋밋하고 인물은 머리카락·이목구비·옷 주름으로 엣지가 많다."""
    g = np.asarray(Image.fromarray(rgb).convert("L"), dtype=np.float32)[:usable_h]
    gx = np.abs(np.diff(g, axis=1)).sum(axis=0)
    gy = np.abs(np.diff(g, axis=0)).sum(axis=1)

    def peak(v, win):
        if len(v) <= win:
            return len(v) // 2
        k = np.convolve(v, np.ones(win) / win, mode="same")
        return int(np.argmax(k))

    return peak(gx, max(31, len(gx) // 6)), peak(gy, max(31, len(gy) // 6))


def _hist(rgb):
    """색 분포를 잰다 — 같은 장면인지 가리는 데 쓴다."""
    a = rgb[::4, ::4]
    h = []
    for c in range(3):
        v, _ = np.histogram(a[:, :, c], bins=24, range=(0, 256))
        h.append(v / max(v.sum(), 1))
    return np.concatenate(h)


def same_scene(a, b, thr=0.93):
    """두 프레임이 같은 장면인가.

    ★scene detection 은 인물이 크게 움직이기만 해도 컷으로 잡는다. 그때마다
      구도를 새로 잡으면 **자막까지 같은데 화면 크기만 바뀌어** 튄다.

    ★★**색만으로 판정하면 안 된다.** 같은 헬스장에서 찍은 영상은 인물이 바뀌어도
      색 분포가 비슷해서, 0.86 으로 뒀더니 남자→여자 전환까지 「같은 장면」이 됐다.
      **얼굴이 잡히면 얼굴 위치·크기를 먼저 본다.**"""
    if a is None or b is None:
        return False
    if float(np.minimum(_hist(a), _hist(b)).sum()) < thr:
        return False                       # 색부터 다르면 볼 것도 없다

    if HAS_YN:
        # 자격 있는 얼굴만 견준다 (2026-09-29 — 흐린 뒤통수·무늬가 «가장 큰 얼굴» 이면 같은 장면을 다르다고 봤다)
        fa, fb = 얼굴고르기(a, None, a.shape[0]), 얼굴고르기(b, None, b.shape[0])
        if fa and fb:
            ga, gb = fa[0], fb[0]
            W = a.shape[1]
            # 얼굴이 화면 폭의 12% 넘게 움직이거나 크기가 30% 넘게 달라지면 다른 장면
            moved = abs((ga[0] + ga[2] / 2) - (gb[0] + gb[2] / 2)) / W
            scaled = abs(ga[3] - gb[3]) / max(ga[3], gb[3], 1)
            return moved <= 0.12 and scaled <= 0.30
        if bool(fa) != bool(fb):
            return False                   # 한쪽에만 얼굴이 있으면 바뀐 것이다
    return True


def frame_at(src, sec, work, tag):
    # ★캐시 이름에 시각을 넣는다 (2026-09-28) — 예전엔 조각·비트 번호(tag)만으로 캐시해, 경계를 고쳐 다시 구우면
    #   같은 번호의 «옛 시각» 프레임으로 구도를 정했다(준비의 grab 이 같은 함정을 피해 따로 뽑는 이유).
    #   시각은 소수 4자리로 넘긴다 — 격자 경계값(p−0.002)을 0.01초로 반올림하면 이웃 프레임이 뽑힌다.
    p = os.path.join(work, f"_s_{tag}_{max(0, sec):.4f}.png")
    if not os.path.exists(p):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{max(0, sec):.4f}", "-i", src, "-frames:v", "1",
                        "-y", p], capture_output=True)
    return _read_rgb(p)


def frames_of(src, seg, work, tag, n=5):
    out = []
    t0, t1 = seg["t0"], seg["t1"]
    for k in range(n):
        sec = t0 + (t1 - t0) * (k + 1) / (n + 1)
        p = os.path.join(work, f"_f_{tag}_{k}_{sec:.2f}.png")    # 시각을 이름에(경계 고친 재굽기에 옛 프레임 금지)
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-ss", f"{sec:.2f}", "-i", src, "-frames:v", "1", "-y", p],
                           capture_output=True)
        a = _read_rgb(p)
        if a is not None:
            out.append(a)
    return out


def face_track(src, seg, W, usable_h, work, tag, step=0.8):
    """조각 안에서 얼굴이 어떻게 움직이는지 **여러 시점을 훑어** 궤적을 만든다."""
    t0, t1 = seg["t0"], seg["t1"]
    n = max(2, min(14, int((t1 - t0) / step)))
    pts = []
    for k in range(n + 1):
        sec = t0 + (t1 - t0) * k / n
        p = os.path.join(work, f"_t_{tag}_{k}_{sec:.2f}.png")    # 시각을 이름에(경계 고친 재굽기에 옛 프레임 금지)
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-ss", f"{sec:.2f}", "-i", src, "-frames:v", "1", "-y", p],
                           capture_output=True)
        a = _read_rgb(p)
        if a is None:
            continue
        fs = 얼굴고르기(a, None, usable_h)            # 가짜·흐린 얼굴을 거른다(2026-09-29 — 모든 구도 경로가 한 곳을 지난다)
        if not fs:
            continue
        if len(fs) > 1:
            x0 = min(f[0] for f in fs); y0 = min(f[1] for f in fs)
            x1 = max(f[0] + f[2] for f in fs); y1 = max(f[1] + f[3] for f in fs)
            box_ = (x0, y0, x1 - x0, y1 - y0)
        else:
            box_ = fs[0]
        pts.append((sec - t0, box_))
    return pts


def smooth(vals, win=3):
    """궤적을 다듬는다 — 검출이 한두 프레임 튀어도 카메라는 흔들리면 안 된다."""
    if len(vals) < 3:
        return vals
    out = []
    for i in range(len(vals)):
        lo, hi = max(0, i - win // 2), min(len(vals), i + win // 2 + 1)
        out.append(sum(vals[lo:hi]) / (hi - lo))
    return out


def 그림경계(rgb, W, H):
    """프레임에서 «실제 그림» 의 경계 (x0, y0, x1, y1) — 레터박스·필러박스의 순흑 띠를 뺀 자리.

    ★2026-09-21 띱 7차(Deep76·79·90·91) — 굽기에는 레터박스 경로가 없었다. 조각 «전체»가
      프레임-인-프레임일 때만 build 가 잘라냈고(세 점 일치), 샷마다 띠가 있다 없다 하는 소재
      (재연 장면만 시네마스코프)는 얼굴 추적 crop 이 검은 띠 안까지 들어가 완성본 위쪽에
      최대 116px 검은 띠가 박혔다. 준비(prproj) 쪽은 09-08 Deep14 때 고쳤는데 굽기 쪽이 남은 구멍.
      → 조각 단위가 아니라 **비트(샷)마다** 경계를 재고, crop 은 그 안에서만 움직인다.
    띠로 인정하는 조건: 줄 최대 밝기 ≤ 26 의 «균일한 순흑»(준비와 같은 기준) · 두께 12px 이상 ·
    한 변의 25% 이하(그보다 두꺼우면 프레임-인-프레임이거나 어두운 장면이다 — 여기서 다루지 않는다).
    검은 배경 위 글자 카드(밝은 영역 < 15%)는 띠가 아니라 내용이다 — 전체를 돌려준다.

    ★2026-10-03 판정을 안쪽경계.비트경계 하나로 (루키치171·206·172 «어두운 장면 = 가짜 띠» 클래스): 예전 본문은
      «최대 밝기 ≤ 26 인 가장자리 = 띠» 였다 — 진짜 띠가 없는 12편 원본(1초 간격)에서 어두운 장면 430장에 가짜 띠를 냈고
      (171 274초 왼쪽 340px·위 111px 등) 그 띠가 crop 울타리가 되어 얼굴 자리를 밀어냈다. 이제 띠는 «디지털 순흑 + 곧은
      그림 경계» 가 함께 맞을 때만 인정한다(준비·굽기 경계와 같은 판정 — 규칙과 실측은 s2pipe/안쪽경계.py ·
      시험 검수도구/안쪽경계시험.py). 두께 12px↑·한 변 25%↓ 규칙은 그대로."""
    from . import 안쪽경계
    return 안쪽경계.비트경계(rgb, W, H)


def 가림경계(경계, seg, a, e, usable_h, ratio):
    """조각 표식 «가림» [[x0,y0,x1,y1(,t0,t1)], …] — 원본 화면 속에 박힌 캡션(자막띠 밖 · 카드 검출 밖) 자리.
    ★2026-09-27 싱글268 — 좌상단 캡션 «2524년 대한민국»(x136~690·y749~827 · 원본 138.9~141.1초)이 완성본 상자
      왼쪽에 비쳤다. 자막띠 자르기(세로 한계)로는 못 막는 자리라, 그 시간 동안 그림경계를 캡션 바깥쪽으로 줄인다 —
      왼쪽·오른쪽·위·아래 중 crop(비율 ratio)을 가장 크게 둘 수 있는 쪽. 관문은 번인관문.걸림 이 같은 사각형으로 본다."""
    vx0, vy0, vx1, vy1 = 경계
    from .번인관문 import 관문겹침
    for r in seg.get("가림") or []:
        t0, t1 = (r[4], r[5]) if len(r) >= 6 else (seg["t0"], seg["t1"])
        # ★겹침은 관문(번인관문.걸림)과 같은 자로 — 0.1초 이하로 스친 비트(가림 끝이 다음 샷 첫 비트에 격자 한두 장 걸침)는
        #   예전엔 그 비트 «전체»(0.8초)에 가림을 걸어 옆 샷 구도까지 비틀었다(2026-09-29 점심이네5 카페 어깨너머 샷 번갈이).
        #   관문도 0.1초 이하는 겹침으로 안 보므로 여기서 풀어도 관문과 어긋나지 않는다.
        if min(t1, e) - max(t0, a) <= 관문겹침:
            continue
        x0, y0, x1, y1 = r[:4]
        if x1 <= vx0 or x0 >= vx1 or y1 <= vy0 or y0 >= min(vy1, usable_h):
            continue
        후보 = [(max(vx0, x1), vy0, vx1, vy1), (vx0, vy0, min(vx1, x0), vy1),
                (vx0, max(vy0, y1), vx1, vy1), (vx0, vy0, vx1, min(vy1, y0))]

        def 넓이(b):
            w, h = b[2] - b[0], min(b[3], usable_h) - b[1]
            if w <= 0 or h <= 0:
                return 0
            return min(h, w / ratio) * min(w, h * ratio)
        vx0, vy0, vx1, vy1 = max(후보, key=넓이)
    return (vx0, vy0, vx1, vy1)


def _얼굴든(c, q, 몫=0.6):
    """crop c=(w,h,x,y) 안에 얼굴 q 의 가로 몫(기본 60%) 이상과 세로 가운데가 드는가 — «이 얼굴이 보이는가»."""
    w, h, x, y = c[:4]
    fx, fy, fw, fh = q[:4]
    가로 = max(0, min(x + w, fx + fw) - max(x, fx)) / max(fw, 1)
    return 가로 >= 몫 and y <= fy + fh / 2 <= y + h


def 담기(bw, bh, tx, ty, face, 경계, usable_h, ratio):
    """★구도의 «최종 관문» — 어느 경로(plan_beats·plan_frame)로 정했든 crop 은 여기를 지난다.

    ① crop 은 그림경계(레터박스 뺀 자리) 안에 있다.
    ② 검출된 얼굴(또는 무리 상자)은 crop 안에 있다 — **부드러움 제한보다 얼굴 담기가 먼저다.**
       (2026-09-21 Deep87: 중간 샷에서 확대 1.79 로 시작한 뒤 원본이 타이트 클로즈업으로
        바뀌었는데 «한 비트 4.5%» 제한에 묶여 확대가 1.5~1.7 에 머물렀고, 말하는 사람이
        눈·이마만 잡혀 입이 잘렸다. 기존 검사는 «얼굴이 검출되는가» 만 봤다.)
       원본 컷에서 크기가 바뀌는 것은 튐이 아니다 — 원본이 이미 앵글을 바꿨다.
    돌려주는 값: (bw, bh, tx, ty, 얼굴담김) — 얼굴이 쓸 수 있는 자리보다 크면 최대로 넓히고
    얼굴담김=None(불가피) 을 준다."""
    vx0, vy0, vx1, vy1 = 경계
    vy1 = min(vy1, usable_h)
    vw, vh = max(vx1 - vx0, 2), max(vy1 - vy0, 2)
    담김 = True
    if face:
        fx, fy, fw, fh = face[:4]
        need_h = fh * 1.22                       # 이마 위 8% · 턱 아래 14% (입이 자막·밑변에 안 걸리게)
        need_w = fw * 1.10
        need_h = max(need_h, need_w / ratio)
        if bh < need_h:
            bh = need_h
    if bh > vh:
        bh = vh
    bw = bh * ratio
    if bw > vw:
        bw, bh = vw, vw / ratio
    bw, bh = int(bw), int(bh)
    if face:
        if fh * 1.22 > bh + 1 or fw * 1.10 > bw + 1:
            담김 = None                          # 얼굴이 쓸 수 있는 자리보다 크다 — 불가피
            ty = fy + fh / 2 - bh * 0.5          # 가운데에 놓아 위아래를 고르게 내준다
            tx = fx + fw / 2 - bw / 2
        else:
            ty = min(ty, fy - fh * 0.08)         # 이마가 윗변 아래
            ty = max(ty, fy + fh * 1.14 - bh)    # 턱이 밑변 위 (입이 먼저다 — 나중에 걸어 이긴다)
            tx = min(tx, fx - fw * 0.05)
            tx = max(tx, fx + fw * 1.05 - bw)
    원tx, 원ty = tx, ty
    tx = max(vx0, min(tx, vx1 - bw))
    ty = max(vy0, min(ty, vy1 - bh))
    if face and 담김:
        담김 = bool(ty <= fy + fh * 0.15 and ty + bh >= fy + fh * 0.98
                    and tx <= fx + fw * 0.1 and tx + bw >= fx + fw * 0.9)
        if not 담김 and (abs(tx - 원tx) > 1 or abs(ty - 원ty) > 1):
            담김 = None      # 얼굴이 원본 프레임 가장자리·자막 띠에 걸쳐 있다 — 그림경계가 이긴다(불가피)
    return bw, bh, int(tx), int(ty), 담김


# ── 말하는 얼굴 (2026-10-03 루키치170·172·162 «구도가 말하는 사람을 놓친다» 클래스) ─────────────────────────
# ★예전 구도는 «누가 말하는가» 를 전혀 보지 않았다 — 자격 얼굴 중 «점수가 넉넉한 가장 큰 얼굴» 이 주인공이고, 무리가
#   얼굴 폭 3배보다 넓으면 그 큰 얼굴 «하나만» 담았다. 그래서
#   · 루키치170 330.7~333.2초 세 여자 샷: 카메라에 가장 가까운 «먹는» 왼쪽 여자(얼굴 305x438)를 잡고, 말하는 가운데 여자
#     (273x341)는 상자 밖 — 에이전트가 구도용 가림 3개로 손 수리했다.
#   · 루키치172 317.3~324.3초 골목 투샷: 말하는 재민(왼쪽 97x107)이 아니라 비슷한 크기의 혜윤(오른쪽 90x113)을 따라갔다.
#     두 얼굴 사이 486px 은 이미 쓰던 상자 폭(588px) 안에 들어가는데도 «얼굴 폭 3배(291px) 넘게 떨어졌다» 고 하나만 담았다.
# 고친 구조:
#   ① 무리 고르기 — 떨어진 얼굴이라도 «지금 확대 그대로 상자에 같이 들어가면» 같이 담는다(아무도 작아지지 않는다).
#   ② 화자 고르기 — 다 못 담을 때는 «말이 있는 동안(원본 전사 시각) 입이 눈 둘레보다 더 움직인 얼굴» 이 주인공이다.
#      먹기·씹기는 말이 없는 동안이거나, 고개째 흔들려 눈 둘레도 같이 움직이므로 빠진다. 소리와 견주는 자는 전사 시각
#      (원본 vtt) — 프레임 단위 소리 크기 상관은 0.85초 비트에서 가운데 여자 −0.12·먹는 여자 −0.11 로 쓸 수 없었다(실측).
#      실측 170 샷 평균(입−눈 · 정규화 차이): 말하는 가운데 0.111 · 먹는 왼쪽 0.032 · 오른쪽 0.027.
#      작은·어두운 얼굴은 잴 수 없다(172 골목 80px 얼굴은 듣는 혜윤 쪽이 0.17~0.34 로 더 높게 나왔다) — 그래서 폭 화자최소폭
#      이상 얼굴끼리만 견주고, 2배 넘게 앞설 때만 정한다. 못 정하면 같은 샷의 앞뒤 결정을 잇고, 그것도 없으면 예전 규칙(①).
화자최소폭 = 140          # 원본 px — 이보다 작은 얼굴은 입 움직임을 못 잰다(172 골목 80px 실측)
화자문턱 = 0.06           # 입−눈 평균이 이 값 이상이어야 «말한다» (170 말하는 얼굴 0.074~0.119 · 듣는 얼굴 0.002~0.051)
화자배 = 2.0              # 1등이 2등의 이 배 이상일 때만 정한다
_말창캐시 = {}
_검출기들 = {}


def 말창(src):
    """말 구간 [(시작, 끝)] (원본 시각) — 입 움직임을 «말이 있는 동안» 만 재려고 쓴다(말 없을 때 씹는 입은 화자가 아니다).
    박힌 자막 카드(자막띠시각.카드들 — 굽기가 박힌 자막 관문에 쓰려고 이미 재 둔 `<원본>.카드2.json`)와 원본 전사
    (src 옆 <id>.ko.vtt)의 글자 있는 큐를 «합친» 것. 둘 다 없으면 None — 화자를 정하지 않는다.
    ★둘 다 빠지거나 밀린다(2026-10-03 루키치170 실측): 294~296초는 카드 294.1~295.0·295.0~296.0 이 agy 가 들은 말과 맞고
      vtt 는 295.45·297.15 로 1.5~2초 늦었다. 330.6~332.1초 «우리 여기서 자고 갈 건데» 는 vtt 에만 있고 카드는 놓쳤다
      (카드만 쓰면 세 여자 샷의 화자를 못 정해 먹는 여자 쪽으로 다시 갔다). 그래서 합친다 — 빠진 말보다 넓은 창이 낫다."""
    if src in _말창캐시:
        return _말창캐시[src]
    import re
    out = []
    try:
        from . import 자막띠시각
        out += [(float(a), float(b)) for a, b in 자막띠시각.카드들(src)]
    except Exception:
        pass
    p = os.path.splitext(src)[0] + ".ko.vtt"
    if os.path.exists(p):
        for a, b, c, d, e, f, x in re.findall(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)[^\n]*\n(.+)",
                                             open(p, encoding="utf-8").read()):
            if re.search(r"[가-힣A-Za-z]", x):
                out.append((int(a) * 3600 + int(b) * 60 + float(c), int(d) * 3600 + int(e) * 60 + float(f)))
    out = sorted(out) or None
    _말창캐시[src] = out
    return out


def _말중(말, t, 여유=0.15):
    return bool(말) and any(a - 여유 <= t <= b + 여유 for a, b in 말)


def _반크기(W, H):
    return (W // 2) // 2 * 2, (H // 2) // 2 * 2


def _반프레임(src, g, W, H, k0, k1):
    """원본 프레임 [k0, k1) 을 가로세로 반으로 줄인 RGB 로 하나씩 (번호, 배열) — 프레임격자.프레임들 과 같은 찾아가기
    (경계값 -ss · passthrough) 라 번호가 정확하다. 한 번에 다 올리지 않고 흘려 읽는다(조각 20초 = 480장)."""
    k0, k1 = max(0, k0), min(g.n, k1)
    if k1 <= k0:
        return
    w2, h2 = _반크기(W, H)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", repr(g.경계값(k0)), "-i", src, "-frames:v", str(k1 - k0),
                          "-vf", f"scale={w2}:{h2}:flags=area", "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w2 * h2 * 3
    try:
        for k in range(k0, k1):
            b = p.stdout.read(n)
            if len(b) < n:
                break
            yield k, np.frombuffer(b, np.uint8).reshape(h2, w2, 3)
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def _검출(rgb, score=0.45):
    """반 크기 프레임 → 얼굴 [x,y,w,h, 눈·코·입끝 10점, 점수] (원본 좌표로 2배) — 입끝 점이 필요해서 _faces_yunet 과 따로."""
    global MODEL_PATH
    if MODEL_PATH and not os.path.exists(MODEL_PATH):
        MODEL_PATH = _ascii_copy(MODEL) or MODEL_PATH
    key = (rgb.shape[1], rgb.shape[0], score)
    det = _검출기들.get(key)
    if det is None:
        det = _검출기들[key] = cv2.FaceDetectorYN.create(MODEL_PATH, "", (rgb.shape[1], rgb.shape[0]),
                                                         score_threshold=score, nms_threshold=0.3, top_k=50)
    _, fs = det.detect(np.ascontiguousarray(rgb[:, :, ::-1]))
    if fs is None:
        return []
    return [np.concatenate([f[:14] * 2, f[14:15]]) for f in fs]


def _같은자리(q, r, 몫=0.6):
    """두 얼굴 상자(x,y,w,h…)가 같은 사람 자리인가 — 중심 차가 가로·세로 모두 큰 쪽 크기의 몫 안."""
    return (abs((q[0] + q[2] / 2) - (r[0] + r[2] / 2)) <= max(q[2], r[2]) * 몫
            and abs((q[1] + q[3] / 2) - (r[1] + r[3] / 2)) <= max(q[3], r[3]) * 몫)


def 입움직임(src, g, W, H, k0, k1, faces, 말):
    """비트 [k0, k1) 에서 얼굴마다 «입 움직임 − 눈 둘레 움직임» 의 [합, 표본 수] — 말 구간 안 프레임만 잰다.
    움직임 = 이웃 두 프레임의 같은 자리 조각(입: 입끝 두 점 가운데 · 눈: 두 눈 가운데, 크기는 눈 사이 거리로) 의 평균 밝기
    차를 조각의 대비(표준편차+8)로 나눈 값. 고개·몸이 움직이면 입과 눈이 같이 움직이므로 «입 − 눈» 만 남긴다."""
    합 = [[0.0, 0] for _ in faces]
    if not faces or not HAS_YN or not 말:
        return 합
    w2, h2 = _반크기(W, H)

    def 조각(gray, cx, cy, w_, h_):
        x0, x1, y0, y1 = int(cx - w_ / 2), int(cx + w_ / 2), int(cy - h_ / 2), int(cy + h_ / 2)
        if x0 < 0 or y0 < 0 or x1 > gray.shape[1] or y1 > gray.shape[0] or x1 - x0 < 4 or y1 - y0 < 4:
            return None
        return cv2.resize(gray[y0:y1, x0:x1], (24, 16), interpolation=cv2.INTER_AREA)

    앞 = None                                       # (회색, 이 프레임 검출) — 검출한 프레임과 바로 다음 프레임을 한 쌍으로
    for k, f in _반프레임(src, g, W, H, k0, k1):
        gray = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
        if 앞 is not None:
            g0, ds = 앞
            for i, q in enumerate(faces):
                m = [d for d in ds if _같은자리(q, d)]
                if not m:
                    continue
                d = min(m, key=lambda d: abs(d[0] + d[2] / 2 - q[0] - q[2] / 2))
                d = d / 2                                     # 반 크기 좌표로
                ex, ey = (d[4] + d[6]) / 2, (d[5] + d[7]) / 2
                mx, my = (d[10] + d[12]) / 2, (d[11] + d[13]) / 2
                dd = max(4.0, float(np.hypot(d[6] - d[4], d[7] - d[5])))
                입0, 입1 = 조각(g0, mx, my + dd * 0.15, dd * 1.3, dd * 0.9), 조각(gray, mx, my + dd * 0.15, dd * 1.3, dd * 0.9)
                눈0, 눈1 = 조각(g0, ex, ey, dd * 1.8, dd * 0.6), 조각(gray, ex, ey, dd * 1.8, dd * 0.6)
                if 입0 is None or 입1 is None or 눈0 is None or 눈1 is None:
                    continue
                s입 = float(np.mean(np.abs(입1 - 입0))) / (float(입0.std()) + 8)
                s눈 = float(np.mean(np.abs(눈1 - 눈0))) / (float(눈0.std()) + 8)
                합[i][0] += max(0.0, s입 - s눈)
                합[i][1] += 1
            앞 = None
            continue
        if (k - k0) % 2 == 0 and _말중(말, g.시작(k)):
            앞 = (gray, _검출(f))
    return 합


def 화자고르기(잼들, 샷들):
    """비트마다 재 둔 [(얼굴, 합, 수)] (재지 않은 비트는 None) → 비트마다 화자 얼굴(없으면 None).
    한 비트는 같은 샷 안 앞뒤 한 비트까지 같은 자리 얼굴의 값을 모아 견준다(0.85초 한 비트는 표본 10개라 흔들린다).
    정한 비트 사이·샷 첫머리의 못 정한 비트는 같은 샷에서 가장 가까운 결정을 같은 자리 얼굴로 잇는다(샷 첫 비트에서
    못 정했다고 큰 얼굴로 갔다가 다음 비트에 화자로 걸어가면 그 사이 화자가 잘린다 — 170 첫 비트 실측 1.6배)."""
    n = len(잼들)
    화자 = [None] * n
    for s0, s1 in 샷들:
        for k in range(s0, s1):
            if not 잼들[k]:
                continue
            모 = []
            for q, s, c in 잼들[k]:
                for j in (k - 1, k + 1):
                    if s0 <= j < s1 and 잼들[j]:
                        for r, s2, c2 in 잼들[j]:
                            if _같은자리(q, r):
                                s, c = s + s2, c + c2
                                break
                모.append((q, s / c if c >= 4 else None))
            잰 = sorted([x for x in 모 if x[1] is not None], key=lambda x: -x[1])
            if len(잰) >= 2 and 잰[0][1] >= 화자문턱 and 잰[0][1] >= 화자배 * 잰[1][1]:
                화자[k] = 잰[0][0]
        # 못 정한 비트 — 같은 샷의 가장 가까운 결정(앞 먼저)을 같은 자리 얼굴로 잇는다
        정 = [k for k in range(s0, s1) if 화자[k] is not None]
        for k in range(s0, s1):
            if 화자[k] is not None or not 잼들[k] or not 정:
                continue
            for j in sorted(정, key=lambda j: (abs(j - k), j > k)):
                m = [q for q, _, _ in 잼들[k] if _같은자리(q, 화자[j])]
                if m:
                    화자[k] = m[0]
                    break
    return 화자


def 무리고르기(fs, 주, usable_h, box, W=None, 경계=None):
    """자격 얼굴 fs · 주인공 주(화자 또는 fs[0]) → 상자가 담을 얼굴 목록.
    ① 예전 규칙 — 주인공 넓이의 45% 이상인 얼굴(mains)이 주인공 얼굴 폭의 pair_max_span(3)배 안에 모여 있으면 다 담는다.
    ② 그보다 넓으면 주인공부터 가까운 얼굴을 하나씩 더하되, «주인공 혼자일 때의 확대 그대로» 상자에 (담기 여유 10%
       까지) 들어가는 얼굴만 더한다 — 담아도 아무도 작아지지 않는다(2026-10-03 172 골목 투샷: 486px 이 588px 상자에 들어갔다).
    ①이라도 무리가 «가장 넓힌 상자»(원본 폭 W · 세로 usable_h)에 담기 여유째 안 들어가면 ②로 간다 — 다 담으려다 둘 다
       반씩 잘린다(2026-10-03 루키치178 83.5초 두 얼굴 463·325px · 무리 폭 1248px×1.1 > 상자 최대 1059px → 둘 다 72~79% 만 보임)."""
    if not fs:
        return []
    big = 주[2] * 주[3]
    mains = [q for q in fs if q[2] * q[3] >= big * 0.45]
    if 주 not in mains:
        mains = [주] + mains

    def 폭(m):
        return max(q[0] + q[2] for q in m) - min(q[0] for q in m)
    ratio = box["w"] / box["h"]
    쓸높이 = usable_h
    최대폭 = min(W or 10 ** 9, usable_h * ratio)
    if 경계:                                     # 레터박스 샷은 띠 안쪽만 쓸 수 있다(2026-10-03 Deep14 185.4초 — 띠 안 높이 756 에
        vx0, vy0, vx1, vy1 = 경계                 #   두 얼굴 무리를 맞추다 상자가 모자라 둘 다 가장자리에 걸쳤다)
        쓸높이 = max(1, min(vy1, usable_h) - vy0)
        최대폭 = min(최대폭, vx1 - vx0, 쓸높이 * ratio)

    def 들어감(m):
        return 폭(m) * 1.10 <= 최대폭 and (max(q[1] + q[3] for q in m) - min(q[1] for q in m)) * 1.22 <= 쓸높이
    if len(mains) <= 1 or (폭(mains) <= 주[2] * box.get("pair_max_span", 3.0) and 들어감(mains)):
        return mains
    zmin, zmax = box.get("zoom_range", [1.10, 1.80])
    z1 = max(zmin, min(zmax, usable_h / max(주[3] / box.get("face_ratio", 0.61), 1)))
    bw1 = min((usable_h / z1) * ratio, 최대폭)
    out = [주]
    for q in sorted((q for q in mains if q is not 주), key=lambda q: abs((q[0] + q[2] / 2) - (주[0] + 주[2] / 2))):
        if 폭(out + [q]) * 1.10 <= bw1 and 들어감(out + [q]):
            out.append(q)
    return out


def plan_pan(src, seg, idx, W, H, usable_h, box, work):
    """조각 하나를 **통으로 쓰되 카메라가 얼굴을 따라가게** 한다.

    ★컷을 잘게 나눠 crop 을 갈아끼우면 경계마다 화면이 점프한다.
      크기는 고정하고 위치만 시간에 따라 옮기면 그 점프가 아예 없어진다.
    """
    face_ratio = box.get("face_ratio", 0.61)
    face_y = box.get("face_y", 0.40)
    zmin, zmax = box.get("zoom_range", [1.10, 1.80])
    dur = max(seg["t1"] - seg["t0"], 0.1)

    pts = face_track(src, seg, W, usable_h, work, f"{idx:02d}")
    if not pts:
        return None, None

    # 확대율은 조각 안에서 고정한다 — 크기가 변하면 crop 폭이 바뀌어 다루기 어렵다
    hs = sorted(p[1][3] for p in pts)
    fh = hs[len(hs) // 2]
    z = max(zmin, min(zmax, usable_h / max(fh / face_ratio, 1)))
    bh = int(usable_h / z)
    bw = int(bh * box["w"] / box["h"])
    if bw > W:
        bw, bh = W, int(W * box["h"] / box["w"])
    bh = min(bh, usable_h)

    ts = [p[0] for p in pts]
    xs = smooth([p[1][0] + p[1][2] / 2 - bw / 2 for p in pts])
    ys = smooth([p[1][1] + p[1][3] / 2 - bh * face_y for p in pts])
    xs = [max(0, min(v, W - bw)) for v in xs]
    ys = [max(0, min(v, usable_h - bh)) for v in ys]

    def piecewise(times, vals):
        """구간마다 선형으로 잇는 ffmpeg 표현식. 뒤에서부터 감싸 올린다."""
        e = f"{vals[-1]:.0f}"
        for i in range(len(times) - 2, -1, -1):
            t0_, t1_ = times[i], times[i + 1]
            a, b = vals[i], vals[i + 1]
            span = max(t1_ - t0_, 0.01)
            lin = f"({a:.0f}+({b - a:.0f})*(t-{t0_:.2f})/{span:.2f})"
            e = f"if(lt(t,{t1_:.2f}),{lin},{e})"
        return e

    vf = (f"crop={bw}:{bh}:x='{piecewise(ts, xs)}':y='{piecewise(ts, ys)}',"
          f"scale={box['w']}:{box['h']}:flags=lanczos")
    if box.get("mirror"):
        vf += ",hflip"
    moved = max(xs) - min(xs)
    return vf, {"zoom": round(z, 2),
                "how": f"얼굴 추적 {len(pts)}점 · 가로 {moved:.0f}px 이동",
                "crop": (bw, bh, int(xs[0]), int(ys[0])), "run": 0, "hold": 0.0}


def plan_beats(src, seg, idx, W, H, usable_h, box, work, cuts=(), prev=None, 머리="이어짐", 틀=None):
    """조각을 짧은 **비트**로 나누고, 비트마다 구도를 **조금씩만** 바꾼다.

    ★레퍼런스 실측(ref/cut_zoom.py · beat.py):
        화면 변화 간격 0.8초 · 한 번의 변화는 줌 4.0% · 줌 속도 초당 5.4%
      우리는 1.4초마다 7.1% 씩 바꿔서 튀었다. **자주·작게가 답이다** —
      오늘 여덟 번 실패한 시도는 전부 반대 방향(덜 자주·더 크게)이었다.

    ★원본 컷 경계에서는 제한을 풀어 준다. 원본이 이미 앵글을 바꿨으니 우리가
      같이 바꿔도 튀지 않는다 — 오히려 안 바꾸면 컷이 지워진다(팬 모드의 병).

    ★2026-09-28 «경계 구도» 클래스 수리 (싱글51 1프레임 튐 · 싱글48 이음매 뒤 얼굴이 1.2초 가장자리):
      · 비트 경계는 «프레임 번호» 로 정한다(s2pipe/프레임격자.py). 원본 화면 전환은 그 전환 프레임 «바로 거기»가
        경계다 — 0.01초 반올림·0.05초 이분 탐색으로 1~2프레임 늦게 구도가 바뀌면 새 샷 첫 프레임이 앞 구도로 나간다.
      · 전환은 이웃 프레임 차이의 날카로운 봉우리로 확인한다. scene_cuts 가 놓친 전환(51편 4곳)도 비트 경계가 되고,
        same_scene 이 «다르다» 해도 봉우리가 없으면 전환이 아니다(51편 25.99초 가짜 컷 → 0.23초 비트에 큰 이동 = 3프레임 휙).
      · 궤적 다듬기(smooth)·빈 얼굴 채우기는 샷 안에서만 — 앞 샷 얼굴 자리가 새 샷 구도로 끌려오지 않게.
      · 머리 = 조각 첫 비트가 무엇인가 (build 가 정한다):
          "새샷"   원본에서 이어지지 않는 이음매(점프 컷) — 앞 조각 구도를 끌고 오지 않는다(prev 무시, 새 샷 얼굴로 바로).
                   싱글48 38.05초: 첫 비트가 앞 조각 마지막 구도에서 비트당 몇 %씩만 움직여 얼굴이 1.2초 왼쪽 끝에 걸렸다.
          "전환"   원본에서 이어지지만 이음매가 화면 전환 프레임 — 컷처럼 푼다(at_cut).
          "이어짐" 원본에서 끊김 없이 이어진 이음매 — 앞 구도에서 이어 간다(여기서 튀면 안 된다).
      · 틀 = build 가 정한 조각 프레임 창 {"k0","k1"} — 없으면 t0·t1 을 격자에 맞춰 쓴다.
    """
    from . import 프레임격자 as G
    beat = box.get("beat_sec", 0.85)
    dz_max = box.get("beat_zoom", 0.045)
    dp_max = box.get("beat_shift", 0.045)
    relief = box.get("beat_cut_relief", 2.5)
    face_ratio = box.get("face_ratio", 0.61)
    face_y = box.get("face_y", 0.40)
    zmin, zmax = box.get("zoom_range", [1.10, 1.80])
    g = G.얻기(src)
    k0, k1 = (틀["k0"], 틀["k1"]) if 틀 else (g.번호(seg["t0"]), g.번호(seg["t1"]))
    fps = g.fps
    if 머리 == "새샷":
        prev = None                                     # 점프 컷 — 앞 조각 구도를 끌고 오지 않는다

    # 원본 프레임 차이(조각 전체 · 64x36) — 전환 위치를 프레임 단위로 잰다
    _기점 = max(0, k0 - 5)
    _F = G.프레임들(src, g, _기점, k1 + 5)
    _D = G.차이열(_F)

    def _전환(k, 느슨=False):
        # 번쩍임(조명 깜빡임)은 전환이 아니다 — F 를 넘겨 프레임격자.날카로운 이 가린다(2026-09-29 점심이네20 가스불)
        j = k - _기점
        if not (0 < j < len(_D)):
            return False
        return G.날카로운(_D, j, F=_F) or (느슨 and G.날카로운(_D, j, 최소=4.0, 배=3.0, F=_F))

    # 비트 경계 — 원본 전환은 전부 살리고(짧아도 경계), 그 사이가 벌어지면 격자를 끼운다
    전환들 = sorted({g.번호(c) for c in cuts if k0 < g.번호(c) < k1}
                  | {k for k in range(k0 + 1, k1) if _전환(k)})
    # scene_cuts 값이 봉우리 옆(±2)이면 봉우리로 — 격자 반올림이 어긋났을 때의 받침
    def _번쩍(k):
        j = k - _기점
        return 0 < j < len(_D) and G.날카로운(_D, j) and not G.날카로운(_D, j, F=_F)

    for i_, k in enumerate(전환들):
        if not _전환(k):
            옆 = [k + d for d in (-1, 1, -2, 2) if k0 < k + d < k1 and _전환(k + d)]
            if 옆:
                전환들[i_] = 옆[0]
            elif any(_번쩍(k + d) for d in (0, -1, 1)):
                전환들[i_] = None                          # scene_cuts 가 번쩍임을 컷으로 잡았다 — 경계가 아니다(2026-09-29 20편)
    전환들 = sorted({x for x in 전환들 if x is not None})
    박자 = max(1, int(round(beat * fps)))
    최소 = max(1, int(round(0.35 * fps)))
    bs, at_cut = [k0], [머리 in ("새샷", "전환")]
    for m in 전환들 + [k1]:
        컷 = m != k1
        while m - bs[-1] > int(round(beat * 1.5 * fps)):
            bs.append(bs[-1] + 박자); at_cut.append(False)
        if m - bs[-1] >= 최소 or (컷 and m > bs[-1]):
            if 컷 and m - bs[-1] < 최소 and len(bs) > 1 and not at_cut[-1]:
                bs[-1], at_cut[-1] = m, True               # 격자 경계가 전환 바로 앞 — 격자를 전환으로 옮긴다
            else:
                bs.append(m); at_cut.append(컷)
    if bs[-1] != k1:
        if k1 - bs[-1] < 최소 and len(bs) > 1 and not at_cut[-1]:
            bs[-1] = k1                                 # 끝 격자 조각이 짧으면 합친다(옛 규칙과 같다)
        else:
            bs.append(k1); at_cut.append(False)
    at_cut[-1] = False

    # ★비트가 «놓친 원본 컷»에 걸치면 그 자리에서 쪼갠다 (2026-09-21 Deep87 실측: 어두운 술집
    #   장면의 298.9s 컷을 scene_cuts 가 놓쳐 비트 298.30~299.15 가 두 샷에 걸쳤고, 구도는 비트
    #   한가운데(앞 샷) 프레임으로 정해져 뒤 0.2초가 앞 샷 구도로 나갔다 — 이마만 보임).
    #   비트의 머리·꼬리 프레임이 다른 장면이면 그 사이 «이웃 프레임 차이가 가장 큰 프레임»이 전환이다(2026-09-28 —
    #   예전 0.05초 이분 탐색·round(,2)는 1~2프레임 늦었다). 그 봉우리가 전환 모양(어두운 장면도 잡히게 느슨하게)이
    #   아니면 서서히 바뀐 것 — 쪼개지 않는다(51편 25.99초 가짜 컷).
    _thr = box.get("same_scene_thr", 0.93)

    def _같은(u, v):
        return same_scene(frame_at(src, g.경계값(u), work, f"{idx:02d}k{u}"),
                          frame_at(src, g.경계값(v), work, f"{idx:02d}k{v}"), _thr)

    nb, nc = [bs[0]], [at_cut[0]]
    for k in range(len(bs) - 1):
        a, e = nb[-1], bs[k + 1]
        if e - a >= int(round(0.45 * fps)) and not _같은(a + 1, e - 1):
            안 = [c for c in range(a + 1, e) if 0 < c - _기점 < len(_D)]
            c = max(안, key=lambda x: _D[x - _기점]) if 안 else None
            if c is not None and _전환(c, 느슨=True):
                최소2 = max(1, int(round(0.2 * fps)))
                if c - a >= 최소2 and e - c >= 최소2:
                    nb.append(c); nc.append(True)
                elif c - a < 최소2 and len(nb) > 1:
                    nb[-1], nc[-1] = c, True             # 컷이 머리에 붙었다 — 앞 비트를 컷까지 늘린다
                elif e - c < 최소2 and k + 1 < len(bs) - 1:
                    bs[k + 1], at_cut[k + 1] = c, True   # 컷이 꼬리에 붙었다 — 다음 비트가 컷에서 시작한다
                else:
                    nb.append(c); nc.append(True)       # 짧아도 전환은 경계다(샷 둘이 한 구도를 나눠 쓰지 않게)
        nb.append(bs[k + 1]); nc.append(at_cut[k + 1])
    nb[-1], nc[-1] = k1, False
    # 같은 번호 겹침 정리(짧은 조각에서 앞 규칙들이 같은 자리를 두 번 넣을 수 있다)
    bk, ak = [nb[0]], [nc[0]]
    for x, y in zip(nb[1:], nc[1:]):
        if x > bk[-1]:
            bk.append(x); ak.append(y)
        elif y:
            ak[-1] = True
    if len(bk) < 2:
        bk, ak = [k0, k1], [at_cut[0], False]
    bs_k, at_cut = bk, ak
    bs = [g.경계값(x) for x in bs_k]                   # 시각 = 격자 경계값(프레임 번호가 원본)

    # ★★**1패스 — 비트마다 얼굴을 먼저 다 찾아 둔다.**
    #   예전에는 찾자마자 바로 구도를 정했는데, 얼굴 검출은 프레임마다 몇 픽셀씩
    #   흔들린다. 그 흔들림이 그대로 카메라에 실려 **화면이 떠는 것처럼 보였다.**
    #   먼저 모아서 궤적을 다듬은 뒤(smooth) 구도를 정한다 — `plan_pan` 은 이미
    #   그렇게 하고 있었는데 여기만 안 하고 있었다.
    경계들, 힌트, 자격들 = [], [], []
    nb = len(bs) - 1
    for k in range(nb):
        a, e = bs[k], bs[k + 1]
        km = (bs_k[k] + bs_k[k + 1]) // 2                 # 비트 가운데 프레임(번호)
        rgb = frame_at(src, g.경계값(km), work, f"{idx:02d}m{km}")
        경계들.append(가림경계(그림경계(rgb, W, H), seg, a, e, usable_h,   # ★비트(샷)마다 — 레터박스는 샷 단위로 나타난다
                               box["w"] / box["h"]))
        # ★자격 있는 얼굴만(점수·초점을 같은 프레임 얼굴과 견줌 · 작은 얼굴 제외) — 규칙은 얼굴고르기 한 곳(2026-09-29)
        #   fs[0] = 주인공 후보(점수가 넉넉한 얼굴 중 가장 큰 것) — 말하는 얼굴이 따로 정해지면 아래에서 그쪽이 주인공이다
        fs = 얼굴고르기(rgb, box, usable_h) if (rgb is not None and HAS_YN) else []
        자격들.append(list(fs))                            # 이 비트의 자격 얼굴 전부(주인공 아닌 얼굴 포함)
        # 얼굴 없는 샷의 자리 힌트 — 주인공 크기(6%)엔 못 미쳐도 확실한(점수 0.8↑) 작은 얼굴 · 잔무늬 세로 중심
        힌 = None
        if not fs and rgb is not None:
            작은 = [q for q in (_faces_yunet(rgb, 0.8) if HAS_YN else []) if q[1] + q[3] // 2 < usable_h]
            if 작은:
                힌 = ("얼굴", min(q[0] for q in 작은), min(q[1] for q in 작은),
                      max(q[0] + q[2] for q in 작은), max(q[1] + q[3] for q in 작은))
            else:
                힌 = ("잔무늬", None, _busy_center(rgb, usable_h)[1], None, None)
        힌트.append(힌)

    # 샷(전환과 전환 사이) — 다듬기·화자 잇기·빈 얼굴 채우기는 샷 안에서만
    샷들, _s = [], 0
    for k in range(1, nb + 1):
        if k == nb or at_cut[k]:
            샷들.append((_s, k)); _s = k

    # ★말하는 얼굴 (2026-10-03 — 위 «말하는 얼굴» 절). 얼굴을 잴 수 있을 만큼 큰 자격 얼굴이 둘 이상이고 말이 있는 비트만 잰다.
    말 = 말창(src) if HAS_YN else None
    잼들 = [None] * nb
    if 말:
        for k in range(nb):
            후보 = [q for q in 자격들[k] if q[2] >= 화자최소폭]
            if len(후보) >= 2 and any(min(b_, bs[k + 1]) > max(a_, bs[k]) for a_, b_ in 말):
                r = 입움직임(src, g, W, H, bs_k[k], bs_k[k + 1], 후보, 말)
                잼들[k] = [(q, s_, c_) for q, (s_, c_) in zip(후보, r)]
    화자들 = 화자고르기(잼들, 샷들)

    raw = []
    for k in range(nb):
        fs = 자격들[k]
        f, many = None, False
        if fs:
            # ★주인공 = 말하는 얼굴(정해졌으면) · 아니면 fs[0]. 담을 얼굴은 무리고르기 한 곳에서 —
            #   ★★둘 다 감싸는 것은 크기가 비슷할 때만(주인공 넓이 45%↑ — 뒤쪽 작은 얼굴 하나로 화면이 확 넓어지지 않게),
            #   ★★멀리 떨어진 둘은 «지금 확대 그대로 같이 들어갈 때만» 감싼다(감싼 상자가 넓어지면 둘 다 작아진다 —
            #   실측 가로 폭이 얼굴의 중앙 2.1배·최대 5.7배).
            주 = 화자들[k] if 화자들[k] is not None else fs[0]
            mains = 무리고르기(fs, 주, usable_h, box, W, 경계들[k])
            many = len(mains) > 1
            if many:
                x0 = min(q[0] for q in mains); y0 = min(q[1] for q in mains)
                x1 = max(q[0] + q[2] for q in mains)
                y1 = max(q[1] + q[3] for q in mains)
                # ★둘을 감싼 상자에는 눈이 없다 — 그 자리는 비워 둔다
                f = (x0, y0, x1 - x0, y1 - y0, None, None)
            else:
                f = mains[0]
        raw.append((f, many))

    # ★비트 «안» 에서 얼굴이 크게 움직이면 그 길 전체를 담는다 (2026-10-03 루키치177 229.7~236.7초 — 숙였다 일어나며
    #   «여보!» 를 외치는 남자: 얼굴이 0.3초 만에 y 30 → 490 으로 내려갔는데 구도는 비트 가운데 한 장의 얼굴로만 정해져
    #   비트 첫머리·끝에서 얼굴이 상자 밖이었다(232.9~233.5초 · 235.3~235.9초 — 옛 얼굴관문은 가운데 한 장만 봐서 못 잡음).
    #   같은 샷의 이웃 비트와 얼굴 자리가 얼굴 높이의 0.3배 넘게 다르면 그 비트의 처음·끝 프레임 얼굴을 더 보고, 길이
    #   얼굴의 1.4배 넘게 넓으면 그 길을 감싼 상자를 «무리» 처럼 담는다(조금 넓게 잡힌다). 이웃이 가만있으면 더 보지 않는다.
    샷번 = [0] * nb
    for i_, (s0, s1) in enumerate(샷들):
        for k in range(s0, s1):
            샷번[k] = i_

    def _중(q):
        return q[0] + q[2] / 2, q[1] + q[3] / 2
    for k in range(nb):
        f, many = raw[k]
        if many or bs_k[k + 1] - bs_k[k] < max(2, int(round(0.4 * fps))):
            continue
        if f is None:
            # 샷 첫 비트인데 가운데 프레임에 자격 얼굴이 없다(고개 돌림·숙임) — 처음·끝 프레임에서 찾는다
            #   (2026-10-03 Deep79 183.7초: 가운데 184.1초는 얼굴 없음 · 첫 183.8초·끝 184.5초엔 드러머 얼굴 → «얼굴 없는 비트» 로
            #   가서 첫 0.25초 입이 상자 밑변 밖이었다)
            if not at_cut[k]:
                continue
            찾음 = []
            for kk in (bs_k[k] + 1, bs_k[k + 1] - 2):
                rgb2 = frame_at(src, g.경계값(kk), work, f"{idx:02d}e{kk}")
                fs2 = 얼굴고르기(rgb2, box, usable_h) if rgb2 is not None else []
                if fs2:
                    찾음.append(fs2[0])
            if len(찾음) == 2 and not (abs(_중(찾음[1])[0] - _중(찾음[0])[0]) <= 2 * 찾음[0][3]
                                     and abs(_중(찾음[1])[1] - _중(찾음[0])[1]) <= 2 * 찾음[0][3]):
                찾음 = 찾음[:1]                             # 끝 프레임 얼굴이 딴 사람 자리 — 첫 얼굴만
            if 찾음:
                x0 = min(q[0] for q in 찾음); y0 = min(q[1] for q in 찾음)
                x1 = max(q[0] + q[2] for q in 찾음); y1 = max(q[1] + q[3] for q in 찾음)
                raw[k] = ((x0, y0, x1 - x0, y1 - y0, None, None), True) if len(찾음) > 1 else (찾음[0], False)
                if not 자격들[k]:
                    자격들[k] = list(찾음)
            continue
        이웃 = [raw[j][0] for j in (k - 1, k + 1) if 0 <= j < nb and 샷번[j] == 샷번[k] and raw[j][0] is not None]
        cx_, cy_ = _중(f)
        # 샷 첫 비트(원본 전환·조각 머리)는 이웃과 상관없이 늘 본다 — 새 샷은 숙인 채·움직이며 시작하는 일이 많고, 그 첫
        #   0.2~0.4초가 비트 가운데 얼굴로 정한 상자 밖이었다(회귀 재기 2026-10-03: 싱글50 21.4초 · 206 47.7초 · Deep76 374.5·378.3초
        #   · Deep79 183.7초 — 옛 계획에도 있던 자리를 촘촘한 얼굴관문이 «샷 첫머리 반 잘림» 으로 잡았다)
        if not at_cut[k] and not any(abs(_중(n)[0] - cx_) > 0.3 * f[3] or abs(_중(n)[1] - cy_) > 0.3 * f[3] for n in 이웃):
            continue
        길 = [f]
        for kk in (bs_k[k] + 1, bs_k[k + 1] - 2):
            rgb2 = frame_at(src, g.경계값(kk), work, f"{idx:02d}e{kk}")
            fs2 = 얼굴고르기(rgb2, box, usable_h) if rgb2 is not None else []
            # 같은 사람만 — 가운데 프레임의 자격 얼굴들 중 «가장 가까운 얼굴이 주인공 f» 인 얼굴만 f 의 이어짐으로 본다
            #   (2026-10-03 Deep14 185.4초: 2얼굴높이 안에 있던 옆 사람 얼굴을 합쳐 상자가 두 사람 사이로 가 둘 다 가장자리에 걸쳤다)
            def _짝(q):
                후 = 자격들[k] or [f]
                m = min(후, key=lambda r: (_중(r)[0] - _중(q)[0]) ** 2 + (_중(r)[1] - _중(q)[1]) ** 2)
                # 주인공과 한 얼굴 크기 안에 겹친 상자(같은 사람의 얼굴+귀 두 검출 — Deep76 355.6초)도 주인공이다
                return tuple(m[:4]) == tuple(f[:4]) or _같은자리(m, f, 1.0)
            near = [q for q in fs2 if abs(_중(q)[0] - cx_) <= 2 * f[3] and abs(_중(q)[1] - cy_) <= 2 * f[3]
                    and 0.6 <= q[3] / max(f[3], 1) <= 1.6 and _짝(q)]
            if near:
                길.append(min(near, key=lambda q: (_중(q)[0] - cx_) ** 2 + (_중(q)[1] - cy_) ** 2))
        x0 = min(q[0] for q in 길); y0 = min(q[1] for q in 길)
        x1 = max(q[0] + q[2] for q in 길); y1 = max(q[1] + q[3] for q in 길)
        if x1 - x0 > 1.4 * f[2] or y1 - y0 > 1.4 * f[3]:
            raw[k] = ((x0, y0, x1 - x0, y1 - y0, None, None), True)

    # 궤적 다듬기 — 얼굴이 없는 비트는 앞값으로 채우고 이동평균을 건다
    def _fill(v):
        out, last = [], None
        for x in v:
            last = x if x is not None else last
            out.append(last)
        first = next((x for x in out if x is not None), None)
        return [x if x is not None else first for x in out]

    # ★★**중심을 눈 쪽으로 당긴다.** 상자 중심은 머리 기울기·머리카락에 흔들리는데
    #   눈은 덜 흔들려서 화면이 안정된다. 다만 **눈에만 맡기지 않는다** — 옆모습이나
    #   가려진 얼굴에서 눈 검출이 한 번씩 밀리기 때문에 상자 중심과 섞는다
    #   (`eye_center` 가 그 비율, 1.0 이면 완전히 눈 기준).
    ew = box.get("eye_center", 0.0)

    def _cx(f):
        c = f[0] + f[2] / 2
        return c if not (ew and f[4] is not None) else c * (1 - ew) + f[4] * ew

    def _cy(f):
        c = f[1] + f[3] / 2
        return c if not (ew and f[5] is not None) else c * (1 - ew) + f[5] * ew

    has = any(f for f, _ in raw)
    # ★샷(전환과 전환 사이)마다 따로 채우고 다듬는다 (2026-09-28 «경계 구도» 클래스) — 조각 전체를 한 줄로
    #   이동평균하면 전환 뒤 첫 비트 목표가 앞 샷 얼굴 자리 쪽으로 끌려가 새 샷 얼굴이 가장자리에 걸렸다. (샷들은 위에서 나눴다)
    cxs, cys, fhs = [None] * len(raw), [None] * len(raw), [None] * len(raw)
    # ★얼굴 없는 샷의 목표 (2026-09-29 점심이네17 숲 와이드 · 29 밤 한강) — 예전엔 «지금 구도를 지킨다» 였는데 조각 첫 샷이면
    #   지킬 구도가 없어 기본값(가운데 · 위에서 10%)으로 가서 나무 윗부분·빈 밤하늘만 나왔다. 앞 샷 얼굴 확대(최대 1.8배)를
    #   얼굴 없는 새 샷에 그대로 끌고 오는 것도 같은 구멍이다. 이제 샷마다 «사람이 있는 자리»를 잰다:
    #   확실한 작은 얼굴(점수 0.8↑ · 주인공 크기 6% 미만 — 17편 숲 34x43)이 있으면 그 무리를, 없으면 잔무늬가 몰린 세로 자리
    #   (하늘·벽은 밋밋하다)를 가운데 둔다. 확대는 기본값(1+(최대−1)×0.4) — 얼굴이 없으니 더 당길 까닭이 없다.
    무얼굴 = [None] * len(raw)
    _sw = box.get("smooth_win", 3)
    for s0, s1 in 샷들:
        조 = raw[s0:s1]
        if not any(f for f, _ in 조):
            if not (at_cut[s0] or (s0 == 0 and prev is None)):
                continue                                 # 원본에서 이어지는 샷 — 얼굴을 잠깐 놓친 것이다, 지금 구도를 지킨다(cur)
            얼 = [h for h in 힌트[s0:s1] if h and h[0] == "얼굴"]
            if 얼:
                목 = ("얼굴", (min(h[1] for h in 얼) + max(h[3] for h in 얼)) / 2,
                     (min(h[2] for h in 얼) + max(h[4] for h in 얼)) / 2)
            else:
                ys_ = sorted(h[2] for h in 힌트[s0:s1] if h)
                목 = ("잔무늬", None, ys_[len(ys_) // 2]) if ys_ else None
            무얼굴[s0:s1] = [목] * (s1 - s0)
            continue                                     # 이 샷엔 자격 얼굴이 없다 — 아래에서 무얼굴 목표로
        xs = _fill([_cx(f) if f else None for f, _ in 조])
        ys = _fill([_cy(f) if f else None for f, _ in 조])
        hs = _fill([f[3] if f else None for f, _ in 조])
        if not globals().get("_SMOOTH_OFF"):     # 견주기용 — 평소에는 켜져 있다
            # ★스무딩 창을 config 로 (2026-09-10 사장님 «튀는 구간 없게»): 창이 넓을수록
            #   얼굴 검출 흔들림이 더 눌려 카메라가 안정된다. 기본 3, 숨은기록은 5.
            xs, ys, hs = smooth(xs, _sw), smooth(ys, _sw), smooth(hs, _sw)
        cxs[s0:s1], cys[s0:s1], fhs[s0:s1] = xs, ys, hs

    out, cur = [], prev
    for k in range(len(bs) - 1):
        a, e = bs[k], bs[k + 1]
        f, many = raw[k]
        fh = fhs[k]

        if fh:
            z = usable_h / max(fh / (0.62 if many else face_ratio), 1)
        elif 무얼굴[k]:
            z = 1.0 + (zmax - 1.0) * 0.4           # 얼굴 없는 샷 — 기본 확대(앞 샷 얼굴 확대를 끌고 오지 않는다)
        elif cur:
            z = usable_h / max(cur[1], 1)          # 못 찾으면 지금 크기를 지킨다
        else:
            z = 1.0 + (zmax - 1.0) * 0.4
        z = max(zmin, min(zmax, z))
        # ★목표 확대는 «이 비트의 얼굴이 들어오는 값»을 넘지 않는다(2026-09-21 Deep87).
        #   안 그러면 목표(zmin 1.10)로 슬금슬금 다가갔다가 담기 관문에 걸려 1.00 으로 되튀는
        #   톱니가 생긴다(실측 1.00→1.13→1.00). zmin 아래로 내려가도 된다 — 원본이 초근접이면
        #   우리가 더 확대할 이유가 없다.
        if f:
            z = min(z, max(1.0, usable_h / max(f[3] * 1.22, 1)))

        # ★원본 화면 전환(at_cut)에서는 걸음 제한을 아예 풀고 새 샷 얼굴 자리로 바로 연다 (2026-10-03 루키치162 «경계 구도» 2차).
        #   예전엔 전환에서도 제한을 «완화폭(relief 1.8~2.5배)» 만큼만 풀었다 — 흰 배경 인터뷰 두 사람을 번갈아 보여 주는
        #   샷(162 원본 115.8·118.8·121.0…초, 얼굴이 x 750 ↔ 1135 로 갈림)에서 상자가 비트당 57px 씩만 옮겨 가, 새 샷마다
        #   얼굴이 상자 가장자리에 붙은 채 열리고(담기는 «안에만 있으면» 통과) 다음 비트들에서 천천히 가운데로 왔다.
        #   원본이 이미 앵글을 바꾼 프레임이라 우리가 같이 바꿔도 튀지 않는다 — 제한은 «같은 샷 안» 의 움직임에만 건다.
        # ★말하는 얼굴이 지금 상자 밖이면(같은 샷 안에서 화자가 바뀜) 걸음 제한을 풀고 한 번에 옮긴다 (2026-10-03 루키치170
        #   294~298초 두 남자 투샷 — 둘 사이 963px 이 680px 상자에 안 들어가는데, «같은 샷 안 얼굴 바뀜» 걸음(비트당 104px)
        #   으로 7비트를 걸어 말하는 사람이 2.5초 동안 상자 밖이었다). 아래 빈 구도처럼 비트 안에서 짧게 흘러간다(튐 아님).
        화자빈 = bool(cur) and not at_cut[k] and 화자들[k] is not None and not _얼굴든(cur, 화자들[k])
        걸음 = None if (at_cut[k] or 화자빈) else cur
        lz = dz_max
        if 걸음:                                    # 한 비트에 허용한 만큼만 움직인다
            pz = usable_h / max(cur[1], 1)
            z = max(pz * (1 - lz), min(pz * (1 + lz), z))

        bh = int(usable_h / z)
        bw = int(bh * box["w"] / box["h"])
        if bw > W:
            bw, bh = W, int(W * box["h"] / box["w"])
        bh = min(bh, usable_h)

        # ★★**크기는 비트 시작에 계단처럼 바뀐다**(crop 의 w·h 는 시간 표현식을 못 쓴다).
        #   그래서 미세한 변화까지 반영하면 매 비트마다 화면이 자잘하게 튄다.
        #   **눈에 안 띌 만큼 작은 변화면 앞 크기를 그대로 유지한다** — 움직임은
        #   위치 보간이 맡고, 크기는 바꿀 값어치가 있을 때만 바꾼다.
        hold = box.get("hold_zoom", 0.0)
        if 걸음 and hold and abs(bh - cur[1]) <= cur[1] * hold:
            bw, bh = cur[0], cur[1]

        if fh and at_cut[k] and f:
            # ★샷 첫 비트는 그 비트의 얼굴 자리 그대로(2026-10-03) — 다듬기(이동평균)는 같은 샷의 뒤 비트들과 섞어, 걷는
            #   사람이면 새 샷이 얼굴 앞쪽이 아니라 뒤따라오는 자리에서 열린다. 전환 프레임에서는 흔들림이 보이지 않는다.
            tx = _cx(f) - bw / 2
            ty = _cy(f) - bh * face_y
        elif fh:                                 # ★다듬은 궤적을 쓴다(원 검출값이 아니라)
            tx = cxs[k] - bw / 2
            ty = cys[k] - bh * face_y
        elif 무얼굴[k]:
            종, hx, hy = 무얼굴[k]
            tx = (W - bw) / 2 if hx is None else hx - bw / 2
            ty = hy - bh * (face_y if 종 == "얼굴" else 0.5)
        elif cur:
            tx, ty = cur[2] + (cur[0] - bw) / 2, cur[3] + (cur[1] - bh) / 2
        else:
            tx, ty = (W - bw) / 2, usable_h * 0.10

        lp = dp_max
        if 걸음:
            mx, my = lp * W, lp * usable_h
            tx = max(cur[2] - mx, min(cur[2] + mx, tx))
            ty = max(cur[3] - my, min(cur[3] + my, ty))
        tx = max(0, min(tx, W - bw))
        ty = max(0, min(ty, usable_h - bh))

        # ★★크기와 위치를 **합쳐서** 한 번 더 제한한다. 둘을 따로 제한하면 한 비트에서
        #   크기 10.2% + 위치 11.2% 가 같이 움직인다(실측, 40.12초) — 각각은 상한 안이지만
        #   보는 사람에게는 한 번의 큰 변화다. **레퍼런스는 한 번의 변화가 4% 뿐이다.**
        #   넘치면 목표를 앞 구도 쪽으로 당긴다 — 방향은 지키고 크기만 줄인다.
        if 걸음 and box.get("beat_budget", True):
            budget = dz_max
            used = (abs(bh - cur[1]) / max(cur[1], 1)
                    + max(abs(tx - cur[2]) / max(W, 1),
                          abs(ty - cur[3]) / max(usable_h, 1)))
            if budget > 0 and used > budget:
                f = budget / used
                bh = max(1, int(round(cur[1] + (bh - cur[1]) * f)))
                bw = int(bh * box["w"] / box["h"])
                if bw > W:
                    bw, bh = W, int(W * box["h"] / box["w"])
                bh = min(bh, usable_h)
                tx = max(0, min(cur[2] + (tx - cur[2]) * f, W - bw))
                ty = max(0, min(cur[3] + (ty - cur[3]) * f, usable_h - bh))

        # ★최종 관문 — 그림경계 안 · 얼굴 담기 (변화 제한·예산보다 뒤에 걸어 이것이 이긴다)
        vx0, vy0, vx1, vy1 = 경계들[k]
        # ★얼굴 담기가 변화 제한을 이기는 것은 «따라갈 값어치가 있는 얼굴»일 때만이다.
        #   여러 명이 나오는 장면은 비트마다 다른 얼굴이 «가장 큰 얼굴»로 잡힌다 — 그때마다
        #   담으면 카메라가 좌우로 휘둘린다(2026-09-21 Deep91 조각4 실측: x 163→605→943→377).
        #   ① 첫 비트 ② 원본 컷 ③ 앞 비트와 같은 얼굴(중심이 얼굴 한 개 폭 안) ④ 크기가 아예
        #   안 맞는 초근접 — 이 넷일 때만 담는다. 그 밖(같은 샷 안에서 얼굴이 바뀜)은 예전처럼
        #   제한된 걸음으로 다가간다 — 경계 안에 두는 것은 언제나 한다.
        fk = raw[k][0]
        담을얼굴 = None
        # ⑤ 지금 구도에 이 비트의 자격 얼굴이 «하나도» 없으면 다가가지 않고 담는다 (2026-09-29 점심이네15 89.6~92.5 초점
        #   옮김 샷 · 11편 213~217 고개 숙임) — 걸음 제한은 «지금 보이는 사람» 을 두고 휘둘리지 않으려는 것인데, 아무도 안
        #   보이는 구도를 지킬 까닭은 없다. 예전엔 비트당 5.4% 씩 2.5초를 걸어 말하는 얼굴이 그동안 반쯤 잘렸다.
        빈구도 = bool(cur) and bool(자격들[k]) and not any(_얼굴든(cur, q) for q in 자격들[k])
        빈구도 = 빈구도 or 화자빈                      # 말하는 사람이 안 보이는 구도도 지킬 까닭이 없다
        if fk:
            앞 = raw[k - 1][0] if k else None
            같은 = bool(앞) and abs((fk[0] + fk[2] / 2) - (앞[0] + 앞[2] / 2)) <= max(fk[2], 앞[2]) \
                and abs((fk[1] + fk[3] / 2) - (앞[1] + 앞[3] / 2)) <= max(fk[3], 앞[3])
            if cur is None or at_cut[k] or 같은 or fk[3] * 1.22 > bh or 빈구도:
                담을얼굴 = fk
        bw, bh, tx, ty, 담김 = 담기(bw, bh, tx, ty, 담을얼굴, 경계들[k], usable_h,
                                   box["w"] / box["h"])
        if fk and 담을얼굴 is None:
            담김 = None                          # 따라가지 않기로 한 얼굴 — 게이트 대상이 아니다
        elif 담을얼굴 and cur and not at_cut[k] and not (fk[3] * 1.22 > cur[1]) and not 빈구도:
            # 같은 샷 안에서 같은 얼굴을 따라잡는 중 — 한 번에 뛰지 않고 컷 완화폭(relief)만큼만 간다
            mx, my = dp_max * relief * W, dp_max * relief * usable_h
            tx2 = int(max(cur[2] - mx, min(cur[2] + mx, tx)))
            ty2 = int(max(cur[3] - my, min(cur[3] + my, ty)))
            tx2 = max(vx0, min(tx2, vx1 - bw)); ty2 = max(vy0, min(ty2, min(vy1, usable_h) - bh))
            if (tx2, ty2) != (tx, ty):
                tx, ty, 담김 = tx2, ty2, None    # 아직 따라가는 중 — 다음 비트에 마저 간다
        assert vx0 <= tx and tx + bw <= vx1 and vy0 <= ty and ty + bh <= min(vy1, usable_h), \
            f"crop 이 그림경계 밖이다 — 비트 {k} crop {bw}x{bh}@{tx},{ty} 경계 {경계들[k]} (검은 띠가 박힌다)"

        # 비트 안에서는 앞 구도 중심에서 이 목표로 흘러간다 — 계단이 아니라 움직임이 되게
        # ★단 원본 화면 전환(조각 머리 포함)에서는 흘러오지 않고 목표 구도로 바로 연다 (2026-09-28 «경계 구도» 클래스 —
        #   샷이 바뀌었는데 앞 샷 crop 중심에서 출발하면 새 샷 첫 프레임들이 앞 구도를 끌고 온다. 전환이 크기·자리
        #   바뀜을 가려 주는 것은 «바로 그 프레임» 뿐이다).
        if cur and not at_cut[k]:
            sx = max(vx0, min(cur[2] + (cur[0] - bw) / 2, vx1 - bw))
            sy = max(vy0, min(cur[3] + (cur[1] - bh) / 2, min(vy1, usable_h) - bh))
            if 담을얼굴 and 담김 and not 빈구도:     # 빈 구도에서 넘어갈 때는 샷 한가운데라 뛰지 않고 흘러간다(튐 금지)
                # 시작 위치도 얼굴을 담는다 — 원본 컷에서 크기가 바뀐 비트는 흘러오지 않고 제자리에서 연다
                fx, fy, fw, fh = 담을얼굴[:4]
                if not (sy <= fy + fh * 0.15 and sy + bh >= fy + fh * 0.98
                        and sx <= fx + fw * 0.1 and sx + bw >= fx + fw * 0.9):
                    sx, sy = tx, ty
        else:
            sx, sy = tx, ty
        # ★영구 관문 (2026-09-28 싱글48 38.05초 — 이음매 뒤 말하는 얼굴이 1.2초 왼쪽 끝에 반쯤 걸렸다): 전환·조각 머리
        #   비트는 «시작 구도» 에 얼굴이 담겨야 한다. 예전 게이트는 목표 구도만 봤고, 따라가지 않기로 한 얼굴(face_in
        #   None)은 아예 안 봤다 — 머리 비트가 «따라가지 않음» 으로 빠져 통과했다.
        if at_cut[k] and 담을얼굴 and 담김:
            fx, fy, fw, fh = 담을얼굴[:4]
            assert (sy <= fy + fh * 0.15 and sy + bh >= fy + fh * 0.98
                    and sx <= fx + fw * 0.1 and sx + bw >= fx + fw * 0.9), \
                (f"조각 {idx} 비트 {k}(원본 프레임 {bs_k[k]}): 전환 직후 시작 구도에 얼굴이 없다 — "
                 f"시작 crop {bw}x{bh}@{int(sx)},{int(sy)} · 얼굴 {tuple(int(v) for v in 담을얼굴[:4])} (framing.plan_beats)")
        dur = max(e - a, 0.05)
        if 빈구도 and cur and not at_cut[k]:
            # ★빈 구도·화자 바뀜에서 얼굴로 가는 흐름은 0.5초 안에 끝낸다 (2026-10-03 루키치177 235.3초 — 숙였다 일어난 사람에게
            #   0.83초 비트 전체로 흘러가 얼굴이 0.6초 동안 상자 밖이었다. 얼굴관문 «얼굴 잘림» 한계 0.5초와 맞춘다).
            dur = min(dur, 0.5)
        if abs(sx - tx) < 1.5 and abs(sy - ty) < 1.5:
            vf = f"crop={bw}:{bh}:{int(tx)}:{int(ty)}"
        else:
            # ★★**선형으로 옮기면 떨린다.** 비트가 바뀔 때마다 카메라가 등속으로
            #   출발해 등속으로 멈추므로 시작·끝에서 속도가 툭 끊긴다 —
            #   0.85초마다 그러니 화면이 잘게 떠는 것처럼 보인다.
            #   **smoothstep(3u²-2u³)** 으로 양끝을 눕히면 이어 붙은 듯 흐른다.
            u = f"min(t/{dur:.2f},1)"
            ease = u if box.get("ease") == "linear" else f"({u}*{u}*(3-2*{u}))"
            # ★반 픽셀로 움직인다 (2026-09-29 점심이네27 229.14~231.48 «3프레임 주기 계단»). crop 의 x·y 는 정수이고 yuv420 은
            #   짝수로 내림된다(exact=0) — 20장에 21px 가는 느린 팬이 원본 2px(출력 3.8px) 걸음으로 뛰고 19장 중 9장은 멈췄다.
            #   2배(bicubic — 선명도 82.1 vs 지금 80.8, bilinear 는 56.6 으로 흐려진다)로 키운 뒤 exact=1 로 자르면 원본 0.5px
            #   걸음이 되어 멈춤 1/19 · 최대 걸음 3.1px 로 ease 곡선을 그대로 따른다. 움직이는 비트만 — 멈춘 비트는 예전 그대로.
            vf = (f"scale=iw*2:ih*2:flags=bicubic,crop={2 * bw}:{2 * bh}:"
                  f"x='2*({sx:.0f}+({tx - sx:.0f})*{ease})':"
                  f"y='2*({sy:.0f}+({ty - sy:.0f})*{ease})':exact=1")
        vf += f",scale={box['w']}:{box['h']}:flags=lanczos"
        if box.get("mirror"):
            vf += ",hflip"

        out.append((a, e, vf, {"zoom": round(usable_h / max(bh, 1), 2), "at_cut": at_cut[k],
                               "face": bool(raw[k][0]), "face_in": 담김,
                               "bounds": 경계들[k],
                               "crop": (bw, bh, int(tx), int(ty)),
                               "시작crop": (bw, bh, int(sx), int(sy)),
                               # 말하는 얼굴(정해졌을 때 · 비트 가운데 프레임 자리) — 얼굴관문이 실제 상자 궤적에서 다시 본다
                               "화자": tuple(int(v) for v in 화자들[k][:4]) if 화자들[k] is not None else None,
                               "f0": bs_k[k], "f1": bs_k[k + 1]}))     # 원본 프레임 번호 [f0, f1)
        cur = (bw, bh, int(tx), int(ty))
    return out


_크기캐시 = {}


def _크기(src):
    """원본 가로·세로 (ffprobe · 한 편에 한 번)."""
    if src not in _크기캐시:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", src], capture_output=True, text=True)
        try:
            w, h = (int(x) for x in r.stdout.strip().split("\n")[0].split(",")[:2])
        except Exception:
            w, h = 1920, 1080
        _크기캐시[src] = (w, h)
    return _크기캐시[src]


def _가로몫(c, q, 넓힘=0.0, W=None):
    """얼굴 q 의 가로(양옆을 얼굴 폭 × 넓힘 만큼 넓힌 «머리 폭», 원본 화면 W 안으로 자름) 중 crop c 안에 든 몫."""
    w, x = c[0], c[2]
    a, b = q[0] - q[2] * 넓힘, q[0] + q[2] * (1 + 넓힘)
    if W:
        a, b = max(0, a), min(W, b)
    return max(0, min(x + w, b) - max(x, a)) / max(b - a, 1)


def _온전(c, q, usable_h=None, W=None, 넓힘=0.0, 몫=0.85):
    """crop c=(w,h,x,y) 안에 얼굴 q 가 «온전히» 보이는가.
    가로 — 얼굴 상자(넓힘>0 이면 양옆을 얼굴 폭×넓힘 만큼 넓힌 «머리 폭» — 검출 상자는 귀·머리카락을 뺀 얼굴만이다)의 몫 이상.
    세로 — 눈(상자 위 30%)부터 입(85%)까지. 원본 화면 끝·자막띠(usable_h) 밖으로 나간 몫은 어차피 못 담으니 요구하지 않는다.
    얼굴이 crop 보다 크면(원본 초근접) 얼굴 가운데가 들면 온전으로 본다."""
    w, h, x, y = c[:4]
    fx, fy, fw, fh = q[:4]
    if fw * (1 + 2 * 넓힘) > w * 0.95 or fh > h * 0.9:
        return x <= fx + fw / 2 <= x + w and y <= fy + fh / 2 <= y + h
    아래 = fy + fh * 0.85 if usable_h is None else min(fy + fh * 0.85, usable_h - 2)
    return _가로몫(c, q, 넓힘, W) >= 몫 and y <= max(0, fy + fh * 0.3) and y + h >= 아래


def _머리온전(c, q, usable_h=None, W=None):
    """샷 첫머리용 엄한 자 — 머리 폭(얼굴 상자 양옆 0.2배씩)의 90% 이상 = 얼굴 상자 바깥 여백이 얼굴 폭의 6% 이상.
    ★2026-10-03 루키치162 — 새 샷이 얼굴 상자를 crop 안쪽 끝에 붙인 채(여백 얼굴 폭의 0~4% · 162 원본 115.8초 7px/166px)
      열려 화면에서는 머리가 반쯤 잘려 보였는데, 얼굴 상자만 재는 자(옛 60% · 아래 85%)로는 다 든 것이었다.
      샷 한가운데까지 이 자를 쓰면 정상 구도도 걸린다(172 288.96초 여백 5.9% · 326.08초 11% 를 보고 정함) — 첫머리만."""
    return _온전(c, q, usable_h, W, 넓힘=0.2, 몫=0.9)


def 얼굴관문(src, plan, idx, work, usable_h, 확실=0.8, 한계초=0.5, 준확실=0.72, 머리초=0.5, 머리한계초=0.2, 간격=2):
    """★영구 관문 — 구운 상자 «궤적 전체» 에서 얼굴이 제대로 담겼는가. 걸림 목록을 돌려준다(build 가 멈춘다).

    잰다: 조각의 원본 프레임을 간격(2)장마다 다 본다 — 비트 «안» 의 움직이는 상자(시작crop → crop, vf 와 같은 smoothstep)를
    그 프레임 시각대로 다시 그려 견준다. 얼굴은 계획(plan_beats·얼굴고르기)과 «다른 자»: 검출기가 확신하는 얼굴 전부(점수
    0.8↑ · 세로 6%↑ · 초점 밖 제외)와 준확실 얼굴(0.72↑ — 필터 낀 영상통화 칸, 2026-10-02 루키치211).
    걸림 종류
      «얼굴 잘림»  확실한 얼굴이 화면에 있는데 상자 안에 «온전한»(얼굴 상자 가로 85%↑·눈~입 세로 안 — _온전) 얼굴이 하나도 없는 시간이
                   연달아 한계초(0.5초)를 넘는다 — 얼굴이 아예 밖이거나 가장자리에 반쯤 걸쳐 있다.
      «샷 첫머리 반 잘림»  원본 화면 전환 뒤 머리초(0.5초) 안에서 머리까지 온전한 얼굴(_머리온전 — 여백 얼굴 폭 6%↑)이
                   하나도 없는 시간이 머리한계초(0.2초) 이상 — 새 샷이 앞 샷 구도를 끌고 와 얼굴이 가장자리에 걸친 채 열린 것.
      «화자 밖»    계획이 말하는 얼굴(info 화자)로 정한 사람이 «말하는 동안»(말창) 상자 안에 온전하지 않은 시간이 한계초를 넘는다 —
                   가림·경계·걸음 제한 같은 다른 길이 화자를 밀어낸 것.

    ★2026-10-03 다시 짬 (루키치162 1차 굽기 18.5·21.5·36.5초 얼굴 반 잘림 · 177 숙였다 일어나는 사이 · 걸림 0 으로 통과):
      예전 관문은 비트마다 «가운데 프레임 한 장» 만 «목표 crop» 으로 봤다. 비트 안에서 상자는 시작crop 에서 목표로 흘러가므로
      가운데 프레임의 실제 상자는 목표와 다르고, 비트 첫머리(새 샷이 앞 구도로 열리는 바로 그 0.4초)는 아예 안 봤다.
      또 «가로 60% 만 들면 든 것» 이라 가장자리에 반쯤 걸친 얼굴도 통과했다(162: 목표 crop 에서는 얼굴이 안쪽 끝에 붙어 있었다).
    ★2026-09-29 (점심이네 «가짜 얼굴») — 계획이 고른 얼굴만 보던 build 관문은 계획이 벽 무늬·흐린 뒤통수를 고르면 통과했다.
      여러 얼굴 중 하나만 온전히 들어도 통과다(멀리 떨어진 사람은 한 사람만 담는 것이 규칙 — 무리고르기)."""
    if not HAS_YN or not plan:
        return []
    from . import 프레임격자 as G
    g = G.얻기(src)
    W, H = _크기(src)
    fps = g.fps
    a0 = min(i["f0"] for _, _, _, i in plan)
    a1 = max(i["f1"] for _, _, _, i in plan)
    bi = 0
    표 = []                                   # (원본 프레임, 실제 crop, 얼굴들, 비트 번호, 샷 머리로부터 초)
    샷시작 = plan[0][3]["f0"] if plan[0][3].get("at_cut") else None
    for k, f in _반프레임(src, g, W, H, a0, a1):
        while bi + 1 < len(plan) and k >= plan[bi][3]["f1"]:
            bi += 1
            if plan[bi][3].get("at_cut"):
                샷시작 = plan[bi][3]["f0"]
        a, e, vf, info = plan[bi]
        if (k - info["f0"]) % 간격:
            continue
        bw, bh, tx, ty = info["crop"][:4]
        _, _, sx, sy = (info.get("시작crop") or info["crop"])[:4]
        import re as _re
        _m = _re.search(r"min\(t/([\d.]+),1\)", vf or "")             # vf 가 쓴 흐름 길이 그대로(빈 구도는 0.5초로 줄인다)
        dur = float(_m.group(1)) if _m else float(f"{max(e - a, 0.05):.2f}")
        u = min(((k - info["f0"]) / fps) / dur, 1.0)
        ease = u if "(3-2*" not in vf else u * u * (3 - 2 * u)
        c = (bw, bh, sx + round(tx - sx) * ease, sy + round(ty - sy) * ease)
        ds = [d for d in _검출(f, 0.6) if d[1] + d[3] / 2 < usable_h and d[3] >= usable_h * 0.06]
        if len(ds) > 1:                         # 초점 밖(흐린 앞사람·잠든 뒷사람)은 담지 않아도 된다 — 가장 선명한 것의 0.18배 아래
            import cv2 as _cv
            gray = _cv.cvtColor(np.ascontiguousarray(f), _cv.COLOR_RGB2GRAY)
            sh = [_선명도(gray, tuple(int(v / 2) for v in d[:4]) + ((d[4] + d[6]) / 4, (d[5] + d[7]) / 4, float(d[14]),
                                                                   float(np.hypot(d[6] - d[4], d[7] - d[5])) / 2))[0]
                  for d in ds]
            ds = [d for d, s in zip(ds, sh) if s >= max(sh) * 0.18]
        qs = [(float(d[0]), float(d[1]), float(d[2]), float(d[3]), float(d[14])) for d in ds]
        머리 = (k - 샷시작) / fps if 샷시작 is not None else None
        표.append((k, c, qs, bi, 머리))

    def _iou(p, q):
        ix = max(0, min(p[0] + p[2], q[0] + q[2]) - max(p[0], q[0]))
        iy = max(0, min(p[1] + p[3], q[1] + q[3]) - max(p[1], q[1]))
        n = ix * iy
        return n / max(p[2] * p[3] + q[2] * q[3] - n, 1)

    Δ = 간격 / fps
    말 = 말창(src)
    상태 = []
    for j, (k, c, qs, bi, 머리) in enumerate(표):
        이웃 = [q for jj in (j - 1, j + 1) if 0 <= jj < len(표) for q in 표[jj][2] if q[4] >= 준확실]
        준 = [q for q in qs if q[4] >= 준확실 or any(_iou(q, r) >= 0.3 for r in 이웃)]
        확 = [q for q in qs if q[4] >= 확실]
        온 = (not 확) or any(_온전(c, q, usable_h, W) for q in 확 + 준)
        머리온 = (not 확) or any(_머리온전(c, q, usable_h, W) for q in 확 + 준)
        화 = plan[bi][3].get("화자")
        화밖 = False
        if 화 and _말중(말, g.시작(k), 0.0):             # 말하는 동안만 센다(말 앞뒤 빈 시간에 다른 사람을 비춰도 된다)
            m = [q for q in 확 + 준 if _같은자리(q, 화)]
            화밖 = bool(m) and not any(_온전(c, q, usable_h, W) for q in m)
        상태.append((not 온, (not 머리온) and 머리 is not None and 머리 < 머리초, 화밖))

    걸 = []
    for 종, 자리, 한계 in (("얼굴 잘림", 0, 한계초), ("샷 첫머리 반 잘림", 1, 머리한계초 - 1e-6), ("화자 밖", 2, 한계초)):
        j = 0
        while j < len(표):
            if not 상태[j][자리]:
                j += 1
                continue
            j1 = j
            while j1 + 1 < len(표) and 상태[j1 + 1][자리] and 표[j1 + 1][0] - 표[j1][0] <= 간격:
                j1 += 1
            길이 = (j1 - j + 1) * Δ
            if 길이 > 한계:
                k, c, qs, bi, _ = 표[j]
                걸.append({"조각": idx, "종류": 종, "t0": round(g.시작(표[j][0]), 2), "t1": round(g.시작(표[j1][0]) + Δ, 2),
                          "crop": tuple(int(v) for v in c),
                          "얼굴": [tuple(int(v) for v in q[:4]) + (round(q[4], 2),) for q in qs if q[4] >= 확실]})
            j = j1 + 1
    걸.sort(key=lambda x: x["t0"])
    return 걸


def plan_frame(src, seg, idx, W, H, usable_h, box, work, prev=None):
    """한 구간의 crop 창을 정한다.

    - 확대율: punch 가 높을수록 크게. 레퍼런스 실측 범위 안에서만 움직인다
    - 위치: 얼굴을 중심에 둔다. 못 찾으면 잔무늬가 많은 곳, 그것도 없으면 중앙
    """
    zmin, zmax = box.get("zoom_range", [1.10, 1.80])
    face_ratio = box.get("face_ratio", 0.42)     # 얼굴이 화면 세로에서 차지할 비율
    face_y = box.get("face_y", 0.40)             # 얼굴 중심을 화면 세로 어디에 둘지

    how, face, group = "중앙", None, None
    경계 = (0, 0, W, H)
    if box.get("follow_face"):
        frames = frames_of(src, seg, work, f"{idx:02d}")
        if frames:
            경계 = 그림경계(frames[len(frames) // 2], W, H)
        if HAS_YN:
            for a in frames:
                fs = 얼굴고르기(a, box, usable_h)       # 가짜·흐린 얼굴을 거른다 · fs[0] = 주인공 (2026-09-29)
                if fs:
                    경계 = 그림경계(a, W, H)
                    face = fs[0]
                    # ★여러 명이면 **다 담아야 한다.** 하나만 골라 61% 로 맞추면
                    #   나머지가 프레임 밖으로 나간다 — 세 사람 장면이 전부 1.8배가 됐다.
                    if len(fs) > 1:
                        x0 = min(f[0] for f in fs); y0 = min(f[1] for f in fs)
                        x1 = max(f[0] + f[2] for f in fs)
                        y1 = max(f[1] + f[3] for f in fs)
                        group = (x0, y0, x1 - x0, y1 - y0)
                    how = f"얼굴 {len(fs)}개"
                    break
        if face is None and frames:
            # ★얼굴을 못 찾으면 **앞 구도를 그대로 잇는다.** 잔무늬로 새로 잡으면
            #   엉뚱한 데를 짚어 튄다 — 못 찾은 것이 화면을 옮길 이유가 되지는 않는다.
            if prev:
                pw, ph, px, py = prev[:4]
                경계 = 가림경계(경계, seg, seg["t0"], seg["t1"], usable_h, box["w"] / box["h"])
                pw, ph, px, py, _ = 담기(pw, ph, px, py, None, 경계, usable_h, box["w"] / box["h"])
                vf = (f"crop={pw}:{ph}:{px}:{py},"
                      f"scale={box['w']}:{box['h']}:flags=lanczos")
                if box.get("mirror"):
                    vf += ",hflip"
                return vf, {"zoom": round(box["w"] / max(pw, 1), 2),
                            "how": "얼굴 못 찾음 · 앞 구도 이음",
                            "crop": (pw, ph, px, py),
                            "run": (prev[4] if len(prev) > 4 else 0) + 1}
            bx, by = _busy_center(frames[len(frames) // 2], usable_h)
            face, how = (bx - 60, by - 80, 120, 160), "잔무늬"

    # ★확대율은 punch 가 아니라 **얼굴 크기**가 정한다.
    #   punch 로만 잡았더니 고른 구간이 다 punch 7~10 이라 전부 1.5~1.8배가 됐고
    #   얼굴이 화면에 꽉 차 이마가 잘렸다. 레퍼런스는 어깨까지 들어온다.
    if group:
        # 여러 명 — 무리 전체가 화면의 78% 안에 들어오게 잡는다
        z = min(usable_h / max(group[3] / 0.62, 1), W / max(group[2] / 0.80, 1) * (H / W))
        z = max(zmin, min(zmax, z))
        face = group
        how += " · 무리"
    elif face:
        want_h = face[3] / face_ratio            # 이만큼 보이면 얼굴 비율이 맞는다
        z = usable_h / max(want_h, 1)
        punch = seg.get("punch", 5)
        z *= 1.0 + 0.04 * max(0, punch - 7)      # 결정적 대사면 살짝 더
        z = max(zmin, min(zmax, z))
    else:
        z = 1.0 + (zmax - 1.0) * 0.4

    base_h = int(usable_h / z)
    base_w = int(base_h * box["w"] / box["h"])
    if base_w > W:
        base_w = W
        base_h = int(base_w * box["h"] / box["w"])
    base_h = min(base_h, usable_h)

    if face:
        cx = face[0] + face[2] // 2
        cy = face[1] + face[3] // 2
        x = int(cx - base_w / 2)
        y = int(cy - base_h * face_y)            # 얼굴을 위쪽에 — 어깨가 들어오게
    else:
        x = (W - base_w) // 2
        y = int(usable_h * 0.10)
    # ★한 번에 크게 옮기지 않는다. 레퍼런스는 1~2초마다 화면을 바꾸는데도 안 튄다 —
    #   빠른 전환이 문제가 아니라 **점프 폭**이 문제였다. 목표가 멀면 조금씩 다가간다.
    if prev:
        lim = box.get("max_shift", 0.16) * W
        px, py = prev[2], prev[3]
        if abs(x - px) > lim:
            x = int(px + lim * (1 if x > px else -1))
        if abs(y - py) > lim:
            y = int(py + lim * (1 if y > py else -1))

    x = max(0, min(x, W - base_w))
    y = max(0, min(y, usable_h - base_h))

    # ★앞 컷과 비슷하면 **그 구도를 그대로 물려받는다.**
    #   먹는 장면처럼 얼굴이 손·음식에 가려지면 검출이 흔들리는데,
    #   그때마다 새로 잡으면 같은 장면인데 화면이 확 바뀐다.
    keep = box.get("keep_if_close", {"zoom": 0.07, "shift": 0.06, "max_run": 3})
    held = 0
    if prev:
        pw, ph, px, py, run = (*prev[:4], prev[4] if len(prev) > 4 else 0)
        # ★1순위 — **앞 컷 끝과 이 컷 시작이 같은 그림이면** 구도를 그대로 물려준다.
        #   자막까지 같은데 화면 크기만 바뀌던 자리가 여기서 잡힌다.
        cont = same_scene(
            frame_at(src, seg["t0"] - 0.2, work, f"{idx:02d}p"),
            frame_at(src, seg["t0"] + 0.2, work, f"{idx:02d}n"),
            box.get("same_scene_thr", 0.86))
        dz = abs(base_w - pw) / max(pw, 1)
        dx = abs(x - px) / max(W, 1)
        dy = abs(y - py) / max(usable_h, 1)
        close = dz <= keep.get("zoom", 0.07) and max(dx, dy) <= keep.get("shift", 0.06)
        # ★연속 유지에 상한을 둔다. 없으면 한 번 물려받은 값이 계속 이어져 화면이 굳는다.
        #   다만 **같은 장면인 게 확인되면 상한을 넉넉히 준다** — 억지로 바꿀 이유가 없다.
        # ★유지에 **시간 상한**을 둔다. 횟수만으로는 부족하다 — 1초짜리 컷 아홉 개를
        #   이어도 9초라 괜찮아 보이지만, 화면은 9초 내내 고정이다.
        hold = float(prev[5]) if len(prev) > 5 else 0.0  # 같은 구도로 버틴 시간
        room = hold + (seg["t1"] - seg["t0"]) <= box.get("hold_max_sec", 3.0)
        cap = keep.get("max_run", 3) * (3 if cont else 1)
        if (cont or close) and run < cap and room:
            base_w, base_h, x, y = pw, ph, px, py
            z = box["w"] / max(pw, 1)
            held = run + 1
            new_hold = hold + (seg["t1"] - seg["t0"])
            how += f" · {'같은 장면' if cont else '앞 구도'} 유지({new_hold:.1f}초)"

    # ★최종 관문 — 그림경계 안 · 얼굴 담기 («잔무늬» 자리표는 얼굴이 아니라서 담기 대상이 아니다)
    경계 = 가림경계(경계, seg, seg["t0"], seg["t1"], usable_h, box["w"] / box["h"])
    base_w, base_h, x, y, 담김 = 담기(base_w, base_h, x, y,
                                     face if how.startswith("얼굴") else None,
                                     경계, usable_h, box["w"] / box["h"])
    vf = (f"crop={base_w}:{base_h}:{x}:{y},"
          f"scale={box['w']}:{box['h']}:flags=lanczos")
    if box.get("mirror"):
        vf += ",hflip"
    return vf, {"zoom": round(z, 2), "how": how, "crop": (base_w, base_h, x, y),
                "face_in": 담김, "bounds": 경계,
                "run": held,
                "hold": (hold + (seg["t1"] - seg["t0"])) if held else 0.0}
