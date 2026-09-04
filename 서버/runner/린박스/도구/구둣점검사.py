# -*- coding: utf-8 -*-
"""나레·대사 자막에 **구둣점**(마침표·쉼표 따위)이 들어 있나 본다.

왜
  2026-08-28 신병4 EP5 나레 「하나, 그리고 거기」 — 쉼표가 서버 원본부터 들어와
  mp4·prproj·srt 까지 그대로 나갔다. 작품 카드 「구둣점 금지」 위반인데
  **서버는 구둣점을 걸러 주지 않는다.** 그래서 우리 쪽에서 잰다.

무엇을 보나
  · ass: 스타일 이름이 band_narr · band_dlg · band_emph 인 줄 (효과자막·제목·크레딧은 안 본다 —
    효과자막의 「?!」 는 허용이다)
  · 대본 json(_payload_stitch.json 처럼 서버에 보낼 것): «narr»·«text»·«caption» 값
  · txt: 한 줄이 자막 하나

잡는 글자:  , . 。 ， ․ ‥ … ;  :  ·(가운뎃점)   ★ ? ! 는 잡지 않는다 (사장님이 정하면 --물음느낌 으로)

쓰는 법
  python 구둣점검사.py <captions.ass | 대본.json | 대본.txt> [--물음느낌]
    걸리면 줄마다 보여 주고 종료코드 1. 없으면 0.
"""
import argparse
import io
import json
import re
import sys

P = argparse.ArgumentParser()
P.add_argument('파일')
P.add_argument('--물음느낌', action='store_true', help='? ! 도 잡는다')
A = P.parse_args()

구둣점 = ',.。，․‥…;:·'
if A.물음느낌:
    구둣점 += '?!'
찾기 = re.compile('[' + re.escape(구둣점) + ']')

보는층 = ('band_narr', 'band_dlg', 'band_emph')


def ass줄들(경로):
    for i, 줄 in enumerate(io.open(경로, encoding='utf-8').read().split('\n'), 1):
        if not 줄.startswith('Dialogue:'):
            continue
        칸 = 줄.split(',', 9)
        if len(칸) < 10 or 칸[3] not in 보는층:
            continue
        글 = re.sub(r'\{[^}]*\}', '', 칸[9])
        yield '%d행 %s %s' % (i, 칸[1], 칸[3]), 글


def json줄들(경로):
    """서버에 보내는 payload — BLOCKS 의 각 항목은 ["N"|"D", 글, …] 꼴 (stitch 규격).
    그 밖의 json 은 narr·text·caption 키를 찾는다."""
    d = json.load(io.open(경로, encoding='utf-8'))
    if isinstance(d, dict) and isinstance(d.get('BLOCKS'), list):
        for i, b in enumerate(d['BLOCKS'], 1):
            if isinstance(b, list) and len(b) >= 2 and b[0] in ('N', 'D') and isinstance(b[1], str):
                yield 'BLOCKS[%d] %s' % (i, b[0]), b[1]
        return

    def 걷기(x, 길):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ('narr', 'text', 'caption', '나레', '대사') and isinstance(v, str):
                    yield '%s.%s' % (길, k), v
                else:
                    yield from 걷기(v, '%s.%s' % (길, k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from 걷기(v, '%s[%d]' % (길, i))
    yield from 걷기(d, '')


def txt줄들(경로):
    for i, 줄 in enumerate(io.open(경로, encoding='utf-8').read().split('\n'), 1):
        if 줄.strip():
            yield '%d행' % i, 줄


if A.파일.endswith('.ass'):
    줄들 = list(ass줄들(A.파일))
elif A.파일.endswith('.json'):
    줄들 = list(json줄들(A.파일))
else:
    줄들 = list(txt줄들(A.파일))

탈 = [(어디, 글) for 어디, 글 in 줄들 if 찾기.search(글)]
print('잰 자막 %d장 · **구둣점 든 것 %d장**' % (len(줄들), len(탈)))
for 어디, 글 in 탈:
    표시 = 찾기.sub(lambda m: '【%s】' % m.group(0), 글)
    print('  ✗ %-28s %s' % (어디, 표시))
if 탈:
    print('★ 나레·대사에 구둣점을 넣지 않는다 (작품 카드 「구둣점 금지」). 지우고 다시 재라.')
sys.exit(1 if 탈 else 0)
