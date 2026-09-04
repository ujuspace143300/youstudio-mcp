# -*- coding: utf-8 -*-
r"""드라마 폴더 아래의 **공식 SRT 후보**를 전부 읽어 JSON 으로 낸다 — 서버(lb_transcript)가 내용 대조로 고른다.

왜 (2026-09-04 사장님 「전사가 완벽할 수 없다 — SRT 로 맞춰라」 · 제안 20260904 · 규격 §94)
  볼케이노 키트의 srt고르기.py 는 편 폴더의 srt대사.txt(SRT 에서 베낀 대사)와 후보를 글자 그대로 대조한다.
  유스튜디오는 그 srt대사.txt 가 아직 없다(전사만 있다). 그래서 후보를 통째로 서버에 올리고,
  서버가 **전사 낱말(대사.json)** 과 글자·시각을 대조해 고른다 (srt.ts pickSrt — 로직은 srt고르기.py 를 옮김).
  경로로 짐작하지 않는다 — 옆 드라마·다른 회차 SRT 를 물면 보고서가 그럴듯하게 거짓이 된다.

쓰는 법
  python srt후보읽기.py <뿌리 폴더> [--최대줄 4000]
  표준출력: [{"path": "...", "lines": [[시작초, 끝초, "글"], ...]}, ...]  (JSON 한 덩어리)
  작업/·완성/·blocks/·_회귀* 폴더는 건너뛴다 — 우리가 만든 납품 SRT(자막_대사.srt 등)를 후보로 물지 않게.
"""
import argparse
import io
import json
import os
import re
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

P = argparse.ArgumentParser()
P.add_argument('뿌리')
P.add_argument('--최대줄', type=int, default=4000)
A = P.parse_args()

건너뜀 = {'작업', '완성', 'blocks', 'narr_norm', 'cache', 'node_modules', '.git'}


def srt읽기(p):
    txt = io.open(p, encoding='utf-8-sig', errors='replace').read()
    out = []
    for blk in re.split(r'\n\s*\n', txt):
        m = re.search(r'(\d\d):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d+)', blk)
        if not m:
            continue
        g = m.groups()
        s = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3][:3].ljust(3, '0')) / 1000.0
        e = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7][:3].ljust(3, '0')) / 1000.0
        글 = ' '.join(l.strip() for l in blk.split('\n')[2:] if l.strip())
        글 = re.sub(r'<[^>]+>', '', 글).strip()
        if 글:
            out.append([round(s, 3), round(e, 3), 글])
    return out


후보 = []
뿌리 = os.path.abspath(A.뿌리)
for r, dirs, files in os.walk(뿌리):
    dirs[:] = sorted(d for d in dirs if d not in 건너뜀 and not d.startswith('_회귀') and not d.startswith('.'))
    for f in sorted(files):
        if not f.lower().endswith('.srt'):
            continue
        p = os.path.join(r, f)
        try:
            lines = srt읽기(p)
        except OSError:
            continue
        if not lines:
            continue
        후보.append({'path': p.replace(os.sep, '/'), 'lines': lines[:A.최대줄], 'total': len(lines)})

print(json.dumps(후보, ensure_ascii=False))
