"""싱크 검사기 - 편을 내보내기 전에 반드시 통과시킨다.

왜 있나 (2026-08-18):
  구간을 `-i src -ss T -c copy` 로 잘랐더니 영상 스트림 start_time 이 0.806초가 되고
  오디오는 0.013초에서 시작했다. 블록 하나가 소재 0.44초를 요청했는데 그 자리엔
  아직 그림이 없어서 영상 1.7초 / 소리 0.96초로 어긋났고, 완성본 앞부분이
  280~350ms 밀렸다. 눈으로는 못 잡고 숫자로만 잡힌다.

쓰는 법:
  python _synccheck.py <편폴더>            # 1·2단계 (자르기 전/구운 뒤)
  python _synccheck.py <편폴더> --final    # 3단계까지 (완성본 대조)
"""
import json, os, subprocess, sys, wave
import numpy as np

TOL_STREAM_START = 0.10   # 구간 파일: 영상·소리 시작 차이 한계(초)
TOL_BLOCK_AV     = 0.08   # 블록: 영상 길이 - 소리 길이 한계(초). AAC 한 프레임 21.3ms + 여유
TOL_FINAL_SHIFT  = 0.10   # 완성본: 원음 대조 시프트 한계(초)

def ff(args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()

def dur(path, stream=None):
    a = ["ffprobe", "-v", "error"]
    if stream:
        a += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        a += ["-show_entries", "format=duration"]
    v = ff(a + ["-of", "csv=p=0", path])
    return float(v.split()[0]) if v else 0.0

def start(path, stream):
    v = ff(["ffprobe", "-v", "error", "-select_streams", stream,
            "-show_entries", "stream=start_time", "-of", "csv=p=0", path])
    return float(v.split()[0]) if v else 0.0

def env(path, hop=160):
    w = wave.open(path)
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    w.close()
    n = len(a) // hop
    return np.array([np.sqrt((a[i*hop:(i+1)*hop]**2).mean() + 1e-9) for i in range(n)])

def shift_ms(final, fs, src, ss, t):
    """완성본의 한 대목과 소재의 같은 대목을 포락선 상관으로 맞춰 시프트(ms)를 잰다."""
    # ★완성본 쪽은 **블록 구간 그대로**(여유 없음), 소재 쪽만 앞뒤 0.8초 넓게 떠서 미끄러뜨린다.
    #   예전엔 양쪽에 0.3초씩 여유를 뒀는데, 0.5초짜리 짧은 블록에선 그 여유가 이웃 블록 소리라
    #   이웃과 맞춰 버려 «±블록길이» 만큼 밀렸다고 오판했다 (2026-09-03 불륜 EP5 블록 11·12·14 —
    #   파형으로 직접 재니 0ms). 여유가 완성본에 들어가면 안 된다 — 거긴 다른 소재 시각이다.
    PAD = 0.8
    for p, s, d, o in ((final, fs, t, "_sc_f.wav"),
                       (src,   max(0, ss-PAD), t+2*PAD, "_sc_s.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(s), "-t", str(d), "-i", p,
                        "-vn", "-ar", "16000", "-ac", "1", o, "-y"], check=True)
    f, s = env("_sc_f.wav"), env("_sc_s.wav")
    f = (f - f.mean()) / (f.std() + 1e-9)
    s = (s - s.mean()) / (s.std() + 1e-9)
    half = int(round(PAD * 100))            # 10ms 단위 — 소재 창의 가운데가 lag 0
    curve = {}
    for lag in range(-80, 81):
        i0 = half + lag
        b = s[i0:i0 + len(f)]
        if len(b) < len(f) or len(f) < 5:
            continue
        curve[lag] = float((f * b).mean())
    for o in ("_sc_f.wav", "_sc_s.wav"):
        if os.path.exists(o):
            os.remove(o)
    best = max(curve.items(), key=lambda kv: kv[1])
    # ★반복 대사 보강 (2026-09-03 · 신병4 EP14 «왜 그랬어/왜 그랬냐고»):
    #   같은 말이 되풀이되는 대목에선 최강 봉우리가 옆 반복구(+520ms 안팎)에 걸린다.
    #   한계 안(±TOL_FINAL_SHIFT)에 있는 **국소 봉우리**를 따로 돌려주고, 부르는 쪽이
    #   최강 봉우리가 한계 밖일 때만 그것을 채택할지 판단한다. 두 값을 다 찍는다.
    peaks = [l for l in curve
             if curve[l] >= curve.get(l - 1, -9) and curve[l] >= curve.get(l + 1, -9)]
    tol = int(round(TOL_FINAL_SHIFT * 100))          # 10ms 단위
    inner = [l for l in peaks if abs(l) <= tol and l != best[0]]
    alt = None
    if inner:
        l = max(inner, key=lambda l: curve[l])
        alt = (l * 10, curve[l])
    return best[0] * 10, best[1], alt


def main(work, do_final):
    src = os.path.join(work, "구간.mp4")
    fails = []

    # ── 1단계: 구간 파일 자체 ─────────────────────────────────
    vs, as_ = start(src, "v:0"), start(src, "a:0")
    gap = abs(vs - as_)
    ok = gap <= TOL_STREAM_START
    print(f"[1] 구간 파일  v.start={vs:.3f}  a.start={as_:.3f}  차이={gap:.3f}s  "
          f"{'OK' if ok else '실패'}")
    if not ok:
        fails.append(f"구간 파일의 영상·소리 시작이 {gap:.3f}s 어긋남 - "
                     f"-c copy 로 자른 파일이다. -i 뒤에 -ss 두고 재인코딩해 다시 잘라라")

    # ── 2단계: 구운 블록 ─────────────────────────────────────
    bdir = os.path.join(work, "blocks")
    blocks = sorted(f for f in os.listdir(bdir) if f.startswith("b") and f.endswith(".mp4")) \
        if os.path.isdir(bdir) else []
    blocks = [b for b in blocks if b != "merged.mp4"]
    bad = []
    for b in blocks:
        p = os.path.join(bdir, b)
        v, a = dur(p, "v:0"), dur(p, "a:0")
        if abs(v - a) > TOL_BLOCK_AV:
            bad.append((b, v, a, v - a))
    print(f"[2] 블록 {len(blocks)}개  영상/소리 길이 어긋남 {len(bad)}개  "
          f"{'OK' if not bad else '실패'}")
    for b, v, a, d in bad:
        print(f"      {b}  영상 {v:.3f}  소리 {a:.3f}  차이 {d:+.3f}s")
        fails.append(f"{b} 의 영상·소리 길이가 {d:+.3f}s 어긋남 - "
                     f"그 블록의 소재 시작초가 영상 시작 전이거나 파일 끝을 넘었다")

    # ── 3단계: 완성본 원음 대조 ───────────────────────────────
    if do_final:
        plan = os.path.join(work, "_synccheck_points.json")
        if not os.path.exists(plan):
            print("[3] 건너뜀 - _synccheck_points.json 없음 "
                  "([{blk,final_start,src_start,dur,label}...] 형식)")
        else:
            pts = json.load(open(plan, encoding="utf-8"))
            final = os.path.join(work, [f for f in os.listdir(work)
                                        if f.startswith("완성") and f.endswith(".mp4")][0])
            print(f"[3] 완성본 원음 대조 - {os.path.basename(final)}")
            worst = 0
            for p in pts:
                ms, corr, alt = shift_ms(final, p["final_start"], src, p["src_start"], p["dur"])
                note = ""
                # 최강 봉우리가 한계 밖인데 한계 안에 절반 넘는 세기의 봉우리가 따로 있으면
                # 반복 대사로 보고 그쪽을 채택한다 (진짜 밀림이면 한계 안 봉우리가 없다).
                if abs(ms) > TOL_FINAL_SHIFT * 1000 and alt and alt[1] >= 0.5 * corr:
                    note = f"  ← 반복 대사 의심: 최강 {ms:+}ms(상관 {corr:.2f}) 대신 한계 안 봉우리 채택"
                    ms, corr = alt
                mark = "OK" if abs(ms) <= TOL_FINAL_SHIFT * 1000 else "실패"
                print(f"      블록{p['blk']:>3}  {p['label'][:18]:<20} "
                      f"{ms:>+6}ms  상관 {corr:.2f}  {mark}{note}")
                if abs(ms) > TOL_FINAL_SHIFT * 1000:
                    fails.append(f"블록{p['blk']} 원음이 {ms:+}ms 밀림 ({p['label']})")
                worst = max(worst, abs(ms))
            print(f"      최대 시프트 {worst}ms (한계 {int(TOL_FINAL_SHIFT*1000)}ms)")

    print()
    if fails:
        print(f"싱크 검사 실패 - {len(fails)}건")
        for f in fails:
            print(f"  · {f}")
        return 1
    print("싱크 검사 통과")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0], "--final" in sys.argv))
