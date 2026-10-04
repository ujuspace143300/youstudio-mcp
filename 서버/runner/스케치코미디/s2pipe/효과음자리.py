# -*- coding: utf-8 -*-
"""스케치 prproj 효과음(A3 한 트랙 — 훅 dun · 절정 dudun · 반전 gaze) 자리 잡기와 겹침 관문 — 한 곳.

★2026-10-04 루키치75 «A3 트랙 겹침» 클래스 수리 (땜질 금지 — 사장님 맡김 «도구 수리 A»).
  증상(⑧ 조립 verify «트랙 A3 겹침 0» 실패 · 실패 당시 prproj(.마스터효과전)에서 되읽은 A3 자리):
    75  절정 63.433~66.033 · 반전 64.700~67.000 (1.33초 겹침)     140 절정 50.967~53.567 · 반전 53.433~55.733
    149 절정 58.900~61.500 · 반전 60.567~62.867                  152 절정 56.400~59.000 · 반전 57.133~59.433
    배치 에이전트가 매번 조각 phase 를 손으로 바꾸거나 다시 짜서 FROM=6·7 로 돌렸다(140·149·152·75 네 번).
  클래스: 준비_prproj 가 효과음을 «하나씩 따로» 말 틈(±2.5초)으로 옮겼다 — 옮길 자리를 고를 때 «같은 A3 트랙에 이미 놓은
    효과음» 을 보지 않았다. dudun 은 2.6초라 절정 조각이 2.6초보다 짧거나(75 1.2초), 절정을 뒤로 · 반전을 앞으로 밀면 둘이
    겹친다. 그리고 겹침을 재는 곳이 ⑧ 조립 verify 하나뿐이라 ⑦ 준비(템플릿 굽기 수 분)까지 다 돈 뒤에야 걸렸다.
  수리: ① 자리잡기() — 차례로 놓되 «말 틈» 과 «A3 비어 있음» 을 함께 만족하는 가장 가까운 자리를 고른다. 말 틈이 없으면
          A3 가 빈 가장 가까운 자리에 −12dB, 그것도 없으면 그 효과음을 뺀다(까닭을 말한다) — 겹친 채로는 절대 내지 않는다.
       ② 겹침은 조립과 «같은 자»(30fps 시퀀스 격자 반올림 · wav 길이 내림 · 영상 끝 자름)로 잰다 — 조립_prproj_sk.frame_ticks
          ·verify 와 같은 셈. 조립은 이 파일의 시퀀스fps 가 자기 FRAME 과 같은지 확인한다.
       ③ 관문 겹침들() — 준비가 timeline 을 쓰기 전에 A3 겹침 0 을 assert(⑧ 까지 안 간다).
  왜 예전 검사를 지났나: make --check(①⑤)는 조각·자막만 보고 효과음 자리를 계산하지 않는다(효과음은 ⑦ 준비에서 처음 생긴다).
    ⑦ 준비엔 효과음 자리 관문이 없었고, 겹침은 ⑧ 조립의 prproj 공통 verify(트랙 겹침 0)만 잡았다.
  시험: 검수도구/효과음자리시험.py — 네 편의 실패 당시 입력을 옛 셈이 그대로 재현(겹침)하고 새 셈이 겹침 0 인지 본다.
"""
import math

시퀀스fps = 30            # 조립_prproj_sk.FRAME 8467200000 틱 = TPS 254016000000 / 30 — 조립이 같은지 assert 한다
최대이동 = 2.5            # 말 틈을 찾는 범위(초) — 2026-09-03 사장님 «배속처럼 들림» 때 정한 값
걸음 = 0.1
말창비 = 0.7              # 효과음 앞 70% 만 말과 안 겹치면 된다(꼬리 페이드는 말 밑으로 들어가도 됨 — 옛 셈 그대로)


def 틀(t0, t1, wav길이, 영상끝=None):
    """조립과 같은 셈의 A3 클립 (시작 장, 끝 장) — frame_ticks(가장 가까운 장) · 길이는 wav 길이 내림 · 영상 끝 자름.
    조립_prproj_sk: t0 = frame_ticks(t0) · length = min(끝맞춤(frame_ticks(t1)) − t0, (dur_ticks // FRAME) × FRAME)."""
    a = int(round(float(t0) * 시퀀스fps))
    b = int(round(float(t1) * 시퀀스fps))
    if 영상끝 is not None:
        b = min(b, int(round(float(영상끝) * 시퀀스fps)))
    n = min(b - a, int(math.floor(float(wav길이) * 시퀀스fps + 1e-9)))
    return a, a + n


def 겹침들(틀들):
    """[(이름, 시작 장, 끝 장)] → 겹치는 짝 [(앞 이름, 뒤 이름, 겹친 장 수)] — verify «트랙 겹침 0» 과 같은 판정(뒤 Start < 앞 End)."""
    s = sorted((x for x in 틀들 if x[2] > x[1]), key=lambda x: (x[1], x[2]))
    return [(p[0], q[0], p[2] - q[1]) for p, q in zip(s, s[1:]) if q[1] < p[2]]


def 자리잡기(효과음들, 말들, total):
    """효과음들: [{"라벨", "t0"(이야기 구조 자리), "길이"(mp3 초), "wav길이", "스냅"(bool)}] — 놓는 차례대로(훅 → 절정 → 반전).
    말들: [(시작, 끝)] 완성본 낱말 시각. total: 시퀀스 길이(영상 끝).
    → [{"라벨", "t0", "t1", "낮춤"(−12dB), "뺌", "글"}] (입력 차례). 결과의 A3 틀은 서로 겹치지 않는다."""
    놓인 = []                                                    # [(이름, 시작 장, 끝 장)]
    결과 = []

    def _틀(e, c):
        return 틀(c, min(c + e["길이"], total), e["wav길이"], total)

    def _비었나(e, c):
        a, b = _틀(e, c)
        return b > a and not 겹침들(놓인 + [(e["라벨"], a, b)])

    def _말없나(e, c):
        창 = e["길이"] * 말창비
        return not any(not (끝 <= c or 시 >= c + 창) for 시, 끝 in 말들)

    def _후보():
        for k in range(0, int(round(최대이동 / 걸음)) + 1):
            for 부호 in ((1,) if k == 0 else (1, -1)):
                yield round(k * 걸음 * 부호, 6)

    for e in 효과음들:
        t0 = round(float(e["t0"]), 3)
        r = {"라벨": e["라벨"], "t0": t0, "낮춤": False, "뺌": False, "글": ""}
        if not e.get("스냅"):
            if not _비었나(e, t0):
                r.update(뺌=True, 글=f"효과음 {e['라벨']}: 제자리 {t0:.2f}s 가 A3 의 다른 효과음과 겹침 — 뺌")
        else:
            # 후보는 저장할 값(소수 3자리) 그대로 잰다 — 반올림이 장 경계를 넘어 겹침이 새로 생기지 않게
            자리 = next((c for c in (round(t0 + d, 3) for d in _후보())
                        if c >= 0 and c + e["길이"] * 말창비 <= total and _말없나(e, c) and _비었나(e, c)), None)
            if 자리 is not None:
                if abs(자리 - t0) > 0.05:
                    r["글"] = f"효과음 {e['라벨']}: 대사·효과음 겹침 → {t0:.2f}s → {자리:.2f}s 로 이동"
                r["t0"] = 자리
            else:
                자리 = next((c for c in (round(t0 + d, 3) for d in _후보()) if c >= 0 and _비었나(e, c)), None)
                if 자리 is not None:
                    r.update(t0=자리, 낮춤=True,
                             글=f"★효과음 {e['라벨']}: 말 틈 없음(±{최대이동}s) — "
                                + ("제자리" if abs(자리 - t0) <= 0.05 else f"{t0:.2f}s → {자리:.2f}s(A3 빈 자리)")
                                + " · -12dB 로 낮춤")
                else:
                    r.update(뺌=True, 글=f"★효과음 {e['라벨']}: ±{최대이동}s 안에 A3 빈 자리가 없다(앞 효과음과 겹침) — 뺌")
        r["t0"] = round(r["t0"], 3)
        r["t1"] = round(min(r["t0"] + e["길이"], total), 3)
        if not r["뺌"]:
            a, b = _틀(e, r["t0"])
            놓인.append((e["라벨"], a, b))
        결과.append(r)
    assert not 겹침들(놓인), f"효과음 자리잡기가 겹침을 냈다 {겹침들(놓인)}"
    return 결과


def 옛자리잡기(효과음들, 말들, total):
    """2026-10-04 전 준비_prproj 의 셈 그대로(하나씩 따로 말 틈으로 · A3 를 안 봄) — 시험에서 실패 재현용으로만 쓴다."""
    결과 = []
    for e in 효과음들:
        t0 = float(e["t0"])
        낮춤 = False
        if e.get("스냅"):
            창 = e["길이"] * 말창비
            best = None
            for k in range(0, 26):
                for 부호 in (1, -1):
                    cand = t0 + 부호 * k * 0.1
                    if cand < 0 or cand + 창 > total:
                        continue
                    if not any(not (끝 <= cand or 시 >= cand + 창) for 시, 끝 in 말들):
                        best = cand
                        break
                if best is not None:
                    break
            if best is None:
                낮춤 = True
            else:
                t0 = best
        결과.append({"라벨": e["라벨"], "t0": round(t0, 3), "t1": round(min(t0 + e["길이"], total), 3), "낮춤": 낮춤, "뺌": False})
    return 결과
