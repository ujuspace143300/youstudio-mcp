# -*- coding: utf-8 -*-
r"""2패스 loudnorm — 통합 -13.4 LUFS · 트루피크 -1.0 dBTP (규격 §6)

왜 2패스인가
  1패스(동적 정규화)는 구간마다 게인을 흔들어 나레와 원음의 균형을 무너뜨린다.
  먼저 재고(measured_*) 그 값으로 **선형** 게인만 걸어야 톤이 그대로 남는다.
  마스터를 다시 만들면 서버가 걸어 둔 정규화가 빠지므로 믹스에서 다시 건다.
"""
import json
import re
import subprocess

_원본 = 'blocks/master_sfx.wav'
SRC = 'blocks/master_sfx_mb.wav'      # 멀티밴드를 먼저 먹인 것
OUT = 'blocks/master_sfx_ln.wav'
# ★2026-09-01 사장님 「소리가 듣는 사람 불편하지 않게」 — 크기를 한 칸 낮췄다.
#   -13.36 은 유튜브 기준(-14)보다 크다. 크게 밀어 넣으면 유튜브가 도로 깎는데,
#   깎이기 전 이미 눌린 소리라 «시끄럽고 답답한» 소리만 남는다.
#   -14.0 으로 두면 유튜브가 손대지 않고, 셈여림도 살아 있다.
#   천장은 그대로 -3.0 dBTP (선택적 제한) — AAC 로 굽는 동안 밀리는 몫까지 봐서 -3.4.
I, TP, LRA = -14.0, -3.4, 11.0

# ── 멀티밴드 압축(브로드캐스트) + 선택적 제한 −3dB ──────────────────
#   ★2026-08-27 사장님 지시 — «멀티밴드 압축기 브로드캐스트로 해주고,
#     선택적 제한에 -3데시벨은 넘지 않게».
#   프리미어의 「멀티밴드 압축기 · 브로드캐스트」는 세 대역을 따로 눌러 준다.
#   ffmpeg 에는 그 부품이 없으므로 **같은 일을 세 갈래로 갈라서** 한다 —
#     저역 ~120Hz · 중역 120~2.5k · 고역 2.5k~  각각 acompressor 로 누르고 다시 섞는다.
#   그 뒤 alimiter 로 **−3dB(0.7079) 천장**을 씌운다. 이것이 «선택적 제한»이다.
#   ★2026-09-01 — 세 대역 모두 **한 단 부드럽게** 했다(문턱 +2dB · 비율↓ · makeup↓).
#     세게 누르면 큰 소리와 작은 소리가 붙어 «계속 시끄러운» 소리가 되고, 오래 들으면
#     귀가 아프다. 사장님이 「듣는 사람 불편하지 않게」라 한 것이 이것이다.
멀티밴드 = (
    "asplit=3[lo][mid][hi];"
    "[lo]lowpass=f=120,"
    "acompressor=threshold=-22dB:ratio=2.2:attack=25:release=300:makeup=1.2[lo2];"
    "[mid]highpass=f=120,lowpass=f=2500,"
    "acompressor=threshold=-20dB:ratio=2:attack=15:release=220:makeup=1.2[mid2];"
    "[hi]highpass=f=2500,"
    "acompressor=threshold=-24dB:ratio=2.2:attack=8:release=150:makeup=1.4[hi2];"
    "[lo2][mid2][hi2]amix=inputs=3:normalize=0"
)
리미터 = "alimiter=limit=0.7079:attack=5:release=50:level=disabled"   # −3.0 dB 천장

# ── ① 멀티밴드 압축을 **먼저** 건다 ─────────────────────────────────
#   정규화 뒤에 압축하면 압축이 레벨을 다시 깎아 −20 LUFS 로 주저앉는다(실측).
#   압축 → 정규화 → 제한 순서라야 목표 라우드니스에 맞는다.
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', _원본, '-filter_complex', 멀티밴드,
                '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', SRC], check=True)

p1 = subprocess.run(['ffmpeg', '-v', 'info', '-i', SRC, '-af',
                     f'loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json',
                     '-f', 'null', '-'], capture_output=True, text=True,
                    encoding='utf-8', errors='replace')
m = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', p1.stderr, re.S)
if not m:
    raise SystemExit('1패스 측정값을 못 읽었다\n' + p1.stderr[-800:])
d = json.loads(m[-1])
print('1패스 — I %s · TP %s · LRA %s · thresh %s'
      % (d['input_i'], d['input_tp'], d['input_lra'], d['input_thresh']))

def 걸기(tp):
    af = (f"loudnorm=I={I}:TP={tp}:LRA={LRA}"
          f":measured_I={d['input_i']}:measured_TP={d['input_tp']}"
          f":measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}"
          f":offset={d['target_offset']}:linear=true:print_format=summary"
          f",{리미터}")
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', SRC, '-af', af,
                    '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', OUT], check=True)


# 되재서 확인한다 — «걸었다» 가 아니라 «맞았다» 를 봐야 한다
#   ★loudnorm 의 print_format=json 되재기는 **트루피크를 0.4~0.7dB 낙관한다.**
#     그걸 믿고 넘겼다가 완성본이 규격(-1.0)을 넘긴 편이 둘 나왔다(03·08).
#     ebur128 이 진짜 값이다. 그리고 «달란 값» 과 «나온 값» 이 다르므로,
#     규격에 들 때까지 목표를 0.4dB 씩 낮춰 **다시 건다.**
def 되재기(f):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', f,
                        '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace').stderr
    return (float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r)[-1]),
            float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', r)[-1]))


한계 = -3.3          # 마스터가 이보다 낮아야 AAC 완성본이 -3.0 안에 든다
목표TP = TP
for 회 in range(6):
    걸기(목표TP)
    i, tp = 되재기(OUT)
    print('%d회 — 달란 TP %.1f · ebur128 I %.1f LUFS · TP %.1f dBFS'
          % (회 + 1, 목표TP, i, tp))
    if tp <= 한계:
        break
    목표TP -= 0.4
else:
    raise SystemExit('★TP 를 %s 까지 낮췄는데도 규격에 못 들었다 — 믹스를 봐라' % 목표TP)
print('결과   — I %.2f LUFS · TP %.2f dBFS (ebur128 실측)' % (i, tp))
print('→', OUT)
