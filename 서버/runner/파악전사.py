# -*- coding: utf-8 -*-
"""파악전사 — 소재의 **영상 그림과 소리를 같이** 제미나이(agy · 구독)에게 읽힌다. **파악용이다 — 자막·싱크에 쓰지 않는다.**

  사장님 결정(2026-09-26 · 볼트 규칙 「전사는 용도로 나눈다」):
    «파악은 제미나이 자막용은 스피치매틱스로 하자» · «영상, 그림 무조건 읽어야지 정확하게»
    · 파악 전사는 EvoLink 로 «한 조각도 안 넘김».

  왜
    대목 순위표·구간 고르기·내용 이해는 낱말 시각이 0.1초까지 맞을 필요가 없다. agy 는 울트라 구독으로 돌아
    호출 비용이 0 이다. 소리만 받아쓰면 누가 말하는지·어떤 장면인지를 못 가린다 — 그래서 **그림과 소리를 같이**
    읽히고, 화자는 그림(화면에 누가 있나·입 모양·얼굴·명찰·호명)으로 가린다. 소리만 읽는 길은 두지 않는다
    (영상 스트림이 없는 입력은 시작 전에 멈춘다).
    제미나이 시각은 중앙 0.2~0.3초·가끔 수 초 어긋난다 — 완성 검사 1번(원음 대조 0.1초)을 못 넘으므로
    자막·싱크 재료는 지금처럼 Speechmatics 이고, 이 도구의 결과는 **이름으로** 가른다.

  쓰는 법
    python 파악전사.py <소재 영상(mp4·mov·mkv…)> [--from 초] [--to 초] [--사전 드라마정보.json]
                       [--낼 <접두 경로>] [--모델 gemini-3.8-flash-low] [--조각 300] [--겹침 15] [--다시]
    예) python 파악전사.py 소재/신병4_EP10_EPK.mp4 --사전 작업/드라마정보.json --낼 작업/_파악/EPK10
    --사전 은 셋 다 받는다 — 드라마정보.json(«낱말사전» [{content, sounds_like}] · 있으면 «인물») ·
           이름 목록(["김현욱", …]) · {"인물": [{"이름": "김현욱", "생김새": "안경 쓴 이병"}, …]}.
           낱말 철자는 받아쓰기 철자를 맞추고, 인물 이름(과 생김새)은 화자 칸을 이름으로 채우게 한다.
    --낼 을 안 주면 지금 폴더에 <소재 이름> 으로 낸다.

  어떻게 읽히나 (agy_gemini.py 의 방식 그대로 — 그 파일은 고치지 않는다)
    · 조각마다 ffmpeg 로 **저해상 영상 조각**(짧은 변 480 · 2fps · bwdif · 소리 aac 모노)을 _파악조각/조각_NN_<키>.mp4 로
      뽑아 body 에 @inline_file(video/mp4, 절대경로)로 넣는다(<키> 는 아래 「지키는 것」 조각 영상 키).
      agy_gemini._build 가 그 영상의 소리를 mp3 로 따로 뽑아 «그림 파일 + 소리 파일» 두 첨부로 답변 전용 에이전트에게 준다(view_file 은 mp4 의 그림만 넘긴다 — _audio_of).
      그래서 여기서는 소리를 따로 뽑지 않는다(중복).
    · 2026-09-26 맥2 실측: view_file 은 영상을 **1초에 1장** 넘긴다(프레임 번호를 찍은 5fps 12초 조각 → F52·57·62…
      12장). 그래서 조각은 2fps 면 넉넉하다(더 올려도 모델이 보는 장수는 같고 파일만 커진다).
      그 12초 조각에 입력 5천 토큰 · 10초 · 소리도 받아썼다(모델 답 «소리없음 false» + 받아쓴 말).
    · 절단은 «빠른 탐색(-i 앞 -ss, 10초 앞까지) + 정확 절단(-i 뒤 -ss) + 재인코딩»이다. 4.5GB 1080i 소재를 조각마다
      처음부터 풀면 느려서다. 조각 시작이 소재와 맞는지는 소리 상관으로 쟀다 — 300.0000초(어긋남 0, 2026-09-26).
    · 비월주사 소재(신병4 EPK 1080i TFF)는 bwdif 로 편다. 프레임에 비월 표시가 있는 것만 펴므로 순차 소재는 그대로다.
    · JSON 은 여기서 읽는다(body 에 responseSchema 를 넣지 않고 같은 형식 지시를 질문 끝에 붙인다 — agy_gemini 가
      붙이던 글 그대로). agy_gemini 가 검사하면 모델의 괄호 실수 하나에도 None 이 되어 한 번뿐인 «다시» 를 써 버린다
      (아래 「실패 종류」).

  조각 길이 — 기본 300초 · 겹침 15초 (2026-09-26 맥2 실측 · 신병4 EPK10 0~300초 · flash-low · Speechmatics 낱말과 대조)
      조각   호출  agy 초(합)        30초 밀도 상관  시작 어긋남 중앙·p90  지어냄·빠짐 의심  화자 칸 이름 비율
      300초   1    106               0.964           0.22 · 0.75초          6 · 10            43%
      180초   2    50+79(1회 다시)   0.972           0.23 · 1.10초          5 · 12            18%
      120초   3    56+53+34          0.969           0.27 · 1.12초          5 · 11             2%
    받아쓰기 품질은 셋이 같고, 300초가 가장 빠르다(소재 1초에 0.35초). 300초 한 조각은 입력 4.1만·출력 0.7만 토큰,
    시간 제한 10분의 1/6 이다. 조각 영상 뽑기는 300초에 32초(다음 조각은 agy 가 답하는 동안 미리 뽑는다).
    (위 표의 «화자 칸 이름 비율» 은 v3 질문으로 **채운** 비율이다 — 맞은 비율이 아니다. 아래 v4 실측 참고.)
    ★시각은 «분:초» 글자로 받는다 — 초(숫자)로 달라면 1:11.9 를 111.9 로 붙여 쓴다(초로 주석 · 첫 시험 전부 망가짐).

  EPK10 전체 실측 (2026-09-26 맥2 · 1866.7초 · 조각 7개 · 볼트 실측.md = 볼케이노 린박스/_파악전사_시험_20260926/실측.md)
      v3(명찰 오독판): 30초 밀도 상관 0.956 · 시작 어긋남 중앙 0.23초·p90 0.87초 · 이름 채움 75% — 그러나 명찰로 붙인
          이름이 틀렸다(오석진·배홍길 = 실제 조백호·박재수). 그 답을 지금 규칙으로 다시 매기면 이름 발화 362 중 231 이
          미확인(오석진 15·배홍길 17·조각 7 박민석 5 모두 포함)이고, 겹침 이름 짝 8 중 어긋남 4 를 잡는다.
      v4(지금): 30초 밀도 상관 0.945 · 시작 어긋남 중앙 0.25초·p90 0.98초 · 지어냄 의심 13(v3 23) · 빠짐 의심 62(v3 63)
          · 이름 채움 47%(207/442) · **확인된 이름 37%**(들음 165) · 미확인 42 · 겹침 이름 짝 5 중 어긋남 0(이음 조백호=중대장)
          · «들음» 표본 10을 원본 프레임으로 보니 맞음 8(명찰·얼굴) · 판정 못 함 2(어둡거나 먼 장면) · 틀림 0
          · agy 11번(실패 3 — 모두 조각 4 «Malformed function call», 1회 멈춘 뒤 같은 명령으로 이어 받음)
          · 벽시계 1003초(소재 1초에 0.54초) · gemini_route fallback 0.

  실패 종류 (2026-09-26 맥2 실측 — 파악전사 agy 호출 43번 가운데 실패 11)
      ① 괄호 실수 — «}}]» 처럼 닫는 괄호가 남거나 배열을 안 닫는다 → _JSON_고쳐읽기 가 고친다(다시 부르지 않는다).
      ② 헛답 — 답 전체가 «}» 하나(1번) · agy «Malformed function call: Function call is empty»(6번) → 한 번 더,
         또 나면 멈춘다(종료코드 2 · 같은 명령을 다시 돌리면 이어 받는다). ★Malformed 는 agy stdout 의 response 칸에
         온전한 답이 들어 있는데 status=ERROR 라 agy_gemini.generate 가 None 을 돌려준다(원답 기록으로 확인 — 실측.md 8절).
         agy_gemini 를 고치면 이 실패가 거의 사라진다 — 그 파일은 사장님 결정 없이 고치지 않는다.
      ③ 제미나이 필터 — «This request was blocked by Gemini's filters». 답 첫머리에서 막히면 한 번 더(다음엔 통과한 일이
         있다). **답 중간에서 막히면 같은 대사에서 매번 막힌다** — EPK10 1567초 «육군의 뿌리인 하나의 중대부터 무…»
         (간첩 패러디)가 세 번 다 같은 자리에서 끊겼다. 그래서 끊긴 답은 버리지 않고 온전한 발화까지 살리고
         (_잘린_JSON_살리기), **막힌 대사 뒤부터 조각 끝까지**를 한 번 더 받는다. 막힌 대사 구간은 «막힌구간» 으로
         남긴다 — 사람이 그 자리를 직접 봐야 한다. (칸 순서를 장면·화면글자·발화로 두어 발화에서 막혀도 장면은 남는다.)

  내는 것 — 이름에 words·대사·transcript 를 넣지 않고 .srt·.vtt 를 만들지 않는다.
            (srt고르기.py 가 *.srt 를, 짓기.py 가 EPK_words.json 을, 스케치가 .ko.vtt 를 이름으로 집어 간다.
             접두 이름에 그 낱말이 있으면 시작 전에 멈춘다.)
    <접두>_파악전사.json      머리 "용도": "파악 — 자막·싱크 금지" · "엔진" · "읽은것": "영상그림+소리" · 소재 · 소재_sha256(+방식)
                              · 구간 · 조각[{from,to,초,route…}] · 미완 · 미완_까닭 · 막힌구간 · 화자_주의 · 화자_확인_셈 · 겹침_이름짝
                              (미완 = agy 가 멈춰 끝까지 못 받음 **또는** 막힌구간이 있음 — «미완» 칸만 보는 도구가 구멍 난
                               결과를 온전한 것으로 믿지 않게. 어느 쪽인지는 미완_까닭)
                              · 화자_어긋남[{s,글,앞,뒤}] · 발화[{s,e,화자,이름근거,화자확인,글,근거,조각(,화자_다른조각)}]
                              · 장면[{s,e,요지,화면인물,화면인물_미확인,자리,조각}] · 화면글자[{s,종류,글,조각}]
                              (s·e 는 소재 절대초)
    <접두>_파악_밀도30s.txt    30초마다 글자 수(공백 뺌)·발화 수 — 대목 고르기용
    <접두>_파악_덩이.txt       장면 머리줄(요지·자리·화면인물 — 미확인 이름엔 «?») + 시각·[화자·확인·근거]·글
                              · 화면글자(종류) · ★막힌구간 · ★겹침 화자 어긋남
    <접두 폴더>/_파악조각/     조각_NN_<키>.mp4 · 조각_NN_나머지_<키>.mp4(저해상 영상 조각 — 지워도 된다, 다시 뽑는다.
                              키가 같은 것만 다시 쓴다 — 「지키는 것」 조각 영상 키) · 조각_NN.json(받은 답 캐시 —
                              다시 돌리면 안 받은 조각만 받는다. 소재 지문·구간·모델·사전·질문판이 다르거나 부분 답의
                              영상키가 안 맞으면 새로 받는다. --다시 는 전부 새로)

  종료코드   0 끝까지 받음 · 2 agy 막힘(받은 데까지 «미완» 으로 쓰고 멈춤 — 같은 명령을 다시 돌리면 이어 받는다)
            · 3 시작 전 멈춤(agy 없음·영상 없음·입력 잘못)
            · 4 끝까지 받았으나 제미나이 필터가 막은 대사 구간이 있다(머리 «막힌구간» · «미완» true · 다시 돌려도 같다
              — 사람이 본다)

  지키는 것
    · EvoLink 로 한 조각도 넘기지 않는다. 실패(None·헛답·그림/소리 못 읽음·시각 이상)한 요청은 **한 번만 다시** 하고,
      또 실패면 거기서 멈춘다(종료코드 2). 답의 route 가 agy 가 아니면 역시 멈춘다.
      답이 중간에서 끊기면 끊긴 뒤를 **한 번** 더 받는다(«나머지» — 같은 요청의 되풀이가 아니라 못 받은 뒷부분).
      그래서 조각 하나에 agy 호출은 많아야 세 번이다(조각_받기 주석).
      ★«조각당 세 번» 은 2026-09-26 재검증에서 짚혔으나 그대로 둔다(그 뒤 판단 — 사장님 보고 대상). 까닭: agy 는 구독이라
      부를 때마다 돈이 나가지 않고(EvoLink 0 · 유료 호출이 아니다), «나머지» 는 필터가 막은 대사를 건너뛰고 그 뒤를
      받는 유일한 길이다 — 없으면 막힌 자리부터 조각 끝까지가 통째로 빈다(EPK10 1567초 · 300초 조각의 뒤 4분).
    · 조각 영상 키 — 영상 조각은 **소재 지문(sha256+방식)·절대 구간(from·to)·뽑는 방식(vf·인코딩 인자)** 의 해시(16자)로
      묶는다. 파일 이름(조각_NN_<키>.mp4)과 mp4 안(comment 태그 «youstudio.pakak.chunk=<키>»)에 같이 넣고,
      다시 쓸 때는 태그 키까지 같아야 쓴다. agy 에 보내기 직전(부르기)에도 태그 키를 다시 읽어 이 조각 키와 다르면
      멈춘다(최종 관문 — 이름이 어떻게 바뀌어도 남의 영상은 못 나간다).
      답 캐시(조각_NN.json)도 부분 답마다 보낸 영상의 키(«영상키»)를 적고, 그 키가 맞아야 다시 쓴다.
      ★2026-09-26 재검증 재현 2건: 조각 영상을 «이름(조각_NN.mp4)이 있고 길이가 ±0.6초 맞으면» 다시 썼다. 같은 --낼
      폴더에서 다른 소재(가짜 소재 둘)나 다른 구간(EPK10 0~60초 뒤 --from 1500)을 돌리면 **앞 영상을 agy 에 보냈다**
      (1500초 쪽을 물었는데 0초 쪽 그림 — 맥2 가짜 agy 재현에서 보낸 영상과의 프레임 차이 0초 쪽 3~20 · 1500초 쪽 53~87).
      답 캐시는 키를 봐서 새로 받았지만 보내는 영상은 키 없이 길이만 봤다 — 그래서 답이 «새로 받음·route agy» 로 멀쩡해
      보여 아무 검사도 못 잡았고, 그 답이 **맞는 키로 캐시에 들어갔다**(그래서 영상키 없는 옛 캐시는 새로 받는다).
      지금까지의 시험은 늘 같은 소재·같은 --from 이라 다시 쓴 영상이 우연히 맞았다. «나머지» 영상도 같은 구멍이었다.
    · generate 는 EvoLink 를 직접 부르지 않는다(2026-09-26 읽어 확인 — 실패면 None 을 돌려 부른 쪽이 가게 한다).
      그 약속이 깨져도 새지 않게 두 겹으로 막는다: ① agy_gemini.py 글에 EvoLink 주소·인터넷 호출 모듈이 생기면
      시작 전에 멈춘다 ② 이 프로세스의 인터넷 연결(socket.connect)을 막는다 — agy·ffmpeg 는 따로 도는 프로그램이라
      상관없고, 파이썬 안에서 EvoLink 로 가는 길은 없다. YOUSTUDIO_GEMINI_ROUTE=evolink 이면 시작 전에 멈춘다.
    · agy_gemini.generate 는 실패를 gemini_route.jsonl 에 route "fallback"(= EvoLink 로 간 횟수 = 돈) 으로 적는다.
      파악전사는 EvoLink 로 안 가므로 그 줄을 route "agy_fail_stop" 으로 바꿔 적는다(_record 를 감싼다 —
      agy_gemini.py 는 고치지 않는다). 그래야 fallback 줄 수가 계속 «돈 나간 횟수» 로 맞는다.
    · 화자 이름표 — **이름은 들린 것(호명·자기소개)과 방송 자막으로만 붙이고, 도구가 다시 확인한다.**
      ★2026-09-26 검증에서 명찰로 붙인 이름이 틀렸다: 명찰 조백호를 «오석진»(15발화), 박재수를 «배홍길»(17발화)·
      «박민석»(사전 이름) 으로 읽었고, 화환 리본의 «행정보급관 박재수» 도 «박민석» 으로 적었다. 480p·1초 1장 조각에서
      명찰은 글자가 아니라 회색 띠다(1197·1243초 조각 프레임을 눈으로 확인) — 모델은 못 읽는 글자를 사전 이름 쪽으로
      지어낸다. 그래서 (v4 질문) 기본은 «남1·여1» 번호이고, 명찰·리본·사전 목록으로 이름을 붙이지 말라고 묻고,
      이름근거(호명·자기소개·화면자막·생김새·명찰·없음)와 화면글자 종류(자막·간판·문서·명찰·기타)를 따로 받는다.
      도구는 모델의 이름근거를 믿지 않고 발화마다 «화자확인» 을 조각 안 증거로 매긴다(_화자_확인):
        들음(계급+이름 자기소개, 또는 남이 부른 바로 다음 차례에 대답) · 자막 · 생김새 · 미확인(«?») · 번호.
      겹침 구간에서 두 조각이 같은 말에 다른 이름을 붙이면 «화자_어긋남» 으로 모은다(_겹침_화자검사 — 3차 판에서 8짝 중 4).
      «들음» 도 이름과 이름표가 한 자리에서 이어졌다는 것까지다. 이름표를 조각 안에서 같은 사람에게만 붙였는지는
      모델 몫이라 모른다 — 화자 이름은 파악용 짐작이고, 나레·인물표에 옮기려면 프레임으로 본다(머리 «화자_주의»).
      «남1·여1» 은 **조각 안에서만** 일관된다(조각끼리 «남1» 이 같은 사람이라는 보장이 없다 · 발화마다 «조각» 번호).
      근거 칸은 말한 사람을 무엇으로 가렸는지(소리·그림·둘다).
    · 조각 사이는 --겹침 초만큼 겹쳐 받는다(말이 조각 경계에서 잘리지 않게). 겹친 구간은 **앞 조각 것**을 쓴다 —
      단 앞 조각 끝에 걸려 잘렸을 발화만 뒤 조각이 온전히 들은 것으로 바꾼다(_합치기 주석).
    · 맥 PATH 빈틈: agy_gemini._agy_exe() 는 맥에서 shutil.which 만 본다. agy 를 설치하기 전에 켠 셸·세션은 PATH 에
      ~/.local/bin(공식 설치 자리)이 없어 못 찾는다 — 그래서 import 전에 그 자리를 PATH 앞에 넣는다.
      윈도우는 agy_gemini 가 %LOCALAPPDATA%\\agy\\bin 을 본다.
    · 저장소판(서버/runner/)과 볼트판(설치/)은 바이트까지 같다. 둘 다 «같은 폴더의 agy_gemini.py» 를 쓴다.
"""
import argparse
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
_local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
if os.name != "nt" and os.path.isdir(_local_bin) and _local_bin not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = _local_bin + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True   # 볼트 설치/ 에 __pycache__ 가 생겨 Obsidian Sync 로 컴퓨터마다 퍼지지 않게
import agy_gemini  # noqa: E402  같은 폴더의 agy_gemini.py — 고치지 않는다

CALLER = "파악전사"
DEFAULT_MODEL = "gemini-3.8-flash-low"   # 긴 소재는 low — high 는 60초 대사에 167초라 긴 조각이 시간 제한을 넘는다(규칙)
DEFAULT_조각 = 300.0                     # 머리 주석 「조각 길이」 실측
DEFAULT_겹침 = 15.0
DEFAULT_LIMIT_MIN = 10
영상_짧은변 = 480        # 짧은 변 픽셀. 얼굴·명찰을 가리려면 360 보다 480
영상_FPS = 2            # view_file 이 1초에 1장만 넘긴다(머리 주석 실측) — 2 면 넉넉하다
영상_VF = (f"bwdif=mode=send_frame:deint=interlaced,fps={영상_FPS},"
          f"scale='if(gte(iw,ih),-2,{영상_짧은변})':'if(gte(iw,ih),{영상_짧은변},-2)',setsar=1")
영상_인코딩 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
             "-ac", "1", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]
조각키_태그 = "youstudio.pakak.chunk="   # 조각 영상 mp4 의 comment 태그 머리(머리 주석 「지키는 것」 조각 영상 키)
FULL_HASH_MAX = 512 * 1024 * 1024       # 이보다 크면 sha256 을 «앞·가운데·끝 1MB + 크기» 로 빠르게 잰다
금지낱말 = ("words", "대사", "transcript")
용도 = "파악 — 자막·싱크 금지"
읽은것 = "영상그림+소리"
질문판 = "영상+소리 2026-09-26 v4 이름근거·글자종류"   # 질문·스키마·캐시 모양을 바꾸면 올린다 — 옛 답을 다시 쓰지 않는다
근거값 = ("소리", "그림", "둘다")
이름근거값 = ("호명", "자기소개", "화면자막", "생김새", "명찰", "없음")   # 화자 칸 이름을 어디서 알았나(모델이 적는다)
글자종류값 = ("자막", "간판", "문서", "명찰", "기타")                   # 화면글자 종류 — 이름 확인에는 «자막» 만 쓴다
화자확인값 = ("번호", "들음", "자막", "생김새", "미확인")               # 도구가 매긴다(_화자_확인)
막힘표시 = ("blocked by Gemini's filters", "This request was blocked")

# 화자 이름표 가르기 (_화자_확인 · _겹침_화자검사)
번호꼴 = re.compile(r"^(남|여|아이|남자|여자|목소리|화자|사람|\?)\s*\d*$|불명|모름|알\s*수\s*없")
계급 = ("훈련병", "이병", "일병", "상병", "병장", "하사", "중사", "상사", "원사", "준위",
        "소위", "중위", "대위", "소령", "중령", "대령", "준장", "소장", "중장", "대장")
직함 = set(계급) | {"중대장", "소대장", "부소대장", "분대장", "대대장", "연대장", "사단장", "행보관", "행정보급관",
                  "당직사관", "당직부사관", "주임원사", "교관", "조교", "선임", "후임", "간부", "병사", "군의관"}
직함_줄임 = {"행보관": "행정보급관"}   # 줄임 → 온이름. 말로는 줄여 부른다(1231초 «행보관님!» → 행정보급관 이름표)
호명_응답_초 = 6.0  # 남이 이름을 부른 발화 끝에서 이 초 안에 그 이름표가 다음 차례(두 발화 안)로 말해야 «들음»
자막_근처_초 = 10.0  # 방송 자막에 이름이 뜬 시각에서 이 초 안에 그 이름표가 말해야 «자막»

시각칸 = {"type": "STRING", "description": "조각 맨 앞을 0:00.0 으로 한 분:초.소수 — 예 0:07.5 · 1:05.3 · 4:59.0"}
# 칸 순서 = 모델이 쓰는 순서. 발화를 맨 뒤에 둔다 — 필터가 답 중간(발화)을 막아도 장면·화면글자는 온전히 남는다.
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "읽음": {"type": "OBJECT", "properties": {"그림": {"type": "BOOLEAN"}, "소리": {"type": "BOOLEAN"}},
               "required": ["그림", "소리"]},
        "장면": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "s": 시각칸, "e": 시각칸,
            "요지": {"type": "STRING"},
            "화면인물": {"type": "ARRAY", "items": {"type": "STRING"}},
            "자리": {"type": "STRING"}},
            "required": ["s", "e", "요지", "화면인물", "자리"]}},
        "화면글자": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "s": 시각칸, "종류": {"type": "STRING", "enum": list(글자종류값)}, "글": {"type": "STRING"}},
            "required": ["s", "종류", "글"]}},
        "발화": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "s": 시각칸, "e": 시각칸,
            "화자": {"type": "STRING"}, "이름근거": {"type": "STRING", "enum": list(이름근거값)},
            "글": {"type": "STRING"},
            "근거": {"type": "STRING", "enum": list(근거값)}},
            "required": ["s", "e", "화자", "이름근거", "글", "근거"]}},
    },
    "required": ["읽음", "장면", "화면글자", "발화"],
}
JS = agy_gemini._to_json_schema(SCHEMA)


class 멈춤(Exception):
    def __init__(self, 코드, 글):
        super().__init__(글)
        self.코드 = 코드


def nfc(s):
    return unicodedata.normalize("NFC", s)


def mmss(t):
    t = max(0, int(t))
    return "%02d:%02d" % divmod(t, 60) if t < 3600 else "%d:%02d:%02d" % (t // 3600, t % 3600 // 60, t % 60)


# ── agy 기록 감싸기: 파악전사의 실패는 EvoLink 로 안 간다 → "fallback"(돈) 으로 적지 않는다 ──
_원래기록 = agy_gemini._record


def _기록(caller, route, sec, reason="", model=""):
    if caller == CALLER and route == "fallback":
        route, reason = "agy_fail_stop", "파악전사는 EvoLink 로 안 넘김(멈춤) — " + (reason or "")
    _원래기록(caller, route, sec, reason, model)


agy_gemini._record = _기록


# ── EvoLink 로 새는 길 막기 (머리 주석 「지키는 것」) ──
def _evolink_길_검사():
    """agy_gemini.py 글에 EvoLink 주소나 인터넷 호출 모듈이 생겼으면 멈춘다 — generate 가 None 대신 스스로
    EvoLink 를 부르게 바뀌면 파악 전사가 돈을 쓰게 된다."""
    글 = Path(agy_gemini.__file__).read_text(encoding="utf-8", errors="replace")
    본문 = "\n".join(l for l in 글.splitlines() if not l.lstrip().startswith("#"))
    걸림 = [p for p in (r"evolink\.ai", r"^\s*(import|from)\s+(urllib|requests|http|httpx|aiohttp)\b")
            if re.search(p, 본문, re.I | re.M)]
    if 걸림:
        raise 멈춤(3, f"agy_gemini.py 안에 인터넷 호출 길이 생겼다({', '.join(걸림)}) — EvoLink 로 샐 수 있어 "
                    "파악 전사를 시작하지 않는다. 그 파일이 무엇을 부르는지 확인한 뒤 이 검사를 고쳐라")


def _인터넷_막기():
    """이 파이썬 프로세스의 인터넷 연결을 막는다(agy·ffmpeg 는 따로 도는 프로그램이라 상관없다)."""
    원래 = socket.socket.connect

    def connect(self, addr):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise 멈춤(2, f"파악전사 안에서 인터넷 연결 시도({addr}) — EvoLink 로 새는 길일 수 있어 막았다")
        return 원래(self, addr)

    socket.socket.connect = connect


# ── 입력 ──
def 소재정보(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,codec_name,width,height:stream_disposition=attached_pic",
                        "-of", "json", str(src)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout)
        길이 = float(d["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise 멈춤(3, f"소재를 못 읽었다(ffprobe): {src}")
    ss = d.get("streams", [])
    영상 = [s for s in ss if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    소리 = [s for s in ss if s.get("codec_type") == "audio"]
    return 길이, 영상, 소리


def 지문(src):
    """소재 sha256. 512MB 이하는 전체, 넘으면 «앞·가운데·끝 1MB + 크기» (방식을 같이 적는다)."""
    size = src.stat().st_size
    h = hashlib.sha256()
    with src.open("rb") as f:
        if size <= FULL_HASH_MAX:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
            return h.hexdigest(), "전체"
        for at in (0, size // 2, size - (1 << 20)):
            f.seek(at)
            h.update(f.read(1 << 20))
    h.update(str(size).encode())
    return h.hexdigest(), "앞·가운데·끝1MB+크기"


def 사전_읽기(path):
    """→ (낱말 [(철자, [비슷하게 들리는 말…])], 인물 [(이름, 생김새)])

    드라마정보.json «낱말사전» 은 이름과 일반 낱말(계급 따위)이 섞여 있어 어느 것이 사람인지 모른다 — 낱말로만 넣고
    «사람 이름이면 화자로 써라» 고 질문에 적는다. 이름 목록(문자열 배열)과 «인물» 은 사람으로 넣는다."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    낱말, 인물 = [], []
    if isinstance(d, list):
        d = {"인물": d}
    if not isinstance(d, dict):
        return 낱말, 인물
    for x in d.get("낱말사전") or []:
        if isinstance(x, str) and x.strip():
            낱말.append((nfc(x.strip()), []))
        elif isinstance(x, dict) and str(x.get("content", "")).strip():
            c = nfc(str(x["content"]).strip())
            낱말.append((c, [nfc(s) for s in x.get("sounds_like", []) if isinstance(s, str) and nfc(s) != c]))
    사람 = d.get("인물") or d.get("이름") or []
    if isinstance(사람, dict):
        사람 = [{"이름": k, "생김새": v} for k, v in 사람.items()]
    for x in 사람 if isinstance(사람, list) else []:
        if isinstance(x, str) and x.strip():
            인물.append((nfc(x.strip()), ""))
        elif isinstance(x, dict) and str(x.get("이름") or x.get("name") or "").strip():
            인물.append((nfc(str(x.get("이름") or x.get("name")).strip()),
                       nfc(str(x.get("생김새") or x.get("설명") or "").strip())))
    return 낱말, 인물


def 조각표(a, b, 조각, 겹침):
    """[(from, to)] — 조각 사이를 겹침만큼 겹친다. 마지막에 30초 못 되게 남으면 앞 조각에 붙인다."""
    out, s = [], a
    while True:
        e = min(s + 조각, b)
        if 0 < b - e < 30:
            e = b
        out.append((round(s, 3), round(e, 3)))
        if e >= b - 1e-6:
            return out
        s = e - 겹침


def 조각키(소재지문, a, b):
    """조각 영상 하나의 키(16자) — 소재 지문(sha256·방식)·절대 구간·뽑는 방식. 머리 주석 「지키는 것」 조각 영상 키."""
    sha, 방식 = 소재지문
    글 = json.dumps({"소재_sha256": sha, "방식": 방식, "from": round(a, 3), "to": round(b, 3),
                    "vf": 영상_VF, "인코딩": 영상_인코딩}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(글.encode("utf-8")).hexdigest()[:16]


def 조각키_읽기(mp4):
    """mp4 안 comment 태그에 적힌 조각 키. 없거나 못 읽으면 None."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "json", str(mp4)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        c = (json.loads(r.stdout)["format"].get("tags") or {}).get("comment") or ""
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return c[len(조각키_태그):] if c.startswith(조각키_태그) else None


def 영상뽑기(src, a, b, 폴더, 머리이름, 소재지문):
    """저해상 영상 조각(소리 포함) — 머리 주석 「어떻게 읽히나」 → (경로, 키).
    파일은 <폴더>/<머리이름>_<키>.mp4 이고 mp4 안에도 키를 적는다. 이미 있으면 **키(태그)가 같고** 길이가 맞을 때만
    그대로 쓴다 — 길이만 보던 때 다른 소재·구간 영상을 agy 에 보냈다(머리 주석 「지키는 것」 조각 영상 키)."""
    키 = 조각키(소재지문, a, b)
    dst = 폴더 / f"{머리이름}_{키}.mp4"
    L = b - a
    if dst.exists():
        try:
            길이, 영상, 소리 = 소재정보(dst)
            if 영상 and 소리 and abs(길이 - L) < 0.6 and 조각키_읽기(dst) == 키:
                return dst, 키
        except 멈춤:
            pass
    tmp = dst.with_name(dst.stem + ".part.mp4")
    앞 = max(0.0, a - 10.0)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{앞:.3f}", "-i", str(src), "-ss", f"{a - 앞:.3f}", "-t", f"{L:.3f}",
                        "-map", "0:v:0", "-map", "0:a:0", "-vf", 영상_VF, *영상_인코딩,
                        "-metadata", f"comment={조각키_태그}{키}", str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 4096:
        tmp.unlink(missing_ok=True)
        raise 멈춤(3, f"영상 조각을 못 뽑았다(ffmpeg {a:.1f}~{b:.1f}초): {(r.stderr or '').strip()[-200:]}")
    os.replace(tmp, dst)
    if 조각키_읽기(dst) != 키:                  # 되읽기 — 태그가 안 들어갔으면 다음에 다시 쓸 수도, 보낼 수도 없다
        raise 멈춤(3, f"영상 조각에 키 태그가 안 들어갔다({dst.name}) — ffmpeg 가 comment 태그를 못 쓰는지 확인")
    return dst, 키


def 질문(L, 낱말, 인물, 소재이름):
    q = [f"첨부는 한국 드라마 소재에서 잘라 낸 {L:.1f}초짜리 조각이다 — 같은 조각의 그림 파일(영상)과 소리 파일 두 개. "
         "둘 다 연다. 그림과 소리는 시각이 같다. 두 파일을 연 뒤에는 도구를 더 부르지 말고 곧바로 답을 한 번에 쓴다.",
         f"소재 파일 이름: {소재이름} (작품을 짐작하는 참고로만 쓴다).",
         "할 일: 소리는 처음부터 끝까지 받아쓰고, 누가 말했는지는 **그림으로** 가린다.",
         "",
         "모든 시각(s·e): 이 조각 맨 앞을 0:00.0 으로 한 «분:초.소수» 글자(예 0:07.5 · 1:05.3). 초 자리는 00~59. "
         f"0:00.0~{mmss(L)}.0 사이. 초만 쓴 숫자(65.3)나 분초를 붙인 숫자(105.3)는 쓰지 않는다.",
         "읽음 — 그림을 실제로 봤으면 그림=true, 소리를 실제로 들었으면 소리=true. 못 열었거나 비었으면 false(지어내지 않는다).",
         "장면 — 장소·상황이 바뀌는 덩이마다 하나(컷마다가 아니다). s·e · 요지(무슨 일인지 한 줄) · "
         "화면인물(그 장면 화면에 보인 사람 — 발화의 화자와 같은 이름표) · 자리(장소, 예: 생활관·복도·사무실).",
         "화면글자 — 화면에 박힌 글자를 처음 보인 시각 s 와 함께, **보이는 획 그대로**. 없으면 빈 배열. "
         "종류: 자막(방송이 얹은 자막 — 인물 소개·장소·회차 자막) · 간판(간판·현수막·게시물·화환 리본) · 문서 · 명찰 · 기타. "
         "흐려서 확실히 읽히지 않는 글자는 적지 않는다. 사람 이름처럼 보여도 아래 낱말 목록의 이름으로 바꿔 적지 않는다. "
         "명찰 글자는 이 영상 크기에서는 거의 읽히지 않는다 — 또렷할 때만 적는다.",
         "발화 — 한 사람이 이어서 한 말 한 덩이(보통 한 문장)마다 하나. 이 조각에 말이 없으면 빈 배열.",
         "  글: 들린 그대로 빠짐없이. 요약·의역·교정하지 않는다. 알아듣기 어려운 곳은 (불분명). "
         "짧은 대답·감탄(네, 아, 야)도 넣는다. 말이 아닌 소리(음악·효과음·웃음)와 화면 글자는 넣지 않는다 — 들린 말만.",
         "  화자: 그 시각의 화면을 보고 누가 말하는지 가린다 — 화면에 누가 있는가, 누구의 입이 움직이는가, 얼굴·옷, "
         "앞뒤 발화와 이어지는 목소리. 이름표는 **기본이 성별+번호**(남1·여1·남2)이고 이 조각 안에서 같은 사람은 같은 번호다.",
         "  이름은 이 조각에서 **그 사람의 이름이 소리로 들렸을 때**(다른 사람이 그 이름으로 부름 = 호명 · 스스로 "
         "«이병 박OO» 처럼 밝힘 = 자기소개) 또는 **방송 자막으로 그 사람 이름이 떴을 때**(화면자막)만 쓰고, 그 사람의 "
         "이 조각 발화 모두에 이어 쓴다. 직함이 불렸으면(중대장님·행보관님) 이름 대신 그 직함을 이름표로 써도 된다.",
         "  명찰·리본·문서의 글자로 이름을 정하지 않는다 — 이 영상 크기에서는 명찰 글자가 보이지 않고, 그렇게 붙인 "
         "이름은 다른 사람 이름이었다. 아래 낱말 목록에 있다는 것만으로 화면의 사람에게 이름을 붙이지도 않는다. "
         "이름이 들리지 않았으면 번호로 쓴다 — 번호는 틀린 이름보다 낫다.",
         "  이름근거: 화자 칸에 이름·직함을 썼으면 그것을 어디서 알았나 — 호명 · 자기소개 · 화면자막 · "
         "생김새(아래 인물 목록의 생김새와 분명히 맞음) · 명찰(명찰 글자로만 — 쓰지 않는 것이 원칙). 번호로 썼으면 없음.",
         "  근거: 말한 사람을 무엇으로 가렸나 — 소리(목소리만) · 그림(화면의 입 모양·얼굴만) · 둘다."]
    if 인물:
        q += ["", "인물 — 생김새가 적힌 사람은 화면의 사람이 그 생김새와 분명히 맞으면 그 이름을 쓴다(이름근거 생김새). "
              "생김새가 없는 이름은 아래 낱말 목록과 같게 다룬다(이름이 들리거나 자막으로 떠야 쓴다):"]
        q += [f"  · {n}" + (f" — {g}" if g else "") for n, g in 인물]
    if 낱말:
        q += ["", "이 드라마의 이름·낱말 철자 — **받아쓰기 철자용**이다. 소리가 비슷하게 들리면 이 철자로 적는다. "
              "들리지 않은 말을 지어 넣지 않는다. 이 목록은 누가 누구인지 알려 주지 않는다 — 목록의 이름을 화면의 "
              "얼굴·명찰·리본 글자에 맞춰 붙이지 않는다:"]
        q.append("  " + " · ".join(c + (f"({'·'.join(s[:4])}처럼 들릴 수 있다)" if s else "") for c, s in 낱말))
    # agy_gemini.generate 가 responseSchema 를 받으면 붙이던 형식 지시와 같은 글(머리 주석 「어떻게 읽히나」 끝)
    q += ["", "[출력 형식] JSON 값 하나만 출력하라. 앞뒤 설명·코드블록 금지.",
          "아래 JSON Schema 를 반드시 따른다(required 칸 전부, 칸 순서 그대로):", json.dumps(JS, ensure_ascii=False)]
    return "\n".join(q)


# ── 답 읽기 (머리 주석 「실패 종류」) ──
def _JSON_고쳐읽기(s, 한도=12):
    """모델이 가끔 내는 괄호·따옴표 실수만 고쳐 읽는다 → (값, 고친 수) 또는 (None, 까닭).
    고치는 것 (2026-09-26 EPK10 실측에서 나온 것들):
      · 남는 닫는 괄호 — «…"둘다"}}], "장면"…» (285~585초 조각)
      · 안 닫은 배열 — «…"자리": "본부 입구"}, "화면글자": […» 처럼 배열 안에서 칸 이름이 나온다(1425~1725초 조각)
        → 그 칸 이름 앞 쉼표 자리에 «]» 를 넣는다
      · 글 안의 따옴표 — «"글": "그가 "간첩" 이래"» → 안쪽 따옴표를 \\" 로
      · 빠진 쉼표 · 끝에 남는 괄호."""
    for n in range(한도 + 1):
        try:
            return json.loads(s), n
        except json.JSONDecodeError as e:
            p = e.pos
            ch = s[p] if p < len(s) else ""
            앞 = s[:p].rstrip()
            if e.msg.startswith("Extra data") and not s[p:].strip(" \n\t}]"):
                s = s[:p]
            elif ch in "}]" and "delimiter" in e.msg:
                s = s[:p] + s[p + 1:]
            elif ch == ":" and "delimiter" in e.msg and 앞.endswith('"'):
                k1 = s.rfind('"', 0, len(앞) - 1)            # 칸 이름을 여는 따옴표
                c = s.rfind(",", 0, k1)
                if c < 0:
                    return None, f"JSON 이 깨졌다({e.msg} · {p}번째 글자)"
                s = s[:c] + "]" + s[c:]
            elif e.msg.startswith("Expecting ',' delimiter") and ch in '{"':
                s = s[:p] + "," + s[p:]
            elif e.msg.startswith("Expecting ',' delimiter") and 앞.endswith('"') and ch not in ",:}]":
                q = len(앞) - 1                                # 글을 일찍 닫아 버린 안쪽 따옴표
                s = s[:q] + '\\"' + s[q + 1:]
            else:
                return None, f"JSON 이 깨졌다({e.msg} · {p}번째 글자)"
    return None, f"JSON 을 {한도}번 고쳐도 안 읽힌다"


def _잘린_JSON_살리기(s):
    """중간에 끊긴 JSON 을 «마지막으로 온전히 닫힌 배열 원소» 까지 살려 괄호를 닫는다 → (값 또는 None, 끊긴 꼬리 글)."""
    stack, instr, esc, cut, cut_stack = [], False, False, None, None
    짝 = {"}": "{", "]": "["}
    for i, ch in enumerate(s):
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack or stack[-1] != 짝[ch]:
                break
            stack.pop()
            if stack and stack[-1] == "[":
                cut, cut_stack = i + 1, list(stack)
    if cut is None:
        return None, s
    닫기 = "".join("}" if c == "{" else "]" for c in reversed(cut_stack))
    try:
        return json.loads(s[:cut] + 닫기), s[cut:]
    except json.JSONDecodeError:
        return None, s[cut:]


def 답_해석(text):
    """agy 답 글 → (답, 사정) 또는 (None, 까닭).
    사정 = {"JSON고침": n, "잘림": None | {"까닭", "막힌_s", "막힌_e"(조각 기준 «분:초» 글자 또는 None)}}"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    막힘 = min((t.find(m) for m in 막힘표시 if m in t), default=-1)
    i = t.find("{")
    if i < 0 or (막힘 >= 0 and 막힘 < i):
        return None, ("제미나이 필터가 답 첫머리에서 막았다" if 막힘 >= 0 else "답에 JSON 이 없다") + f": {t[:80]}"
    몸 = t[i:막힘] if 막힘 >= 0 else t[i:t.rfind("}") + 1]
    잘림 = None
    obj, n = (None, 0) if 막힘 >= 0 else _JSON_고쳐읽기(몸)
    if obj is None:
        obj, 꼬리 = _잘린_JSON_살리기(몸)
        if not isinstance(obj, dict):
            return None, (f"제미나이 필터가 막았고 살릴 발화가 없다: {몸[-80:]}" if 막힘 >= 0 else f"{n}: {몸[:80]}")
        m = re.search(r'"s"\s*:\s*"([0-9:.]+)"\s*,\s*"e"\s*:\s*"([0-9:.]+)"', 꼬리) or \
            re.search(r'"s"\s*:\s*"([0-9:.]+)"', 꼬리)
        잘림 = {"까닭": "제미나이 필터가 답 중간에서 막음" if 막힘 >= 0 else "답이 중간에 끊김",
              "막힌_s": m.group(1) if m else None, "막힌_e": m.group(2) if m and m.lastindex == 2 else None,
              "꼬리": nfc(꼬리.strip())[:160]}
        for k in ("장면", "화면글자", "발화"):
            obj.setdefault(k, [])
        n = 0
    if not isinstance(obj, dict):
        return None, "답이 JSON 객체가 아니다"
    bad = agy_gemini._schema_errors(obj, JS)
    if bad:
        return None, "스키마와 다르다: " + "; ".join(bad[:3])
    if 잘림 and not obj["발화"]:
        return None, f"{잘림['까닭']} — 살린 발화가 없다"
    return obj, {"JSON고침": n, "잘림": 잘림}


def _근거(v):
    v = str(v or "")
    if v in 근거값:
        return v
    if "소리" in v and "그림" in v:
        return "둘다"
    return "그림" if "그림" in v else "소리" if "소리" in v else "?"


_시각꼴 = re.compile(r"^\s*(?:(\d+):)?(\d+):([0-5]?\d(?:\.\d+)?)\s*$")
시각이상_한도 = 0.10     # 발화·장면 시각 중 이만큼 넘게 이상하면 그 답을 버린다(_시각정리 주석)


def 초로(v):
    """«분:초.소수»(또는 시:분:초) 글자 → 초. 숫자이거나 다른 꼴이면 None.

    ★2026-09-26 맥2 실측 — 초(숫자)로 달라고 하면 제미나이가 영상 시각을 분:초로 읽어 **붙여 쓴다**:
      1:11.9 → 111.9, 2:11.2 → 211.2 (신병4 EPK10 0~300초 · 300초 조각 95발화 대부분, 120초 조각 세 개 모두).
      같은 답 안에서 진짜 초와 섞이기도 해서(…266.3, 209.9…) 숫자만 보고는 되돌릴 수 없다 — 30초 밀도 상관이
      0.07 로 무너졌다. 그래서 모델이 본래 쓰는 분:초 글자로 받고 여기서 바꾼다(바꾼 뒤 상관 0.96).
      숫자로 온 값은 받지 않는다."""
    if not isinstance(v, str):
        return None
    m = _시각꼴.match(v)
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _시각정리(답, L):
    """조각 기준 «분:초» 를 초로 바꾸고 검사한다 → (발화, 장면, 화면글자, 셈).

    셈: 꼴어긋남(분:초 글자가 아님) · 벗어남(−1초 미만·길이+2초 초과) · 뒤로감(발화 순서에서 앞 발화보다 3초 넘게
        앞선 시작) · 뒤집힘(e<s — e=s 로 두고 센다) · 이상비율. 꼴어긋남·벗어남은 버린다.
    이상비율 = (꼴어긋남 + 벗어남 + 뒤로감) / (발화 + 장면) — 시각이상_한도를 넘으면 부르는 쪽이 그 답을 버린다
    (초로 주석의 붙여 쓰기가 다시 나와도 캐시·결과로 들어가지 않게 하는 관문)."""
    발화, 장면, 글자 = [], [], []
    셈 = {"꼴어긋남": 0, "벗어남": 0, "뒤로감": 0, "뒤집힘": 0}

    def 잼(v):
        t = 초로(v)
        if t is None:
            셈["꼴어긋남"] += 1
        elif not (-1 <= t <= L + 2):
            셈["벗어남"] += 1
            t = None
        return t

    앞 = -math.inf
    for u in 답.get("발화", []):
        글 = nfc(str(u.get("글", "")).strip())
        if not 글:
            continue
        s = 잼(u.get("s"))
        if s is None:
            continue
        e = 초로(u.get("e"))
        e = s if e is None else e
        셈["뒤로감"] += s < 앞 - 3
        앞 = max(앞, s)
        셈["뒤집힘"] += e < s
        s = min(max(s, 0.0), L)
        이름근거 = nfc(str(u.get("이름근거", "")).strip())
        발화.append({"s": s, "e": min(max(e, s), L), "화자": nfc(str(u["화자"]).strip() or "?"),
                   "이름근거": 이름근거 if 이름근거 in 이름근거값 else "없음", "글": 글, "근거": _근거(u.get("근거"))})
    for c in 답.get("장면", []):
        s = 잼(c.get("s"))
        if s is None:
            continue
        e = 초로(c.get("e"))
        e = L if e is None else e
        s = min(max(s, 0.0), L)
        장면.append({"s": s, "e": min(max(e, s), L), "요지": nfc(str(c["요지"]).strip()),
                   "화면인물": [nfc(str(x)) for x in c.get("화면인물", [])], "자리": nfc(str(c.get("자리", "")).strip())})
    for g in 답.get("화면글자", []):
        s, 글 = 초로(g.get("s")), nfc(str(g.get("글", "")).strip())
        종류 = nfc(str(g.get("종류", "")).strip())
        if 글 and s is not None and -1 <= s <= L + 2:
            글자.append({"s": min(max(s, 0.0), L), "종류": 종류 if 종류 in 글자종류값 else "기타", "글": 글})
    발화.sort(key=lambda u: u["s"])
    전체 = len(답.get("발화", [])) + len(답.get("장면", []))
    셈["이상비율"] = round((셈["꼴어긋남"] + 셈["벗어남"] + 셈["뒤로감"]) / 전체, 3) if 전체 else 0.0
    return 발화, 장면, 글자, 셈


def _맨글(t):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t)


def _닮음(a, b):
    a, b = _맨글(a), _맨글(b)
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


def _통이름(화자):
    """이름표 → 비교용 한 꼴(글자만 · 끝 «님» 뺌 · 줄인 직함은 온이름으로 — 행보관님 = 행정보급관)."""
    t = re.sub(r"님$", "", _맨글(화자))
    return 직함_줄임.get(t, t)


def _이름열쇠(화자):
    """화자 이름표 → (들렸는지 찾을 열쇠들, 이름 토막들). 계급·직함 토막은 이름이 아니다.
    «최일구 하사» → 열쇠 {최일구하사, 최일구, 일구} · «중대장님» → {중대장} · «최 상사» → {최상사, 상사}."""
    통 = _통이름(화자)
    토막 = [_통이름(t) for t in re.split(r"[\s·,/()\[\]]+", 화자)]
    토막 = [t for t in 토막 if t]
    이름들 = [t for t in 토막 if t not in 직함 and len(t) >= 2 and not t.isdigit()]
    열쇠 = {통} | set(이름들) | {n[1:] for n in 이름들 if re.fullmatch(r"[가-힣]{3}", n)}   # 이름만 부름(현욱아)
    if not 이름들:
        열쇠 |= {t for t in 토막 if t in 직함 and t not in 계급}          # 직함 이름표(중대장) — 계급 하나로는 안 된다
    열쇠 |= {줄임 for 줄임, 온 in 직함_줄임.items() if 온 in 열쇠}       # 행정보급관 이름표는 «행보관» 으로도 불린다
    return {k for k in 열쇠 if len(k) >= 2}, 이름들


def _화자_확인(발화, 글자, 생김새이름):
    """조각 안 발화마다 «화자확인» 을 매긴다(제자리 수정). 모델이 적은 이름근거를 믿지 않고, 이름표와 이름이
    **이 조각 안에서 기계로 이어지는 자리**가 한 군데라도 있는지만 본다(이름표 단위 — 같은 이름표의 발화는 같은 값).
      번호   남1·여1 꼴 — 이름을 주장하지 않음
      들음   ① 자기소개 — 그 이름표 발화에 «계급+이름»(병장 강찬석)·«이름+입니다» 가 있다
             ② 호명 응답 — 남의 발화가 그 이름(이름만·직함 포함)을 부르고, 그 끝에서 호명_응답_초 안에 그 이름표가
                다음 차례(두 발화 안)로 말한다
      자막   종류 «자막» 화면글자에 그 이름이 뜨고 자막_근처_초 안에 그 이름표가 말한다(명찰·간판·문서 글자는 안 친다)
      생김새  인물 목록에 생김새가 적힌 이름이고 모델이 이름근거를 생김새로 적었다
      미확인  이름이 있는데 위 자리가 없다 — 명찰·사전 짐작일 수 있다(덩이에 «?» 로 보인다)

    왜 이렇게 좁나 (2026-09-26 맥2 — 옛 답 7조각을 다시 매겨 봄)
      · 명찰로 받은 이름은 틀린다: 검증에서 명찰 조백호를 «오석진», 박재수를 «배홍길» 로 읽었다. 480p 조각에서 명찰은
        글자가 아니라 회색 띠다(1197·1243초 조각 프레임을 눈으로 확인). 이 둘은 위 규칙으로 모두 미확인(15·17발화).
      · «근처에서 그 이름이 들렸다» 만으로는 모자란다: 조각 7 은 행보관(실제 박재수 — 화환 리본)을 «박민석» 으로 적었고,
        94초 뒤 «야, 박민석이 아버지한테 말씀드렸나?» 가 있어 창 120초·60초·30초 모두 들음이 되었다. 부른 바로 다음
        차례에 대답했는지를 봐야 이 가짜가 빠진다.
    «들음» 도 이름과 이름표가 이어졌다는 것까지다 — 모델이 조각 안에서 그 이름표를 같은 사람에게만 붙였는지는 모른다
    (머리 화자_주의). 자기 발화 속 이름은 부르는 말일 수 있어 계급이 앞설 때만 자기소개로 친다."""
    자막 = [(g["s"], _맨글(g["글"])) for g in 글자 if g.get("종류") == "자막"]
    차례 = sorted(발화, key=lambda v: v["s"])
    확인표 = {}
    for h in {u["화자"] for u in 발화}:
        if 번호꼴.search(h):
            확인표[h] = "번호"
            continue
        열쇠, 이름들 = _이름열쇠(h)
        같음 = _통이름(h)                                                  # 행보관님 = 행정보급관
        내것 = [u for u in 차례 if _통이름(u["화자"]) == 같음]
        확인 = None
        if 생김새이름 and h in 생김새이름 and any(u.get("이름근거") == "생김새" for u in 내것):
            확인 = "생김새"
        if not 확인 and any(any(r + n in _맨글(u["글"]) for r in 계급 for n in 이름들)
                          or any(n + "입니다" in _맨글(u["글"]) for n in 이름들) for u in 내것):
            확인 = "들음"                                                      # ① 자기소개
        if not 확인:
            for i, v in enumerate(차례):
                if _통이름(v["화자"]) == 같음 or not any(k in _맨글(v["글"]) for k in 열쇠):
                    continue
                if any(_통이름(w["화자"]) == 같음 and w["s"] - v["e"] <= 호명_응답_초 for w in 차례[i + 1:i + 3]):
                    확인 = "들음"                                              # ② 호명 응답
                    break
        if not 확인 and any(any(k in t for k in 열쇠) and any(abs(u["s"] - s) <= 자막_근처_초 for u in 내것)
                          for s, t in 자막):
            확인 = "자막"
        확인표[h] = 확인 or "미확인"
    for u in 발화:
        u["화자확인"] = 확인표[u["화자"]]


def _겹침_화자검사(받은):
    """겹친 구간에서 두 조각이 같은 말(시작 ±2초 · 글 닮음 0.5 이상)에 **서로 다른 이름**을 붙였으면 모은다
    → (어긋남 목록, 이음 목록, 비교한 짝 수). 어긋남은 둘 중 하나가 틀린 이름이다 — 사람이 프레임으로 본다.
      · 이름끼리(최일구 ↔ 강찬석)·직함끼리(행보관 ↔ 중대장) 다르면 어긋남.
      · 이름 ↔ 직함(조백호 ↔ 중대장)은 모순이 아니라 같은 사람을 달리 부른 것일 수 있어 «이음» 으로 따로 둔다
        (2026-09-26 4차 판: 겹침 어긋남 4곳이 모두 조백호 ↔ 중대장이었다 — 조백호가 그 중대장이다).
      · 한쪽이 번호(남1)면 모순이 아니라 모름이라 세지 않는다.
    받은 = 조각별 {from,to,발화(조각 기준 초)}."""
    어긋남, 이음, 짝수 = [], [], 0
    for k in range(len(받은) - 1):
        A, B = 받은[k], 받은[k + 1]
        z0, z1 = B["from"], A["to"]
        au = [u for u in A["발화"] if A["from"] + u["s"] >= z0 - 1]
        bu = [v for v in B["발화"] if B["from"] + v["s"] <= z1 + 1]
        쓴 = set()
        for u in au:
            us = A["from"] + u["s"]
            best, bj = 0.5, None
            for j, v in enumerate(bu):
                if j in 쓴 or abs(us - (B["from"] + v["s"])) > 2:
                    continue
                r = _닮음(u["글"], v["글"])
                if r >= best:
                    best, bj = r, j
            if bj is None:
                continue
            쓴.add(bj)
            v = bu[bj]
            if 번호꼴.search(u["화자"]) or 번호꼴.search(v["화자"]):
                continue
            짝수 += 1
            if _통이름(u["화자"]) == _통이름(v["화자"]):
                continue
            ua, va = _이름열쇠(u["화자"])[1], _이름열쇠(v["화자"])[1]      # 이름 토막(없으면 직함 이름표)
            m = {"s": round(us, 2), "글": u["글"][:40],
                 "앞": {"조각": k + 1, "화자": u["화자"], "화자확인": u.get("화자확인")},
                 "뒤": {"조각": k + 2, "화자": v["화자"], "화자확인": v.get("화자확인")}}
            if bool(ua) != bool(va):
                이음.append(m)
                continue
            if ua and any(x in y or y in x for x in ua for y in va):
                continue               # 이름끼리 한쪽이 다른 쪽에 들면 같은 이름(최일구 ↔ 최일구 하사 · 병남 ↔ 최병남)
            어긋남.append(m)
    return 어긋남, 이음, 짝수


def _조각_펼치기(c, L, 생김새이름=frozenset()):
    """캐시 한 조각(부분 답 1~2개) → 조각 기준 초의 (발화, 장면, 화면글자, 셈 합).
    부분 답은 «처음 답(0~L)» 과 «막힌 대사 뒤부터 받은 나머지(R~L)». 장면은 앞 부분이 덮은 끝 뒤로 이어지는 몫만.
    발화마다 화자확인을 매긴다(_화자_확인 — 조각 안 증거만)."""
    발화, 장면, 글자 = [], [], []
    합 = {"꼴어긋남": 0, "벗어남": 0, "뒤로감": 0, "뒤집힘": 0}
    for p in c["부분"]:
        R = p["from"]
        u, x, g, 셈 = _시각정리(p["답"], p["to"] - R)
        for k in 합:
            합[k] += 셈[k]
        발화 += [dict(v, s=v["s"] + R, e=v["e"] + R) for v in u]
        끝 = max((v["e"] for v in 장면), default=-math.inf)
        for v in x:
            v = dict(v, s=v["s"] + R, e=v["e"] + R)
            if v["e"] <= 끝 + 1:
                continue
            v["s"] = max(v["s"], 끝)
            장면.append(v)
        for v in g:
            v = dict(v, s=v["s"] + R)
            if not any(abs(v["s"] - h["s"]) <= 5 and _닮음(v["글"], h["글"]) >= 0.6 for h in 글자):
                글자.append(v)
    발화.sort(key=lambda v: v["s"])
    _화자_확인(발화, 글자, 생김새이름)
    return 발화, 장면, 글자, 합


def _합치기(조각들, 끝여유=0.5):
    """조각별 답(조각 기준 초) → 소재 절대초 발화·장면·화면글자. 겹친 구간은 **앞 조각 우선**(사장님 설계 2026-09-26).

      ① 앞 조각 끝에 걸린 발화(끝 끝여유초 안까지 이어짐)는 말이 잘린 채 받혔을 수 있다 — 뒤 조각이 그 발화를
         처음부터 들었으면(시작이 뒤 조각 시작 + 끝여유 뒤) 앞 조각 것을 버린다.
      ② 뒤 조각에서는 앞 조각이 남긴 마지막 발화의 끝(H) − 0.3초 뒤에 시작한 발화만 받는다.
      ③ 그래도 겹침 안에서 앞 조각과 같은 말(시작 ±3초 · 글 닮음 0.6 이상)이면 버린다(조각마다 시각이 조금씩 달라서).
      장면은 앞 조각이 덮은 끝 뒤로 이어지는 몫만, 화면글자는 앞 조각 끝 뒤의 것만(같은 글 ±5초는 버린다) 받는다.
    """
    발화, 장면, 글자 = [], [], []
    n = len(조각들)
    for k, c in enumerate(조각들):
        a0, a1 = c["from"], c["to"]
        us = [dict(u, s=round(a0 + u["s"], 2), e=round(a0 + u["e"], 2), 조각=k + 1) for u in c["발화"]]
        xs = [dict(x, s=round(a0 + x["s"], 2), e=round(a0 + x["e"], 2), 조각=k + 1) for x in c["장면"]]
        gs = [dict(g, s=round(a0 + g["s"], 2), 조각=k + 1) for g in c["화면글자"]]
        if k > 0:
            p = 조각들[k - 1]
            앞것 = [u for u in 발화 if u["조각"] == k]
            H = min(max((u["e"] for u in 앞것), default=a0), p["to"])
            us = [u for u in us if u["s"] >= H - 0.3
                  and not (u["s"] < p["to"] and any(abs(u["s"] - q["s"]) <= 3 and _닮음(u["글"], q["글"]) >= 0.6
                                                     for q in 앞것))]
            끝 = max((x["e"] for x in 장면 if x["조각"] == k), default=a0)
            ys = []
            for x in xs:
                if x["e"] <= 끝 + 1:
                    continue
                x["s"] = max(x["s"], round(끝, 2))
                ys.append(x)
            xs = ys
            gs = [g for g in gs if g["s"] >= p["to"]
                  and not any(abs(g["s"] - h["s"]) <= 5 and _닮음(g["글"], h["글"]) >= 0.6 for h in 글자)]
        if k < n - 1:
            다음 = 조각들[k + 1]["from"]
            us = [u for u in us if not (u["e"] >= a1 - 끝여유 and u["s"] >= 다음 + 끝여유)]
            xs = [dict(x, e=min(x["e"], a1)) for x in xs]
        발화 += us
        장면 += xs
        글자 += gs
    발화.sort(key=lambda u: u["s"])
    장면.sort(key=lambda x: x["s"])
    글자.sort(key=lambda g: g["s"])
    return 발화, 장면, 글자


# ── 내기 ──
def _쓰기(접두, 머리, 발화, 장면, 글자, a, b):
    out = dict(머리)
    out["발화"], out["장면"], out["화면글자"] = 발화, 장면, 글자
    p = Path(f"{접두}_파악전사.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    끝 = 머리["받은_끝"] if 머리.get("멈춘까닭") else b
    칸 = [[0, 0] for _ in range(max(1, math.ceil((끝 - a) / 30)))]
    for u in 발화:
        i = int((u["s"] - a) // 30)
        if 0 <= i < len(칸):
            칸[i][0] += len("".join(u["글"].split()))
            칸[i][1] += 1
    큰 = max(x[0] for x in 칸) or 1
    미완표 = " · ★미완(받은 데까지)" if 머리.get("멈춘까닭") else " · ★미완" if 머리["미완"] else ""
    막힌 = 머리.get("막힌구간") or []
    막힌표 = f" · ★막힌구간 {len(막힌)}곳" if 막힌 else ""
    줄 = [f"# 파악전사 30초 밀도 — {용도} · 읽은 것 {읽은것}", f"# 소재 {머리['소재']} · 엔진 {머리['엔진']}{미완표}{막힌표}",
          "# 시작초  (분:초)   글자   발화"]
    for i, (n, m) in enumerate(칸):
        t = a + i * 30
        표 = "".join(" ★막힘" for h in 막힌 if h["from"] < t + 30 and h["to"] > t)[:6]
        줄.append(f"{t:8.1f}  ({mmss(t)})  {n:5d}  {m:4d}  " + "▇" * round(20 * n / 큰) + 표)
    Path(f"{접두}_파악_밀도30s.txt").write_text("\n".join(줄) + "\n", encoding="utf-8")

    어긋남 = 머리.get("화자_어긋남") or []
    줄 = [f"# 파악전사 덩이 — {용도} · 읽은 것 {읽은것}. 시각은 제미나이 시각(보통 0.2~0.3초, 가끔 수 초 어긋남).",
          "# 화자 [이름표·확인·근거]: 확인 = 들음(계급+이름 자기소개, 또는 부른 바로 다음 차례에 대답) · "
          "자막(방송 자막에 뜸) · 생김새 · 미확인(이름에 «?» — 명찰·사전 짐작일 수 있다, 믿지 말 것).",
          "#   «들음» 도 이름과 이름표가 한 자리에서 이어졌다는 것까지다 — 얼굴이 그 사람인지는 프레임으로 본다. "
          "남1·여1 은 조각 안에서만 일관된다(조각이 바뀌면 새로 센다).",
          f"# 소재 {머리['소재']} · 엔진 {머리['엔진']}{미완표}{막힌표}"
          + (f" · ★겹침 화자 어긋남 {len(어긋남)}곳" if 어긋남 else "")]
    사건 = ([(x["s"], 0, x) for x in 장면] + [(h["from"], 1, h) for h in 막힌]
          + [(g["s"], 2, g) for g in 글자] + [(u["s"], 3, u) for u in 발화]
          + [(m["s"], 4, dict(m, 조각=m["앞"]["조각"])) for m in 어긋남])
    지난조각 = None
    for t, kind, x in sorted(사건, key=lambda z: (z[0], z[1])):
        if x["조각"] != 지난조각:
            c = 머리["조각"][x["조각"] - 1]
            줄.append(f"┄┄ 조각 {x['조각']} ({c['from']:.1f}~{c['to']:.1f}초) ┄┄")
            지난조각 = x["조각"]
        if kind == 0:
            모름 = set(x.get("화면인물_미확인", []))
            줄.append(f"\n── {mmss(x['s'])}~{mmss(x['e'])} · {x['요지']}" + (f" · 자리: {x['자리']}" if x["자리"] else "")
                     + (f" · 화면: {', '.join(n + ('?' if n in 모름 else '') for n in x['화면인물'])}"
                        if x["화면인물"] else ""))
        elif kind == 1:
            줄.append(f"{x['from']:8.1f} ({mmss(x['from'])}) ★{x['까닭']} — {x['from']:.1f}~{x['to']:.1f}초를 못 받았다"
                     f"(사람이 직접 본다) · 끊긴 글: {x.get('꼬리', '')[:60]}")
        elif kind == 2:
            종류 = x.get("종류", "기타")
            줄.append(f"{x['s']:8.1f} ({mmss(x['s'])}) «화면글자·{종류}{'(미확인 — 480p 명찰은 안 읽힌다)' if 종류 == '명찰' else ''}» {x['글']}")
        elif kind == 3:
            확인 = x.get("화자확인", "")
            if 확인 == "번호":
                표 = f"{x['화자']}·{x['근거']}"
            elif 확인 == "미확인":
                표 = f"{x['화자']}?·미확인({x.get('이름근거', '')})·{x['근거']}"
            else:
                표 = f"{x['화자']}·{확인}·{x['근거']}"
            줄.append(f"{x['s']:8.1f} ({mmss(x['s'])}) [{표}] {x['글']}"
                     + (f"   ★다른 조각은 «{x['화자_다른조각']}»" if x.get("화자_다른조각") else ""))
        else:
            줄.append(f"{x['s']:8.1f} ({mmss(x['s'])}) ★겹침 화자 어긋남 — 조각 {x['앞']['조각']} «{x['앞']['화자']}» "
                     f"↔ 조각 {x['뒤']['조각']} «{x['뒤']['화자']}» (같은 말: {x['글'][:30]}) — 둘 중 하나는 틀린 이름")
    Path(f"{접두}_파악_덩이.txt").write_text("\n".join(줄) + "\n", encoding="utf-8")
    return p


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")   # 윈도우 기본 cp949 로 나가면 한글이 깨진다
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="소재 영상의 그림과 소리를 agy(제미나이)로 읽힌다 — 파악용(자막·싱크 금지)")
    ap.add_argument("소재")
    ap.add_argument("--from", dest="a", type=float, default=0.0, help="시작 초")
    ap.add_argument("--to", dest="b", type=float, default=None, help="끝 초(기본 소재 끝)")
    ap.add_argument("--사전", help="드라마정보.json(낱말사전·인물) 또는 이름 목록 json")
    ap.add_argument("--낼", help="접두 경로 — <접두>_파악전사.json 따위로 낸다(기본 ./<소재 이름>)")
    ap.add_argument("--모델", default=DEFAULT_MODEL)
    ap.add_argument("--조각", type=float, default=DEFAULT_조각, help="조각 길이(초)")
    ap.add_argument("--겹침", type=float, default=DEFAULT_겹침, help="조각끼리 겹치는 초(10~15)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT_MIN, help="조각 하나 시간 제한(분)")
    ap.add_argument("--다시", action="store_true", help="이미 받은 조각도 새로 받는다")
    a = ap.parse_args()
    try:
        return run(a)
    except 멈춤 as e:
        print(f"\n멈춤: {e}", file=sys.stderr)
        return e.코드


def run(a):
    src = Path(nfc(os.path.abspath(a.소재)))
    if not src.is_file():
        raise 멈춤(3, f"소재가 없다: {src}")
    접두 = nfc(os.path.abspath(a.낼)) if a.낼 else nfc(os.path.join(os.getcwd(), src.stem))
    이름 = os.path.basename(접두).lower()
    나쁜 = [w for w in 금지낱말 if w in 이름]
    if 나쁜 or 이름.endswith((".srt", ".vtt")):
        raise 멈춤(3, f"접두 이름에 {', '.join(나쁜) or '.srt/.vtt'} 가 있다 — 자막·싱크 도구가 이름으로 집어 간다. --낼 로 다른 이름을 줘라")
    if not (a.조각 > 2 * a.겹침 >= 0):
        raise 멈춤(3, f"--조각({a.조각}) 은 --겹침({a.겹침}) 의 두 배보다 길어야 한다")
    if os.environ.get("YOUSTUDIO_GEMINI_ROUTE", "").strip().lower() == "evolink":
        raise 멈춤(3, "YOUSTUDIO_GEMINI_ROUTE=evolink 가 켜져 있다 — 파악 전사는 agy 로만 돈다(EvoLink 금지). 끄고 다시 돌려라")
    _evolink_길_검사()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise 멈춤(3, "ffmpeg/ffprobe 가 없다 — 볼트 환경/ 의 이 컴퓨터 파일을 보고 설치")
    exe = agy_gemini._agy_exe()
    if not exe:
        raise 멈춤(3, "agy 를 못 찾았다 — 설치: https://antigravity.google/cli (맥 ~/.local/bin/agy · 윈도우 %LOCALAPPDATA%\\agy\\bin) "
                    "뒤 `python ~/.claude/agy_call.py --usage` 로 로그인 확인. 파악 전사는 EvoLink 로 돌리지 않는다")

    전체, 영상, 소리 = 소재정보(src)
    if not 영상:
        raise 멈춤(3, "영상이 필요하다 — 파악은 그림과 소리를 같이 읽힌다(2026-09-26 사장님 «영상, 그림 무조건 읽어야지 정확하게»). "
                    "소리 파일만으로는 돌리지 않는다. 같은 소재의 영상 파일을 줘라")
    if not 소리:
        raise 멈춤(3, "소리 스트림이 없다 — 파악은 그림과 소리를 같이 읽힌다. 소리가 든 영상 파일을 줘라")
    A = max(0.0, a.a)
    B = 전체 if a.b is None else min(a.b, 전체)
    if B - A < 1:
        raise 멈춤(3, f"구간이 비었다: {A}~{B}초 (소재 {전체:.1f}초)")
    낱말, 인물 = 사전_읽기(a.사전) if a.사전 else ([], [])
    생김새이름 = frozenset(n for n, g in 인물 if g)
    q판 = hashlib.sha256((질문판 + json.dumps(SCHEMA, ensure_ascii=False) + 질문(1.0, [], [], "")
                         + f"{영상_짧은변}/{영상_FPS}").encode()).hexdigest()[:12]
    사전지문 = hashlib.sha256(json.dumps([낱말, 인물], ensure_ascii=False).encode()).hexdigest()[:16]
    sha, 방식 = 지문(src)
    폴더 = Path(os.path.dirname(접두))
    조각폴더 = 폴더 / "_파악조각"
    조각폴더.mkdir(parents=True, exist_ok=True)
    표 = 조각표(A, B, a.조각, a.겹침)
    _인터넷_막기()
    print(f"파악전사 · {src.name} · {A:.1f}~{B:.1f}초 · 조각 {len(표)}개({a.조각:.0f}초·겹침 {a.겹침:.0f}초) · "
          f"agy/{a.모델} · {읽은것} · 사전 낱말 {len(낱말)}·인물 {len(인물)}", flush=True)

    def 캐시_읽기(k, 키):
        캐시 = 조각폴더 / f"조각_{k:02d}.json"
        if a.다시 or not 캐시.exists():
            return None
        try:
            c = json.loads(캐시.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if c.get("키") != 키:
            print(f"  조각 {k}: 캐시가 다른 조건(소재·구간·모델·사전·질문판)이라 새로 받는다", flush=True)
            return None
        # 답마다 «보낸 영상의 키» 가 이 조각·그 부분 구간의 키와 같아야 쓴다. 조각 영상 키 전(2026-09-26 재검증 전)
        # 캐시는 키가 맞아도 **다른 영상으로 받은 답**일 수 있다(머리 주석 「지키는 것」 조각 영상 키) — 새로 받는다.
        부분 = c.get("부분") or []
        if not 부분 or any(p.get("영상키") != 조각키((sha, 방식), 키["from"] + p.get("from", 0.0), 키["to"]) for p in 부분):
            print(f"  조각 {k}: 캐시 답을 어느 영상으로 받았는지 확인이 안 된다(조각 영상 키 없음·다름) — 새로 받는다",
                  flush=True)
            return None
        return c

    키들 = {k: {"소재_sha256": sha, "from": s, "to": e, "모델": a.모델, "사전": 사전지문, "질문판": q판, "읽은것": 읽은것}
          for k, (s, e) in enumerate(표, 1)}
    캐시들 = {k: 캐시_읽기(k, 키들[k]) for k in 키들}

    def 부르기(k, mp4, 키, L, 로그):
        """agy 한 번 → (답, 사정, 초, resp) 또는 (None, 까닭, 초, resp). resp 는 route 검사용.
        보내기 직전에 영상 안 키를 다시 읽어 이 조각 키와 다르면 멈춘다(최종 관문 — 머리 주석 「지키는 것」 조각 영상 키)."""
        속키 = 조각키_읽기(mp4)
        if 속키 != 키:
            raise 멈춤(3, f"보낼 영상 조각의 키가 이 조각과 다르다({Path(mp4).name} · 안에 적힌 키 {속키} · 이 조각 {키}) — "
                        "다른 소재·구간 영상을 agy 에 보낼 뻔해 멈췄다. _파악조각 의 그 파일을 지우고 다시 돌려라")
        body = {"contents": [{"role": "user", "parts": [
                    {"@inline_file": {"path": str(mp4), "mime": "video/mp4"}},
                    {"text": 질문(L, 낱말, 인물, src.stem)}]}]}

        def log(m):
            m = m.replace("→ EvoLink 로 넘어간다", "→ (파악전사는 EvoLink 로 넘기지 않는다)")
            로그.append(m.strip())
            print(m, flush=True)

        t1 = time.time()
        try:
            resp = agy_gemini.generate(body, caller=CALLER, model=a.모델, limit_min=a.limit, log=log)
        except getattr(agy_gemini, "AgyStop", ()) as e:
            # 2026-09-27 합친 agy_gemini 는 영상 요청이 끝내 실패하면 None 대신 AgyStop 을 던진다(맥1 d822dd5).
            #   파악전사는 전과 똑같이 «agy 실패» 로 받는다 — 한 번 더, 또 실패면 받은 데까지 «미완» 으로 쓰고 멈춘다.
            resp = None
            로그.append(str(e)[:300])
        초 = round(time.time() - t1, 1)
        if resp is None:
            return None, f"agy 실패: {로그[-1] if 로그 else ''}", 초, None
        if resp.get("route") != "agy" or not str(resp.get("modelVersion", "")).startswith("agy/"):
            return None, "agy 아닌 길", 초, resp
        답, 사정 = 답_해석(agy_gemini.text_of(resp))
        if 답 is None:
            return None, 사정, 초, resp
        읽음 = 답.get("읽음") or {}
        if 읽음.get("그림") is not True or 읽음.get("소리") is not True:
            return None, f"모델이 첨부를 다 못 읽었다고 답했다(읽음 {읽음})", 초, resp
        셈 = _시각정리(답, L)[3]
        if 셈["이상비율"] > 시각이상_한도:
            return None, f"시각이 이상하다({셈}) — 분:초 붙여 쓰기·조각 밖 시각", 초, resp
        return 답, 사정, 초, resp

    def 조각_받기(k, s, e, mp4, 영상키):
        """조각 하나를 받는다 → (부분, 막힌구간, 버린까닭, usage, 멈춘까닭 또는 None).

        호출 몫(조각 하나에 agy 많아야 세 번):
          · 다시 1번 — 실패(None·헛답·그림/소리 못 읽음·시각 이상)한 요청을 한 번 더. 또 실패면 멈춘다(사장님 설계).
          · 나머지 1번 — 답이 중간에서 끊겼을 때 끊긴 자리 뒤부터 조각 끝까지. 필터가 막은 대사는 다시 불러도
            같은 자리에서 막히므로(머리 주석 「실패 종류」③ · EPK10 1567초 세 번 모두) 그 대사를 건너뛰고 구멍으로 남긴다.
            «다시» 와 다른 몫이다 — 같은 요청을 되풀이하는 게 아니라 아직 못 받은 뒷부분을 받는 것이고, 한 번뿐이다.
          나머지까지 또 끊기면 더 부르지 않고 끝까지를 구멍으로 남긴다."""
        L = e - s
        로그, 버린까닭, 부분, 구멍, usage = [], [], [], [], []
        다시, 나머지 = 1, 1
        R, 대상, 대상키, 차 = 0.0, mp4, 영상키, 0
        while True:
            차 += 1
            print(f"  조각 {k}/{len(표)}  {s + R:.1f}~{e:.1f}초 받는 중" + (f" ({차}차)" if 차 > 1 else ""), flush=True)
            try:
                답, 사정, 초, resp = 부르기(k, 대상, 대상키, L - R, 로그)
            except 멈춤 as ex:            # 인터넷 막기(_인터넷_막기) 따위 — 받은 데까지 «미완» 으로 쓰고 멈춘다
                return 부분, 구멍, 버린까닭, usage, f"조각 {k}: {ex}"
            if 답 is None and resp is not None and 사정 == "agy 아닌 길":
                return 부분, 구멍, 버린까닭, usage, \
                    f"조각 {k}: agy 가 아닌 길로 답이 왔다(route={resp.get('route')} · {resp.get('modelVersion')})"
            if 답 is None:
                버린까닭.append(f"{차}차 {초:.0f}초: {사정}"[:300])
                print(f"  조각 {k}: {차}차 답을 버린다 — {사정}"[:300], flush=True)
                if 다시:
                    다시 -= 1
                    continue
                return 부분, 구멍, 버린까닭, usage, f"조각 {k}({s:.1f}~{e:.1f}초) 두 번 실패 — " + " / ".join(버린까닭)
            usage.append(resp.get("usageMetadata"))
            부분.append({"from": R, "to": L, "답": 답, "잘림": 사정["잘림"], "JSON고침": 사정["JSON고침"], "초": 초,
                       "영상키": 대상키})
            z = 사정["잘림"]
            if not z:
                return 부분, 구멍, 버린까닭, usage, None
            끝 = R + max((u["e"] for u in _시각정리(답, L - R)[0]), default=0.0)
            필터 = z["까닭"].startswith("제미나이 필터")
            if 필터:
                bs, be = 초로(z.get("막힌_s")), 초로(z.get("막힌_e"))
                bs = R + bs if bs is not None and R + bs >= 끝 - 1 else 끝
                be = R + be if be is not None and R + be > bs else bs + 5.0
                R2 = round(min(be + 0.3, L), 1)
            else:                                    # 필터 아닌 끊김 — 건너뛰지 않고 끊긴 자리부터
                R2 = round(min(끝 + 0.1, L), 1)
            if not 나머지 or L - R2 < 5:
                if 필터 or 나머지 == 0:
                    구멍.append({"from": round(s + 끝, 2), "to": round(e, 2), "까닭": z["까닭"], "꼬리": z.get("꼬리", "")})
                return 부분, 구멍, 버린까닭, usage, None
            if 필터:
                구멍.append({"from": round(s + 끝, 2), "to": round(s + R2, 2), "까닭": z["까닭"], "꼬리": z.get("꼬리", "")})
                print(f"  조각 {k}: {z['까닭']} — {s + 끝:.1f}~{s + R2:.1f}초(막힌 대사)를 건너뛰고 나머지를 받는다", flush=True)
            else:
                print(f"  조각 {k}: {z['까닭']} — {s + R2:.1f}초부터 나머지를 받는다", flush=True)
            나머지 -= 1
            R = R2
            try:
                대상, 대상키 = 영상뽑기(src, s + R, e, 조각폴더, f"조각_{k:02d}_나머지", (sha, 방식))
            except 멈춤 as ex:
                return 부분, 구멍, 버린까닭, usage, f"조각 {k}: {ex}"

    받은, 조각정보, 막힌구간 = [], [], []
    멈춘까닭 = None
    with ThreadPoolExecutor(1) as pool:       # 다음 조각 영상은 agy 가 답하는 동안 미리 뽑는다
        미리 = {}

        def 뽑기(k):
            s, e = 표[k - 1]
            t0 = time.time()
            p, 키 = 영상뽑기(src, s, e, 조각폴더, f"조각_{k:02d}", (sha, 방식))
            return p, 키, round(time.time() - t0, 1)

        for k, (s, e) in enumerate(표, 1):
            c = 캐시들[k]
            L = e - s
            if c is None:
                try:
                    mp4, 영상키, 뽑은초 = (미리.pop(k).result() if k in 미리 else 뽑기(k))
                except 멈춤 as ex:
                    멈춘까닭 = f"조각 {k}: {ex}"
                    break
                다음 = next((j for j in range(k + 1, len(표) + 1) if 캐시들[j] is None), None)
                if 다음 and 다음 not in 미리:
                    미리[다음] = pool.submit(뽑기, 다음)

                t0 = time.time()
                부분, 구멍, 버린까닭, usage, 까닭 = 조각_받기(k, s, e, mp4, 영상키)
                if 까닭:
                    멈춘까닭 = 까닭
                    break
                c = {"키": 키들[k], "route": "agy", "modelVersion": f"agy/{a.모델}",
                     "초": round(time.time() - t0, 1), "뽑기초": 뽑은초, "받은때": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "시도": len(부분) + len(버린까닭), "버린까닭": 버린까닭, "usage": usage, "부분": 부분, "막힌구간": 구멍}
                (조각폴더 / f"조각_{k:02d}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
                캐시됨 = False
            else:
                캐시됨 = True
            발화, 장면, 글자, 셈 = _조각_펼치기(c, L, 생김새이름)
            받은.append({"from": s, "to": e, "발화": 발화, "장면": 장면, "화면글자": 글자})
            막힌구간 += [dict(h, 조각=k) for h in c.get("막힌구간", [])]
            조각정보.append({"번호": k, "from": s, "to": e, "초": c["초"], "뽑기초": c.get("뽑기초"), "route": c["route"],
                          "모델": c["modelVersion"], "캐시": 캐시됨, "시도": c.get("시도", 1),
                          "버린까닭": c.get("버린까닭", []), "JSON고침": sum(p.get("JSON고침", 0) for p in c["부분"]),
                          "부분": [[round(s + p["from"], 2), round(s + p["to"], 2)] for p in c["부분"]],
                          "usage": c.get("usage"), "발화수": len(발화), "장면수": len(장면), "화면글자수": len(글자),
                          "시각": 셈})
            걸림 = "캐시" if 캐시됨 else f"{c['초']:.0f}초(뽑기 {c.get('뽑기초')}초)"
            나쁨 = {x: n for x, n in 셈.items() if n}
            고침 = 조각정보[-1]["JSON고침"]
            print(f"  조각 {k}/{len(표)}  {걸림} · 발화 {len(발화)} · 장면 {len(장면)} · 화면글자 {len(글자)}"
                  + (f" · 시도 {c.get('시도')}" if c.get("시도", 1) > 1 else "")
                  + (f" · JSON 괄호 고침 {고침}" if 고침 else "")
                  + (f" · ★막힌구간 {len(c.get('막힌구간', []))}" if c.get("막힌구간") else "")
                  + (f" · 시각 {나쁨}" if 나쁨 else ""), flush=True)
        for f in 미리.values():
            f.cancel()

    발화, 장면, 글자 = _합치기(받은) if 받은 else ([], [], [])
    어긋남, 이음, 이름짝 = _겹침_화자검사(받은)
    for m in 어긋남:                          # 합친 결과에 남은 앞 조각 발화에 표시
        for u in 발화:
            if u["조각"] == m["앞"]["조각"] and abs(u["s"] - m["s"]) < 0.01:
                u["화자_다른조각"] = f"{m['뒤']['화자']}(조각 {m['뒤']['조각']})"
    확인이름 = {k: {u["화자"] for u in c["발화"] if u.get("화자확인") in ("들음", "자막", "생김새")}
              for k, c in enumerate(받은, 1)}
    for x in 장면:
        x["화면인물_미확인"] = [n for n in x["화면인물"] if not 번호꼴.search(n) and n not in 확인이름.get(x["조각"], set())]
    확인셈 = {v: sum(u.get("화자확인") == v for u in 발화) for v in 화자확인값}
    머리 = {"용도": 용도, "도구": "파악전사.py", "엔진": f"agy/{a.모델}", "읽은것": 읽은것,
          "영상조각": f"짧은변 {영상_짧은변} · {영상_FPS}fps · bwdif · 소리 aac 모노(agy_gemini 가 mp3 로 따로 붙임)",
          "소재": str(src), "소재_sha256": sha, "소재_sha256_방식": 방식, "소재_길이": round(전체, 3),
          "구간": [round(A, 3), round(B, 3)], "조각_길이": a.조각, "겹침": a.겹침, "질문판": 질문판,
          "사전": {"낱말": [c for c, _ in 낱말], "인물": [n for n, _ in 인물]},
          "만든때": time.strftime("%Y-%m-%d %H:%M:%S"),
          "화자_주의": "화자 이름은 파악용 짐작이다 — 그대로 나레·자막·인물표에 옮기지 않는다. "
                     "명찰·리본 글자로 붙인 이름은 틀린다(2026-09-26 EPK10: 명찰 조백호를 «오석진», 박재수를 «배홍길»·«박민석» 으로 "
                     "읽었다 — 480p 조각에서 명찰은 글자가 아니라 회색 띠고, 사전 이름 쪽으로 쏠린다). 그래서 질문은 이름을 "
                     "호명·자기소개·방송 자막으로만 붙이게 하고, 도구는 발화마다 «화자확인» 을 조각 안 증거로 다시 매긴다: "
                     "들음(계급+이름 자기소개, 또는 남이 그 이름을 부른 바로 다음 차례에 그 이름표가 대답) · 자막 · 생김새 · "
                     "미확인(증거 없음 — 믿지 말 것) · 번호. «들음» 도 이름과 이름표가 한 자리에서 이어졌다는 것까지이고, "
                     "모델이 조각 안에서 그 이름표를 같은 사람에게만 붙였는지는 모른다. "
                     "남1·여1 은 조각 안에서만 일관된다 — 조각끼리 같은 번호가 같은 사람이라는 보장이 없다. "
                     "겹침 구간에서 두 조각이 같은 말에 다른 이름을 붙인 곳은 «화자_어긋남» 에 모은다(둘 중 하나는 틀림)",
          "화자_확인_셈": 확인셈, "겹침_이름짝": 이름짝, "화자_어긋남": 어긋남,
          "화자_이음": sorted({f"{m['앞']['화자']} = {m['뒤']['화자']}" for m in 이음}),
          "시각_주의": "제미나이 시각 — 중앙 0.2~0.3초·가끔 수 초 어긋난다. 자막 카드·블록 절단·싱크에 쓰지 않는다",
          "조각": 조각정보,
          # 미완 — agy 가 멈췄거나 **필터가 막은 구간이 있으면** true(2026-09-26 재검증: 막힌구간만 있을 때 false 라
          #   «미완» 칸만 보는 도구가 구멍 난 결과를 온전한 것으로 믿을 수 있었다). 어느 쪽인지는 미완_까닭.
          "미완": 멈춘까닭 is not None or bool(막힌구간),
          "미완_까닭": ([f"agy 멈춤 — 받은_끝 뒤는 못 받았다: {멈춘까닭}"] if 멈춘까닭 else [])
                     + ([f"제미나이 필터가 막은 대사 구간 {len(막힌구간)}곳 — 그 자리는 받아쓰지 못했다(다시 돌려도 같다 · "
                         "사람이 본다 · 막힌구간)"] if 막힌구간 else []),
          "받은_끝": 조각정보[-1]["to"] if 조각정보 else A,
          "막힌구간": 막힌구간}
    if 멈춘까닭:
        머리["멈춘까닭"] = 멈춘까닭
    p = _쓰기(접두, 머리, 발화, 장면, 글자, A, B)
    총 = sum(x["초"] for x in 조각정보 if not x["캐시"])
    print(f"\n{'★미완 ' if 머리['미완'] else ''}냄: {p}  (발화 {len(발화)} · 장면 {len(장면)} · 화면글자 {len(글자)} · "
          f"새로 받은 시간 {총:.0f}초)")
    print(f"     {접두}_파악_밀도30s.txt · {접두}_파악_덩이.txt")
    print(f"     화자확인 " + " · ".join(f"{k} {n}" for k, n in 확인셈.items())
          + f" · 겹침 이름 짝 {이름짝}개 중 어긋남 {len(어긋남)} · 이름↔직함 이음 {len(이음)}"
          + (f" ({', '.join(머리['화자_이음'])})" if 이음 else ""))
    for m in 어긋남:
        print(f"     ★겹침 화자 어긋남 {m['s']:.1f}초 «{m['글'][:24]}» — 조각 {m['앞']['조각']} {m['앞']['화자']} ↔ "
              f"조각 {m['뒤']['조각']} {m['뒤']['화자']}", file=sys.stderr)
    if 멈춘까닭:
        print(f"\nagy 막힘 — 사장님 규칙상 EvoLink 로 넘기지 않았다. {멈춘까닭}\n"
              f"확인: python ~/.claude/agy_call.py --usage  (남은 양·로그인) · 같은 명령을 다시 돌리면 받은 조각은 건너뛰고 이어 받는다",
              file=sys.stderr)
        return 2
    if 막힌구간:
        print("\n★제미나이 필터가 막은 대사 구간이 있다(머리 «미완» true) — 그 자리는 받아쓰지 못했다(다시 돌려도 같다). "
              "사람이 직접 본다:\n"
              + "\n".join(f"   {mmss(h['from'])}~{mmss(h['to'])} ({h['from']:.1f}~{h['to']:.1f}초) · {h['까닭']} · "
                          f"끊긴 글 «{h.get('꼬리', '')[:50]}»" for h in 막힌구간), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
