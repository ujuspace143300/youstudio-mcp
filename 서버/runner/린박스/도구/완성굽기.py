# -*- coding: utf-8 -*-
"""납품용 완성본 mp4 를 굽는다 — **배율 균일 영상 + 매트 + 로고 + 채널 서식 자막**.

서버가 낸 마스터와 무엇이 다른가
  · 영상: 서버 블록은 컷마다 배율이 널뛰고 레터박스가 매트 창에 들어온다.
    `영상굽기.py` 가 낸 `blocks/merged_균일.mp4` 를 쓴다.
  · 자막: 서버 기본 서식이 아니라 작품 서식(`captions_신병4_로고.ass` 등).
    폭맞춤(`\\fscx`)이 들어 있어 긴 대사가 화면을 안 벗어난다.
  · 하단: 크레딧 문구 대신 **로고 PNG** 를 얹는다 (문구를 쓸 편은 --자막 을 로고 아닌
    쪽으로 주고 --로고 없음).
  · 소리: 서버가 맞춘 `blocks/master.wav` 를 그대로 쓴다 (라우드니스·트루피크 규격).

쓰는 법
  python 완성굽기.py <편폴더> <낼파일.mp4> [--영상 blocks/merged_균일.mp4]
                     [--소리 blocks/master.wav] [--자막 captions_신병4_로고.ass]
                     [--로고 그래픽/로고.png] [--창위 450] [--창아래 1470]
"""
import argparse
import os
import subprocess

P = argparse.ArgumentParser()
P.add_argument('편')
P.add_argument('낼')
P.add_argument('--영상', default='blocks/merged_균일.mp4')
P.add_argument('--소리', default='blocks/master.wav')
P.add_argument('--자막', default='captions_신병4_로고.ass')
P.add_argument('--로고', default='그래픽/로고.png')
P.add_argument('--창위', type=int, default=450)
P.add_argument('--창아래', type=int, default=1470)
P.add_argument('--가로', type=int, default=1080)
P.add_argument('--세로', type=int, default=1920)
A = P.parse_args()

편 = os.path.abspath(A.편)


def 길(x):
    return x if os.path.isabs(x) else os.path.join(편, x)


영상, 소리, 자막 = 길(A.영상), 길(A.소리), 길(A.자막)
# ★«낼 파일» 만은 편 폴더가 아니라 **내가 선 자리** 기준이다 — 길() 로 붙이면
#   «작업_EP4/작업_EP4/…» 가 되어 ffmpeg 이 못 연다 (2026-08-27 EP4 에서 겪음).
낼길 = os.path.abspath(A.낼)
글꼴방 = os.path.join(편, 'fonts')
로고 = 길(A.로고) if A.로고 and A.로고 != '없음' else None
매트높이 = A.창위
아랫높이 = A.세로 - A.창아래

for p in (영상, 소리, 자막):
    if not os.path.exists(p):
        raise SystemExit('★없다: %s' % p)

ins = ['-i', 영상, '-i', 소리]
fc = ("color=c=#000000:s=%dx%d:r=30,format=yuv444p[bg];"
      "[0:v]format=yuv444p,setsar=1[clip];"
      "[bg][clip]overlay=0:%d:format=yuv444:shortest=1[v0];"
      "color=c=#000000:s=%dx%d:r=30,format=yuv444p[ctop];"
      "[v0][ctop]overlay=0:0:format=yuv444:shortest=1[otop];"
      "color=c=#000000:s=%dx%d:r=30,format=yuv444p[cbot];"
      "[otop][cbot]overlay=0:%d:format=yuv444:shortest=1[obot]"
      % (A.가로, A.세로, A.창위, A.가로, 매트높이, A.가로, 아랫높이, A.창아래))

앞 = '[obot]'
if 로고:
    # ★`-loop 1` 이 없으면 로고는 **1프레임짜리 입력**이라 shortest 가 영상 전체를
    #   1프레임으로 잘라 버린다 (2026-08-27 겪음 — 소리만 50초, 그림은 한 장).
    ins += ['-loop', '1', '-i', 로고]
    fc += ';[obot][2:v]overlay=0:0:format=yuv444:shortest=1[ol]'
    앞 = '[ol]'

fc += (";%sass=filename='%s':fontsdir='%s',format=yuv444p,scale=out_range=tv,"
       "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[v]"
       % (앞, 자막, 글꼴방))

# ★영상 길이에 맞춰 자른다 — AAC 는 앞뒤에 패딩을 붙여 소리가 0.2초쯤 길어진다.
#   안 자르면 컨테이너 길이가 영상보다 길게 찍혀 «규격 안인가» 검사가 어긋난다.
_r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                     '-show_entries', 'stream=duration', '-of', 'csv=p=0', 영상],
                    capture_output=True, text=True)
_길이 = float(_r.stdout.split()[0])   # ffprobe 가 두 줄 내는 파일이 있다(타임코드 트랙) — 첫 값만 (2026-09-03)

cmd = (['ffmpeg', '-y'] + ins + ['-filter_complex', fc, '-map', '[v]', '-map', '1:a',
       '-t', '%.3f' % _길이,
       '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
       '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709',
       '-color_trc', 'bt709', '-r', '30', '-c:a', 'aac', '-b:a', '192k',
       '-movflags', '+faststart', 낼길, '-loglevel', 'error'])
subprocess.run(cmd, check=True)

r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
                    낼길], capture_output=True, text=True)
d = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'csv=p=0', 낼길], capture_output=True, text=True)
print('완성본 %s · %s · %.3f초' % (os.path.basename(낼길),
                               r.stdout.strip(), float(d.stdout.split()[0])))
if r.stdout.strip() != '%d,%d' % (A.가로, A.세로):
    raise SystemExit('★해상도가 규격과 다르다')
