# -*- coding: utf-8 -*-
"""블록마다 **나레를 걷어낸 원음 wav** 를 뽑는다 (프리미어 A1 에 깔 소리).

왜
  서버가 구운 블록 mp4 의 소리는 «원음 + 나레» 를 이미 섞은 것이라 프리미어에서
  나레 볼륨을 따로 못 만진다. 편집할 수 있게 하려면 A1 에는 **원음만**, A2 에는
  **나레만** 있어야 한다. 그래서 서버 argv 에서 나레 입력과 믹스 구간만 걷어내고
  같은 필터로 다시 굽는다 — 길이·정규화가 블록 mp4 와 한 프레임도 안 어긋난다.

★argv 를 새로 짓지 않는다. 서버가 준 것에서 나레 부분만 도려낸다.

쓰는 법
  python 원음스템.py <편폴더> [--낼방 편집소스/원음]
"""
import argparse
import io
import json
import os
import re
import subprocess

P = argparse.ArgumentParser()
P.add_argument('편')
P.add_argument('--낼방', default=os.path.join('편집소스', '원음'))
A = P.parse_args()

편 = os.path.abspath(A.편)
낼방 = A.낼방 if os.path.isabs(A.낼방) else os.path.join(편, A.낼방)
os.makedirs(낼방, exist_ok=True)

일감 = json.load(io.open(os.path.join(편, '_block_jobs.json'), encoding='utf-8'))
일감.sort(key=lambda j: j['index'])

만든것 = []
for j in 일감:
    b = int(j['index'])
    argv = list(j['argv'])
    fc = argv[argv.index('-filter_complex') + 1]
    낼 = os.path.join(낼방, 'b%02d_원음.wav' % b)

    나레길 = [x for x in argv if re.search(r'/n%02d\.wav$' % b, x)]
    if 나레길:
        # ① 믹스 구간을 «원음만» 구간으로 바꾼다
        앞, 뒤 = fc.split('concat=n=', 1)
        n, 나머지 = 뒤.split(':', 1)
        나머지 = 나머지.split('[cv][ca];', 1)[1]
        whole = re.search(r'apad=whole_len=(\d+)', 나머지).group(1)
        trim = re.search(r'atrim=0:([0-9.]+)', 나머지).group(1)
        끝페이드 = re.search(r'afade=t=out:st=([0-9.]+)',
                          나머지.split('amix')[1]).group(1)
        새fc = (앞 + 'concat=n=' + n + ':v=1:a=1[cv][ca];'
                + '[ca]loudnorm=I=-23.0:TP=-3:LRA=11,'
                + 'apad=whole_len=%s,atrim=0:%s,' % (whole, trim)
                + 'afade=t=in:st=0:d=0.002:curve=qsin,'
                + 'afade=t=out:st=%s:d=0.002:curve=qsin[a]' % 끝페이드)
        # ② 나레 `-i` 를 통째로 뺀다
        k = argv.index(나레길[0])
        del argv[k - 1:k + 1]
        argv[argv.index('-filter_complex') + 1] = 새fc
    # 나레가 없는 D 블록은 원래 소리가 곧 원음이다 — 그대로 쓴다

    # ★그림 갈래 [cv] 를 **버리는 곳에 이어 준다.** 안 이으면 ffmpeg 이
    #   «Filter 'concat' has output 0 (cv) unconnected» 로 거부한다 (2026-08-27 겪음).
    k = argv.index('-filter_complex') + 1
    argv[k] = argv[k] + ';[cv]nullsink'

    앞부분 = argv[:argv.index('-map')]
    cmd = 앞부분 + ['-map', '[a]', '-c:a', 'pcm_s24le', '-ar', '48000',
                  '-ac', '2', 낼, '-loglevel', 'error']
    subprocess.run(cmd, check=True)
    만든것.append(낼)
    print('  b%02d_원음.wav %s' % (b, '(나레 걷어냄)' if 나레길 else '(원래 원음)'))

print('원음 스템 %d개 → %s' % (len(만든것), 낼방))
