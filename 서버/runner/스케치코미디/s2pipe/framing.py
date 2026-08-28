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
        shutil.copy2(src, dst)
    return dst if dst.isascii() else None


try:
    import cv2
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
    det = cv2.FaceDetectorYN.create(MODEL_PATH, "", (rgb.shape[1], rgb.shape[0]),
                                    score_threshold=score, nms_threshold=0.3, top_k=50)
    bgr = rgb[:, :, ::-1].copy()
    _, faces = det.detect(bgr)
    if faces is None:
        return []
    # ★★검출기는 얼굴 상자와 함께 **5점(오른눈·왼눈·코·입 양끝)** 을 준다 —
    #   그동안 상자만 쓰고 버렸다. `f[4]`·`f[5]` 에 **두 눈의 중점**을 실어 보낸다.
    #   상자 중심은 머리 기울기·머리카락에 흔들리는데 눈은 훨씬 덜 흔들린다.
    out = []
    for f in faces:
        ex = ey = None
        if len(f) >= 8:
            ex = (float(f[4]) + float(f[6])) / 2
            ey = (float(f[5]) + float(f[7])) / 2
        out.append((int(f[0]), int(f[1]), int(f[2]), int(f[3]), ex, ey))
    return out


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
        fa, fb = _faces_yunet(a), _faces_yunet(b)
        if fa and fb:
            ga = max(fa, key=lambda f: f[2] * f[3])
            gb = max(fb, key=lambda f: f[2] * f[3])
            W = a.shape[1]
            # 얼굴이 화면 폭의 12% 넘게 움직이거나 크기가 30% 넘게 달라지면 다른 장면
            moved = abs((ga[0] + ga[2] / 2) - (gb[0] + gb[2] / 2)) / W
            scaled = abs(ga[3] - gb[3]) / max(ga[3], gb[3], 1)
            return moved <= 0.12 and scaled <= 0.30
        if bool(fa) != bool(fb):
            return False                   # 한쪽에만 얼굴이 있으면 바뀐 것이다
    return True


def frame_at(src, sec, work, tag):
    p = os.path.join(work, f"_s_{tag}.png")
    if not os.path.exists(p):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{max(0, sec):.2f}", "-i", src, "-frames:v", "1",
                        "-y", p], capture_output=True)
    return _read_rgb(p)


def frames_of(src, seg, work, tag, n=5):
    out = []
    t0, t1 = seg["t0"], seg["t1"]
    for k in range(n):
        sec = t0 + (t1 - t0) * (k + 1) / (n + 1)
        p = os.path.join(work, f"_f_{tag}_{k}.png")
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
        p = os.path.join(work, f"_t_{tag}_{k}.png")
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-ss", f"{sec:.2f}", "-i", src, "-frames:v", "1", "-y", p],
                           capture_output=True)
        a = _read_rgb(p)
        if a is None:
            continue
        fs = [f for f in (_faces_yunet(a) if HAS_YN else [])
              if f[1] + f[3] // 2 < usable_h]
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


def plan_beats(src, seg, idx, W, H, usable_h, box, work, cuts=(), prev=None):
    """조각을 짧은 **비트**로 나누고, 비트마다 구도를 **조금씩만** 바꾼다.

    ★레퍼런스 실측(ref/cut_zoom.py · beat.py):
        화면 변화 간격 0.8초 · 한 번의 변화는 줌 4.0% · 줌 속도 초당 5.4%
      우리는 1.4초마다 7.1% 씩 바꿔서 튀었다. **자주·작게가 답이다** —
      오늘 여덟 번 실패한 시도는 전부 반대 방향(덜 자주·더 크게)이었다.

    ★원본 컷 경계에서는 제한을 풀어 준다. 원본이 이미 앵글을 바꿨으니 우리가
      같이 바꿔도 튀지 않는다 — 오히려 안 바꾸면 컷이 지워진다(팬 모드의 병).
    """
    beat = box.get("beat_sec", 0.85)
    dz_max = box.get("beat_zoom", 0.045)
    dp_max = box.get("beat_shift", 0.045)
    relief = box.get("beat_cut_relief", 2.5)
    face_ratio = box.get("face_ratio", 0.61)
    face_y = box.get("face_y", 0.40)
    zmin, zmax = box.get("zoom_range", [1.10, 1.80])
    t0, t1 = seg["t0"], seg["t1"]

    # 비트 경계 — 원본 컷은 전부 살리고, 그 사이가 벌어지면 격자를 끼운다
    marks = [c for c in cuts if t0 + 0.3 < c < t1 - 0.3]
    bs, at_cut = [t0], [False]
    for m in marks + [t1]:
        while m - bs[-1] > beat * 1.5:
            bs.append(bs[-1] + beat); at_cut.append(False)
        if m - bs[-1] >= 0.35:
            bs.append(m); at_cut.append(m is not t1 and m in marks)
    bs[-1] = t1

    # ★★**1패스 — 비트마다 얼굴을 먼저 다 찾아 둔다.**
    #   예전에는 찾자마자 바로 구도를 정했는데, 얼굴 검출은 프레임마다 몇 픽셀씩
    #   흔들린다. 그 흔들림이 그대로 카메라에 실려 **화면이 떠는 것처럼 보였다.**
    #   먼저 모아서 궤적을 다듬은 뒤(smooth) 구도를 정한다 — `plan_pan` 은 이미
    #   그렇게 하고 있었는데 여기만 안 하고 있었다.
    raw = []
    for k in range(len(bs) - 1):
        a, e = bs[k], bs[k + 1]
        rgb = frame_at(src, (a + e) / 2, work, f"{idx:02d}b{k:02d}")
        f, many = None, False
        if rgb is not None and HAS_YN:
            fs = [q for q in _faces_yunet(rgb, box.get("face_score", 0.45))
                  if q[1] + q[3] // 2 < usable_h]
            # ★★배경의 작은 얼굴을 버린다. 지나가는 사람·액자·포스터가 잡히면
            #   구도가 그쪽으로 끌려간다 — 세로가 화면의 6% 도 안 되면 주인공이 아니다.
            fs = [q for q in fs if q[3] >= usable_h * 0.06]
            if fs:
                # ★★**큰 것부터 정렬한다.** 예전엔 `fs[0]`, 곧 검출기가 준 순서대로
                #   첫 번째를 썼다 — 그게 주인공이라는 보장이 없다.
                fs.sort(key=lambda q: -q[2] * q[3])
                big = fs[0][2] * fs[0][3]
                # ★★둘 다 감싸는 것은 **크기가 비슷할 때만**이다. 예전엔 얼굴이 2개면
                #   무조건 감쌌는데, 뒤쪽의 작은 얼굴 하나 때문에 화면이 확 넓어졌다.
                mains = [q for q in fs if q[2] * q[3] >= big * 0.45]
                # ★★**멀리 떨어진 둘을 억지로 감싸지 마라.** 감싼 상자가 넓어지면
                #   그만큼 축소되어 **둘 다 작아진다.** 실측에서 가로 폭이 얼굴의
                #   중앙 2.1배, 최대 5.7배까지 나왔다 — 3배를 넘으면 큰 쪽만 잡고
                #   나머지는 화면 밖으로 보낸다(대화 장면은 어차피 번갈아 잡힌다).
                if len(mains) > 1:
                    span = (max(q[0] + q[2] for q in mains)
                            - min(q[0] for q in mains))
                    if span > fs[0][2] * box.get("pair_max_span", 3.0):
                        mains = [fs[0]]
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
    if not has:
        cxs = cys = fhs = [None] * len(raw)
    else:
        xs = _fill([_cx(f) if f else None for f, _ in raw])
        ys = _fill([_cy(f) if f else None for f, _ in raw])
        hs = _fill([f[3] if f else None for f, _ in raw])
        if globals().get("_SMOOTH_OFF"):         # 견주기용 — 평소에는 켜져 있다
            cxs, cys, fhs = xs, ys, hs
        else:
            cxs, cys, fhs = smooth(xs), smooth(ys), smooth(hs)

    out, cur = [], prev
    for k in range(len(bs) - 1):
        a, e = bs[k], bs[k + 1]
        f, many = raw[k]
        fh = fhs[k] if has else None

        if fh:
            z = usable_h / max(fh / (0.62 if many else face_ratio), 1)
        elif cur:
            z = usable_h / max(cur[1], 1)          # 못 찾으면 지금 크기를 지킨다
        else:
            z = 1.0 + (zmax - 1.0) * 0.4
        z = max(zmin, min(zmax, z))

        lz = dz_max * (relief if at_cut[k] else 1)
        if cur:                                     # 한 비트에 허용한 만큼만 움직인다
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
        if cur and hold and abs(bh - cur[1]) <= cur[1] * hold:
            bw, bh = cur[0], cur[1]

        if fh:                                   # ★다듬은 궤적을 쓴다(원 검출값이 아니라)
            tx = cxs[k] - bw / 2
            ty = cys[k] - bh * face_y
        elif cur:
            tx, ty = cur[2] + (cur[0] - bw) / 2, cur[3] + (cur[1] - bh) / 2
        else:
            tx, ty = (W - bw) / 2, usable_h * 0.10

        lp = dp_max * (relief if at_cut[k] else 1)
        if cur:
            mx, my = lp * W, lp * usable_h
            tx = max(cur[2] - mx, min(cur[2] + mx, tx))
            ty = max(cur[3] - my, min(cur[3] + my, ty))
        tx = max(0, min(tx, W - bw))
        ty = max(0, min(ty, usable_h - bh))

        # ★★크기와 위치를 **합쳐서** 한 번 더 제한한다. 둘을 따로 제한하면 한 비트에서
        #   크기 10.2% + 위치 11.2% 가 같이 움직인다(실측, 40.12초) — 각각은 상한 안이지만
        #   보는 사람에게는 한 번의 큰 변화다. **레퍼런스는 한 번의 변화가 4% 뿐이다.**
        #   넘치면 목표를 앞 구도 쪽으로 당긴다 — 방향은 지키고 크기만 줄인다.
        if cur and box.get("beat_budget", True):
            budget = dz_max * (relief if at_cut[k] else 1)
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

        # 비트 안에서는 앞 구도 중심에서 이 목표로 흘러간다 — 계단이 아니라 움직임이 되게
        if cur:
            sx = max(0, min(cur[2] + (cur[0] - bw) / 2, W - bw))
            sy = max(0, min(cur[3] + (cur[1] - bh) / 2, usable_h - bh))
        else:
            sx, sy = tx, ty
        dur = max(e - a, 0.05)
        if abs(sx - tx) < 1.5 and abs(sy - ty) < 1.5:
            vf = f"crop={bw}:{bh}:{int(tx)}:{int(ty)}"
        else:
            # ★★**선형으로 옮기면 떨린다.** 비트가 바뀔 때마다 카메라가 등속으로
            #   출발해 등속으로 멈추므로 시작·끝에서 속도가 툭 끊긴다 —
            #   0.85초마다 그러니 화면이 잘게 떠는 것처럼 보인다.
            #   **smoothstep(3u²-2u³)** 으로 양끝을 눕히면 이어 붙은 듯 흐른다.
            u = f"min(t/{dur:.2f},1)"
            ease = u if box.get("ease") == "linear" else f"({u}*{u}*(3-2*{u}))"
            vf = (f"crop={bw}:{bh}:"
                  f"x='{sx:.0f}+({tx - sx:.0f})*{ease}':"
                  f"y='{sy:.0f}+({ty - sy:.0f})*{ease}'")
        vf += f",scale={box['w']}:{box['h']}:flags=lanczos"
        if box.get("mirror"):
            vf += ",hflip"

        out.append((a, e, vf, {"zoom": round(z, 2), "at_cut": at_cut[k],
                               "face": bool(raw[k][0]),
                               "crop": (bw, bh, int(tx), int(ty))}))
        cur = (bw, bh, int(tx), int(ty))
    return out


def plan_frame(src, seg, idx, W, H, usable_h, box, work, prev=None):
    """한 구간의 crop 창을 정한다.

    - 확대율: punch 가 높을수록 크게. 레퍼런스 실측 범위 안에서만 움직인다
    - 위치: 얼굴을 중심에 둔다. 못 찾으면 잔무늬가 많은 곳, 그것도 없으면 중앙
    """
    zmin, zmax = box.get("zoom_range", [1.10, 1.80])
    face_ratio = box.get("face_ratio", 0.42)     # 얼굴이 화면 세로에서 차지할 비율
    face_y = box.get("face_y", 0.40)             # 얼굴 중심을 화면 세로 어디에 둘지

    how, face, group = "중앙", None, None
    if box.get("follow_face"):
        frames = frames_of(src, seg, work, f"{idx:02d}")
        if HAS_YN:
            for a in frames:
                fs = [f for f in _faces_yunet(a) if f[1] + f[3] // 2 < usable_h]
                if fs:
                    face = max(fs, key=lambda f: f[2] * f[3])
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

    vf = (f"crop={base_w}:{base_h}:{x}:{y},"
          f"scale={box['w']}:{box['h']}:flags=lanczos")
    if box.get("mirror"):
        vf += ",hflip"
    return vf, {"zoom": round(z, 2), "how": how, "crop": (base_w, base_h, x, y),
                "run": held,
                "hold": (hold + (seg["t1"] - seg["t0"])) if held else 0.0}
