# -*- coding: utf-8 -*-
"""서버가 준 블록 일감에서 **컷계획.json · 배치계획.json** 을 짓는다.

왜 이게 있어야 하나
  `xml짓기.py`(프리미어 XML)와 `영상굽기.py`(균일 배율 영상)와 `덕킹재기.py` 가
  이 두 파일을 읽는다. EP1 때는 이걸 편 폴더 안에서 손으로 만들었고 볼트에 없었다 —
  그래서 EP2 를 시작하자 없었다 (2026-08-27). 편마다 다시 짓는 물건이므로 도구로 둔다.

무엇을 읽나 (전부 편 폴더 안)
  `_block_jobs.json`  서버 stitch_blocks 가 준 일감 (argv 안에 컷 시각·크롭·프레임이 다 있다)
  `그래픽/효과계획.json`  `그래픽짓기.py` 가 낸 효과자막 타이밍 (없으면 효과 칸을 비운다)

무엇을 내나
  `컷계획.json`   [{블록,컷,원본시작,프레임,크롭폭,배율,타임라인시작}, …]
  `배치계획.json` {total, blocks, orig, narr, logo, title, eff}

★프레임 수는 **계획값이 아니라 argv 의 `trim=end_frame=`** 에서 온다.
  서버가 그 값으로 실제 mp4 를 구웠으므로 타임라인이 그것과 어긋나면 안 된다.

쓰는 법
  python 계획짓기.py <편폴더>
"""
import argparse
import io
import json
import os
import re

P = argparse.ArgumentParser()
P.add_argument('편')
P.add_argument('--fps', type=int, default=30)
P.add_argument('--가로', type=int, default=1080, help='매트 창 가로 (린박스 1080)')
P.add_argument('--오프셋', type=float, default=None,
               help='구간이 마스터의 몇 초에서 잘렸나. 주면 원본시작을 **마스터 기준**으로 낸다. '
                    '없으면 편정보.json 의 «구간오프셋» 을 쓰고, 그것도 없으면 0.')
A = P.parse_args()

편 = os.path.abspath(A.편)
FPS = A.fps

# ★원본시작은 **마스터 기준**이어야 한다 — 프리미어는 마스터 한 파일을 물고 in/out 을 잡는다.
#   구간 기준으로 두면 엉뚱한 자리의 그림이 프로젝트에 깔린다 (2026-08-27 EP2 에서 실제로 그랬다).
오프셋 = A.오프셋
if 오프셋 is None:
    _ip = os.path.join(편, '편정보.json')
    오프셋 = (json.load(io.open(_ip, encoding='utf-8')).get('구간오프셋', 0)
            if os.path.exists(_ip) else 0)
오프셋 = float(오프셋)

일감 = json.load(io.open(os.path.join(편, '_block_jobs.json'), encoding='utf-8'))
일감.sort(key=lambda j: j['index'])

컷계획 = []
블록들 = []
나레들 = []
원음들 = []
t = 0                                   # 타임라인 프레임 커서

for j in 일감:
    b = int(j['index'])
    argv = j['argv']
    fc = argv[argv.index('-filter_complex') + 1]

    # ── 컷마다의 원본 시작 시각: argv 의 `-ss <t> -t <d> -i <소재>` 짝 ──
    시작들 = []
    for k, x in enumerate(argv):
        if x == '-ss' and k + 3 < len(argv) and argv[k + 2] == '-t':
            시작들.append(float(argv[k + 1]))

    # ── 컷마다의 크롭과 프레임 수: 필터 그래프의 `[n:v]crop=…trim=end_frame=…` ──
    조각 = re.findall(r'crop=(\d+):(\d+):(\d+):(\d+).*?trim=end_frame=(\d+)', fc)
    # ★소재를 이미 매트 창 크기(1080x1020)로 잘라 서버에 넘기면(drv2 의 구간_인물.mp4)
    #   서버 잡에 crop 필터가 아예 없다 (2026-09-01 EP6 실측). 그때는 컷마다
    #   전체 화면 crop 으로 간주한다 — 균일 배율 작품(신병4)은 크롭 값을 어차피 안 쓴다.
    if not 조각:
        _프레임들 = re.findall(r'trim=end_frame=(\d+)', fc)
        if len(_프레임들) == len(시작들):
            조각 = [('1080', '1020', '0', '0', f) for f in _프레임들]
    if len(조각) != len(시작들):
        raise SystemExit('★b%02d — 컷 시각 %d개인데 크롭은 %d개다'
                         % (b, len(시작들), len(조각)))

    블록프레임 = 0
    for c, ((cw, ch, cx, cy), s) in enumerate(zip(
            [(int(a), int(b_), int(c_), int(d_)) for a, b_, c_, d_, _ in 조각],
            시작들)):
        f = int(조각[c][4])
        컷계획.append({
            '블록': b, '컷': c,
            '원본시작': round(s + 오프셋, 3),
            '프레임': f,
            '크롭폭': cw,
            '배율': round(A.가로 / float(cw) * 100.0, 2),
            '타임라인시작': t + 블록프레임,
        })
        블록프레임 += f

    블록들.append({'name': 'b%02d.mp4' % b, 'start': t, 'frames': 블록프레임})
    원음들.append({'name': 'b%02d_원음.wav' % b, 'start': t})
    # 나레 블록인지는 **믹스에 나레 wav 가 들어갔는가**로 안다 (서버가 그렇게 짰다)
    if any(x.endswith('n%02d.wav' % b) for x in argv):
        나레들.append({'name': 'n%02d.wav' % b, 'start': t})
    t += 블록프레임

전체 = t

효과 = []
효p = os.path.join(편, '그래픽', '효과계획.json')
if os.path.exists(효p):
    for e in json.load(io.open(효p, encoding='utf-8')):
        효과.append({'name': e['file'], 'start': int(e['start']),
                     'frames': max(1, int(e['end']) - int(e['start'])),
                     'text': e['text']})

배치계획 = {
    'total': 전체,
    'blocks': 블록들,
    'orig': 원음들,
    'narr': 나레들,
    'logo': {'name': '로고.png', 'start': 0, 'frames': 전체},
    'title': {'name': '제목.png', 'start': 0, 'frames': 전체},
    'eff': 효과,
}

json.dump(컷계획, io.open(os.path.join(편, '컷계획.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)
json.dump(배치계획, io.open(os.path.join(편, '배치계획.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)

print('컷 %d개 · 블록 %d개 · 나레 %d개 · 효과 %d장 · 전체 %d프레임 (%.2f초) · 구간오프셋 %.3f초'
      % (len(컷계획), len(블록들), len(나레들), len(효과), 전체, 전체 / float(FPS), 오프셋))
if not 효과:
    print('  ※ 효과계획.json 이 없어 효과 칸을 비웠다 — 그래픽짓기.py 를 먼저 돌려라')
