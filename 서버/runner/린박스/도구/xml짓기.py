# -*- coding: utf-8 -*-
"""한 편을 프리미어가 읽을 FCP7 XML 로 낸다 — 정본 맥 사슬 `신병4/xml짓기.py` 의 유스튜디오판 (2026-09-04).

정본과 다른 점 (작품이 신병4 하나가 아니라서)
  · make_xml 을 볼트 절대경로가 아니라 **같은 폴더**(서버/runner/린박스/도구)에서 가져온다.
  · 작품 이름·자막 ass·레터박스 배율을 **인자로** 받는다 (정본은 captions_신병4.ass · 106.25% 가 박혀 있었다).
      --작품 <이름>      시퀀스 이름 «<작품> <편> 숏폼» (기본: 편정보.json 의 «작품», 없으면 린박스)
      --자막 <ass>       기본 captions_<작품>.ass
      --배율 <퍼센트>    V1 컷 배율. 기본 106.25 = 1020/960 (신병4 EPK: 위아래 60px 레터박스). lb_xml 이 lb_probe 의
                         content_h 로 1020/content_h×100 을 넘긴다 — 레터박스가 매트 뒤로 정확히 숨는 값.

규격 §52 — 자막은 <generatoritem> 텍스트 제너레이터로 낸다.
프리미어가 그걸 **진짜 텍스트 그래픽**으로 만들어 주므로 글자를 바로 고칠 수 있고
본떠서만들기.py 가 곳간 서식을 그대로 입힐 수 있다.

트랙
  V1 컷 (편집용마스터에서 in/out 으로 물린다 — 앞뒤로 늘릴 수 있다)
  V2 매트 · V3 로고 · V4 제목 · V5 나레자막 · V6 대사자막 · V7 효과자막
  A1 컷마다의 원음 · A2 나레이션 · A3 효과음(효과음계획.json 이 있을 때만)

쓰는 법
  python xml짓기.py <편폴더> <편집용마스터.mp4> <낼.xml> [--작품 신병4] [--자막 captions_신병4.ass] [--배율 106.25]
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_xml as MX  # noqa: E402

P = argparse.ArgumentParser()
P.add_argument('편')
P.add_argument('마스터')
P.add_argument('낼')
P.add_argument('--작품', default=None)
P.add_argument('--자막', default=None)
P.add_argument('--배율', type=float, default=None)
A = P.parse_args()

편 = A.편
마스터 = A.마스터
낼 = A.낼
FPS = 30

_정보길 = os.path.join(편, '편정보.json')
_정보 = json.load(io.open(_정보길, encoding='utf-8')) if os.path.exists(_정보길) else {}
작품 = A.작품 or _정보.get('작품') or '린박스'
자막 = A.자막 or os.path.join(편, 'captions_%s.ass' % 작품)
if not os.path.isabs(자막) and not os.path.exists(자막):
    자막 = os.path.join(편, 자막)
if not os.path.exists(자막):
    raise SystemExit('★자막 ass 가 없다: %s (lb_subs 의 서식.py 가 낸 captions_<작품>.ass)' % 자막)

# ★전체 길이와 편 이름을 **박아 두지 않는다** — 편마다 다르다 (2026-08-27 EP2 에서 걸림).
_배치미리 = json.load(io.open(os.path.join(편, '배치계획.json'), encoding='utf-8'))
전체 = int(_배치미리['total'])
편이름 = os.path.basename(os.path.normpath(편)).replace('작업_', '')


def 초(x):
    h, m, s = x.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


# ── 자막 읽기 ────────────────────────────────────────────────
서식 = {}
층별 = {}
for 줄 in io.open(자막, encoding='utf-8'):
    if 줄.startswith('Style:'):
        칸 = 줄[6:].split(',')
        서식[칸[0].strip()] = {'글꼴': 칸[1].strip(), '크기': float(칸[2]),
                              '칠': 칸[3].strip(), '선': float(칸[16])}
    elif 줄.startswith('Dialogue:'):
        f = 줄.split(',', 9)
        층 = f[3].strip()
        글 = re.sub(r'\{[^}]*\}', '', f[9]).strip()
        if not 글:
            continue
        m = re.search(r'\\pos\(\s*[\d.]+\s*,\s*([\d.]+)\)', f[9])
        층별.setdefault(층, []).append({
            's': int(round(초(f[1]) * FPS)), 'e': int(round(초(f[2]) * FPS)),
            '글': 글, 'y': float(m.group(1)) if m else None})


def ass색(v):
    """&H00BBGGRR → #RRGGBB"""
    h = v.replace('&H', '').replace('&', '').zfill(8)
    return '#%s%s%s' % (h[6:8], h[4:6], h[2:4])


배치_ = json.load(io.open(os.path.join(편, '배치계획.json'), encoding='utf-8'))


def 글자트랙(층이름들, 이름):
    """한 트랙에 얹을 텍스트 그래픽 클립들"""
    나온 = []
    for 층 in 층이름들:
        st = 서식.get(층, {'글꼴': 'GangwonEduAllBold', '크기': 80,
                          '칠': '&H00FFFFFF', '선': 3.0})
        for i, c in enumerate(층별.get(층, [])):
            # ★영상 끝(배치계획 total)을 넘는 자막은 거기서 자른다 (2026-09-03 사장님 지적) —
            #   서버 ASS 의 헤드라인·크레딧 끝은 «계획 길이»라 실제 프레임 수보다 1~2프레임 길어,
            #   그대로 두면 제목 클립이 영상 뒤에 홀로 남는다 (EP6~EP20 전부 그랬다).
            총 = int(배치_['total'])
            if c['s'] >= 총:
                continue
            dur = max(1, min(c['e'], 총) - c['s'])
            y = c['y'] if c['y'] is not None else 1179
            나온.append(MX.글자클립(
                f'gen-{이름}-{층}-{i}', c['글'], c['s'], dur, c['글'],
                글꼴=st['글꼴'],
                # ★FCP7 텍스트는 720x480 기준 pt 로 잰다 — 480/1920 을 곱한다 (교훈 §326)
                크기=round(st['크기'] * 480.0 / 1920.0, 2),
                색=ass색(st['칠']),
                세로가운데=y + st['크기'] / 2.0,
                프레임높이=1920, 외곽=st['선']))
    나온.sort(key=lambda x: int(re.search(r'<start>(\d+)</start>', x).group(1)))
    return 나온


# ── 나레이션이 덮는 블록 ─────────────────────────────────────
#   ★완성본은 나레 밑 원음을 **−25.1 dB** 로 눌러 놨다 (2026-08-27 실측 · 덕킹재기.py).
#     프로젝트 A1 을 0 dB 로 두면 완성본에선 안 들리던 대사가 프리미어에서 들리고,
#     그 대사에는 자막이 없다 — 사장님: «대사는 있는데 자막이 없는건 아주 큰 하자».
#     그래서 나레 블록의 원음 클립에 같은 감쇠를 건다.
블록시작 = {}
_t = 0
for b in 배치_['blocks']:
    블록시작[_t] = int(b['name'][1:3])
    _t += b['frames']
나레블록 = {블록시작[int(x['start'])] for x in 배치_['narr'] if int(x['start']) in 블록시작}
원음감쇠 = 10 ** (-25.1 / 20.0)      # 0.0556 배


def 소리크기(배):
    """FCP7 오디오 레벨 필터 — 정적 값이라 프리미어가 받는다 (규격 §52)."""
    return ('<filter><effect><name>Audio Levels</name>'
            '<effectid>audiolevels</effectid>'
            '<effectcategory>audiolevels</effectcategory>'
            '<effecttype>audiolevels</effecttype>'
            '<mediatype>audio</mediatype>'
            '<parameter><parameterid>level</parameterid><name>Level</name>'
            '<valuemin>0</valuemin><valuemax>3.98109</valuemax>'
            f'<value>{배:.6f}</value></parameter>'
            '</effect></filter>')


# ── V1 컷 · A1 원음 ──────────────────────────────────────────
# ★배율을 **전 컷 같은 값** 으로 맞춘다 (2026-08-27 사장님 지시 «영상배율을 적절하게 모두 맞춰서 일관되게»).
#   서버 배율은 94.57~137.06% 로 널뛰는데 크롭 중심이 전부 원본 한가운데라 인물을 잡기 위한 확대가 아니다.
#   100% 는 안 된다 — 원본에 위아래 레터박스가 있으면 그 검은 띠가 매트 창 안으로 들어온다.
#   1020/그림높이 로 하면 띠가 매트(0~449 · 1470~) 뒤로 딱 숨는다 (신병4 EPK: 1020/960 = 106.25%).
레터박스배율 = A.배율 if A.배율 is not None else 1020.0 / 960.0 * 100.0
컷들 = json.load(io.open(os.path.join(편, '컷계획.json'), encoding='utf-8'))
F = MX.Files()
v1, a1 = [], []
눌린 = 0
for i, c in enumerate(컷들):
    srcin = int(round(c['원본시작'] * FPS))
    dur = int(c['프레임'])
    start = int(c['타임라인시작'])
    v1.append(MX.clip(f'v1-{i}', f'mc-master', f'컷{i:02d}', start, dur,
                      마스터, 'v', F, srcin=srcin,
                      extra=MX.scale_filter(레터박스배율)))
    누름 = c['블록'] in 나레블록
    if 누름:
        눌린 += 1
    a1.append(MX.clip(f'a1-{i}', f'mc-master', f'원음{i:02d}', start, dur,
                      마스터, 'a', F, srcin=srcin,
                      extra=소리크기(원음감쇠) if 누름 else ''))
print('나레 블록 %s — 원음 −25.1dB 로 누른 컷 %d/%d · 배율 %.2f%%'
      % (sorted(나레블록), 눌린, len(컷들), 레터박스배율))

# ── V2 매트 · V3 로고 ────────────────────────────────────────
매트 = os.path.join(편, '그래픽', '매트.png')
로고 = os.path.join(편, '그래픽', '로고.png')
v2 = [MX.clip('v2-0', 'mc-매트', '매트', 0, 전체, 매트, 'v', F)]
v3 = [MX.clip('v3-0', 'mc-로고', '로고', 0, 전체, 로고, 'v', F)]

# ── V4~V7 자막 ───────────────────────────────────────────────
# ★제목 두 줄은 **트랙을 갈라** 놓는다 (2026-08-27) — 한 트랙에 두면 뒤엣것이 앞엣것을 덮어 한 줄만 남는다.
v4 = 글자트랙(['headline_l1'], '제목1')
v4b = 글자트랙(['headline_l2'], '제목2')
v5 = 글자트랙(['band_narr'], '나레자막')
v6 = 글자트랙(['band_dlg', 'band_emph'], '대사자막')
v7 = 글자트랙(['effect_float'], '효과자막')

# ── A2 나레이션 ──────────────────────────────────────────────
a2 = []
for i, n in enumerate(배치_['narr']):
    p = os.path.join(편, 'blocks', n['name'])
    if not os.path.exists(p):
        continue
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'format=duration', '-of', 'csv=p=0', p],
                       capture_output=True, text=True)
    dur = max(1, int(round(float(r.stdout.strip()) * FPS)))
    a2.append(MX.clip(f'a2-{i}', f'mc-n{i}', n['name'], int(n['start']), dur,
                      p, 'a', F))

# ── A3 효과음 (있을 때만 — 효과음낱개굽기가 낸 효과음계획.json + 효과음/NN_*.wav) ──
a3 = []
_sfx계획 = os.path.join(편, '효과음계획.json')
if os.path.exists(_sfx계획):
    for i, e in enumerate(json.load(io.open(_sfx계획, encoding='utf-8'))):
        p = os.path.join(편, e['파일'])
        if not os.path.exists(p):
            continue
        a3.append(MX.clip(f'a3-{i}', f'mc-sfx{i}', os.path.basename(p),
                          int(round(e['시각'] * FPS)),
                          max(1, int(round(e['길이'] * FPS))), p, 'a', F))

xml = MX.build('%s %s 숏폼' % (작품, 편이름), 전체, v1, [v2, v3, v4, v4b, v5, v6, v7],
               [a1, a2] + ([a3] if a3 else []), None)
io.open(낼, 'w', encoding='utf-8').write(xml)
print('V1 컷 %d · 제목 %d+%d · 나레 %d · 대사 %d · 효과 %d · A1 %d · A2 %d · A3(sfx) %d'
      % (len(v1), len(v4), len(v4b), len(v5), len(v6), len(v7), len(a1), len(a2), len(a3)))
print('→', 낼, os.path.getsize(낼), '바이트')
