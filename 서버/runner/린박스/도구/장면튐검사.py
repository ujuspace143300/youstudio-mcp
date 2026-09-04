# -*- coding: utf-8 -*-
r"""**화면이 튀는가** 를 굽기 전에 판독한다. (2026-08-25)

왜 이 검사기가 있나
  사장님 지적은 늘 «화면이 확 튄다» 였는데, `검수.py` 는 그걸 못 잡았다.
  검수는 완성본의 **화소 차이**로 컷을 세는데
    · 펀치인(같은 그림을 30% 당긴 것)은 문턱을 못 넘어 **안 세고**
    · 나레 화면이 대목 밖에서 온 것은 «컷» 이라 오히려 **잘 세어** 통과시킨다.
  즉 눈에 튀는 것은 놓치고, 눈에 안 튀는 것은 못 센다. 그래서 따로 판독한다.

무엇을 보나 (전부 **굽기 전** 재료로 본다 — 완성본이 없어도 돈다)
  ① 나레 화면이 장면전환을 넘는가      ← 나레 한 장 안에서 장면이 바뀌면 툭 튄다
  ② 나레 화면이 **대목 밖**에서 왔는가  ← 딴 장면을 끌어오면 통째로 튄다
  ②-b **같은 촬영본인데 배율이 바뀌는가** ← 화면은 그대로인데 크기만 툭 변한다.
       컷이 아니라 «글리치» 로 읽힌다. 2026-08-25 사장님이 5·11·35초에서 잡아내셨다.
  ③ 보이는 컷이 몇 개인가              ← 펀치인·배속을 **셈에 넣어** 컷/분을 낸다
  ④ 0.80초를 못 채우는 그림이 있는가    ← 번쩍임

  판정은 두 갈래다.
    ✗ 막힘 — 화면이 실제로 튄다. 고치기 전에는 굽지 마라.
    ! 알림 — 규격 밖이지만 **대목의 성질** 상 어쩔 수 없을 수 있다.
             (롱테이크 대화는 촬영본이 모자라 컷/분이 안 나온다 — 규격 §25)
             사람이 «이 편의 취지» 를 보고 넘길지 정한다.

쓰는 법
  편 폴더에서:  python 장면튐검사.py
"""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FPS = 30
# ★2026-08-25 — 규격 §48. 0.80초(규격 §7 최소 컷)는 **하한**일 뿐 눈에는 번쩍인다.
#   사장님이 짚으신 5·11·35초가 전부 0.80초 조각이었다. 그래서 판정선을 올린다.
def _말이어짐(컷, 끝):
    """전환 뒤 토막에 **말이 이어지고 있나**. 소리 세기로 잰다.

    전환에서 블록을 닫으면 그 토막이 통째로 사라진다. 거기 말이 실려 있으면
    대사가 잘린다 — 그건 번쩍임보다 나쁘다. 그래서 «닫아도 되는 자리» 와
    «닫으면 안 되는 자리» 를 소리로 가른다 (2026-08-27 실측).
    """
    import subprocess as _sp
    import numpy as _np
    def _rms(a, b):
        if b - a < 0.02:
            return 0.0
        r = _sp.run(['ffmpeg', '-v', 'error', '-ss', '%.3f' % a, '-t', '%.3f' % (b - a),
                     '-i', SRC_원본, '-vn', '-ac', '1', '-ar', '16000',
                     '-f', 's16le', '-'], capture_output=True).stdout
        x = _np.frombuffer(r, dtype='<i2').astype('float32')
        return float(_np.sqrt((x ** 2).mean())) if len(x) else 0.0
    앞 = _rms(max(0.0, 컷 - 0.60), 컷)
    뒤 = _rms(컷, 끝)
    # ★절대값(300)으로 자르면 안 된다 — 소재마다 녹음 크기가 다르다 (2026-08-28).
    #   들쥐 선공개는 포핸즈보다 조용해서, 말이 또렷이 이어지는데도(비 0.86)
    #   300 을 못 넘어 «말이 없다» 로 잘못 읽혔다.
    #   → **소재 제 크기**에 견준다.
    global _전체RMS
    try:
        _전체RMS
    except NameError:
        _전체RMS = _rms(0.0, min(30.0, SRC_END if 'SRC_END' in dir() else 30.0)) or 1.0
    # 조용한 소재도 있으므로 바닥은 낮게 — 무음을 거르는 용도일 뿐이다
    바닥 = max(20.0, _전체RMS * 0.10)
    return 뒤 > 바닥 and 뒤 > 앞 * 0.45


MIN_컷 = 1.30          # 이보다 짧으면 «조각» 으로 본다 (채널 컷 중앙값)
번쩍임 = 1.00          # 이보다 짧으면 **막힘** — 확실히 번쩍인다
컷분_낮 , 컷분_높 = 27.0, 47.0

A = json.load(io.open('authored.json', encoding='utf-8'))
SC = sorted(float(x) for x in io.open('scene_cuts.txt'))
상태 = {}
if os.path.exists('화면상태.json'):
    상태 = json.load(io.open('화면상태.json', encoding='utf-8'))
펀치 = set(상태.get('펀치인') or [])
배속 = {int(k): v for k, v in (상태.get('배속') or {}).items()}

SRC = '구간_인물.mp4'
SRC_원본 = '구간.mp4'   # 소리를 재는 원본 (재프레이밍 전)
SRC_END = float(subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', SRC],
    capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip())

# 금지구간(대목 밖)은 fix_cuts.py 의 편별 값에서 그대로 읽는다 — 두 곳에 적지 않는다
금지구간 = []
try:
    _t = io.open('fix_cuts.py', encoding='utf-8').read()
    _l = [x for x in _t.splitlines() if x.startswith('금지구간')]
    if _l:
        금지구간 = eval(_l[0].split('=', 1)[1].strip())
except Exception:
    pass


def 촬영본(t):
    return sum(1 for c in SC if t >= c)


def 다음전환(t):
    return min([c for c in SC if c > t] + [SRC_END])


def 블록길이(i):
    p = 'blocks/b%02d.mp4' % i
    if not os.path.exists(p):
        return None
    return float(subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
        capture_output=True, text=True).stdout.strip())


BL = A['BLOCKS']
# ★대체화면.py 가 그림을 갈아 끼운 블록은 **소재 시각이 다르다.**
#   authored.json 의 시각(소리 자리)으로 재면 있지도 않은 전환을 본다 —
#   포핸즈 01편에서 b09·b15 를 갈아 끼우고도 계속 «막힘» 으로 찍혔다.
ALT = {int(k): float(v) for k, v in (A.get('ALT_SHOTS') or {}).items()}
막힘, 알림 = [], []

# ── ①② 나레 화면 ───────────────────────────────────────────────────
print('■ 나레 화면')
for i, b in enumerate(BL):
    if b[0] != 'N':
        continue
    D = 블록길이(i)
    cuts = b[2] if isinstance(b[2], list) else [[b[2], 1]]
    n = len(cuts)
    each = (D / n) if D else 0.0
    for k, c in enumerate(cuts):
        t = ALT[i] if i in ALT else c[0]
        배 = (배속.get(i) or [1.0] * n)[k] if k < len(배속.get(i) or []) else 1.0
        쓰는초 = each / max(배, 1e-6)
        여유 = 다음전환(t) - t
        표 = 'b%02d-%d %7.2fs 화면 %.2f초' % (i, k + 1, t, each)
        if 배 > 1.02:
            표 += ' · 배속 %.2f배(소재 %.2f초)' % (배, 쓰는초)
        if 쓰는초 > 여유 + 0.02:
            막힘.append('%s — 장면전환을 %.2f초 넘는다 (나레 한 장 안에서 장면이 바뀐다)'
                        % (표, 쓰는초 - 여유))
            print('  ✗ ' + 표 + '  ← 전환까지 %.2f초뿐' % 여유)
            continue
        밖 = [z for z in 금지구간 if t < z[1] and t + 쓰는초 > z[0]]
        if 밖:
            막힘.append('%s — 대목 밖(금지구간 %s)에서 그림을 끌어왔다' % (표, 밖[0]))
            print('  ✗ ' + 표 + '  ← 대목 밖')
            continue
        print('  ✓ ' + 표 + '  (전환까지 %.2f초)' % 여유)

# ── ③④ 보이는 컷 ───────────────────────────────────────────────────
print()
print('■ 보이는 컷 — 펀치인·배속을 셈에 넣는다')


def 앞뒤(b, i):
    """블록이 실제로 화면에 내보내는 (첫 소재시각, 끝 소재시각)"""
    if i in ALT:                      # 대체화면.py 가 통째로 갈아 끼운 블록
        return ALT[i], ALT[i] + (블록길이(i) or 0.0)
    if b[0] == 'N':
        D = 블록길이(i) or 0.0
        cuts = b[2] if isinstance(b[2], list) else [[b[2], 1]]
        n = len(cuts)
        each = D / n
        배 = (배속.get(i) or [1.0] * n)
        끝 = cuts[-1][0] + each / max(배[-1] if len(배) == n else 1.0, 1e-6)
        return cuts[0][0], 끝
    return b[1][0][0], b[1][-1][1]


# ★★잰 게 없으면 «통과» 를 주지 마라 (2026-08-25).
#   이 검사는 **구운 블록의 길이**로 잰다(나레 블록의 화면 길이는 TTS 음성이 정하므로
#   대본만으로는 못 잰다). 그런데 블록이 없으면 아래 루프가 **말없이 다 건너뛰고**
#   「그림 0개 · 화면 튐 없음 ✓」 를 찍는다 — **아무것도 안 재고 파란불을 준다.**
#   포헨즈 1화 2편부터가 정확히 그렇게 샜다. 규격 §8 에 «7c) 굽기 전» 이라 적혀 있어서
#   굽기 전에 돌렸고, 거짓 통과를 받고 그대로 구웠다.
_있는블록 = sum(1 for i in range(len(BL)) if os.path.exists('blocks/b%02d.mp4' % i))
if _있는블록 < len(BL):
    print()
    print('★블록이 %d/%d 개뿐이다 — 아직 다 안 구웠다.' % (_있는블록, len(BL)))
    print('  이 검사는 **구운 블록의 길이**로 잰다. 나레 블록의 화면 길이는 TTS 음성이')
    print('  정하므로 대본만으로는 못 잰다. **굽고 나서(§8 의 8번 뒤에) 돌려라.**')
    print('  굽기 전에 볼 수 있는 것은 «대본검사.py» 다 (블록 경계 vs 장면전환).')
    raise SystemExit(2)

그림 = []          # (길이, 무엇, 소재시작) — 소재시작은 «누가 만든 조각인가» 판정에 쓴다
prev_end, prev_punch = None, None
for i, b in enumerate(BL):
    D = 블록길이(i)
    if D is None:
        continue
    s, e = 앞뒤(b, i)
    punch = (i in 펀치)
    바뀜 = True
    if prev_end is not None:
        같은촬영본 = 촬영본(s) == 촬영본(prev_end)
        붙어있음 = abs(s - prev_end) < 0.05
        # ★배율이 달라도 **컷이 아니다** (2026-08-25).
        #   같은 촬영본에서 크기만 바꾸면 사람 눈에는 컷이 아니라 튐이다.
        #   전에는 이것을 «컷» 으로 세는 바람에 검사기가 결함을 통과시켰다.
        # ★★«또는» 이 아니라 «그리고» 다 (2026-08-26 실측으로 밝힘).
        #   같은 촬영본이어도 **소재 시각이 떨어져 있으면 화면은 바뀐다** —
        #   같은 카메라 안에서 시간이 건너뛰는 것이라 배우가 움직여 있다.
        #   포헨즈 2-5 b01「미안하다」(소재 0.31~1.29) 와 b02(소재 2.44~4.11)가
        #   둘 다 촬영본 0 이라 «이어진 그림» 으로 세어 넘겼는데,
        #   완성본을 재 보니 그 자리에서 화면이 바뀌고 b01 은 **0.97초짜리 번쩍임**이었다.
        #   → 둘 다 맞아야 이어진 것으로 본다.
        if 같은촬영본 and 붙어있음:
            바뀜 = False
        if 같은촬영본 and punch != prev_punch:
            막힘.append('b%02d 앞에서 **같은 촬영본인데 배율이 바뀐다**(펀치인 %s→%s) — '
                        '화면이 툭 튄다. 펀치인을 빼라'
                        % (i, '켬' if prev_punch else '끔', '켬' if punch else '끔'))
    if 바뀜:
        그림.append([0.0, 'b%02d' % i, s])
    if not 그림:
        그림.append([0.0, 'b%02d' % i, s])
    그림[-1][0] += D
    # 블록 **안** 의 장면전환도 그림을 가른다 (원음 블록이 전환을 가로지르는 경우)
    if b[0] == 'D':
        for c in SC:
            if s + 0.05 < c < e - 0.05:
                안쪽 = e - c
                그림[-1][0] -= 안쪽
                이름 = 'b%02d(안쪽전환)' % i
                # ★«영화가 대사 한가운데서 컷한» 자리는 우리가 만든 조각이 아니다
                #   (규격 §22). 전환에서 닫으면 말이 뭉텅 잘린다 — 9편에서 재 보니
                #   잘릴 대목에 그 낱말 소리의 85~94%가 들어 있었다.
                #   그래서 **말이 이어지는지 소리로 재서** 막힘이 아니라 알림으로 돌린다.
                #   말이 없으면(무대사 꼬리) 그대로 막힘이다 — 그건 우리 탓이다.
                if _말이어짐(c, e):
                    이름 += '·말이어짐'
                그림.append([안쪽, 이름, c])
    prev_end, prev_punch = e, punch

총 = sum(g[0] for g in 그림)
컷분 = len(그림) / 총 * 60 if 총 else 0
print('  그림 %d개 · 총 %.2f초 · %.1f컷/분 (규격 %.0f~%.0f)'
      % (len(그림), 총, 컷분, 컷분_낮, 컷분_높))
# ★규격 §13 은 기준이 **둘**이다 (2026-08-25 · 맥에서 보탬)
#     · 내가 만든 조각 (블록 경계 · 나레 컷)  → 0.80초. 그 위로 1.30초를 권한다(§48)
#     · **대사 블록 안** 전환                  → 0.25초. **영화 원본의 편집이라 고칠 것이 아니다**(§22)
#   전에는 1.30 하나로 전부 쟀다. 그러면 **빠르게 편집된 소재가 통째로 막힌다** —
#   신병4 는 소재 자체가 46.7컷/분(140초에 전환 109개)이라 «안쪽전환» 22곳이 전부 ✗ 로 찍혔다.
#   윈도우 쪽 «화면튐_지침 §3» 이 같은 지적을 했다: 검수도 0.75 하나로 잰다.
# ★§22 — «누가 만든 조각인가» 를 먼저 가른다 (2026-08-26).
#   전에는 이름에 «(안쪽전환)» 이 없으면 전부 **내 조각**으로 세어 1.00초 잣대를 댔다.
#   그런데 블록 머리 조각은 **양쪽이 다 영화의 전환**일 수 있다 — 그건 영화가
#   그 촬영본을 그 길이로 찍은 것이지 내가 만든 조각이 아니다. 신병4 에서
#   b05(1.00초)·b13(0.70초)·b19(0.70초)·b20(0.70초) 이 그랬다.
#   그걸 «막힘» 으로 찍는 바람에, 고치겠다고 **대사 밑 그림을 갈아 끼워** 화면이
#   오히려 더 튀었다(§22 가 «더 나쁘다» 고 미리 경고한 그대로다).
#   ★양쪽이 다 전환에 맞닿아 있으면 영화 것이다. 0.25초 잣대를 댄다.
_전환닿음 = 0.08


def _영화것(이름, 시작소재):
    if '(안쪽전환)' in 이름:
        return True
    if 시작소재 is None:
        return False
    앞 = max([c for c in SC if c <= 시작소재 + 0.001] + [0.0])
    return (시작소재 - 앞) <= _전환닿음


def _내조각(이름):
    return '(안쪽전환)' not in 이름


# ★§22 — 영화가 그 길이로 찍은 컷은 «내 조각» 이 아니다. 0.25초 잣대를 댄다.
내것 = [g for g in 그림 if not _영화것(g[1], g[2] if len(g) > 2 else None)]
영화 = [g for g in 그림 if _영화것(g[1], g[2] if len(g) > 2 else None)]
짧은 = [g for g in 내것 if g[0] < 번쩍임 and '말이어짐' not in g[1]]
안쪽짧은 = [g for g in 영화 if g[0] < 0.25 and '말이어짐' not in g[1]]
아슬 = [g for g in 내것 if 번쩍임 <= g[0] < MIN_컷]
안쪽넘김 = [g for g in 영화 if 0.25 <= g[0] < MIN_컷]
# ★윈도우 판(포헨즈 9편): 영화가 대사 한가운데서 컷한 자리(«말이어짐»)는 닫으면 말이 잘리므로 막힘이 아니라 알림 (§22)
봐준 = [g for g in 그림 if '말이어짐' in g[1] and g[0] < (0.25 if _영화것(g[1], g[2] if len(g) > 2 else None) else 번쩍임)]
for g in 봐준:
    print('  ~ %s %.2f초 — 영화 자신의 컷이고 말이 이어진다. 닫으면 말이 잘린다 (§22)' % (g[1], g[0]))
    알림.append('그림 %s %.2f초 — 영화가 대사 한가운데서 컷했다. 닫으면 말이 잘린다 (§22)'
                % (g[1], g[0]))
for g in 짧은 + 안쪽짧은:
    막힘.append('그림 %s 가 %.2f초뿐이다 — 번쩍인다 (번쩍임정리.py 를 다시 돌려라, §48)'
                % (g[1], g[0]))
    print('  ✗ %s %.2f초 — 번쩍임' % (g[1], g[0]))
for g in 아슬:
    print('  ! %s %.2f초 — 조각이다 (1.30초 권장, §48)' % (g[1], g[0]))
    알림.append('그림 %s %.2f초 — 조각 (1.30초 권장, §48)' % (g[1], g[0]))
if 안쪽넘김:
    print('  · 대사 블록 안 전환 %d곳(%.2f~%.2f초) — **영화 자신의 편집이라 그대로 둔다** (§13·§22)'
          % (len(안쪽넘김), min(g[0] for g in 안쪽넘김), max(g[0] for g in 안쪽넘김)))
if not (컷분_낮 <= 컷분 <= 컷분_높):
    촬영본수 = len({촬영본(g) for g in [b for b in SC]}) + 1
    알림.append('컷/분 %.1f — 규격 %g~%g 밖. 이 대목의 촬영본은 %d개뿐이다. '
                '★배율을 바꿔 컷을 «만들지» 마라 — 같은 촬영본에서 크기만 바뀌면 튄다(§47). '
                '늘릴 길은 **나레를 다른 촬영본에 앉히는 것**뿐이고(§25), 그것도 모자라면 '
                '이 대목이 롱테이크라는 뜻이다 — 숫자보다 화면이 먼저다'
                % (컷분, 컷분_낮, 컷분_높, len(SC) + 1))
    print('  ! 컷/분이 규격 밖 — 촬영본 %d개짜리 대목이다 (§25)' % (len(SC) + 1))



# ── ⑤ 배율 — **구운 그림에서 직접 잰다** ────────────────────────────
#   ★2026-08-25. 서버는 컷마다 배율을 1.32→1.14→1.45→1.22 로 **기계적으로 돌려가며**
#   크롭해 굽는다. 화면 내용과 무관한 순환이라 같은 촬영본이 이어지는 자리에서
#   배율만 툭 바뀐다 — 사장님이 5·11·35초에서 잡아내신 것이 이것이다.
#   그래서 «내가 무엇을 했는가»(화면상태.json)를 믿지 않고 **구운 파일을 직접 잰다.**
후보배율 = [1.00, 1.14, 1.22, 1.32, 1.45]


def _프레임(path, t):
    import numpy as _np
    r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '%.3f' % t, '-i', path,
                        '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray',
                        '-s', '270x255', '-'], capture_output=True)
    b = r.stdout
    if len(b) < 270 * 255:
        return None
    return _np.frombuffer(b[:270 * 255], dtype='uint8').reshape(255, 270).astype('float32')


# ★numpy·cv2 가 없으면 **배율 검사만** 접는다 (2026-08-26).
#   전에는 여기서 트레이스백으로 죽어, 앞서 찍은 번쩍임 결과가 판정도 없이 날아갔다.
#   배율 글리치(②-b)는 사장님이 실제로 잡아내신 항목이라 «못 쟀다» 고 반드시 알린다.
try:
    import numpy as _np_있나
    import cv2 as _cv_있나
    배율잴수있다 = True
except ImportError as _e:
    배율잴수있다 = False
    배율못한까닭 = str(_e)


def 배율재기(블록, 컷차례, 소재시각, 블록안시각):
    """구운 블록 그림이 소재의 몇 배로 당겨져 있는지 고른다"""
    import numpy as _np
    B = _프레임('blocks/b%02d.mp4' % 블록, 블록안시각)
    S = _프레임(SRC, 소재시각)
    if B is None or S is None:
        return None
    best, bestz = -2.0, None
    H, W = S.shape
    for z in 후보배율:
        h, w = int(round(H / z)), int(round(W / z))
        y, x = (H - h) // 2, (W - w) // 2
        조각 = S[y:y + h, x:x + w]
        import cv2 as _cv
        늘림 = _cv.resize(조각, (W, H), interpolation=_cv.INTER_AREA)
        a = 늘림 - 늘림.mean()
        b = B - B.mean()
        d = (_np.sqrt((a * a).sum()) * _np.sqrt((b * b).sum())) or 1.0
        c = float((a * b).sum() / d)
        if c > best:
            best, bestz = c, z
    return bestz


print()
print('■ 배율 — 구운 그림에서 직접 잰다 (서버가 컷마다 배율을 돌려 가며 굽는다)')
if not 배율잴수있다:
    print('  ! 못 쟀다 — %s' % 배율못한까닭)
    print('    배율 글리치(같은 촬영본인데 크기만 툭 변하는 것)는 **검사되지 않았다.**')
    print('    설치.md 대로 .venv 를 세우고 그 파이썬으로 다시 돌려라.')
    알림.append('배율 검사를 못 돌렸다 (numpy·cv2 없음) — 이 편은 ②-b 가 미검증이다')
앞배율, 앞촬영본, 앞이름 = None, None, None
for i, b in (enumerate(BL) if 배율잴수있다 else []):
    D = 블록길이(i)
    if D is None:
        continue
    조각 = ([(c[0], c[0]) for c in (b[2] if isinstance(b[2], list) else [[b[2], 1]])]
            if b[0] == 'N' else [(c[0], c[1]) for c in b[1]])
    if i in ALT:        # ★대체화면.py 가 갈아 끼운 블록 — 소재 시각이 다르다
        조각 = [(ALT[i], ALT[i] + D)]
    n = len(조각)
    for k, (s_, e_) in enumerate(조각):
        # ★한 점만 재면 틀린다 (2026-08-27, 포헨즈 9편 b09).
        #   그 순간 화면이 흐리거나 밋밋하면 상관값이 엇비슷해져 옆 배율을 집는다.
        #   b09 는 ffmpeg 크롭이 1.22 인데 한 점에서 1.14 로 읽혀 애먼 b10 을 막았다.
        #   → 조각 안 세 곳에서 재서 **다수결**로 정한다.
        _몫 = D / n
        _표 = []
        for _r in (0.15, 0.45, 0.80):
            _안 = _몫 * k + min(_몫 * _r, _몫 - 0.05)
            _소 = s_ + min(_몫 * _r, _몫 - 0.05)
            _z = 배율재기(i, k, _소, _안)
            if _z is not None:
                _표.append(_z)
        z = max(set(_표), key=_표.count) if _표 else None
        이름 = 'b%02d-%d' % (i, k + 1) if n > 1 else 'b%02d' % i
        if z is None:
            continue
        같은촬영본 = (앞촬영본 is not None and 촬영본(s_) == 앞촬영본)
        if 같은촬영본 and 앞배율 is not None and abs(z - 앞배율) > 0.01:
            막힘.append('%s — 앞(%s)과 **같은 촬영본인데 배율이 %.2f→%.2f 로 바뀐다**. '
                        '화면이 툭 튄다 (drv2 의 배율맞춤 훅을 확인하라)'
                        % (이름, 앞이름, 앞배율, z))
            print('  ✗ %s 배율 %.2f  ← 앞 %s 은 %.2f (같은 촬영본)' % (이름, z, 앞이름, 앞배율))
        else:
            print('  ✓ %s 배율 %.2f%s' % (이름, z, ' (촬영본 바뀜)' if not 같은촬영본 else ''))
        앞배율, 앞촬영본, 앞이름 = z, 촬영본(e_), 이름

# ── 판정 ────────────────────────────────────────────────────────────
print()
print('=' * 62)
if 막힘:
    print('  막힘 %d건 — 고치기 전에는 굽지 마라' % len(막힘))
    for m in 막힘:
        print('   ✗ ' + m)
else:
    print('  화면 튐 없음 ✓')
if 알림:
    print('  알림 %d건 — 편의 취지를 보고 사람이 정한다' % len(알림))
    for m in 알림:
        print('   ! ' + m)
print('=' * 62)
sys.exit(1 if 막힘 else 0)
