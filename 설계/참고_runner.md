# 참고 — 볼케이노 runner 구조

> `설계/참고자료분석.md` 에서 분리한 조각. 목차는 그 파일에 있다.

## 1. 볼케이노 runner 구조

> 출처: `볼케이노 MCP/작업파일/06_자산/runner/` 의 `volcano_run.py`(1,050줄) · `volcano_drive.py`(588줄) · `README.md`. 2026-08-15 읽음. 읽기만 했다.
> 한 줄 요지: **runner 는 "받은 것을 그대로 실행하는 껍데기"** 다. 무엇을 만들지·어떤 값인지는 전부 서버가 정해 내려주고, runner 는 응답의 *문법* 만 안다. 채널 노하우는 서버(Cloudflare Worker)에 있어서 이 폴더에는 없다.

### 1-1. 메인 루프 (volcano_drive.py `drive` → `_drive_loop`)

```
payload = {}
step = "start"                       # 소재(source)는 start 에서 한 번만 보낸다
반복 (최대 40회):
    res = 서버.step(step, payload, source)          # JSON-RPC 한 번
    if res.status == "need_input":                  # 대본·제목 같은 창작 자리
        carry 값만 payload 에 옮기고 → 멈춰서 사람에게 넘긴다
    payload += execute(res)                         # 기계 일 전부 (파일쓰기·jobs·argv·측정)
    if res.author:                                  # 기계 일을 다 한 뒤 사람 손이 필요한 자리
        멈춘다 (한 일을 버리지 않는다)
    if res.next_step 없음 또는 "(" 로 시작 → 끝
    step = res.next_step
어디서든 예외 → 서버 `feedback` 단계에 "[실행기 중단] 어느 step 에서" 한 줄 보고 → 원래 예외 다시 던짐
```

`execute()` 안의 순서도 규격이다: ⓪ 선언된 출력 폴더 미리 생성 → ① 검사(check_fonts·check_photo) → ② write_files → ③ frames 굽기 → ④ jobs(TTS·이미지·인코드) → ⑤ do[].argv 실행 → ⑥ concat_argv·argv(최종 렌더) → verify → measure → carry.
이유: 명령이 쓸 입력을 먼저 만들어야 한다("⑤를 ②③보다 먼저 돌렸다가 vconcat.txt 없다로 죽었다").

### 1-2. 서버 응답 필드와 용도

요청은 MCP JSON-RPC 2.0(`tools/call` → `volcano_video`, 인자 `{step, preset, payload, source}`), 응답은 `result.structuredContent` 가 아래 JSON.

| 필드 | 용도 |
| :---- | :---- |
| `status` | `"need_input"` 이면 사람이 채울 차례. 그 외는 기계 실행 |
| `next_step` | 다음에 부를 step 이름. 없거나 `(`로 시작하면 종료 |
| `message` · `warnings[]` | 화면에 그대로 찍는 안내·경고 |
| `then_call_with[]` | 멈출 때 "다음엔 무엇을 채워 부르라"는 안내문 |
| `author {for, keys, why}` | 기계 일 끝난 뒤 사람이 만들어야 할 값 목록(감정 선택·프레임 메모 등). 있으면 멈춤 |
| `carry[]` | 이 응답에 있는 값 중 payload 에 그대로 실어 다음 단계에 돌려줄 키 이름들 |
| `auth` | 제공자 키를 어디서 읽어 어느 헤더에 실을지 (`header, env_var, key_file, scheme, label`) |
| `do[]` | 로컬 명령 목록. `cmd` 이름 + `argv`(또는 `argv_candidates`+`pick_by`), `optional`, `note`, `out`. 특수 cmd: `check_fonts`(잉크 크기 대조로 글꼴 폴백 감지) · `check_photo`(사진 슬롯에 일러스트 유입 감지) · `scene_cuts` · `measure_lufs` · `measure_sfx` · `measure_audio` · `fetch_asset`(url+sha256+extract_to, tar.gz) |
| `write_files[]` | `{path, content, encoding?, sha256?}` — 자막(.ass)·concat 목록·프리미어 프로젝트 등을 **바이트 그대로** 쓴다 |
| `frames[]` | `{src, dst, resize, crop, order?}` — 이미지 리사이즈·크롭 지시 |
| `jobs[]` + `jobs_kind` | 일감 묶음. 종류: `synthesize`(TTS) · `generate_images` · `fetch_images` · `transcribe` · `argv`(컷 인코드) |
| `retry` · `min_bytes` · `parallel` · `stagger_sec` · `pace_sec` · `backoff_sec` · `poll{}` | jobs 실행 파라미터. **runner 에 기본값 없음** — 전부 서버가 준다 |
| `asr {order, providers}` · `edge_params` | 전사 제공자 사다리와 파형 분석 상수 |
| `concat_argv` · `argv` · `out_path` | 최종 이어붙이기·렌더 명령과 산출 경로 |
| `verify {argv, expect, cmd, note}` · `verify_note[]` | 실행 후 확인 명령. 출력이 expect 와 다르면 중단 |
| `measure[]` | 무엇을 재서 payload 어느 칸에 넣을지 (`{as, of, index_by, file, unit:"seconds"}` 또는 `{as, from:"cmd:이름", unit:"json_stdout"}`) |
| `_meta` | MCP 래퍼 알림(있으면 찍기만) |

### 1-3. 로컬에서 실제로 하는 일과 라이브러리

| 일 | 도구 | 비고 |
| :---- | :---- | :---- |
| 영상 렌더·이어붙이기·컷 인코드·오디오 후처리 | `ffmpeg` (subprocess) | argv 는 **한 글자도 안 고치고** 서버 것 실행. `-threads` 추가 금지(바이트가 달라짐) |
| 길이·라우드니스·장면전환 측정 | `ffprobe` · `ffmpeg ebur128/showinfo` stderr 파싱 | `-v error` 붙이면 측정값 사라짐 |
| 프레임 굽기(리사이즈·크롭) · RGB 변환 | Pillow | LANCZOS · JPEG quality=100 · subsampling=0 고정 |
| 효과음·음악 스펙트럼 측정, 파형 상승엣지, 일러스트 판정 | numpy (FFT) | 임계값은 서버 `params` |
| 피사체 중심(얼굴→엣지 무게중심) | OpenCV haarcascade | 좌표만 서버에 보냄, 크롭은 서버가 결정 |
| TTS · 이미지 생성(제출+폴링) · 이미지 검색(위키미디어 등) · 전사(Speechmatics/Groq/Gladia/로컬 whisper) | `urllib` 표준 라이브러리만 | 엔드포인트·본문·pick 경로 전부 서버가 줌 |
| 자산 팩 다운로드 | urllib + hashlib + tarfile | sha256 대조 후 해제 |
| 병렬 실행 | threading + queue | 폭은 서버 `parallel` |

외부 의존: `ffmpeg/ffprobe`, `pillow`, `numpy`, `opencv-python`. 나머지는 표준 라이브러리.

### 1-4. API 키 전달 방식 (값은 코드에 없다 — 전부 로컬 환경에서 읽는다)

두 층이다.
1. **서버 인증** — 모든 호출과 `/asset/…` 다운로드에 `Authorization: Bearer <토큰>`. 함께 `MCP-Protocol-Version: 2025-11-25`, `User-Agent: volcano-runner/1.0`(기본 UA 는 Cloudflare 가 403 으로 막음).
2. **제공자 키(TTS·이미지)** — 서버가 `auth` 로 "이 헤더에, 이 환경변수 또는 이 키파일에서 읽어, 이 접두어(scheme)로" 를 지정 → runner 가 로컬에서 읽어 헤더에 붙임. 호출자가 `headers=` 로 직접 넘긴 것이 우선(README 예시는 `X-API-KEY`). 전사 키는 `headers["asr_keys"] = {제공자: 키}` 사전으로 넘기고, 제공자별 `auth_header/auth_prefix` 는 서버 cfg. **서버는 키를 보관하지 않는다.** `http_headers()` 가 문자열 아닌 값을 걸러 urllib 에 넘긴다.

### 1-5. 파일 경로 지정 방식

- 서버가 `path`(write_files) · `out`/`raw`(jobs) · `dst`(frames) · `out_path`(최종) · `extract_to`(자산) 로 **경로를 명시**한다. runner 는 argv 를 뜯어 출력을 추측하지 않는다.
- `_declared_outs()` 가 선언된 경로를 한 곳에서 모아 **실행 전에 부모 폴더를 전부 만든다**(ffmpeg 은 폴더를 안 만든다 — 최종 렌더가 `out/` 없어서 죽은 사고).
- 다운로드는 `.part` 로 받고 검사 통과 후 `os.replace` 로 제 이름(원자적 교체). 캐시 건너뛰기는 서버가 준 `skip_if {path, key, min_bytes}` 로만 — 파일 존재만으로 추측하지 않는다(대본 고쳤는데 옛 음성이 붙은 사고).
- 예외: 로컬 whisper 출력 폴더 `asr/` 는 runner 가 오디오 옆에 스스로 만든다.

### 1-6. 에러 처리

- 모든 실패는 `StepError`(메시지에 고치는 법 포함) 로 **큰 소리로 멈춘다**. 조용히 건너뛰지 않는다 — 빈 컷·빈 음성이 렌더 게이트에서야 잡히던 사고 때문.
- **재시도**는 서버가 준 만큼만: TTS·이미지 생성 `retry` 회, 이미지 검색·다운로드 429 는 `backoff_sec` 간격표, 이미지 생성 `poll{max_tries, interval_sec}`. 전사는 `asr.order` 사다리로 다음 제공자로 넘어감(단, "단어 0개"는 실패가 아니라 정상 측정값).
- 병렬 풀은 실패를 모아뒀다가 전부 끝난 뒤 한 번에 던진다. 같은 출력 경로를 두 잡이 쓰면 시작 전에 막는다.
- **서버 보고**: `drive` 가 예외를 잡아 `feedback` step 에 `{kind:"bug", step, text[:400]}` 을 보내고 원래 예외를 다시 던진다. 보고 자체가 실패해도 삼킨다(진짜 오류를 가리지 않기 위해).
- 건너뛰는 예외 두 가지: `optional: true` 인 명령의 도구가 없을 때, 로컬 whisper 가 안 깔렸을 때.
- 안전장치: 루프 40회 초과 → 순환 의심으로 중단. `verify.expect` 불일치 → 중단. 자산·파일 sha256 불일치 → 중단.

### 1-7. runner 안에 "규격" 값이 있는가 — 거의 없다. 예외 몇 개

채널 규격(컷 길이·자막 자수·프롬프트·필터 상수·임계값)은 **하나도 없다.** 아래는 남아 있는 상수인데, 성격이 "실행 기술" 이지 "채널 규격" 은 아니다. 다만 우리 서버를 만들 때 알고 있어야 한다.

| 위치 | 상수 | 성격 |
| :---- | :---- | :---- |
| `bake_frames` | LANCZOS · JPEG quality=100 · subsampling=0 | 정본과 픽셀 일치용. 사실상 규격의 일부 |
| `bake_frames` | `src.startswith("pepe")` 면 흰 배경 합성 | **채널 특정 토큰**이 새어 있음. 우리는 안 쓴다 |
| `is_illustration` | 128×96 축소, 색 양자화 32, 흰색 >0.35, 색 <90 | 사진/일러스트 판정식. 서버 지시(check_photo)의 판정을 runner 가 들고 있음 |
| `fetch_images` | JPEG quality=95, URL 후보 40개 상한 | 실행 편의 상수 |
| `wav_seconds` | ffprobe argv 를 runner 가 직접 지음 | 유일하게 runner 가 짓는 명령 |
| 기타 | 타임아웃 120/180/900초, max_steps=40, 오류 메시지 400자·stderr 800자 절단 | 운영 상수 |

결론: 검사 [20](명세 잎값 유출)을 의식해 지은 코드다. **우리도 같은 경계를 지킨다** — 규격은 `스타일/영화롱폼/규격.json` → 서버, runner 는 문법만.

### 1-8. 규모와, 처음부터 만든다면 어디가 오래 걸리나

- 코드: `volcano_run.py` 1,050줄 + `volcano_drive.py` 588줄 = **1,638줄**. 이 중 상당수가 "왜 이렇게 했나" 주석(실측 사고 기록 15건 이상 — 윈도우 CRLF·cp949, Cloudflare UA, macOS 글꼴 폴백, numpy 제자리 덮어쓰기, ffmpeg 폴더 미생성 등).
- 오래 걸릴 순서:
  1. **응답 문법 설계** (1-2 표) — 서버↔runner 계약 자체. 이게 곧 아키텍처다. 나머지는 이 문법을 채우는 일.
  2. **플랫폼 사고 재발견** — 위 주석들은 실제로 겪고 나서 적힌 것. 처음부터 만들면 같은 함정을 다시 밟는다. 그대로 이어받을 가치가 가장 큰 부분.
  3. **측정 함수의 DSP** (`measure_audio`·`rise_edges`·`measure_sfx`) — FFT·라우드니스·온셋. 영화 롱폼에 필요한지부터 판단.
  4. 전사 제공자 사다리(4종 응답 파서 + 멀티파트/폴링/로컬 CLI).
- 빨리 끝나는 것: 이미지 생성·검색 (우리 소재는 영화 원본이라 아예 필요 없을 수 있음), TTS 호출(단순 POST).
- **핵심 시사점**: runner 는 채널을 모르므로, 우리 서버가 같은 응답 문법을 쓰면 **이 runner 를 거의 그대로 재사용**할 수 있다. 처음부터 만들 것은 서버(단계 상태 기계 + 규격 + 게이트)이지 runner 가 아니다. → `설계/단계와게이트.md` 로 이어진다.
