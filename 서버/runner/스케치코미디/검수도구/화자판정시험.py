#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화자판정시험.py — 화자 판정이 실패를 삼키고 «통과» 하지 않는가 (s2pipe/화자색.who뽑기 · 화자판정).

왜 (2026-10-04 루키치61 · 수리C)
  ⑥ 로그 «화자 판정 2회차 실패: 'who'» 뒤 «2회 표결» 로 계속됐다. 'who' 는 응답이 JSON 객체인데 who 키가 없어 난 KeyError
  문구 한 낱말이라 원인이 안 보였고, 실패 회차를 다시 묻지 않아 3회 표결이 2회로 내려갔다. 또 회차가 전부 일반 실패면
  «색 구분 없이 간다» 로 조용히 통과했다(2026-09-28 설계) — 판정을 못 했는데 통과가 됐다.
  수리: 응답의 다른 꼴을 받는 who뽑기() · 실패 회차 한 번 더 묻기 · 유효 2회 미만이면 화자판정실패로 멈춤.

무엇을 재나 (agy 를 부르지 않는다 — gem.ask 를 가짜로 바꾼다)
  1) who뽑기 — 모델이 내는 여러 꼴 9가지를 받고, 못 받는 꼴은 까닭(응답 머리)을 붙여 ValueError.
  2) 화자판정 — 한 회차가 who 없는 객체 → 다시 물어 3회 표결 · 두 회차가 계속 실패 → 화자판정실패 · 전부 실패 → 화자판정실패.

쓰는 법
  ~/.volcano/venv/bin/python3 화자판정시험.py      종료코드 0 = 모두 맞음 · 1 = 틀림
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 화자색 as H, gem   # noqa: E402

틀림 = []


def 봄(이름, 참):
    print(("[OK] " if 참 else "[X] ") + 이름)
    if not 참:
        틀림.append(이름)


def 시험_뽑기():
    n = 3
    받을꼴 = {
        "who 객체": '{"who":["1","2","1"],"cast":{"1":"남자"}}',
        "목록만": '["1","2","1"]',
        "숫자 목록": '[1,2,1]',
        "목록 속 객체": '[{"who":["1","2","1"]}]',
        "한 겹 안": '{"result":{"who":["1","2","1"]}}',
        "speakers 키": '{"speakers":["1","2","1"],"cast":{}}',
        "대문자 Who": '{"Who":["1","2","1"]}',
        "줄 번호 키": '{"0":"1","1":"2","2":"1"}',
        "줄마다 객체": '[{"line":0,"who":"1"},{"line":1,"who":"2"},{"line":2,"who":"1"}]',
        "잘린 응답": '{"who":["1","2","1"],"cast":{"1":"남',
    }
    for 이름, txt in 받을꼴.items():
        try:
            who, _c = H.who뽑기(txt, n)
            봄(f"뽑기 {이름}", who == ["1", "2", "1"])
        except Exception as e:                               # noqa: BLE001
            봄(f"뽑기 {이름} — {e}", False)
    못받을꼴 = {"cast 만": '{"cast":{"1":"남자"}}', "줄 수 다름": '{"who":["1","2"]}', "글": "모르겠습니다"}
    for 이름, txt in 못받을꼴.items():
        try:
            H.who뽑기(txt, n)
            봄(f"못 뽑기 {이름} — 통과돼 버림", False)
        except ValueError as e:
            봄(f"못 뽑기 {이름} → ValueError «{str(e)[:50]}»", True)


def 가짜판정(답목록):
    """gem.ask 를 차례로 답목록을 내는 가짜로 바꾼다(동시 호출이라 자물쇠로 차례를 지킨다)."""
    import threading
    잠 = threading.Lock()
    남은 = list(답목록)

    def ask(payload, models, timeout=600, **_k):
        with 잠:
            a = 남은.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a, "가짜"
    gem.ask = ask
    gem.shrink_for_inline = lambda mp4, log=print: mp4


def 시험_판정():
    d = tempfile.mkdtemp()
    mp4 = os.path.join(d, "cut.mp4")
    open(mp4, "wb").write(b"0")
    줄 = ["안녕", "누구세요", "나야"]
    좋음 = '{"who":["1","2","1"],"cast":{"1":"남자","2":"여자"}}'
    # 루키치61 꼴 — 1회가 who 없는 객체 → 다시 물어 3회 표결
    가짜판정([좋음, '{"cast":{"1":"남자"}}', 좋음, 좋음])
    who, 불안정, _c = H.화자판정(줄, mp4, "시험")
    봄("한 회차 who 없음 → 다시 물어 표결", who == ["1", "2", "1"] and 불안정 == [])
    # 두 회차가 다시 물어도 실패 → 유효 1회 → 멈춤
    가짜판정([좋음, "모름", "모름", "모름", "모름"])
    try:
        H.화자판정(줄, mp4, "시험")
        봄("유효 1회 → 멈춤 (통과돼 버림)", False)
    except H.화자판정실패 as e:
        봄(f"유효 1회 → 멈춤 «{str(e)[:40]}»", True)
    # 전부 일반 실패 → 예전엔 «색 구분 없이 간다» 통과 → 이제 멈춤
    가짜판정([RuntimeError("시간 제한")] * 6)
    try:
        H.화자판정(줄, mp4, "시험")
        봄("전부 실패 → 멈춤 (통과돼 버림)", False)
    except H.화자판정실패:
        봄("전부 실패 → 멈춤", True)


if __name__ == "__main__":
    시험_뽑기()
    시험_판정()
    print(f"틀림 {len(틀림)}")
    sys.exit(1 if 틀림 else 0)
