# 참고 — 프리미어 prproj 구조와 우리 timeline.json 매핑 (계단 0 학습, 2026-08-17)

출처(읽기만, 코드 복사 없음): 볼케이노 `longformmovie_이관/pipeline/stages/assemble.py`(ProjectDoc·HookProjectBuilder), `specs/textblob.py`(Source Text 블롭), `tools/normalize_prproj.py`·`verify()`, 그리고 우리가 푼 실물 두 개 — 가족 전달본(`참고_export.md` 9절)·사용자 프리미어 자동저장본(6-3절). 여기 적힌 것만 만든다(설계안 계단 0 원칙 "표에 없는 것은 안 만든다").

## 0. 파일 = gzip 한 겹 + 오브젝트 목록 XML

- `.prproj` = **gzip**(`1f 8b`) 으로 싼 UTF-8 XML `<PremiereData Version="3">`. 풀면 `\t<태그 ObjectID="n" …>…\t</태그>` 가 **루트 오브젝트 블록**으로 줄줄이 있고, 서로 `ObjectRef="n"`(정수 ID) 또는 `ObjectURef="uuid"`(UID) 로 가리킨다. 트리가 아니라 **참조 그래프**다.
- 저장: `gzip(xml, 레벨 9, mtime 0)`. 탭 들여쓰기·개행·헤더는 도너 그대로 두고 **블록 단위로만** 넣고 빼고 바꾼다(가족 `ProjectDoc`: `_find_block`으로 `^\t<Tag …ObjectID="n"` 부터 `</Tag>` 까지 잘라 치환·삭제·`</PremiereData>` 앞에 append).
- ID 규칙: 새 오브젝트의 `ObjectID` = 도너 최대값+1 부터 순차. `ObjectUID`·`ClipID`·`FileKey`·`LastContentState` = 새 uuid4. 루트 레벨 ObjectID 는 유일해야 하고, 모든 `ObjectRef`/`ObjectURef` 는 실존 대상을 가리켜야 한다(댕글링 0). 시퀀스 UID·트랙 UID·트랙 그룹 ObjectID 는 **도너 것을 그대로** 쓴다(바꾸지 않는다).
- 시간 단위: **틱** — 1초 = 254016000000 틱(TPS). 23.976 프레임 = 10594584000 틱. 우리 결정(프레임 스냅): 초 → `round(초 × 24000/1001)` 프레임 → × 10594584000. 오디오 샘플 틱: 44100Hz = TPS/44100 = 5760000, 48kHz = 5292000, 24000Hz = 10584000. 시퀀스 오디오 레이트 틱은 5292000(48k) — 미디어 스트림 레이트와 **다르다**(혼동하면 스트림 거부, 가족 #1888).
- 텍스트 그래픽 소스는 프리미어 내장 합성 미디어(`Graphic`) 이고 In 점은 관례상 3600초(= 914457600000000 틱).

## 1. 시퀀스와 트랙

| 오브젝트 | 역할 | 우리가 하는 일 |
| :---- | :---- | :---- |
| `Sequence ObjectUID=…` | 이름·`MZ.WorkOutPoint`/`MZ.OutPoint`(총 길이 틱)·`MZ.EditLine`(저장된 재생 헤드)·`TrackGroups`(Video/Audio/Data 그룹 ObjectRef)·`LinkContainer`(V/A 링크 목록) | 이름 = "<제목> 리캡", 길이 = timeline 총 틱, LinkContainer 에 V1↔A1 링크 등록. UID 는 도너 그대로 |
| `VideoTrackGroup`(ObjectID) | `Tracks > Track Index ObjectURef=<트랙 UID>` 목록 · `FrameRate`(프레임 틱) · `FrameRect 0,0,1920,1080` | 도너가 23.976·1920×1080 이면 손대지 않음 |
| `AudioTrackGroup` | 트랙 UID 목록 · `FrameRate 5292000` · MasterTrack | 손대지 않음 |
| `DataTrackGroup` + `CaptionDataClipTrack` | 캡션 트랙 | 우리 도너엔 없게 만든다(있으면 비워 둔다) |
| `VideoClipTrack ObjectUID=…` / `AudioClipTrack` | `ClipItems > TrackItems > TrackItem Index ObjectRef=<아이템>` 목록 · `TransitionItems`(비움) · `IsLocked` | **아이템 목록만 시간순으로 교체**(Index 0..n) — 트랙 이름(`V1 원본컷` 등)은 도너에서 사람이 붙인 것으로 식별 |

## 2. 원본 컷 — timeline.json `pics[k]` → V1 + A1

한 컷 = 비디오 사슬 4블록 + 오디오 사슬 여러 블록 + 링크 1.

**비디오** (`build_footage` 실측 서식):
| 블록 | 필수 자식 | 값 |
| :---- | :---- | :---- |
| `VideoComponentChain` | DefaultMotion/DefaultOpacity true, ComponentID 1/2, 빈 `Components` | 새 ID (모션 없음) |
| `VideoClip` | `Clip{ MarkerOwner→Markers(도너 mp4 마커 참조), Source→VideoMediaSource(도너 mp4), ClipID uuid, InPoint, OutPoint }`, `ScaleToFramePolicy 1` | In/Out = `src_in/src_out` 초 → 프레임 스냅 틱 |
| `SubClip` | `Clip ObjectRef`, `MasterClip ObjectURef`(도너 mp4 마스터클립 UID), `OrigChGrp 0`, `Name` | Name = 컷 이름(예 "01 나레이션덮기 seg1") |
| `VideoClipTrackItem` | `ClipTrackItem{ ComponentOwner→Components(체인), TrackItem{Start,End}, SubClip }`, `FrameRect 0,0,1920,1080`, `PixelAspectRatio 1,1`, `ToneMapSettings {"peak":-1,"version":3}` | Start/End = `t0/t1` 틱(Start 0 이면 생략 가능) |

**오디오** (`_emit_audio_clip_item`·`_emit_intrinsic_volume` 실측 서식):
| 블록 | 필수 자식 | 값 |
| :---- | :---- | :---- |
| 볼륨 필터 3블록: `AudioFilterComponent`(Internal Volume) + `AudioComponentParam` Mute + `AudioComponentParam` Level | Level 의 `StartKeyframe -91445760000000000,<값>,…`·`CurrentValue`, 필터 `FrameRate 5292000` | **값 = 진폭 문자열**: 0 dB = `0.177827998996`(프리미어 스케일 unity), −12 dB ≈ 0.0447, −15 dB = `0.031653400511`. 가족 전달본 A1 기본 −15/덕킹 −30 dB. **우리는 도너 견본(A3 −12 dB) 의 문자열을 그대로 복제** — 수식으로 만들지 않는다 |
| `AudioComponentChain` | `ComponentChain > Components > Component Index 0 → 필터` | 아이템마다 새로 |
| `SecondaryContent` × 채널 수 | `Content→AudioMediaSource`, `ChannelIndex 0..N−1` | 원본 mp4 스테레오 = 2개 |
| `AudioClip` | `Clip{ MarkerOwner, Source→AudioMediaSource(도너 mp4 오디오), ClipID, InPoint, OutPoint }`, `SecondaryContents`, `AudioChannelLayout` | In/Out = 비디오와 동일 틱, 레이아웃 스테레오 `[{"channellabel":100},{"channellabel":101}]` / 모노 `[{"channellabel":100}]`(추정 — 도너 견본에서 확인) |
| `SubClip` | 위와 같음 | Name = 컷 이름 |
| `AudioClipTrackItem` | `ClipTrackItem{…}`, `ID`(uuid) | Start/End |
| `Link` | `TrackItemGroup > TrackItems[0=비디오 아이템, 1=오디오 아이템]` → 시퀀스 `LinkContainer > Links > Link Index ObjectRef` 에 등록 | V1↔A1 컷마다 1개. A2/A3 는 링크 안 함 |

우리 규칙(규격 「조립.덕킹_방식」= 별도트랙): `audio: keep` 컷 → A1, `audio: duck` 컷 → **A3**(볼륨 견본 −12 dB 복제). A1 과 A3 를 합치면 V1 과 1:1 이므로 링크는 V1↔(A1 또는 A3) 로 컷마다 건다.

## 3. 나레이션 — `nars[n]`(wav) → A2

wav 하나마다 **미디어 계보 전체를 새로** 만든다(도너에 없는 파일이므로). 가족 `_emit_narration_lineage` 실측 서식:
| 블록 | 핵심 자식 |
| :---- | :---- |
| `AudioStream` | `AudioChannelLayout`(모노), `SampleType`(16bit = 3, 도너 견본에서 확인), `FrameRate`(24000Hz = 10584000 틱), `Duration`(길이 틱) |
| `Media ObjectUID` | `AudioStream ObjectRef`, `ImporterPrefs`(base64 상수 — 없으면 링크 불가), **`FilePath` = 절대 경로**, `ImplementationID`, `Title`(파일명), `FileKey`(uuid), `ConformedAudioRate`, `RelativePath`(파일명), `MediaFileHistory0`(파일명), **`ActualMediaFilePath` = 절대 경로** — bare 파일명만 쓰면 미디어 오프라인(가족 #1841) |
| `AudioMediaSource` | `MediaSource > Media ObjectURef`, `OriginalDuration` |
| `Markers` | ByGUID·LastContentState uuid |
| `ClipLoggingInfo` | ClipName, MediaInPoint 0, MediaOutPoint, MediaFrameRate(시퀀스 프레임 틱), TimecodeFormat 110 |
| 마스터 `AudioClip` + `SecondaryContent` + `AudioComponentChain`(최소) + `ClipChannelSerializer`/`ClipChannelVectorSerializer`/`ClipChannelGroupVectorSerializer` | 채널 배선(모노 1개) |
| `MasterClip ObjectUID` | LoggingInfo·AudioComponentChains·Clips·AudioClipChannelGroups·`Name`·MasterClipChangeVersion 3 |
| `ClipProjectItem ObjectUID` | `Name`, `MasterClip ObjectURef` → **`RootProjectItem > Items` 에 등록**(프로젝트 패널에 보이게) |
| 트랙 아이템 | 2절 오디오 사슬과 같음(볼륨 0 dB 견본, 채널 1, In 0 / Out 길이, Start/End = t0/t1) |

**우리 방식**: 도너에 `b01.wav` 견본이 1개 있으므로 위 계보를 **손으로 서식 짜지 않고 견본 계보를 통째로 복제**(ObjectID/UID 재배선 + 경로·이름·길이·레이트 치환)한다. 원본 mp4 의 `Media`도 도너 것을 그대로 두되 `FilePath/ActualMediaFilePath` 만 실제 경로로.

## 4. 자막 — `cues[c]` → V2(대사)/V3(나레) 텍스트 클립

가족 방식(`build_titles`): 도너의 **텍스트 클립 서브트리 1벌**(TrackItem·ComponentChain·VideoFilterComponent(AE.ADBE Text)·파라미터 22개·SubClip·VideoClip)을 큐마다 **복제 → ObjectID/Ref 전부 재배선 → 몇 군데만 치환**:
| 치환 지점 | 무엇을 |
| :---- | :---- |
| `VideoClipTrackItem > TrackItem` | Start/End 틱 |
| `VideoClip` | `ClipID` 새 uuid, `InPoint` 3600s 틱, `OutPoint` = In + (End−Start) |
| `SubClip > Name` | 큐 텍스트 |
| `VideoFilterComponent > InstanceName` | 큐 텍스트(블롭 텍스트와 동기화) |
| `ArbVideoComponentParam "Source Text"` | **블롭**(아래) + `BinaryHash` 재발급 |
| `PointComponentParam "Position"` | 우리 도너에선 **치환 안 함** — 견본에서 사람이 잡은 값 그대로(0~1 정규화, 예 0.5:0.9556). 가족은 여기서 y 를 계산해 넣었다 |
| Scale/Rotation/Opacity 등 나머지 20개 | 그대로 |

**Source Text 블롭**(`textblob.py` 지식): base64 → 헤더 8바이트(길이 = 전체−12) + 매직 `44 33 22 11` + FlatBuffers. root → main(레이어) 테이블 → f0 = **런(run) 벡터**(런 = 텍스트 문자열 + StyleTable(f1 크기 float32 · f2 채움색 RGB 미니테이블 · 스트로크·그림자·그라데 슬롯…)) · f1 = **폰트 이름 벡터**(PostScript 명 문자열). 안전한 조작만:
- 텍스트 치환 = **tail relocation**: 새 문자열을 버퍼 끝에 붙이고(4바이트 정렬, `u32 길이 + utf8 + \0`) 그 런의 문자열 참조 오프셋 하나만 새 위치로 돌린다(옛 바이트는 죽은 채 둔다). in-place 덮어쓰기는 문자열 슬롯 패딩이 공유 vtable 과 겹칠 수 있어 **금지**(가족 실측). 마지막에 헤더 길이 갱신 → 재파싱으로 자가검증.
- 폰트도 같은 방법으로 문자열 치환 가능(1차엔 안 함 — 도너 견본 폰트 그대로).
- 크기·색은 StyleTable 의 해당 바이트 in-place(1차엔 안 함).
- 런 벡터·스타일 테이블을 **처음부터 재조립하지 않는다**(가족이 회귀를 겪음: vtable/tsize 미세 불일치 → 프리미어가 스타일 무시).
- `BinaryHash` = 새 uuid 앞 28자 + `hex8(블롭 길이 + 12)`.
- 1차 범위: **한 큐 = 한 런 = 한 폰트·한 크기**(우리 도너 견본이 1런이면 그대로, 2런이면 두 번째 런을 빈 문자열로) — 2줄 자막은 문자열 안 `\r`(가족 xml_escape 가 `&#13;`) 개행. 확인 항목.

## 5. 검증(가족 `verify`/`normalize_prproj` 에서 가져올 규칙)

1. 루트 ObjectID 유일 · ObjectUID 유일 · 댕글링 ObjectRef/URef 0.
2. 트랙별 `ClipItems` 개수 = timeline 실측(V1 46 · A1 36 · A3 10 · A2 27 · V2 120 · V3 74).
3. 트랙 안 아이템 시간 겹침 0, Start<End, 시퀀스 길이 = 마지막 End.
4. 미디어 경로 전부 실존(FilePath/ActualMediaFilePath 절대경로).
5. 블롭 재파싱 성공·런 텍스트 = 큐 텍스트·헤더 길이 일치·BinaryHash 길이 인코딩 일치.
6. gzip 왕복: 풀었다 그대로 싼 결과가 원본과 XML 바이트 동일(계단 2).
7. "기능 동일" diff: 난수(ObjectID 순번·uuid·BinaryHash 앞부분)만 정규화한 뒤 바이트 대조 — 회귀 게이트로 쓴다.

## 6. 우리 도너에서 프로그램이 찾을 것 (도너 절차서와 1:1)

| 도너 안 실체 | 프로그램이 찾는 방법 | 쓰임 |
| :---- | :---- | :---- |
| 시퀀스 `영화롱폼` | `Sequence > Name` | UID·LinkContainer·길이 |
| 트랙 6개(이름 `V1 원본컷`…`A3 덕킹소리`) | 트랙 블록의 이름(트랙 이름은 트랙 `Node > Properties` 또는 `Name` — 계단 1 결과물을 풀어 **실제 위치 확인**) | 아이템 목록 교체 대상 |
| V1/A1 견본 컷(mp4) + 링크 | V1 트랙의 유일한 아이템 → SubClip → VideoClip → Source → Media | 컷 서브트리 템플릿 + mp4 미디어 계보(경로 치환) |
| A2 견본(b01.wav) | A2 트랙 아이템 → 계보 | 나레 계보 템플릿 |
| A3 견본(mp4 소리, −12 dB) | A3 트랙 아이템 → 체인 → 필터 → Level 파라미터 | 덕킹 볼륨 템플릿 |
| V3 `나레 견본` / V2 `대사 견본` 텍스트 클립 | 트랙 아이템 → SubClip Name | 자막 서브트리 템플릿(위치·폰트·크기·모양 포함) |

계단 1 이 끝나면 이 표의 "찾는 방법" 칸을 실제 도너를 풀어 **오브젝트 ID/UID 로 채운다**(그 값들이 규격 「조립.도너」의 내용).
