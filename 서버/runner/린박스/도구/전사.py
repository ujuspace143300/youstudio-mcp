# -*- coding: utf-8 -*-
r"""대사를 **오타 없이** 받아 적는다.

왜 이렇게까지 하나
  자막에 오타가 한 글자라도 있으면 그 편은 못 쓴다. 그런데 영화 음성은 음악·효과음이
  섞여 있어 한 번 전사로는 못 믿는다. 실제로 이런 일이 있었다.
    · 27분을 통째로 64kbps 로 눌러 보냈더니 말 덩어리 경계가 뭉개져
      자막이 **다른 사람 말 위에** 떴다
    · 「손이 근지러워서」를 [소니근]→「손에 익은」으로 잘못 끊었다
    · 「손꾸락 하나」를 「손꾸락 감아」로 들었다

방법 — **세 번 듣고 서로 대조한다**
  ① 원음 그대로
  ② 말소리 대역만 남기고 고르게 편 소리
     (highpass 90 · lowpass 7800 · dynaudnorm — 음악과 저역 효과음을 덜어낸다)
  ③ 잡음을 걷어낸 소리 (afftdn — 배경음악·룸톤을 줄인다)
  **셋 다 같게 들린 낱말만 믿는다.** 둘만 맞거나 확신이 낮으면 ★ 로 찍는다.

  ★ 그래도 놓친다. 사투리·구어는 ASR 이 표준어로 바꿔 버린다 —
    「바빠가지고」를 「바빠서」로, 「고니」를 「공원이」로 들었다.
    그래서 **★ 가 없는 낱말도 사장님 귀가 최종 판정**이다. 이 표는 초안일 뿐이다.

내는 것
  대사.json    낱말마다 시각·화자·확신·두 번 일치 여부
  대사표.txt   사람이 읽는 표 (화자별 발화, ★ 는 확인 필요)
"""
import json
import io
import os
import subprocess
import sys
import time
from difflib import SequenceMatcher

# ★파이프로 잡혀 돌 때 stdout 이 cp949 가 된다 — «—» 한 글자에 통째로 죽는다 (취사병 2026-09-01)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SRC = sys.argv[1] if len(sys.argv) > 1 else '구간.mp4'
def _키(이름):
    """환경변수에 없으면 ~/.volcano/.env 에서 읽는다.

    ★2026-08-26 — `drv2.py` 는 진작 이렇게 하고 있었고 `검증.py` 도 그 파일을 본다.
      **전사.py 만 환경변수만 봤다.** 그래서 새 편을 시작하자마자
      «SPEECHMATICS_API_KEY 가 없다» 로 죽었다 — 키는 멀쩡히 파일에 있는데도.
      키를 읽는 자리는 도구마다 같아야 한다.
    """
    v = os.environ.get(이름, '').strip()
    if v:
        return v
    p = os.path.join(os.path.expanduser('~'), '.volcano', '.env')
    try:
        for ln in io.open(p, encoding='utf-8'):
            ln = ln.strip()
            if ln.startswith(이름 + '='):
                return ln.split('=', 1)[1].strip()
    except OSError:
        pass
    return ''


KEY = _키('SPEECHMATICS_API_KEY')
if not KEY:
    # ★환경변수가 없는 셸에서도 돌게 — 서버와 같은 자리(~/.volcano/keys/)를 본다
    #   ([[volcano-api-key-location]] 함정: .env 는 아무도 안 읽는다. 취사병 2026-09-01 재발)
    p = os.path.expanduser('~/.volcano/keys/speechmatics')
    if os.path.exists(p):
        KEY = open(p, encoding='utf-8').read().strip()
if not KEY:
    raise SystemExit('SPEECHMATICS_API_KEY 가 없다 (환경변수도 ~/.volcano/keys/speechmatics 도 없음)')


# ▼편별 ─── 이 편에서만 쓰는 값 ────────────────────────────────────
# ★낱말사전은 **이 파일에 적지 않는다** (2026-08-27 · 지시/맥1).
#   전에는 여기에 신병4 이름(김현욱·최일구·병장…)이 박힌 채로 볼트에 올라가 있었다.
#   사전은 «그쪽으로 끌어당기는» 도구다. 다른 드라마의 새 편을 뜨면 그 이름들이
#   그대로 따라가 **없는 이름을 만들어 낸다** — 게다가 조용히 틀린다.
#   편정보(제목·로고)를 도구에서 데이터 파일로 뺀 것과 같은 까닭이다 (규격 §70).
#
#   적는 곳 — 앞엣것이 이긴다. 같은 이름이면 앞엣것으로 덮는다.
#     ① 편 폴더    `사전.json`                    이 편에서만 쓰는 낱말
#     ② 편 폴더    `편정보.json` 의 «낱말사전»
#     ③ 드라마 폴더 `드라마정보.json` 의 «낱말사전»  ★이름은 편마다 안 바뀐다.
#                                                   여기가 제자리다 — 한 번 적으면
#                                                   그 드라마의 모든 편이 쓴다.
#   형식은 셋 다 같다. `사전.json` 은 목록만 있으면 된다:
#     [{"content": "김현욱", "sounds_like": ["김현욱", "김현국", "김현웅"]}]
#   `sounds_like` 에는 **실제로 그렇게 들린 말**을 넣는다 — 그래야 그쪽으로 끌어온다.
#   무엇을 넣을지는 `대사맞춤.py` 가 짚어 준다 («ASR 이 못 알아들은 이름» 항목).
# ▲편별 ──────────────────────────────────────────────────

def 사전읽기(기준='.'):
    """편 폴더 → 드라마 폴더 순으로 낱말사전을 모은다. (사전, 어디서읽었나)"""
    편 = os.path.abspath(기준)
    드라마 = os.path.dirname(편)

    def _읽자(경로, 키=None):
        try:
            d = json.load(io.open(경로, encoding='utf-8'))
        except (OSError, ValueError):
            return []
        목 = d.get(키, []) if (키 and isinstance(d, dict)) else d
        return 목 if isinstance(목, list) else []

    자리 = [(os.path.join(편, '사전.json'), None, '사전.json'),
            (os.path.join(편, '편정보.json'), '낱말사전', '편정보.json'),
            (os.path.join(드라마, '드라마정보.json'), '낱말사전', '드라마정보.json')]

    사전, 본이름, 쓴곳 = [], set(), []
    for 경로, 키, 이름 in 자리:
        새것 = []
        for x in _읽자(경로, 키):
            if not isinstance(x, dict) or not (x.get('content') or '').strip():
                print(f'★ {이름} 의 낱말 하나를 건너뛴다 — content 가 없다: {x!r}')
                continue
            c = x['content'].strip()
            if c in 본이름:                 # 앞 자리(더 좁은 범위)가 이긴다
                continue
            본이름.add(c)
            sl = x.get('sounds_like') or []
            sl = [s for s in sl if isinstance(s, str) and s.strip()]
            새것.append({'content': c, 'sounds_like': sl or [c]})
        if 새것:
            사전 += 새것
            쓴곳.append(f'{이름} {len(새것)}개')
    return 사전, ' · '.join(쓴곳)


낱말사전, _사전출처 = 사전읽기()
if 낱말사전:
    print(f'■ 편별 낱말사전 {len(낱말사전)}개 — {_사전출처}')
    print('  ' + ' · '.join(w['content'] for w in 낱말사전))
else:
    # ★경고만 하고 멈추지는 않는다. 사전 없이도 전사는 돌아간다 — 다만 이름이 틀린다.
    print('★ 편별 낱말사전이 비어 있다 — 이름·고유명사를 ASR 이 못 알아듣는다.')
    print('  (「고니」를 「공원이」로 받아 적으면 서버 대조에서 그 편이 반려된다)')
    print('  채우는 곳: 편 폴더 사전.json · 편정보.json 의 «낱말사전»')
    print('             드라마 폴더 드라마정보.json 의 «낱말사전» ← 이름은 여기가 제자리')
    print('  무엇을 넣을지는 대사맞춤.py 가 짚어 준다.')
    print('  이대로 사전 없이 전사한다 — 멈추려면 지금 Ctrl-C.')


def submit(path):
    tc = {"language": "ko", "operating_point": "enhanced",
          "diarization": "speaker"}
    if 낱말사전:                      # ★이름을 미리 일러 주면 그쪽으로 받아 적는다
        tc["additional_vocab"] = 낱말사전
    cfg = json.dumps({"type": "transcription", "transcription_config": tc})
    r = subprocess.run(['curl', '-sS', '-X', 'POST',
                        'https://asr.api.speechmatics.com/v2/jobs/',
                        '-H', f'Authorization: Bearer {KEY}',
                        '-F', f'config={cfg}', '-F', f'data_file=@{path}'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return json.loads(r.stdout)['id']


def fetch(jid):
    for _ in range(240):
        time.sleep(4)
        q = subprocess.run(['curl', '-sS',
                            f'https://asr.api.speechmatics.com/v2/jobs/{jid}',
                            '-H', f'Authorization: Bearer {KEY}'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        st = json.loads(q.stdout)['job']['status']
        if st == 'done':
            break
        if st == 'rejected':
            raise SystemExit(f'전사 거절: {q.stdout[:300]}')
    g = subprocess.run(['curl', '-sS',
                        f'https://asr.api.speechmatics.com/v2/jobs/{jid}/transcript'
                        '?format=json-v2', '-H', f'Authorization: Bearer {KEY}'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return json.loads(g.stdout)


def words(d):
    out = []
    for x in d.get('results', []):
        if x.get('type') != 'word':
            continue
        a = x['alternatives'][0]
        t = (a.get('content') or '').strip()
        if t:
            out.append({'s': x['start_time'], 'e': x['end_time'], 't': t,
                        'c': float(a.get('confidence') or 0.0),
                        'spk': a.get('speaker', '?')})
    return out


# ① 소리를 두 벌로 만든다 — 원음, 그리고 말소리만 남긴 것
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', SRC, '-vn',
                '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '_asr_raw.wav'], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', SRC, '-vn',
                '-af', 'highpass=f=90,lowpass=f=7800,dynaudnorm=f=180:g=7',
                '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '_asr_voice.wav'], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', SRC, '-vn',
                '-af', 'afftdn=nr=14:nf=-28,highpass=f=100,dynaudnorm=f=200:g=5',
                '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '_asr_dn.wav'], check=True)

print('세 벌을 동시에 보낸다 …', flush=True)
j1, j2, j3 = submit('_asr_raw.wav'), submit('_asr_voice.wav'), submit('_asr_dn.wav')
A, B, C = words(fetch(j1)), words(fetch(j2)), words(fetch(j3))
print(f'  원음 {len(A)} · 말소리 {len(B)} · 잡음제거 {len(C)} 낱말')


def agreed(base, other):
    sm = SequenceMatcher(None, [w['t'] for w in base], [w['t'] for w in other],
                         autojunk=False)
    ok = set()
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag == 'equal':
            ok.update(range(i1, i2))
    return ok


ab, ac = agreed(A, B), agreed(A, C)
OUT = []
for i, w in enumerate(A):
    w = dict(w)
    votes = (i in ab) + (i in ac)
    w['votes'] = 1 + votes                      # 자기 자신 포함 몇 벌이 같게 들었나
    w['sure'] = bool(votes == 2 and w['c'] >= 0.62)
    OUT.append(w)
json.dump({'words': OUT}, open('대사.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# 서버 대조용으로 쓰는 seg_asr.json 은 원음 전사를 그대로 둔다
json.dump(fetch(j1) if False else {'results': [
    {'type': 'word', 'start_time': w['s'], 'end_time': w['e'],
     'alternatives': [{'content': w['t'], 'confidence': w['c'], 'speaker': w['spk']}]}
    for w in A]}, open('seg_asr.json', 'w', encoding='utf-8'), ensure_ascii=False)

# ③ 사람이 읽는 표
GAP = 0.55
utt, cur = [], [OUT[0]] if OUT else []
for w in OUT[1:]:
    if w['s'] - cur[-1]['e'] > GAP or w['spk'] != cur[-1]['spk']:
        utt.append(cur)
        cur = [w]
    else:
        cur.append(w)
if cur:
    utt.append(cur)

lines = [f"■ 화자 {len({w['spk'] for w in OUT})}명 · 낱말 {len(OUT)}개 "
         f"· 셋 다 일치 {sum(1 for w in OUT if w['sure'])}개 "
         f"({sum(1 for w in OUT if w['sure'])/max(len(OUT),1)*100:.0f}%)",
         f"■ 낱말사전 {len(낱말사전)}개 ({_사전출처 or '없음'})",
         "★ = 세 벌이 갈렸거나 확신이 낮다. 자막에 그대로 옮기지 말 것.",
         "※ ★ 가 없어도 사투리·구어는 틀릴 수 있다 — 최종 판정은 귀로.", ""]
for g in utt:
    txt = ' '.join((w['t'] if w['sure'] else '★' + w['t']) for w in g)
    lines.append(f"{g[0]['s']:7.2f}~{g[-1]['e']:7.2f} [{g[0]['spk']}] {txt}")
open('대사표.txt', 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('\n'.join(lines[:4]))
print(f"→ 대사.json · 대사표.txt · seg_asr.json  (발화 {len(utt)}덩이)")
