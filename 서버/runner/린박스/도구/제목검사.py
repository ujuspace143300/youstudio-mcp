# -*- coding: utf-8 -*-
r"""화면 제목(HEADLINE)이 **제목 지침서**를 지키는지 잰다.

왜 (2026-09-01 · 사장님 「앞으론 제목지침서 참고해 제작해줘 지금 제목이 엉망이야」)
  키트에 «제목 지침서.txt» 가 있는데도 제목을 손 가는 대로 지었다. 그래서
  「죽는다는데 싫다니까 / 낭만 합격이란다」 처럼 **늘어지는 서술체**가 나갔다.
  글로 적은 규칙은 다시 깨진다 — 그래서 **재는 자**로 만든다.

무엇을 재나 — 지침서 [단계 2] «팩트 임팩트 2줄 헤드라인» 규칙 그대로
  ① 무조건 **2줄**
  ② 각 줄 **10글자 이내** (띄어쓰기 포함)
  ③ **이모지 금지** (지침서: 헤드라인 단계에서는 이모지 제외)
  ④ **음슴체 금지** (`~함` `~임`) — 지침서: 억지스러운 음슴체를 배제
  ⑤ 늘어지는 **대화체 어미 경고** (`~니까` `~란다` `~거든` `~더라`)
     → 지침서는 «핵심 키워드 위주로 간결하고 명확하게» 를 요구한다

  python <키트>/도구/제목검사.py          이 편 폴더에서 잰다
"""
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

한줄한도 = 10        # 지침서 [단계 2] ① 각 줄 10글자 이내 (띄어쓰기 포함)
줄수 = 2             # 지침서 [단계 2] ① 무조건 2줄

_이모지 = re.compile(
    '[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿]')
_음슴체 = re.compile(r'(함|임)$')
_대화체 = ('니까', '란다', '거든', '더라', '잖아', '구나')

if not os.path.exists('authored.json'):
    raise SystemExit('authored.json 이 있는 편 폴더에서 돌려라')

H = json.load(io.open('authored.json', encoding='utf-8')).get('HEADLINE') or []
탈, 경고 = [], []

print('■ 제목 검사 — 제목 지침서 [단계 2] 규칙')
for i, 줄 in enumerate(H, 1):
    print('  %d줄  「%s」  %d자' % (i, 줄, len(줄)))

if len(H) != 줄수:
    탈.append('제목은 **%d줄**이라야 한다 — 지금 %d줄 (지침서 [단계 2] ①)' % (줄수, len(H)))
for i, 줄 in enumerate(H, 1):
    if len(줄) > 한줄한도:
        탈.append('%d줄 「%s」 가 %d자 — **%d자 이내**라야 한다 (지침서 [단계 2] ①)'
                  % (i, 줄, len(줄), 한줄한도))
    if _이모지.search(줄):
        탈.append('%d줄 「%s」 에 이모지가 있다 — 헤드라인엔 이모지를 넣지 않는다 (지침서 [단계 2] ②)'
                  % (i, 줄))
    if _음슴체.search(줄.strip()):
        탈.append('%d줄 「%s」 가 음슴체다 — 배제한다 (지침서 [단계 2] ②)' % (i, 줄))
    for 어미 in _대화체:
        if 줄.strip().endswith(어미):
            # ★경고가 아니라 **탈**이다 (2026-09-01). 사장님이 「엉망」이라 하신 제목이
            #   바로 이 대화체였다 — 「죽는다는데 싫다니까 / 낭만 합격이란다」.
            #   경고로 두면 그냥 통과해 또 나간다.
            탈.append('%d줄 「%s」 가 「%s」 로 끝나는 **대화체**다. 지침서는 «핵심 키워드 위주로 '
                      '간결하고 명확하게» 를 요구한다 — 명사로 끝내라' % (i, 줄, 어미))

for l in 경고:
    print('  ▲ ' + l)
if 탈:
    print()
    for l in 탈:
        print('  ✗ ' + l)
    print('\n  고치는 길: author.py 의 HEADLINE 을 지침서대로 다시 짓고 make_ass.py 를 다시 돌려라')
    print('             지침서: <키트>/제목 지침서.txt  [단계 2] 팩트 임팩트 2줄 헤드라인')
    raise SystemExit(1)
print('  제목이 지침서를 지킨다 ✓')
