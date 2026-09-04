# -*- coding: utf-8 -*-
r"""인물을 화면 한가운데로 끌어오는 소스를 굽는다 → 구간_인물.mp4

서버는 소재를 세로창(1080x1020)에 담을 때 **가로 가운데 WIN px 만** 쓴다.
그래서 WIN x 소재높이 창을 촬영본마다 «인물 자리»(faces.json)로 옮겨 잘라내고
1080x1020 으로 키운다. 서버가 받는 그림은 이미 목표 비율이라 서버 쪽 크롭은
아무것도 하지 않는다. 축소율은 서버가 하던 것과 같아 화질 손해가 없다.

  WIN = 소재높이 x 1080 / 1020    (find_faces.py 와 **같은 값**이어야 한다)
    소년심판 1920x1080 → 1143      타짜 1920x804 → 852
  ★레터박스가 있으면 여기 오기 전에 잘라낸다.

촬영본 하나 안에서는 창을 고정한다 — 움직이면 그게 «흔들림» 으로 보인다.
창이 바뀌는 순간은 언제나 영화 자신의 장면전환과 겹친다.

쓰는 법
  편 폴더에서:  python 도구\reframe.py
"""
import io
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ▼편별 ─── 여기를 이 편 것으로 바꾼다 ────────────────────────────────
SRC = '구간.mp4'
DST = '구간_인물.mp4'
WIN = 1143              # find_faces.py 의 WIN 과 같아야 한다
# ▲편별 ──────────────────────────────────────────────────

OUT_W, OUT_H = 1080, 1020       # 서버 세로창. 채널 규격이라 바꾸지 않는다


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x', path],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    w, h = r.stdout.strip().split('x')[:2]
    return int(w), int(h)


W, H = probe(SRC)
권장 = int(round(H * 1080 / 1020))
if abs(권장 - WIN) > 8:
    raise SystemExit(f"소재가 {W}x{H} 이면 WIN 은 {권장} 이어야 한다 (지금 {WIN}). "
                     f"레터박스를 안 잘랐거나 ▼편별 값을 안 고쳤다.")

F = json.load(open('faces.json', encoding='utf-8'))
MAXX = W - WIN

# ── 창 자리 x(t) ────────────────────────────────────────────────
# 전에는 «구간마다 값 하나» 를 켜고 끄는 식이었다. 그러면 창이 늘 **뚝** 바뀐다.
# 촬영본이 바뀌는 자리는 그래도 되지만(어차피 컷이다), 한 촬영본 **안에서**
# 말하는 사람을 따라 옮길 때는 뚝 끊으면 없던 컷이 하나 생긴 것처럼 보인다.
#
# 그래서 계단이 아니라 **누적 이동** 으로 쓴다:
#     x(t) = x0 + Σ (다음값 − 이전값) · clip((t − 경계)/미는시간, 0, 1)
# 미는시간이 0 에 가까우면 예전처럼 뚝 바뀌고(촬영본 경계),
# 0.35 면 부드럽게 밀린다(화자추적.py 가 `ease` 로 표시해 준 자리).
def _x(r):
    return max(0, min(MAXX, round(W / 2 - r['dx'] - WIN / 2)))


BS_COMMA = chr(92) + ','   # ffmpeg 식 안에서 쉼표는 백슬래시로 막는다
FPS = 영상읽기.초당프레임(A.소재) if 'A' in dir() and hasattr(A, '소재') else 24000 / 1001
HARD = 0.001                      # 사실상 즉시 — 촬영본이 바뀌는 자리
terms = [str(_x(F[0]))]
for prev, r in zip(F, F[1:]):
    d = _x(r) - _x(prev)
    if d == 0:
        continue
    e = float(r.get('ease') or 0.0) or HARD
    # ★급이동(HARD)은 **반 프레임 앞**에서 시작한다 (2026-08-28 실측).
    #   ffmpeg crop 의 t 는 프레임 시작 시각이라 t0 = a 로 두면 경계 프레임(a)은 아직
    #   옛 창이고 다음 프레임에서야 새 창이 된다. 영화 컷은 a 에서 바뀌므로 창이 한
    #   프레임 늦어 **컷 한 번에 두 번 튄다** — 들쥐 1편에서 원음 블록 안 연속쌍 17개.
    #   반 프레임 당기면 경계 프레임부터 새 창이라 컷과 창 전환이 같은 프레임이 된다.
    반프레임 = 0.5 / FPS
    t0 = r['a'] - (e / 2 if e > HARD else 반프레임)
    # ★선형으로 밀면 시작·끝에서 속도가 0↔최대로 **툭** 바뀐다 (2026-08-27 실측).
    #   완성본 프레임을 훑으니 미는 구간 안에 봉우리가 섰다(최고/평균 4.5~5.0) —
    #   부드럽게 미는데도 «살짝 튀는» 자리가 이것이었다.
    #   → 든 코사인(raised cosine)으로 바꾼다. u=0·u=1 에서 속도가 0 이라
    #     들 때도 놓을 때도 걸리는 데가 없다.  s = (1 - cos(PI*u)) / 2
    terms.append("(%d)*(1-cos(PI*max(0%smin(1%s(t-%.3f)/%.3f))))/2"
                 % (d, BS_COMMA, BS_COMMA, t0, e))
expr = '+'.join(terms)
_ease = sum(1 for r in F if float(r.get('ease') or 0) > HARD)
if _ease:
    print(f"부드럽게 미는 자리 {_ease}곳 (화자추적)")

# ★항이 너무 많으면 ffmpeg 이 식을 못 짠다 — «Failed to configure input pad»
#   (2026-09-02 · 4화 옥상 143컷 → 7580자). 파일로 넘겨도 마찬가지다.
#   그럴 땐 **계단식**으로 바꾼다: 든 코사인은 포기하고 if 사슬로 자리만 준다.
#   컷이 촘촘한 액션 장면이라 부드럽게 밀 일도 거의 없다.
if len(expr) > 3000:
    _자리 = [(F[0]['a'] if 'a' in F[0] else 0.0, _x(F[0]))]
    for prev, r in zip(F, F[1:]):
        if _x(r) != _x(prev):
            _자리.append((r['a'], _x(r)))
    식 = str(_자리[-1][1])
    for a, v in reversed(_자리[:-1]):
        식 = "if(lt(t%s%.3f)%s%d%s%s)" % (BS_COMMA, a, BS_COMMA, v, BS_COMMA, 식)
    print('식이 길어 계단식으로 바꾼다 — 항 %d개 · %d자 → %d자'
          % (len(_자리), len(expr), len(식)))
    expr = 식

_ease = sum(1 for r in F if float(r.get('ease') or 0) > HARD)
if _ease:
    print(f"부드럽게 미는 자리 {_ease}곳 (화자추적)")

# ★촬영본이 많으면 식이 길어져 ffmpeg 이 «Failed to configure input pad» 로 죽는다
#   (2026-09-02 · 4화 옥상 143컷 → 7580자). 그럴 땐 식을 **파일로** 넘긴다.
_필터 = f"crop={WIN}:{H}:x='{expr}':y=0,scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1"
if len(_필터) > 2000:
    io.open('_reframe_vf.txt', 'w', encoding='utf-8').write(_필터)
    _vf = ['-filter_script:v', '_reframe_vf.txt']
    print('식이 %d자 — 파일로 넘긴다' % len(_필터))
else:
    _vf = ['-vf', _필터]
cmd = ['ffmpeg', '-y', '-v', 'error', '-i', SRC] + _vf + [
       '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p',
       '-color_range', 'tv', '-colorspace', 'bt709',
       '-color_primaries', 'bt709', '-color_trc', 'bt709',
       '-c:a', 'copy', DST]
print(f"소재 {W}x{H} · 창 {WIN}x{H} → {OUT_W}x{OUT_H} · 촬영본 {len(F)}개 · 식 {len(expr)}자")
r = subprocess.run(cmd)
print("완료 → " + DST if r.returncode == 0 else f"실패 {r.returncode}")
