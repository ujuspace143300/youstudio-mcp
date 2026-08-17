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

---

## 5\. 그 뒤의 실측·진단 기록

첫 임포트부터의 실측·진단·판정(옛 5~19절)은 **`설계/진단일지.md`** 로 옮겼다(2026-08-17 주간정비 — 이 파일 480줄의 82%가 진단 일지였고, 진단은 계속 쌓이기 때문).
이 파일에는 **FCP XML 형식의 근거**만 남긴다.
