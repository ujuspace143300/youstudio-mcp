# -*- coding: utf-8 -*-
r"""이미 지은 prproj 에서 **영상 끝을 넘는 클립의 End** 를 영상 끝으로 당긴다. (2026-09-03)
왜
  제목 클립이 영상보다 1~2프레임 길게 깔려 마지막에 제목만 남는 탈 — 납품한 EP6~EP20 전부.
  새 편은 `자막끝맞춤.py`(ASS) 와 `xml짓기.py` 가 막지만, 이미 나간 prproj 는 이 도구로 고친다.
무엇을 하나
  · 영상 끝 = 프레임으로 환산한 <End> 값 중 **세 번 이상 나오는 가장 큰 값**(V1 마지막 컷·매트·로고·A1 이 같은 값)
    — `--프레임 N` 으로 직접 줄 수도 있다.
  · 그보다 큰 <End> 를 전부 영상 끝으로 바꾼다 (트림이므로 소스 Out 은 손대지 않는다).
  · gzip 으로 되쓰고 되읽어 초과 0 을 확인한다. 원본은 <prproj>.제목끝전 으로 남긴다.
쓰는 법
  python 제목끝맞춤.py <prproj> [--프레임 N] [--확인만]
"""
import argparse, collections, gzip, re, shutil, sys

T = 254016000000
F = T / 30.0
P = argparse.ArgumentParser()
P.add_argument('prproj'); P.add_argument('--프레임', type=int); P.add_argument('--확인만', action='store_true')
A = P.parse_args()

raw = open(A.prproj, 'rb').read()
xml = gzip.decompress(raw).decode('utf-8')
ends = [int(x) for x in re.findall(r'<End>(\d+)</End>', xml)]
if A.프레임:
    총 = A.프레임
else:
    c = collections.Counter(round(e / F) for e in ends)
    후보 = [f for f, n in c.items() if n >= 3]
    if not 후보:
        raise SystemExit('영상 끝을 못 정했다 — --프레임 으로 주라')
    총 = max(후보)
총틱 = int(round(총 * F))
초과 = sorted(set(e for e in ends if e > 총틱))
print(f'{A.prproj}: 영상 끝 {총}프레임 · 넘는 End 값 {[(round(e/F,1)) for e in 초과]} · 클립 {sum(ends.count(e) for e in 초과)}개')
if A.확인만 or not 초과:
    sys.exit(1 if 초과 else 0)
새 = xml
for e in 초과:
    새 = 새.replace(f'<End>{e}</End>', f'<End>{총틱}</End>')
shutil.copy2(A.prproj, A.prproj + '.제목끝전')
open(A.prproj, 'wb').write(gzip.compress(새.encode('utf-8')))
다시 = gzip.decompress(open(A.prproj, 'rb').read()).decode('utf-8')
남 = [int(x) for x in re.findall(r'<End>(\d+)</End>', 다시) if int(x) > 총틱]
print(f'  → 고쳤다 · 되읽기 초과 {len(남)} · 태그 수 같음 {len(re.findall(r"<End>", 다시)) == len(ends)}')
sys.exit(1 if 남 else 0)
