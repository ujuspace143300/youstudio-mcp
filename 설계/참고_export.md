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

