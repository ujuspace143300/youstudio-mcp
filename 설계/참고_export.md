# 참고 — 가족 프리미어 XML 3종 (export 형식 근거)

> 출처: `볼케이노 MCP/프리미어프로용/` — `1_배경이미지+오디오.xml`(74KB) · `2_자막카드.xml`(100KB) · `3_헤드라인.xml`(5KB) · `읽어주세요.txt`(사용 순서·주의). 2026-08-16 읽음. **읽기만 했다.**
> 결론: **FCP XML v5 (`<!DOCTYPE xmeml><xmeml version="5">`)** — 프리미어가 파일 > 가져오기로 읽어 시퀀스를 만드는 교환 형식. prproj 직접 생성(가족 assemble.py 7,856줄)은 하지 않는다는 결정과 맞다. 우리도 같은 계열로 간다.

## 1. 뼈대

```
<xmeml version="5">
  <sequence id="sequence-1">
    <name>…</name>
    <duration>프레임수</duration>
    <rate><timebase>30</timebase><ntsc>TRUE</ntsc></rate>
    <media>
      <video>
        <format><samplecharacteristics><width/><height/><pixelaspectratio>square</pixelaspectratio><rate/></samplecharacteristics></format>
        <track> …clipitem / generatoritem… </track>   ← 트랙 하나 = V1
        <track> … </track>                              ← V2 …
      </video>
      <audio>
        <track> …clipitem(오디오)… </track>              ← A1
        <track> … </track>                              ← A2
      </audio>
    </media>
  </sequence>
</xmeml>
```
- 시간은 전부 **프레임 정수**. `rate` 는 `timebase`(정수) + `ntsc`(TRUE 면 ×1000/1001). 가족은 30/TRUE(=29.97). 우리는 원본 23.976 → **24 + ntsc TRUE**.
- 가족은 시퀀스 3개를 따로 만들어(배경+오디오 / 자막 / 헤드라인) 사용자가 V2·V3 에 시퀀스를 끌어다 놓는 순서를 안내했다(읽어주세요.txt). 우리는 **시퀀스 하나에 트랙을 다 넣는다** — 끌어다 놓을 필요가 없게.

## 2. 영상 클립 (`clipitem`)

```
<clipitem id="v1clip-1">
  <name>표시 이름</name>
  <duration>클립 길이(프레임)</duration>
  <rate>…</rate>
  <start>타임라인 시작 프레임</start><end>타임라인 끝 프레임</end>
  <in>원본 in 프레임</in><out>원본 out 프레임</out>
  <file id="…"><name/><pathurl>file://localhost/C:/…(URL 인코딩)</pathurl><rate/><duration>원본 총 프레임</duration>
    <media><video><samplecharacteristics><width/><height/></samplecharacteristics></video>
           <audio><samplecharacteristics><depth>16</depth><samplerate>44100</samplerate></samplecharacteristics><channelcount>2</channelcount></audio></media>
  </file>
  <filter><effect><name>Basic Motion</name><effectid>basic</effectid>…<parameter><parameterid>scale</parameterid>…</parameter><parameter><parameterid>center</parameterid><value><horiz/><vert/></value></parameter></effect></filter>
</clipitem>
```
- 같은 `file id` 를 여러 clipitem 이 참조할 수 있다(가족은 이미지 하나를 여러 컷에 씀). 우리 컷 43개는 **원본 mp4 하나**를 in/out 만 달리해 참조한다.
- 오디오 clipitem 은 `<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>` 로 원본의 몇 번째 오디오 트랙인지 적는다. 원본 소리를 살릴 컷은 A1 에 같은 in/out 으로 붙인다.
- Basic Motion 의 `center` 는 화면 중앙 기준 픽셀 오프셋(가족 1080×1920 에서 자막 vert 362.5 = 아래쪽). 세로 부호가 프리미어 버전에 따라 반대로 읽힐 수 있다고 읽어주세요.txt 가 경고 — 우리도 첫 임포트에서 확인한다.

## 3. 텍스트 자막 (`generatoritem` Text)

```
<generatoritem id="v2cap-1">
  <name>…</name><duration/><rate/><start/><end/><in>0</in><out>길이</out>
  <effect>
    <name>Text</name><effectid>Text</effectid><effectcategory>Text</effectcategory><effecttype>generator</effecttype><mediatype>video</mediatype>
    <parameter><parameterid>str</parameterid><name>Text</name><value>자막 본문</value></parameter>
    <parameter><parameterid>font</parameterid><name>Font</name><value>S-Core Dream 7 ExtraBold</value></parameter>   ← 프리미어가 보여주는 폰트 이름
    <parameter><parameterid>fontsize</parameterid><name>Size</name><value>102</value></parameter>
    <parameter><parameterid>alignment</parameterid><name>Alignment</name><value>center</value></parameter>
    <parameter><parameterid>fillcolor</parameterid><name>Color</name><value><alpha>255</alpha><red>255</red><green>255</green><blue>255</blue></value></parameter>
  </effect>
  <filter> Basic Motion(scale·center) </filter>   ← 화면 위치
</generatoritem>
```
- 장점(읽어주세요.txt 1번): 프리미어에서 **더블클릭해 바로 고칠 수 있는 텍스트**가 된다(이미지 굽기 아님). 우리 자막도 전부 이 방식.
- 폰트는 이름으로만 지정된다 → 산돌구름이 켜져 있으면 이름으로 잡힌다(외부서비스.md 「내 환경」). 못 잡으면 Effect Controls 에서 직접 고르라는 안내가 붙어 있다.
- 줄바꿈: 두 줄짜리는 프리미어 버전에 따라 한 줄로 붙을 수 있다고 경고 → 우리는 큐를 **한 줄**로만 만든다(subtitle 이 이미 18/29자로 나눠 둠).

## 4. 우리 export 가 가져가는 것 / 다르게 하는 것

| 항목 | 가족 | 우리 |
| :---- | :---- | :---- |
| 형식 | FCP XML v5 | 같음 |
| 시퀀스 | 3개(끌어다 놓기) | **1개**에 V1 원본컷 · V2 대사 자막 · V3 나레 자막 · A1 원본 소리 · A2 나레이션 |
| 프레임레이트 | 30 ntsc | 원본 따라 24 ntsc(23.976) |
| 화면 | 1080×1920 세로 | 1920×1080 가로 |
| 영상 소재 | 이미지 컷 + Motion 키프레임 | 원본 mp4 in/out 참조(Motion 없음) |
| 자막 | Text 제너레이터 | 같음. 폰트는 규격 「자막.폰트」(나레 본명조 · 대사 광화문) |
| 오디오 | narr.wav 한 개 + sfx_bed | 나레이션 **믹스다운 wav 한 개**(A2, 블록 wav 를 실측 t0 에 놓아 ffmpeg 로 합침) + 원본 소리(A1, 컷별) |
| 덕킹 | — | 연장·브리지 컷의 원본 소리는 Audio Levels 로 낮춤(규격 「조립.덕킹_레벨」) — 프리미어가 안 읽으면 수동 |
| 별도 파일 | subtitle.srt | subtitle.srt(합본) · _nar · _dlg · manifest.json |

## 5. 첫 임포트 실측 (2026-08-16, Full Time `render/Full_Time_2023.xml`, 사용자 프리미어)

| 항목 | 예상 | 실측 |
| :---- | :---- | :---- |
| 세로 위치 부호 | 뒤집힐 수 있음(가족 경고) | **① 자막이 화면 상단에 위치** — 부호 문제로 추정 |
| 폰트 이름 자동 인식 | 이름으로 잡힘(산돌구름 켜짐) | **② 폰트가 하나도 적용 안 됨** (본명조·광화문 둘 다) |
| 나레·대사 싱크 | 실측 타이밍 그대로 | **③ 나레·대사 싱크 어긋남 + 나레가 배우 대사와 겹치는 곳** |
| Audio Levels 덕킹 | 안 읽힐 수 있음 | 미확인 |
| 23.976 시퀀스 | 24 ntsc TRUE | 미확인 |

진단·수리는 이 문서 6절과 커밋 이력. 원인을 특정하기 전엔 고치지 않는다.

## 6. 첫 임포트 진단 (2026-08-16 — 고치기 전 원인 특정)

### ① 자막 상단 — 좌표계·부호
- 가족 XML(1080×1920) center 값: 자막 `vert 362.5~410.5`(양수, 아래쪽 자막), 헤드라인 `-575/-693`(음수, 맨 위), 사진 컷 `-98`(중앙 위). → 가족 프리미어에서 **단위 = 픽셀, 양수 = 아래**. 우리 XML: 나레 `+300`, 대사 `+440`(같은 규약). 사용자 프리미어에서는 상단에 뜸 → **이 프리미어는 세로 부호가 반대(양수 = 위)** — 가족 읽어주세요.txt 가 경고한 "버전에 따라 반대" 케이스. 단위(픽셀)까지 다르면 화면 밖으로 나가야 하는데 보였으므로 부호만.
- 확정은 `render/_import_test.xml`(vert +300 / −300 / 0 라벨)로.

### ② 폰트 미적용 — 이름 표기
- generatoritem 구조는 가족과 **바이트 수준 동일**(태그·순서·인코딩 UTF-8, 가족은 CRLF 우리는 LF — 무관). 차이는 `font` 값 문자열뿐.
- 가족 값 `S-Core Dream 7 ExtraBold` = 그 폰트의 name 테이블 **ID1(family) = ID4(full name)** (둘이 같음). 우리 값: 본명조 = `Source Han Serif K`(ID1 family) — 이 폰트의 full name 은 `Source Han Serif K Bold`, PS `SourceHanSerifK-Bold`, 한글 full name `본명조 Bold` / 광화문 = `Sandoll Gwanghwamun`(ID1 = full name, PS `SDGwanghwamun`, 한글 `Sandoll 광화문`).
- 광화문은 family = full name 인데도 안 잡혔다 → "full name 만 필요"로는 설명이 안 된다. 남는 가설: 프리미어가 **PostScript 명**을 요구하거나, 한국어 로캘에서 **한글 이름**(`Sandoll 광화문`·`본명조 Bold`)으로 폰트를 등록해 영문 이름을 못 찾는다. → `_import_test.xml` 의 8종 라벨(영문 full/한글 full/PS/family × 2폰트)로 어느 표기가 잡히는지 확정한 뒤 규격 「자막.폰트」에 그 표기를 쓴다.
- 산돌구름 폰트 파일 위치 확인: `%APPDATA%\Roaming\Program\Common\<해시>\…`(확장자 없는 OTF, WPF/GDI 가 읽음). Source Han Serif K 도 산돌구름 경유.

### ③ 나레·대사 싱크 / 겹침
- **프레임 계산 감사(2d)**: XML 의 rate 태그 전부 `24 + ntsc TRUE`(23.976), V1 컷 43개 start/end/in 이 timeline.json×23.976 과 **43/43 일치**, 반올림 오차 최대 0.019s, 시퀀스 길이 13,603f = 567.358s(총장 567.35). 24.0 혼입 없음. (프리미어가 24 ntsc 를 24.0 으로 잡아도 영상·나레·자막이 모두 프레임 기준이라 상대 싱크는 유지, 절대 시각만 끝에서 0.57s.)
- **데이터 안 겹침(2c-1)**: 나레 [t0,t1] vs 대사 큐 12.2s(11블록, 대부분 대사 큐 꼬리 1.0s 와의 겹침 + 훅 블록1 3.7s).
- **오디오 실측(원본 소리, 200~3500Hz, −32dB)**: 나레 113.3s 중 47.6s 밑에 소리가 있다. 시각몽타주 위(음악·현장음, 정상)를 빼면 **말과 부딪히는 자리 5곳** — n01 훅(구간1 첫 대사 위, 2.7s) · **n03(연장 컷 72.8~75.9 + 구간2 머리, 3.1s — 연장 컷의 원본 대사)** · n04(연장 134.8~139.3, 3.3s) · **n12·n13(구간8 머리 "Hey!" 추격, 3.5s·1.8s)** · n14(1.2s).
- **늘어난발화 규칙 = 추정 절단 → 실측 위반 확인**: 잘린 10건의 꼬리에 실제 소리가 있었다 — `Hey!` 376.4→397.4 를 378.4 로 잘랐는데 꼬리 19s 중 **5.8s 가 실제 소리(추격 중 외침)** → 그 위에 나레 12·13 이 놓였고 무음 컷도 9.5s 를 잘라 냈다. `No fucking way.` 꼬리 21s 중 15.3s 소리(대기 장면 — 말인지 현장음인지 이 방법으론 못 가름), 엔딩곡 가사 3건(미선택 구간). 단어 수 상한은 **예측**이었다 — 발화 끝은 오디오에서 재야 한다.
- **덕킹 미적용 가능성**: 연장·브리지 컷의 원본 소리는 XML `Audio Levels 0.25` 에 맡겼는데 프리미어가 이 필터를 안 읽으면 **원본 대사가 전 볼륨으로 나레와 겹친다**(n03·n04 가 그 자리). 실측 소리 3.1s/3.3s 가 그 증거와 일치.
- 큐 시작 vs 실제 발화 시작 편차는 이번 방법(silencedetect 창)으론 확정 못 함(대화가 연속이라 창 시작이 이미 소리) — 사용자가 "어느 줄이 몇 초 빠르다/늦다" 한 예를 주면 그 줄만 정밀 측정.

### 수리 계획 (사용자 확인 뒤)
| 증상 | 원인 | 고칠 곳 |
| :---- | :---- | :---- |
| ① 상단 | 세로 부호 반대 | 규격 「자막.위치_center」에 `세로부호` 스위치(−1) 또는 값 −300/−440 → export.ts 는 규격만 읽음. `_import_test.xml` 결과로 확정 |
| ② 폰트 | 이름 표기(PS 명 또는 한글 full name 유력) | `_import_test.xml` 로 어느 표기가 잡히는지 확인 → 규격 「자막.폰트」의 XML용 이름 필드(`xml명`) 추가 → export.ts 가 그 필드를 씀 |
| ③-a 나레가 원본 대사와 겹침(연장·브리지 컷) | 덕킹을 프리미어 필터에 맡김 | export.ts: A1 의 덕킹 컷을 **아예 A1 에서 빼고**(원본 소리 없음) 필요하면 A3 에 낮은 볼륨 사본 — 프리미어 필터 의존 제거. 규격 「조립.덕킹_레벨」→ `덕킹_방식: 무음|필터` |
| ③-b 나레가 실제 말 위(구간8 "Hey!" 등) | 늘어난발화 규칙이 추정으로 끝을 잘랐고 무음 컷·틈 배치가 그 위에 얹힘 | transcript.ts: 단어 수 상한 대신 **오디오 실측**(runner 가 `silencedetect` 로 발화 끝 뒤 첫 무음 시작을 재서 measure 로 돌려줌 — 규칙을 "무음 시작까지"로) · subtitle.ts 의 무음 컷·틈 계산도 같은 실측 발화 끝을 쓴다 |
| ③-c 훅 블록1 | 구간1 이 0.0s 대사로 시작해 틈이 없음 | select/subtitle: 훅 앞에 무대사 컷(원본 0 앞은 없으므로 시각몽타주 짧은 컷 또는 seg1 앞 확장 불가) → script 위치를 bridge0 로 옮기거나 hook 을 seg1 첫 틈(12~26s) 이후로. 결정 필요 |
| (확인) 24 ntsc | 프리미어가 23.976 로 잡았는지 | 시퀀스 설정 화면 확인 요청 |

### 6-1. `_import_test.xml` 실측 (2026-08-16)
- 폰트 경고창 "확인할 수 없음(기본 글꼴로 대체됨)" 4건: `Sandoll`+깨진 한글(=B2 `Sandoll 광화문`) · 깨진 한글+`Bold`(=A2 `본명조 Bold`) · `SourceHanSerifK K`(=A4 `Source Han Serif K`) · `SourceHanSerifKBoldold`(=A1 `Source Han Serif K Bold`). **한글 폰트 이름은 파라미터 인코딩에서 깨져 탈락 확정**(본문 한글은 정상 렌더). 공백 있는 영문 이름은 공백을 뭉개 찾다 실패한 흔적.
- **생존(경고 없음)**: A3 `SourceHanSerifK-Bold`(PS) · B1 `Sandoll Gwanghwamun` · B3 `SDGwanghwamun`(PS) · B4 `Sandoll Gwanghwamun TTF`. 실제 렌더 확인은 `_import_test2.xml`(라벨을 시간순으로 하나씩).
- 0:02 에 "A1 …" 라벨이 얇은 고딕(대체)으로 화면 위에 하나만 보임 — 세로 부호 반전으로 8줄이 밖으로 나가거나 겹친 결과.
- **vert=+300 라벨이 화면 위 → 세로 부호 반대 확정** → 규격 「자막.위치_center.세로부호」 = −1.
- **시퀀스 23.976 프레임/초 확정**(스크린샷).

### 6-1b. `_import_test3.xml` 결과 + 시험 5 (2026-08-16)
- **시험3**: FCP7 Text 제너레이터의 `origin` 파라미터(비율)가 **실제로 텍스트를 움직인다** — T1(origin vert 0.3)이 화면 **중하단**으로 이동. (T2~T7 세부는 미보고.) → 자막 위치 자동화의 통로 확보. 단, 0.3 이 "위에서 30%"라면 상단이어야 하므로 origin 은 **화면 중앙 기준 오프셋**(y = 540 + v×1080 또는 540 + v×540)일 가능성이 크다 — 볼케이노 prproj 의 Position(0.5:0.956 등, 위 기준 0~1)과 같은 좌표계라고 **가정하지 않고 잰다**.
- **시험5** `render/_import_test5.xml`: 원본 컷 1개 위에 라벨 6개, 5초씩 순서대로(겹침 없음). origin y 사다리 **0.70 / 0.78 / 0.84(나레 폰트 SourceHanSerifK-Bold 96px) · 0.88 / 0.92 / 0.96(대사 폰트 SDGwanghwamun 52px)**, 문구에 자기 값("y=0.84 (나레 폰트) ← 이 값이 나레이션 자리(840px)인가"). 목표: 1920×1080 에서 **나레 y≈840 · 대사 y≈980** 에 해당하는 origin 값. 이 사다리는 "위 기준 0~1" 가설용 — 중앙 기준이면 전부 화면 밖일 수 있어 보조 사다리 `_import_test5b.xml`(0.28 / 0.34 / 0.41 / 0.56 / 0.68 / 0.82, 같은 폰트 배치)을 함께 둔다. 둘 다 새 빈 프로젝트에서 임포트. 판독: 각 라벨이 화면 어디에 보이는지(안 보이면 "안 보임") — 그 값으로 규격 「자막.위치_center」를 origin 값으로 바꾸고 export 가 `origin` 파라미터를 쓰도록 고친다(코드는 결과 뒤).

**시험5/5b 실측 (2026-08-16)**: 시험5(위 기준 0~1 가설, 0.70~0.96) — **전부 화면 아래로 벗어남**(글자 윗부분만 하단에 살짝 걸림) → 가설 기각. 시험5b(중앙 기준, 0.28~0.82) — **0:11 의 세 번째 라벨(y=0.41)이 실제 대사 자막 자리와 가장 흡사**(사용자 확인).
**좌표 모델(확정)**: origin y 는 **화면 중앙 기준 × 높이 오프셋 — 화면픽셀 = 540 + v × 1080**. 대사 980px → v = 0.4074(실측 0.41 과 일치) · 나레 840px → v = 0.2778. 볼케이노 prproj 의 Position(위 기준 0~1)과는 다른 좌표계 — 변환: origin_y = Position_y − 0.5.
**수출 방식 갈림길 — 결정**: **A안(FCP XML) 확정** — origin 보정으로 자막 위치 자동화가 증명됐다. prproj 직접 생성(9-5(b))은 **2차 과제로 보관**(런·모션·ms 컷이 필요해질 때). 반영: 규격 「자막.위치」(origin 체계, 산출 공식 병기) · export 가 Text 제너레이터에 `origin` 파라미터를 쓰고 Basic Motion center 는 병기 · 확인용 `render/_import_test6.xml`(원본 컷 1개 + 최종값 라벨 2개: 나레 폰트 0.2778 "이게 나레이션 자리면 성공" · 대사 폰트 0.4074 "이게 대사 자리면 성공") · 본편 재생성.

### 6-2. 수리 반영 (2026-08-16, 커밋 참조)
| 증상 | 수리 | 어디 |
| :---- | :---- | :---- |
| ① 상단 | 규격 「자막.위치_center.세로부호」= −1 → export 가 vert 에 곱함 (나레 −300 · 대사 −440) | 규격.json · export.ts |
| ② 폰트 | 규격 「자막.폰트.*.xml명」 신설, 우선 PS 명(`SourceHanSerifK-Bold` · `SDGwanghwamun`) — 렌더 확정은 `_import_test2.xml`(생존 4종 4초씩 + 부호 확인 줄) | 규격.json · export.ts |
| ③-a 덕킹 | 규격 「조립.덕킹_방식」= 별도트랙: A1 = 살릴 컷만, **A3 = 연장·브리지 컷의 원본 소리**(Audio Levels 첨부, 안 읽히면 A3 음소거/볼륨) | export.ts |
| ③-b 늘어난 발화 | transcript ① 에 `silence_scan`(ffmpeg silencedetect, 규격 「전사.무음스캔」 −24dB·0.4s, stderr 측정) → ② 는 발화 끝을 **꼬리 무음을 벗긴 마지막 소리의 끝**으로(추정 절단 폐기), transcript.json 에 `silences` 기록 | transcript.ts · 규격 |
| ③-b 배치·컷 | subtitle: 나레 틈 = 정상 길이 발화 ∪ **실측 소리** 없는 자리(수상하게 긴 세그먼트의 시각은 안 믿음) · 자리 없으면 실측 소리와 가장 덜 겹치는 위치 · 무음 컷은 발화·나레·**지속 ≥1.5s 소리**만 보호(현장음 스웰은 잘라도 됨) | subtitle.ts · 규격 「조립.죽은시간_컷.보호_소리_최소_s」 |
| ③-c 연장 컷 | before/after 가 붙어 있는 이웃 구간이 있으면 화면을 늘리지 않고 그 구간의 틈(over)으로 이동 · 늘려야 하면 앞/뒤 30s 안에서 **실측 소리가 가장 적은 창**을 고른다 (같은 장면 중복·대사 위 겹침 제거 → G16 재사용 0) | subtitle.ts |
| 결과 | Full Time 재출력: 총 553.4s · 컷 46 · 큐 194 · 죽은 시간 8.4% · 재사용 0 · 나레 밑 실측 소리 남은 곳 = 훅 n01(자리 없음)·브리지0 n02·연장 n03 → 전부 A3(덕킹 트랙) 위 | render/ |

### 6-3. `_import_test2.xml` 실측 + 자동저장 prproj 증거 (2026-08-16)
**폰트 — 확정.** 1/5 `SourceHanSerifK-Bold` 굵은 명조 렌더 성공 · 2/5 `SDGwanghwamun` 경고 없이 광화문체 렌더 성공 · 3/5 `Sandoll Gwanghwamun`·4/5 `… TTF`·5/5 `Source Han Serif K` 경고(실패). → **XML 의 font 값은 PostScript 명만 통한다.** 공백 있는 이름은 뭉개지고(경고창의 `SourceHanSerifK K`·`SourceHanSerifKBoldold`), 한글 이름은 인코딩에서 깨진다. 폰트 선택은 가족 체계(본명조·광화문) 그대로이고 XML 표기만 시스템 PS 명 — 규격 「자막.폰트.*.xml명」 확정.

**위치 — 부호가 아니라 "전달 안 됨".** 시험2 라벨(vert −300·−440)도 화면 위쪽. 사용자 프리미어의 자동 저장본(`Desktop/Adobe Premiere Pro Auto-Save/유스튜디오 MCP 첫 테스트--…02-34-01`(시험1)·`…08-24-49`(시험2), gzip XML, 읽기만)을 풀어 보면:
- 임포트된 항목은 전부 `AE.ADBE Text` 그래픽(텍스트 레이어)이고, 텍스트 레이어 `위치` 키프레임이 **17개 모두 `0.0390625:0.15625`**(화면 비율 좌표 = 가로 3.9%·세로 15.6%, 왼쪽 위). XML 의 vert(+420 ~ −440)와 무관하게 같은 값. Basic Motion 에서 온 「모션」 파라미터는 없음.
- 즉 **프리미어 2026(v45) 은 Text 제너레이터의 Basic Motion `center` 를 버리고 텍스트 레이어를 고정 기본 위치에 놓는다.** 시험1 의 "양수 = 위" 판정은 라벨 8개+3개가 한 트랙에 같은 시간으로 겹쳐 첫 항목만 살아남은 상태에서 읽은 **오독** → 규격 「세로부호」 −1 철회, FCP7 규약대로 +1(픽셀·양수 = 아래) 복귀. XML 에는 값이 그대로 남으므로 이 값을 읽는 프로그램(가족 프리미어가 그랬는지는 미확인)에서는 유효.
- 수리: XML 로는 자막 위치를 지정할 수 없으므로 **export manifest 에 `프리미어_후속`**(트랙별 다중 선택 → Essential Graphics 정렬 및 변형, 위치 px = 폭/2+horiz · 높이/2+vert, 정렬·폰트·크기)을 내려보내고 README 순서에 넣는다. 자동화 재시도는 `_import_test3.xml`(FCP7 Text 제너레이터의 `origin` 파라미터 비율/픽셀·`fontalign`·Basic Motion 재시험, 4초씩 7개, 겹침 없음) — 어느 라벨이 움직이면 그 파라미터를 export 에 넣는다.

## 7. 해석 정정 — "구글 순정 = 큰 클립 전달용" 은 오독이었다 (2026-08-16)

- **기존 기록**(2026-08-15, `참고_runner.md` 우리 실측 2 · `단계상세.md` 미정 표 · `외부서비스.md` Google 행 · 규격 「판정.영상」 안내): "EvoLink 도 inline_data 로 영상을 받으니 Files API 는 인라인 상한(≈20MB)을 넘는 **큰 클립**에만 필요하다 → 기본 evolink 인라인, 구글 순정은 스위치."
- **진짜 의미**(가족 강제 규칙, `가족인터뷰.md`): 구글 순정이 필요한 이유는 클립 크기가 아니라 **영화 전체가 Files API 로 제미나이에 가서 멀티모달이 통째로 보는 것**이 검증된 프로세스의 핵심이기 때문이다. 우리 brief(전사 텍스트만)·select(무음 구간 프레임 샘플 + 결말 클립 15s)는 **이 기준에 못 미치는 폴백**이다.
- **정정 사유**: 가족의 "구글 순정 필수" 지시를 EvoLink 인라인 실측(15s·0.45MB 클립이 소리까지 읽힘)으로 대체할 수 있다고 내가 좁게 읽었다. 실측 자체는 맞지만(EvoLink 인라인 동작) 그것으로 "전체를 본다"가 충족되지 않는다. 15s 클립 하나가 읽힌 것과 15분 영화 전체를 한 문맥에서 보는 것은 다른 일이다.
- **처리**: 기존 기록은 지우지 않고 각 자리에 "정정 2026-08-16 → 참고_export.md 7절" 을 붙였다. 새 단계 설계안은 `장면이해_설계안.md`, 구현은 보고 뒤 결정.

## 8. 오디오 트랙 미생성 — 진단·판정 (2026-08-16)

- **증상**: `render/Full_Time_2023.xml` 임포트 시 오디오 트랙(A1/A2/A3)이 아예 안 생기고 비디오만 들어옴.
- **진단 과정 요약**: ① XML 오디오 구조 검사 — 트랙 3개(A1 36 · A2 27 · A3 10), `<file id="src-file"/>` 참조·nar wav 전체 정의(24000/mono/16bit, 27개 파일 존재·길이 일치), 겹침 0·길이 일치·파서 정상 → 결함 없음. ② 첫 임포트(02:12 자동저장)와 대조 — 그때 오디오는 들어왔고(AudioClipTrackItem 70 = A1 43 + A2 27), 코드 diff 상 오디오 차이는 A1 틈·A3 추가뿐. 시험 XML 1~3 은 `<audio>` 가 비어 있어 대조군이 아니었음. ③ 가족 XML 은 클립마다 전체 `<file>` 정의(wav)라는 점만 다름. ④ 이분법 시험 `_import_test4a`(현 구조 축소)·`4b`(옛 구조 축소) 둘 다 **오디오 트랙 생성 O·소리 O**, 본편을 **새 빈 프로젝트**에 임포트 → V1~V3·A1~A3 전부 정상.
- **확정 원인**: 프리미어 쪽 상태 — **같은 소재가 이미 있는 프로젝트에 재임포트하면 오디오 트랙이 조용히 누락된다.** XML 은 무죄, 수리 불필요.
- **운영 규칙**: **XML 임포트는 항상 새 빈 프로젝트에서 한다.** export ② 안내문·서버 README 임포트 순서에 같은 문장을 넣었다.
- 시험 파일: `render/_import_test4a.xml`·`4b.xml` 은 재현용으로 보관, `4c~e` 는 쓸 일이 없어져 삭제(2026-08-16).

## 9. 가족(볼케이노) 완성 prproj 분석 — 같은 원본 Full Time (2026-08-16, 읽기 전용)

파일: `Desktop/가족전달/Full_Time_롱폼_v26_b05.prproj`(gzip → PremiereData v3, 프로젝트 Version 45, 3.7MB) + `media/`(source mp4 · tts wav 39 · sfx wav 12) + `.audio_peak.json` 사이드카. 원본 미수정 — 임시 폴더에 복사해 풀었다. 수치는 `벤치마크/볼케이노_FullTime_실측.json`.

### 9-1. 트랙 구성 (XML 안 표현)
- 시퀀스 1개 `Full_Time_롱폼_v26`(UID `1a30025c-…`), TrackGroups 3: Video(5트랙)·Audio(3트랙)·Data(캡션 1트랙). 트랙은 `VideoClipTrack`/`AudioClipTrack` 오브젝트(ObjectUID) 안 `ClipItems > TrackItems > TrackItem ObjectRef` 목록. 트랙 아이템 = `VideoClipTrackItem`(Start/End 틱, TPS 254016000000) → `SubClip`(이름) → `VideoClip`(InPoint/OutPoint) → `VideoMediaSource` → `Media`(FilePath) 사슬. 오디오는 같은 사슬의 Audio 판.
- **V1** 원본 컷 134 (전부 mp4, 틈 0, 재사용 0) · **V2** 대사 자막 79 · **V3** 나레 자막 34 · **V4** 나레 강조 자막 23 + Cross Dissolve 1(첫 클립 페이드인) · **V5** 빈 트랙 · **A1** 원본 소리 134 + Constant Power 크로스페이드 130(전부 0.167s = 4프레임) · **A2** 나레 wav 39 + 페이드 78 · **A3** 효과음 12 + 페이드 24 · **캡션 트랙** 1개(ID 354) **비어 있음**. V1↔A1 은 `Link` 134 로 묶임.
- 레벨: A1 기본 **−15 dB**(0.1778) · 덕킹 컷 46개 **−30 dB**(0.0317, 총 89.9s) · A2 나레 −15 dB · A3 효과음 −29~−20.5 dB(사이드카 `audio_peak.json` = LUFS −23 목표 자동 게인 결과).

### 9-2. 자막 방식
- **캡션 트랙이 아니라 텍스트 그래픽 클립**(`AE.ADBE Text` VideoFilterComponent, 파라미터 22개: Source Text(FlatBuffers 블롭)·Transform·**Position**·Scale·Rotation·Opacity·Anchor Point…). 그래픽 미디어는 Premiere 합성 소스(`Graphic`, In=3600s 고정 = GRAPHIC_IN_TICKS).
- **위치는 Text 컴포넌트의 `Position` 파라미터, 정규화 좌표(0~1)**: V2 대사 `0.5:0.95556` · V3 나레 `0.5:0.96481` · V4 강조 `0.5:0.92778` — 트랙마다 **한 값으로 고정**(79/34/23 전부 동일). 우리 임포트에서 프리미어가 박아 넣던 `0.039:0.156` 과 같은 자리·같은 단위 → **자막 위치는 이 파라미터를 써야만 자동화된다**(FCP XML 의 Basic Motion 으로는 못 닿음, 6-3절).
- **폰트는 블롭 안 PostScript 명**: 대사 `SDGwanghwamun`, 나레 기본 `SourceHanSerifK-Bold`, 톤 폰트 `SDAchim-bMd`·`SDSeongkyeong-bMd`·`SDKwangya`·`SDGdMyeongjo`·`SDCharisma-bBd`·`SDBangkakbon-cBd`·`SDComicStencil-aBasic`·`SDNemony2dBasicBd`. 블롭마다 `Cafe24Dangdanghae` 가 함께 들어 있음(도너 템플릿 블롭의 기본 폰트 + 실제 폰트 런). 우리 규격 「자막.폰트」의 PS 명 선택(본명조 Bold·광화문)과 일치.
- 파라미터 이름이 영어(`Source Text`, `Position`) — 사용자 프리미어(한국어 UI)가 저장한 파일은 한국어(`소스 텍스트`, `위치`). 즉 이 파일은 사용자 PC 의 프리미어가 저장한 것이 아니다.

### 9-3. 나레이션 wav 참조
- 클립마다 `Media` 오브젝트(FilePath/ActualMediaFilePath = **절대 Windows 경로 `C:\Users\user\Desktop\가족전달\media\tts\nNNN.wav`** — 받는 PC 기준으로 미리 써 둠), `MasterClip` + `ClipProjectItem`(프로젝트 패널 항목) + `AudioMediaSource`/`AudioStream`. 파일명 `n<컷번호 3자리>.wav`(컷 134개 중 39곳). A2 아이템 ObjectID 간격 18 로 일정.

### 9-4. 제작 방식 증거 (단정 없이 목록)
**(a) 프로그램 생성 흔적** — 강함
- ObjectID 간격 일정: V1 아이템 +4(133/133), A2 +18(38/38); 컷 시작/끝 중 50개가 **프레임 비정렬**(ms 단위 — 프리미어 손 편집은 항상 프레임에 붙는다) · 페이드 232개 전부 0.167s · 레벨이 정확히 −15/−30 dB · 트랙마다 위치 한 값 · nar 파일명이 컷 번호 · 미디어 경로가 받는 PC 경로 · 블롭이 같은 템플릿(Cafe24 기본 폰트) 위에 폰트만 치환 · 사이드카 `_meta.stage: audio_spec`, `prproj: …\longformmovie_이관\pipeline\build\fulltime\…b05.prproj` = **참고 폴더의 가족 파이프라인이 이 PC 에서 04:05 에 빌드**(`pipeline/build/fulltime/` 에 b02~b05 있음), 이름 `v26_b05`(빌드 5).
- 참고 폴더 `longformmovie_이관/pipeline/stages/assemble.py`(7,856줄)·`assemble_full.py`·`specs/textblob.py`(미니 FlatBuffers 리더/빌더, GT 블롭 724B md5)·`builders/timeline_builder.py`(4,708줄) 가 바로 그 빌더다(읽기만 함).
**(b) 도너 복제 흔적** — 강함
- `assets/donor/real-edited-2026-v45-25fps.prproj`(65KB, "real-edited" = 사람이 편집한 실물 프로젝트) 를 뼈대로 쓴다고 assemble.py 도큐스트링·`DONOR` 표(seq_uid `1a30025c-…` = 이 파일의 시퀀스 UID, 트랙 UID 8개, mp4/mp3 lineage ObjectID, 타이틀 도너 서브트리 123)가 명시. "도너 타이틀 클립 서브트리 복제 → ObjectID/Ref 재배선 → 블롭 치환 → gzip 재직렬화".
- 잔재: 빈 V5 · 캡션 트랙(ID 354, 비어 있음) + 고아 `CaptionDataClipTrackItem` 18 · `TranscriptClip` 37 + `SyntheticTranscript`(프리미어 음성 텍스트 변환 잔재) · 고아 V1 아이템 9개(114~122, Full Time 훅 컷에 **Horizontal Flip + Motion**) · `Cutback-<uuid>`·`Color Matte` 프로젝트 항목 · 빈 확장 상태 313개 · 트랙 ID 1,7,8,9,19 / 3,4,24 / 354, NextTrackID 20/25, NextAutoNestedSequenceNumber 24 · 프리뷰 프리셋 1080×1920(세로) · 내보내기 경로 `/Volumes/DATA/렌더링/#렌더.mp4`, Ingest 프리셋 `/Applications/Adobe Premiere Pro 2025.app/…`(**Mac Premiere 2025, 영어 UI** 에서 온 도너).
**(c) 사람 수동 편집 흔적** — 약함
- 원본 순서를 거스르는 컷 4개, 첫 클립 Cross Dissolve 1개, 효과음 레벨 제각각 — 전부 프로그램 규칙으로도 설명됨. 프리미어 손 편집의 전형(비정형 값·수동 키프레임·프레임 스냅된 불규칙 길이·최근 저장 프리미어 버전 흔적)은 없음. 도너 자체(real-edited)만 사람 편집물.

### 9-5. 판단 근거
**(a) 우리 FCP XML 방식으로 동급 도달 가능한가**
| 항목 | FCP XML(지금) | 판정 |
| :---- | :---- | :---- |
| 원본 컷 V1 134·틈 0·A1 링크 | 됨(clipitem, 프레임 단위 — 가족은 ms 단위) | ○ |
| A1 기본 −15 dB·덕킹 −30 dB | Audio Levels 필터는 프리미어가 안 읽는 것으로 관측(6절) → 우리는 A3 분리 | △ (레벨 자동 X, 트랙 분리로 대체) |
| 크로스페이드 0.167s 232개 | FCP XML `<transitionitem>` 오디오 크로스페이드 — 프리미어 임포트 지원 **미확인** | ? (시험 필요) |
| 나레 A2·효과음 A3 | 됨 | ○ |
| 자막 텍스트·폰트(PS 명) | 됨(6-3 확정) | ○ |
| **자막 위치(트랙별 정규화 Position)** | **안 됨** — 프리미어가 center 를 버림 → 수동 1회/트랙 | ✕ |
| 자막 한 큐 안 폰트/크기/색 런(스팬) | 안 됨(제너레이터 1폰트) | ✕ |
| 등장 모션 프리셋(키프레임) | 안 됨 | ✕ |
| 캡션 트랙 | 안 됨(가족도 안 씀) | — |
결론: **컷·소리·나레·폰트는 동급, 자막 위치·런·모션은 못 닿음.** 지금 방식 = FCP XML + 트랙별 위치 1회 수동이 최단.
**(b) prproj 직접 생성/바꿔치기의 현실성**
- 가족이 실제로 그 길을 갔고 코드가 참고 폴더에 있다(읽기만): 조립 7.9k + 풀버전 1.8k + 타임라인 4.7k + 블롭 0.9k 줄, 도너 UID/ObjectID 표, FlatBuffers 블롭 패치, ObjectID 재배선, 미디어 오프라인 수리 지식(FilePath 절대경로·ImporterPrefs·FileKey), 게이트 96개. **작업량 추정: 우리가 새로 쓰면 최소 수 주** — 도너 확보(사용자 프리미어 26.3.2 로 실물 편집 1회) + 서브트리 복제·재배선 + 블롭 패치(가장 위험) + 임포트 검증 루프. 자막 위치 하나 때문에 갈 길은 아니다. **중간 길**: 자막만 prproj 로(도너 타이틀 1개 복제) + 나머지 FCP XML — 두 파일을 사람이 합쳐야 해서 지금의 "1회 수동 위치"보다 낫지 않다. 3차 시험(`_import_test3.xml` origin 파라미터) 결과가 오면 최종 판단.
**(c) 미확인 → `가족인터뷰.md` Q1 밑에 추가.**

## 10. 수출 방식 갈림길 — 최종 결정 (2026-08-17)

- **임포트 확인 완료 (v0.6-import)**: `_import_test6.xml` + 본편 `Full_Time_2023.xml` 을 새 빈 프로젝트에 임포트 → 자막이 **대략 제자리**(위치 정밀도는 "비슷한 수준", 완벽하진 않음), 오디오·컷·트랙 정상. FCP XML 경로는 검증 완료.
- **사용자 최종 결정**: 산출물은 XML 임포트가 아니라 **"프리미어 파일(.prproj)을 열면 모든 소스가 전부 제자리에 올라와 있는" 형태** — 볼케이노와 같은 방식.
- **갈림길 기록 갱신**: 6-1b 의 "A안(FCP XML) 확정"을 **본선 = prproj 생성**으로 바꾼다. FCP XML 수출은 **폴백·검증 발판으로 유지**(버리지 않는다 — export 스위치, 자막만 폴백 등 계단마다 되돌아갈 지점). 이유: origin 보정은 "대략 제자리"까지이고, 위치·서식의 정밀은 사람이 프리미어에서 잡은 견본(도너)을 그대로 복제할 때만 보장된다(9-2 가족 방식). 가족 인터뷰 Q1 답("기존에 쓰던 프리미어 파일을 던져주고 구현") = 도너 복제·치환의 실체(`가족인터뷰.md`).
- **이행 계획**: `prproj생성_설계안.md` — 계단 0 학습(매핑 표) → 1 우리 도너(사용자 프리미어 26.3.2·23.976·견본 자막) → 2 gzip 왕복 → 3 치환 사다리(컷 1 → 컷 전체 → 오디오 → 자막 블롭) → 4 export 통합(+prproj 자기검증 게이트). 계단마다 사람이 프리미어에서 열어 확인. 구현은 보고 뒤.

## 11. 도너 결정 변경 — 볼케이노 완성본 채택 (2026-08-17)

- **결정(사용자)**: 우리 도너 = 볼케이노 완성본(`가족전달/Full_Time_롱폼_v26_b05.prproj`). "볼케이노 완성본 자체가 사실 도너다. 볼케이노가 그 형태를 따라 만든 거니 그대로 해보자." 가족 방식과 동일한 실체(진짜 편집 파일을 틀로), **사용자 제작 도너 단계는 사라짐**(`도너/절차서.md` 폴백 보류).
- 원본은 읽기 전용 → 복사본 `도너/볼케이노_FullTime_v26_b05_ppro-v45.prproj`. 적합성 점검(설정 일치·미디어 경로 실존·견본 ID 확보) 통과 — 상세와 ID 는 `참고_prproj구조.md` 6절, 규격 「조립.도너」, 치환 표·잔재 안은 `prproj생성_설계안.md` 계단 1.
- 계단 2 준비물: `도너/왕복.py` → `도너/_왕복_그대로.prproj`(풀고 그대로 재압축, XML 바이트 동일 확인 md5 63bf312e…) · `_왕복_이름변경.prproj`(시퀀스 이름 `…_왕복`). 사람이 파일을 직접 열어 확인한다.

## 12. 자막 레인 규칙 — 동시 표시 금지 · 음성 일치 (2026-08-17)

- **사용자 결정**: 나레 자막과 대사 자막이 **같이 뜨면 집중이 안 된다 → 없앤다**. 볼케이노 완성본 실측도 교차 겹침 0(V2×V3·V2×V4·V3×V4). 이 결정으로 **나레 자막 Position 을 위로 올리는 수리는 취소** — prproj 는 도너 견본 위치 그대로.
- **진단(8:59~9:07 사례)**: n27 음성 536.910~542.110(wav 5.2s = voice.json = 슬롯, 셋 다 일치)인데 V3 큐가 542.830 까지 남았다. 원인 둘 — ① 큐 **최소 길이 0.8s 를 뒤로 밀어** 채운다(전수 5건: n16 +0.16 · n18 +0.267 · n22 +0.24 · n23 +0.4 · n27 +0.72s) ② `splitNarLines` 가 `..!` 를 쪼개 **「!」 한 글자 큐**를 만들었다. 대사 큐는 규칙대로면 위반 0. 교차 겹침은 **20건 19.533s(총장 3.5%)**, 전부 나레 음성이 나오는 중.
- **수리(subtitle 단계)**: R1 나레 큐 ⊆ 음성(앞으로 당겨 채우고, 앞 큐에서 시간 빌리기 → 병합 순) · R2 구두점 단독 큐 금지 · R3 교차 겹침 해소(대사 큐를 나레 밖 **빈 창**으로 자르거나 미룬다 → 대사끼리 겹치면 앞 큐 끝만 자른다 → 자리가 없으면 버린다). 게이트 **G-교차겹침**(hard, 0s) · **G-자막음성일치**(hard) 신설, 정답지 「자막」에 대역.
- **되돌아본 결정 하나**: 잘린 대사 큐를 전부 버렸더니 자막 커버리지가 6.5s 줄어 **G-죽은시간이 0.103 으로 불통**했다(밴드 ≤0.10). 그래서 규격에 **`잘린_대사큐_최소길이_s: 0.5`** 를 두어 **잘린 큐에 한해** 0.5s 까지 허용했다(그 자리에서 대사는 여전히 들린다 — 새 자막을 만드는 게 아니라 살리는 것). 결과 버림 2건.
- **결과(Full Time 재생성)**: 큐 191(나레 73 · 대사 118) · **교차 겹침 0** · **나레 큐 음성 밖 0** · 대사 큐 잘림 17 · 버림 2(`d010 「어 근데 발 전문의는 발가락 안 빨아」` · `d093 「젠장」` — 나레가 그 구간을 통째로 덮었다) · 죽은 시간 0.094 · 게이트 10개 통과. prproj 재생성 `_치환_자막전체.prproj`(V2 118 · V3 73) 자기검증 통과.

## 13. 진단 — 자막은 떠 있는데 나레 소리가 없는 구간 (2026-08-17, 수리 전)

**잰 방법**: 나레 wav 27개를 `ffmpeg silencedetect noise=-40dB:d=0.2` 로 실측해 **발성 구간**을 뽑고, 나레 큐 73개의 창과 겹쳐 「자막은 있는데 무음」인 시간을 계산.

| 사례 | 큐 | wav 안 위치 | 실측 발성 | 무음 노출 |
| :---- | :---- | :---- | :---- | :---- |
| A 539.9s | n27 「그렇게 선 밖에서 끝났습니다..!」 539.690~542.110 | 2.78~5.20 | (0~2.269) · **(3.699~5.2)** | **앞 0.919s** |
| B 274.2s | n14 「그의 발은 선 밖으로 안 나갑니다」 274.009~276.809 | 2.24~5.04 | (0~1.841) · **(2.846~5.04)** | **앞 0.606s** |

**원인 — ElevenLabs 문자 정렬(chars_t)이 문장 사이 쉼을 글자에 붙여 늘린다** (추정 아님, chars_t 실측):
- A: `'.'2.16~2.28 '.'2.28~2.4 ' '2.4~2.78 '그'2.78~3.16 '렇'3.16~3.54 '게'3.54~3.92` — 뒷줄 첫 글자들이 **0.38s/자**(보통 0.08~0.16s)로 늘어나 쉼(2.269~3.699)을 삼켰다 → 큐가 소리보다 0.9s 먼저 뜬다.
- B: `' '1.84~2.24 '그'2.24~2.64 '의'2.64~3.04` — 같은 모양(0.4s/자).
- 반대 방향도 있다: 앞줄 끝 `..` 이 쉼을 물어 **큐가 소리 끝난 뒤까지 남는다**(n26 「꺼졌다가..」 뒤 1.107s · n2 「이어졌고..」 뒤 1.043s · n23 뒤 0.558s · n25 「건네고..」 뒤 0.54s).
- **R1(최소 길이 앞으로 당기기)은 원인이 아니다** — 7건 모두 무음이 큐 안쪽(앞 또는 뒤)에 있고, 당김으로 생긴 경계 무음은 0.

**전수(나레 큐 73개)**: 총 무음 노출 **6.077s / 나레 자막 총 107.51s = 5.7%** · **≥0.3s 인 큐 7개**(앞 무음 3 · 뒤 무음 4) · ≥0.5s 7개. 나머지 66개는 0.21s 이하.

**수리 후보 (승인 대기)**
1. **voice ② 가 wav 마다 발성 구간을 실측**(`ffmpeg silencedetect`, 규격 「음성.무음스캔」 신설 — noise −40dB · d 0.2)해 `voice.json` 에 `speech` 로 남긴다. transcript 의 `silence_scan` 과 같은 방식(서버가 argv 지시, runner 실행 — 재합성 불필요).
2. **subtitle 이 큐 창을 실측 발성으로 클램프**: 큐 시작 = 창 안 첫 발성 시작, 끝 = 창 안 마지막 발성 끝. 최소 길이 채움(당기기·시간 빌리기)도 **발성 구간 안에서만**.
3. **G-자막음성일치 격상**: 기준을 「wav 파일 구간」 → 「**실측 발성 구간**」, 큐당 무음 노출 ≤ 규격 값(제안 0.25s ≈ 6프레임), 총 노출을 metric 으로.
4. 부작용 예상: 클램프로 짧아진 큐(예 n2 「이어졌고..」 1.68s → 0.64s)는 기존 R1 규칙(앞 큐에서 시간 빌리기 → 병합)을 타므로 큐 수가 몇 개 줄 수 있다. timeline 재생성 → prproj 재생성 필요.

