# -*- coding: utf-8 -*-
r"""편 폴더에 키트 도구·자산을 갖다 놓고 ▼편별 값을 박는다 — 볼케이노 키트 `새편.py` + `한편.py 준비`(WIN 맞춤) 의 유스튜디오판.

왜 (볼케이노 키트 그대로)
  도구는 자기가 있는 자리가 아니라 **일하는 자리**(cwd)에서 파일을 찾고, ▼편별 값(SRC·WIN·금지구간)을
  **파일 안 상수**로 갖는다. 그래서 편마다 한 벌 복사하고 그 사본에 값을 박는다 — 러너 폴더의 원본은 안 건드린다.

쓰는 법 (lb_blocks 가 do[] 로 부른다 · cwd = 편 폴더)
  python <repo>/서버/runner/린박스/도구/편폴더차리기.py <편폴더> --repo <저장소 루트> --win 847 [--금지구간 "[[10.5,12.0]]"]
"""
import argparse
import io
import json
import os
import re
import shutil
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

P = argparse.ArgumentParser()
P.add_argument('편폴더')
P.add_argument('--repo', required=True)
P.add_argument('--win', type=int, required=True, help='재프레이밍 창 폭 = round(소재높이 × 1080/1020)')
P.add_argument('--금지구간', default='[]', help='fix_cuts.py 금지구간 JSON — 제목 카드·로고·예고편 자리 (규격 §27)')
P.add_argument('--도구덮기', action='store_true')
A = P.parse_args()

편 = os.path.abspath(A.편폴더)
러너 = os.path.join(os.path.abspath(A.repo), '서버', 'runner', '린박스')
도구 = os.path.join(러너, '도구')
자산 = os.path.join(os.path.abspath(A.repo), '자산', '린박스')

# lb_blocks 가 편 폴더에서 돌리는 도구 (규격 §8 4)~7c · 8b)
필요 = ['find_faces.py', '인물따라가기.py', 'reframe.py', '영상읽기.py', 'fix_cuts.py', '컷다듬기.py',
        '번쩍임정리.py', '대본검사.py', '장면튐검사.py', '컷감지.py', '전사파싱.py']
새로, 그대로 = [], []


def 놓기(src, dst, 덮기):
    if not os.path.exists(src):
        return False
    if os.path.exists(dst) and not 덮기:
        그대로.append(os.path.basename(dst)); return True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst); 새로.append(os.path.basename(dst)); return True


없음 = []
for f in 필요:
    if not 놓기(os.path.join(도구, f), os.path.join(편, f), A.도구덮기):
        없음.append(f)
# 자산 — 도구가 찾는 이름 그대로 (find_faces·인물따라가기·화자표는 cwd 의 yunet.onnx)
놓기(os.path.join(러너, '자산', 'yunet.onnx'), os.path.join(편, 'yunet.onnx'), False)
글꼴 = os.path.join(자산, 'fonts')
if os.path.isdir(글꼴):
    for f in sorted(os.listdir(글꼴)):
        놓기(os.path.join(글꼴, f), os.path.join(편, 'fonts', f), False)
else:
    없음.append('자산/린박스/fonts/*')

# ▼편별 값 박기 — 한편.py 준비가 하던 WIN 맞춤 + fix_cuts 금지구간
def 박기(파일, 패턴, 새줄):
    p = os.path.join(편, 파일)
    if not os.path.exists(p):
        return
    t = io.open(p, encoding='utf-8').read()
    t2 = re.sub(패턴, 새줄, t, count=1, flags=re.M)
    if t2 != t:
        io.open(p, 'w', encoding='utf-8').write(t2)
        print(f'  {파일}: {새줄}')

for 이름 in ('find_faces.py', 'reframe.py'):
    박기(이름, r'^WIN = \d+', 'WIN = %d' % A.win)
try:
    금지 = json.loads(A.금지구간)
    assert isinstance(금지, list)
except Exception:
    raise SystemExit('★--금지구간 은 [[시작,끝],…] JSON 이어야 한다: %r' % A.금지구간)
박기('fix_cuts.py', r'^금지구간 = .*$', '금지구간 = ' + json.dumps(금지, ensure_ascii=False))

print('■ 편 폴더 차림 — %s' % 편)
print('  새로 %d개 · 그대로 %d개' % (len(새로), len(그대로)))
if 없음:
    print('  ★없어서 못 놓은 것: ' + ', '.join(없음))
    if any(x.endswith('.py') for x in 없음):
        raise SystemExit(1)
