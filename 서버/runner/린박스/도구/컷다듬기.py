# -*- coding: utf-8 -*-
r"""원음(D) 블록을 **한 촬영본 안으로** 다듬는다.

왜 필요한가 — 교훈 「무대사 꼬리를 남기지 마라」의 짝
  블록 끝을 «마지막 낱말 + 0.25초» 로 잡았더니, 영화가 그 말이 끝나는 순간
  컷을 하는 바람에 꼬리가 **다음 촬영본으로 0.02~0.4초 넘어갔다.**
  화면에 조각이 번쩍이고 지나간다. 시작 쪽도 마찬가지다.

무엇을 하는가
  블록마다 «그 안에서 실제로 말이 나오는 구간» 을 먼저 찾고,
  그 말이 들어 있는 촬영본의 경계 안쪽(0.04초 여유)으로 블록을 조인다.
  말 자체는 절대 자르지 않는다 — 자를 수밖에 없으면 그 자리를 알려 준다.
"""
import io
import json
import subprocess

GUARD = 0.04          # 장면 경계에서 이만큼 떨어진다
MIN_FRAG = 0.20       # 전환을 넘어간 조각이 이보다 짧으면 «번쩍임» 이라 잘라낸다
MIN_TAIL = 0.02       # 마지막 낱말 뒤 최소 여유
번쩍임 = 1.00         # 이보다 짧은 그림이 뜨면 번쩍인다 (대본검사.py 와 같은 값)
말버림한계 = 0.12     # 번쩍임을 없애려고 버려도 되는 말 앞머리 (2026-08-26)

# ▼편별 ─── 여기를 이 편 것으로 바꾼다 ────────────────────────────
SRC = '구간_인물.mp4'        # 재프레이밍을 마친 소재
# ▲편별 ──────────────────────────────────────────────────

A = json.load(io.open('authored.json', encoding='utf-8'))
W = json.load(io.open('대사.json', encoding='utf-8'))['words']
SC = sorted(float(x) for x in io.open('scene_cuts.txt'))
# ★소재 길이를 손으로 적지 마라 — 편마다 다르다. 재서 쓴다.
SRC_END = float(subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', SRC],
    capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip())
edges = [0.0] + SC + [SRC_END]
shots = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def shot_of(t):
    for a, b in shots:
        if a <= t < b:
            return a, b
    return shots[-1]


changed, warn = 0, []
for bi, b in enumerate(A['BLOCKS']):
    if b[0] != 'D':
        continue
    for c in b[1]:
        s, e = c[0], c[1]
        spoken = [w for w in W if w['e'] > s and w['s'] < e]
        if not spoken:
            continue
        ws, we = spoken[0]['s'], spoken[-1]['e']
        a, z = shot_of((ws + we) / 2)                 # 말이 들어 있는 촬영본
        ns = max(s, a + GUARD)
        ne = min(e, z - GUARD)
        # 말을 자르면 안 된다 — 다만 **번쩍임과 견줘서** 정한다 (2026-08-26)
        if ns > ws:
            # ★앞으로 물러서면 전환선을 넘어 «앞조각» 이 생긴다.
            #   그 조각이 번쩍임(1.00초 미만)이고, 버릴 말이 아주 짧으면(≤0.12초)
            #   **말 앞머리를 조금 버리는 쪽이 낫다.**
            #   포헨즈 2-1 b14 「계속 이러실 거면…」이 그랬다 —
            #   물러서면 0.14초짜리 그림이 번쩍이고(실측: 완성본 20.83초, 4프레임),
            #   전환 뒤에서 열면 「계」 앞머리 0.05초만 잃는다. 눈이 먼저다.
            물러선자리 = min(s, ws - 0.02)
            앞전환 = [x for x in SC if 물러선자리 + 0.05 < x < ne - 0.05]
            앞조각 = (앞전환[0] - 물러선자리) if 앞전환 else 99.0
            버릴말 = (a + 0.01) - ws
            if 앞조각 < 번쩍임 and 0 < 버릴말 <= 말버림한계:
                ns = a + 0.01
                warn.append((bi, c[2],
                             '전환 뒤에서 열었다 — 물러서면 %.2f초 번쩍임, '
                             '여기서 열면 말 앞머리 %.3f초만 잃는다'
                             % (앞조각, 버릴말), round(버릴말, 3)))
            else:
                warn.append((bi, c[2], '시작이 말을 자른다', round(ns - ws, 3)))
                ns = 물러선자리
        if ne < we + MIN_TAIL:
            if we + MIN_TAIL <= z - 0.005:
                ne = we + MIN_TAIL
            else:
                # 말이 촬영본 밖까지 이어진다 = **영화 자신이 대사 도중에 컷한 것**.
                # 소리가 안 끊기므로 넘겨도 «번쩍임» 으로 안 보인다 —
                # 단, 넘어간 조각이 한두 프레임이면 그건 번쩍임이라 잘라낸다.
                frag = min(e, we + MIN_TAIL) - z
                if frag >= MIN_FRAG:
                    ne = min(e, we + MIN_TAIL)
                    warn.append((bi, c[2], '영화가 대사 중에 컷 — 그대로 넘긴다', round(frag, 3)))
                else:
                    # ★여기서 z-GUARD 로 두면 **마지막 낱말이 잘린다.**
                    #   8편 「…하는 거야」 가 0.20초 씹혔다. 화면 번쩍임을 없애려고
                    #   대사를 자르는 것은 규격 위반이다 — 대사가 먼저다.
                    #   말은 끝까지 두고, 남는 짧은 조각은 그림을 갈아 끼워 덮는다.
                    ne = min(e, we + 0.02)
                    warn.append((bi, c[2], '짧은 조각이 남는다 — 그림을 갈아 끼워 덮어라',
                                 round(ne - z, 3)))
        # ★영화가 대사 도중에 컷하면 **끝에 조각이 남는다** (2026-08-26).
        #   포헨즈 2-2 마지막 「…퇴학시켜 주세요」 는 117.409 에서 컷하는데
        #   말이 117.54 에 끝나 **0.15초짜리 그림**이 번쩍이고 영상이 끝났다.
        #   MIN_FRAG(0.20)만 보고 넘겼더니 대본검사의 번쩍임(1.00초)에 걸린다.
        #   말이 없는 뒤쪽으로 **늘려서** 그 그림을 한 컷으로 세워 준다.
        #   (줄이면 대사가 잘린다 — 대사가 먼저다)
        안컷 = [x for x in SC if ns + 0.05 < x < ne - 0.05]
        if 안컷:
            끝컷 = 안컷[-1]
            if ne - 끝컷 < 번쩍임:
                다음컷 = min([x for x in SC if x > ne] + [SRC_END])
                다음말 = min([w['s'] for w in W if w['s'] > ne] + [SRC_END])
                넉넉 = min(끝컷 + 번쩍임 + 0.05, 다음컷 - GUARD, 다음말 - 0.02)
                if 넉넉 > ne:
                    warn.append((bi, c[2], '끝 조각이 짧아 %.2f초 늘렸다' % (넉넉 - ne),
                                 round(넉넉 - 끝컷, 3)))
                    ne = 넉넉
                else:
                    warn.append((bi, c[2], '★끝 조각이 %.2f초뿐인데 늘릴 데가 없다' % (ne - 끝컷),
                                 round(ne - 끝컷, 3)))

        if abs(ns - s) > 1e-6 or abs(ne - e) > 1e-6:
            print("  b%02d  %.2f~%.2f → %.2f~%.2f  (%.2f초, %s)"
                  % (bi, s, e, ns, ne, ne - ns, c[2][:16]))
            c[0], c[1] = round(ns, 3), round(ne, 3)
            changed += 1

# ── 겹침막기 (규격 §7 · 2026-08-26) ────────────────────────────────
# ★이 도구는 블록 시작을 촬영본·낱말 경계로 **당긴다.** 그러다 앞 블록 끝을
#   넘어가면 두 블록이 **같은 소재 구간을 두 번** 쓰게 된다 — 완성본에서
#   똑같은 말과 똑같은 얼굴이 두 번 나온다. 사장님 지적(2026-08-26, 2화).
#   `author.py` 는 겹침을 검사하지만 **이 도구가 돈 뒤에는 아무도 안 본다.**
#   그래서 여기서 막는다. 당긴 결과가 겹치면 앞 블록 끝까지만 당긴다.
_앞끝, _겹친 = None, 0
for _b in A['BLOCKS']:
    if _b[0] != 'D':
        continue
    if _앞끝 is not None and _b[1][0][0] < _앞끝 - 0.001:
        _b[1][0][0] = round(_앞끝, 3)
        _겹친 += 1
    _앞끝 = _b[1][0][1]
if _겹친:
    print('  [겹침막기] %d곳이 앞 블록과 겹쳐 시작을 앞 블록 끝으로 되돌렸다' % _겹친)

json.dump(A, io.open('authored.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print("\n다듬은 블록 %d개" % changed)

# 다시 재서 확인
cross = 0
for bi, b in enumerate(A['BLOCKS']):
    if b[0] != 'D':
        continue
    for c in b[1]:
        if [x for x in SC if c[0] < x < c[1]]:
            cross += 1
            print("  ★b%02d 아직 장면전환을 가로지른다 %.2f~%.2f" % (bi, c[0], c[1]))
print("장면전환을 가로지르는 원음 블록: %d개" % cross)
if warn:
    print("\n말이 잘릴 뻔한 자리:")
    for bi, t, why, d in warn:
        print("  b%02d 「%s」 %s (%.3f초)" % (bi, t[:20], why, d))
