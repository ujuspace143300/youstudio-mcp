#!/usr/bin/env python3
"""ffmpeg스레드시험.py — 스케치 파이프라인의 모든 ffmpeg·ffprobe 호출이 스레드 상한(s2pipe/ff.py)을 지나는지 본다.

★근거 (2026-10-03 18:48 맥1 · 루키치 14편 동시): 부하 150/112/89 · CPU 쉼 0% · 스레드 3416.
  짧은 프레임 뽑기가 -threads 없이 돌아 ffmpeg 하나가 30~42 스레드(조각 굽기는 369)를 띄웠다.
  호출마다 손으로 «-threads 2» 를 붙이던 방식이라 새 호출은 늘 빠졌다(96곳 중 4곳만 있었다).
  그래서 (가) 모든 argv 식이 ff.명령(...) 안에 있어야 하고 (나) 셸 문자열로 ffmpeg 를 부르면 안 된다.
  새 파일·새 호출이 이 규칙을 어기면 여기서 실패한다 — 사람 눈보다 먼저.

  종료코드 0 = 통과 · 1 = 실패(어긴 자리 목록).
  python3 검수도구/ffmpeg스레드시험.py            # 정적 검사 + 단위 시험 + 실제 실행(합성 영상 2초)
  python3 검수도구/ffmpeg스레드시험.py --정적만
"""
import ast
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # 서버/runner/스케치코미디
sys.path.insert(0, ROOT)
from s2pipe import ff  # noqa: E402

건너뜀 = {os.path.join("s2pipe", "ff.py")}
실패 = []


def ff머리(node):
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        node = node.left
    if not isinstance(node, ast.List) or not node.elts:
        return False
    e = node.elts[0]
    if isinstance(e, ast.Constant) and isinstance(e.value, str) and os.path.basename(e.value) in ("ffmpeg", "ffprobe"):
        return True
    return isinstance(e, ast.Subscript) and "ffmpeg" in ast.unparse(e)


def 정적검사():
    n = 0
    for d, _, fs in os.walk(ROOT):
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, ROOT)
            if f.endswith(".sh"):
                # 셸에서 ffmpeg 를 직접 부르면 상한이 안 걸린다(ffprobe 머리 읽기는 디코드가 없어 둔다)
                for i, l in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                    s = l.split("#", 1)[0]
                    if any(w == "ffmpeg" for w in s.replace(";", " ").replace("|", " ").split()):
                        실패.append(f"{rel}:{i} 셸에서 ffmpeg 직접 호출 — 파이썬 ff.명령 으로")
                continue
            if not f.endswith(".py") or rel in 건너뜀 or os.path.abspath(p) == os.path.abspath(__file__):
                continue
            tree = ast.parse(open(p, encoding="utf-8").read())
            부모 = {c: q for q in ast.walk(tree) for c in ast.iter_child_nodes(q)}
            for node in ast.walk(tree):
                # (나) 셸 문자열 — os.system / shell=True / 문자열 한 덩이로 ffmpeg
                if isinstance(node, ast.Call):
                    fn = ast.unparse(node.func)
                    shell = any(k.arg == "shell" and getattr(k.value, "value", False) is True for k in node.keywords)
                    if (fn in ("os.system", "os.popen") or shell) and node.args:
                        a0 = node.args[0]
                        txt = ast.unparse(a0)
                        if "ffmpeg" in txt or "ffprobe" in txt:
                            실패.append(f"{rel}:{node.lineno} 셸 문자열로 ffmpeg 호출 — 리스트 + ff.명령 으로")
                if not ff머리(node):
                    continue
                p_ = 부모.get(node)
                if isinstance(p_, ast.BinOp) and isinstance(p_.op, ast.Add) and ff머리(p_):
                    continue                       # 바깥 덧셈 식이 검사 대상
                n += 1
                if not (isinstance(p_, ast.Call) and ast.unparse(p_.func) in ("ff.명령", "명령")):
                    실패.append(f"{rel}:{node.lineno} ffmpeg/ffprobe 호출이 ff.명령(...) 밖에 있다 — 스레드 상한 없음")
                    continue
                # 출력 자리 확인: 마지막 원소가 옵션(-x)이면 ff.명령 이 출력 옵션을 엉뚱한 데 넣는다
                last = node
                while isinstance(last, ast.BinOp):
                    last = last.right
                if isinstance(last, ast.List) and last.elts:
                    e = last.elts[-1]
                    if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value.startswith("-") and e.value != "-":
                        if os.path.basename(str(getattr(node if isinstance(node, ast.List) else node.left, "elts", [ast.Constant("")])[0].value)) == "ffmpeg":
                            실패.append(f"{rel}:{node.lineno} ffmpeg argv 의 마지막이 옵션({e.value}) — 출력 파일을 맨 끝에")
    return n


def 단위시험():
    def 기대(조건, 말):
        if not 조건:
            실패.append("단위: " + 말)
    a = ff.명령(["ffmpeg", "-v", "error", "-ss", "1", "-i", "a.mp4", "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo", "-"])
    기대(a[a.index("-i") - 2:a.index("-i")] == ["-threads", ff.값("SKETCH_FF_DECODE")], f"입력 디코더 상한 {a}")
    기대(a[1:3] == ["-filter_threads", ff.값("SKETCH_FF_FILTER")], f"필터 상한 {a}")
    기대(a[-3:] == ["-threads", ff.값("SKETCH_FF_DECODE"), "-"], f"그림 출력 상한 {a}")
    b = ff.명령(["ffmpeg", "-threads", "1", "-loop", "1", "-i", "f.png", "-i", "c.mp4", "-filter_complex", "x",
                 "-c:v", "libx264", "-threads", "4", "-y", "o.mp4"])
    기대(b.count("-threads") == 3 and b[b.index("f.png") - 5:b.index("f.png") - 3] == ["-threads", "1"], f"적힌 값 유지 {b}")
    기대("-filter_complex_threads" in b, f"복합 필터 상한 {b}")
    c = ff.명령(["ffmpeg", "-i", "a.mp4", "-c:v", "libx264", "-y", "o.mp4"])
    기대(c[-3:] == ["-threads", ff.값("SKETCH_FF_ENCODE"), "o.mp4"], f"x264 인코더 상한 {c}")
    d = ff.명령(["ffprobe", "-v", "error", "x.mp4"])
    기대(d[1:3] == ["-threads", ff.값("SKETCH_FF_DECODE")], f"ffprobe 상한 {d}")
    os.environ["SKETCH_FF_DECODE"] = "1"
    기대(ff.명령(["ffmpeg", "-i", "a", "b"])[ff.명령(["ffmpeg", "-i", "a", "b"]).index("-i") - 1] == "1", "환경변수로 바꾸기")
    del os.environ["SKETCH_FF_DECODE"]


def _최대스레드(argv):
    t0 = time.time()
    p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    m = 0
    while p.poll() is None:
        o = subprocess.run(["ps", "-M", "-p", str(p.pid)], capture_output=True, text=True).stdout
        m = max(m, len(o.strip().splitlines()) - 1)
        time.sleep(0.002)
    return m, time.time() - t0, p.returncode, p.stderr.read().decode(errors="replace")


def 실제시험():
    """합성 영상(2초 640×360 x264)으로 프레임 한 장 뽑기를 상한 없이·있게 돌려 스레드 최댓값을 비교한다."""
    with tempfile.TemporaryDirectory(prefix="ff스레드_") as d:
        src = os.path.join(d, "t.mp4")
        subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=24:d=4",
                                "-c:v", "libx264", "-g", "48", "-y", src]), check=True)
        날 = ["ffmpeg", "-v", "error", "-ss", "3.5", "-i", src, "-frames:v", "1", "-vf", "scale=64:36", "-y", os.path.join(d, "a.png")]
        m0, *_ = _최대스레드(날)
        m1, _, rc, err = _최대스레드(ff.명령(날))
        print(f"  실제: 프레임 한 장 — 상한 없음 최대 {m0} 스레드 · ff.명령 최대 {m1} 스레드 (종료 {rc})")
        if rc != 0:
            실패.append(f"실제: ff.명령 argv 가 ffmpeg 에서 실패 — {err[-200:]}")
        한도 = 2 * int(ff.값("SKETCH_FF_DECODE")) + 2 * int(ff.값("SKETCH_FF_FILTER")) + 4
        if m1 > 한도:
            실패.append(f"실제: ff.명령 을 지나도 스레드 {m1} > 한도 {한도}")


if __name__ == "__main__":
    n = 정적검사()
    print(f"  정적: argv 식 {n}곳 검사")
    단위시험()
    if "--정적만" not in sys.argv:
        실제시험()
    if 실패:
        print(f"✗ ffmpeg 스레드 시험 실패 {len(실패)}건")
        for x in 실패:
            print("   ", x)
        sys.exit(1)
    print("✓ ffmpeg 스레드 시험 통과")
