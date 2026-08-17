# 서버/ — 영화 롱폼 리캡 MCP 서버 (뼈대)

Cloudflare Workers 에 올릴 MCP 서버. 도구는 `youstudio_video` 하나다.
**서버가 지시를 내리고, 클라이언트(runner/클로드)는 그대로 실행한다.** 규격·명령줄·판단은 전부 서버 쪽에 있다 (`HARNESS.md`, `설계/단계와게이트.md`).

## 지금 되는 것

| step | 상태 | 하는 일 |
| :---- | :---- | :---- |
| `setup` | 구현 | ffmpeg/ffprobe 설치 확인 명령 2개 지시 · 작업 폴더 이름 목록 · **`스타일/영화롱폼/규격.json` 을 응답에 실어 보냄** |
| `start` | 구현 | `source`(영화 파일)와 `payload.workdir` 검사 → ffprobe 명령줄을 서버가 조립해 `jobs_kind:"argv"` 로 지시 → `next_step: probe` |
| `probe` | 구현 | `payload.probe`(ffprobe JSON) 검증 · **오디오 트랙 없으면 hard_fail(status error)+수리 지침** · `metrics` 로 길이·해상도·fps·오디오 유무 · `carry` 에 source·workdir·probe_summary → `next_step: transcript` (지시문에 "ASR 제공자 결정 대기") |
| `transcript` | 구현 | 두 번 부른다. ① `do[]` 로 오디오 추출(ffmpeg 16kHz 모노 mp3) + `jobs_kind:"transcribe"` 로 Groq whisper-large-v3-turbo 호출 지시 — 키는 `auth:{env:"GROQ_API_KEY"}` 위치만(서버 무보관) ② `payload.asr` 검사 → 발화 0건 hard_fail · `write_files` 로 transcript.json · `metrics`(발화 수·발화 길이·무음 비율) → `next_step: brief` |
| `brief` | 구현 | 두 번 부른다. ① `jobs_kind:"judge"` — EvoLink gemini-3.5-flash 에 보낼 프롬프트·바디(JSON 강제·responseSchema·thinkingBudget 0·maxOutputTokens)를 서버가 조립, 전사는 `inputs` 파일 치환(본문은 payload 에 안 실림), `auth:{env:"EVOLINK_API_KEY"}` ② `payload.brief` 검사 → 0건 hard_fail · 타임코드 범위 밖 반려 · `write_files` brief.json · `metrics`(사건 수·평균 길이·커버리지) → `next_step: select` |
| `select` | 구현 | 두 번 부른다. ① `do[]` 로 무음 구간 프레임(5s)·결말 클립(15s) 추출 + `jobs_kind:"judge"`(규격 판정.영상 backend, `@inline_file`/`@file_uri` 표식 파트) 무음 구간마다 1콜 + 결말 1콜 ② 후보(brief 사건+시각 장면) → 우선순위 채움(결말 최우선→중요도) → 창 20~120s·병합 → 역할 → 게이트(G-반복 hard, 나머지 soft) → `metrics`(구간 수·총 길이·평균·비율·분당 블록 대용치·**최대 미선택 스트레치**) → `write_files` clips/visual.json + clips/selection.json → `next_step: script` |
| `script` | 구현 | `need_input` 패턴. ① 서버가 멈추고 **나레이션.md 전문**(텍스트 import) + 규격 「나레이션」 + 정답지 「대본」 + 재료(구간·브리지·시각 사실·장면·결말·사건)를 내려보냄 → 클로드가 블록(위치·본문·의도) 집필 ② 기계 검사(금지 표현·평서체·레지스터·`..`/마침표/쉼표/`..?`·`..!` 위치당 1·문장 상한·**나레 시간점유 G27 hard(자수 추정)**, 나머지 soft) → 불통이면 어느 블록이 왜 + 수리 지침 → 통과 시 script/script.json + metrics → `next_step: voice` |
| `voice` | 구현 | 두 번 부른다. ① `jobs_kind:"synthesize"` — 블록마다 ElevenLabs eleven_v3 호출(pcm_44100), `auth:{env:"ELEVENLABS_API_KEY"}`, `post[]` pcm→wav, measure `bytes` (보이스 미정이면 반려) ② 길이=바이트÷(44100×2) → 실패 hard_fail · voice.json · metrics(총 길이·블록별·실측 자당초 vs 추정·시간점유 실측·여유) · `record_to_ours`(우리실측.json tts) → `next_step: subtitle` |
| `subtitle` | 구현 | 두 번 부른다. ① 컷 타임라인(구간 순서 · over 틈/균등 · before/after 겹침·연장 · 브리지 컷 앵커) → 대사 줄을 모아 `need_input`(번역, 상한 초과 시 judge) ② 큐(나레는 글자별 시각으로, 대사는 꼬리 포함) · 무음 자동 컷 · 게이트(G-자막 자수·겹침, G-죽은시간 홀드 제외) → timeline.json + srt 3종 → `next_step: export`. 불통이면 diagnostics(죽은 구간·컷 대응) |
| `export` | 구현 | 두 번 부른다. ① `do[]` 나레 믹스다운(블록 wav → 실측 t0 amix) + ffprobe ② 길이 검증 → **FCP XML v5**(V1 원본 컷·V2 대사·V3 나레 자막·A1 원본 소리(덕킹)·A2 나레) · SRT 3종 · manifest.json · **1~7 게이트 전체 재검사** → `status: done` |

step 순서: `setup → start → probe → transcript → brief → select → script → voice → subtitle → export`

## 실행법 (로컬)

```bash
cd 서버
npm install            # 처음 한 번
npx wrangler dev       # http://localhost:8787 에 뜬다. Ctrl+C 로 끈다
```

- `GET /health` → `{"ok":true}` 이면 살아 있는 것.
- MCP 엔드포인트는 루트(`/`). Streamable HTTP. 2025 세대 클라이언트는 stateless 로, 2026-07-28 클라이언트는 per-request 로 붙는다(SDK 가 알아서 나눈다).

## 테스트법

`npx wrangler dev` 를 켜 둔 채 **다른 터미널**에서:

```bash
cd 서버
npm test               # = node test/smoke.mjs
# 포트를 바꿨으면: MCP_URL=http://localhost:8788 npm test
```

검사 항목: `/health` · `initialize`(서버 이름·지시문) · `tools/list`(도구 1개, step enum 10개) · `setup`(argv 2개·spec·폴더 목록) · `start`(ffprobe argv·out 경로·measure/carry) · `start` 반려(고치는 법 포함) · 미구현 스텁 · `probe` 정상(metrics·carry·jobs 없음·ASR 대기 지시) · `probe` 오디오 없음(hard_fail+수리 지침) · `probe` payload 없음(반려) · `transcript`① 지시(do[]·transcribe job·auth 에 키 값 없음·상한 안내) · `transcript`② 결과(metrics·write_files·클램프·carry) · 발화 0건 hard_fail · carry 없음 반려 · `brief`① 지시(judge job·inputs 치환·responseSchema·auth 에 키 값 없음) · `brief`② 결과(정렬·클램프·metrics·write_files) · 0건 hard_fail · 범위 밖 반려 · carry 없음 반려. 119항목 전부 `✓` 면 "전부 통과" (전 단계 ①② · 불통 반려 포함).

타입 검사만: `npm run typecheck`

## 클로드에 붙이기 (로컬)

Claude Code 에서:
```bash
claude mcp add --transport http youstudio http://localhost:8787
```
붙은 뒤 "youstudio_video 를 step=setup 으로 불러줘" 라고 하면 첫 응답이 온다.

## 응답 문법

볼케이노 문법을 따른다 (`설계/참고_runner.md` 1-2). 모든 응답에 아래 칸이 있다:

```
status         execute | need_input | done | not_implemented | error
step, preset
next_step      다음에 부를 step. null 이면 끝
then_call_with 다음 호출에 무엇을 실어야 하는지 (안내문)
instructions   이 단계에서 그대로 따를 지시 (순서대로)
need_input     사람이 채울 것 {keys, why} 또는 null
do[]           jobs 앞에 실행하는 준비용 로컬 명령(argv). 볼케이노와 이름은 같고 순서는 앞 (우리 argv 는 전사·판정의 입력을 만든다)
jobs[]         기계 일감. jobs_kind 가 종류를 선언 (argv | transcribe | synthesize | judge | …). transcribe/judge 는 {request, auth:{env}, out} — 키 값은 절대 안 담는다. judge 는 inputs[{placeholder, path}] 로 큰 입력을 파일 치환
post[]         jobs 뒤에 실행하는 로컬 명령(argv) — 예: 받은 pcm 을 wav 로 감싸기. 순서: do → jobs → post → write_files → measure
write_files[]  서버가 내용을 정하고 runner 가 파일로 쓴다 {path, content}
measure[]      runner 에게 주는 측정 규칙 — 무엇을 재서 payload 어느 칸에 넣을지 {as, from:"job:<name>", unit}
metrics        이 단계가 뱉는 숫자 (HARNESS 4장). 나중에 우리실측.json 에 쌓이는 원천 — 게이트는 이 숫자를 정답지 대역과 비교한다
carry[]        이 응답의 값 중 다음 payload 에 그대로 실을 키
message        화면에 찍을 한 줄
```
그 외 칸(`spec`, `workdir_layout`, `source`, `workdir` …)은 단계별 데이터다.

## 파일 지도

```
서버/
├── package.json        이름·의존성·단축 명령(dev/test/typecheck)
├── wrangler.jsonc      Workers 설정 (main=src/index.ts, nodejs_compat)
├── tsconfig.json       TypeScript 검사 설정
├── src/
│   ├── index.ts        Worker 진입점 — 요청을 MCP 핸들러에 넘김. /health
│   ├── server.ts       McpServer 생성 + youstudio_video 도구 등록 + 서버 지시문
│   ├── schema.ts       입력(zod)·응답(타입) 모양. STEP_ORDER 가 상태 기계
│   ├── response.ts     응답 봉투 도우미 (base / notImplemented / reject)
│   └── steps/
│       ├── types.ts    처리기 하나의 모양
│       ├── index.ts    step 이름 → 처리기 등록표 (새 단계는 여기 한 줄)
│       ├── setup.ts    준비 확인 (규격.json import)
│       ├── start.ts    소재 접수 + ffprobe argv 조립
│       ├── probe.ts    원본 확인 — 오디오 없음 hard_fail · metrics · carry
│       ├── transcript.ts 오디오 추출 + Groq 전사 지시 → 결과 검사·transcript.json (규격.json 「전사」)
│       ├── brief.ts    EvoLink judge 지시(프롬프트·responseSchema) → 사건 목록 검사·brief.json (규격.json 「판정」)
│       ├── select.ts   시각 판정 지시(프레임·클립) → 우선순위 채움·역할·게이트 → selection.json (규격 「구간선택」·정답지 「구간선택」)
│       ├── script.ts   need_input(나레이션.md 전문+재료) → 블록 기계 검사·시간점유 게이트 → script.json (규격 「나레이션」·정답지 「대본」)
│       ├── voice.ts    ElevenLabs with-timestamps 합성 지시(pcm) → 실측 길이·글자별 시각·자당초 → voice.json (규격 「음성」)
│       ├── subtitle.ts 컷 타임라인 + 번역(need_input) → 큐·무음 컷·게이트 → timeline.json + srt (규격 「자막」「조립」·정답지 「자막」)
│       ├── export.ts   나레 믹스 → FCP XML v5 + SRT + manifest, 1~7 게이트 재검사 (규격 「조립.내보내기」·참고_export.md)
│   ├── text-modules.d.ts  *.md 텍스트 import 타입 (wrangler rules Text)
│       └── _stub.ts    미구현 자리표
└── test/smoke.mjs      살아 있는지 + 말이 통하는지 검사
```

## 규격이 서버에 실려 가는 방식

`src/steps/setup.ts` 가 `../../../스타일/영화롱폼/규격.json` 을 **import** 한다. wrangler 가 번들할 때 JSON 이 코드 안에 박히므로 배포본에도 그대로 실려 간다. 규격을 고치면 다시 `wrangler dev`/`deploy` 해야 반영된다.

## API 키

서버는 키를 **보관하지 않는다.** 응답의 `auth` 가 "어느 환경변수에서 읽어라"만 말한다.
- ElevenLabs(TTS): 로컬 사용자 환경변수 `ELEVENLABS_API_KEY`.
- EvoLink(텍스트·영상 판정): 로컬 사용자 환경변수 `EVOLINK_API_KEY`.
- Groq: 로컬 사용자 환경변수 `GROQ_API_KEY`. (윈도우: `[Environment]::SetEnvironmentVariable('GROQ_API_KEY','<키>','User')` — 새 터미널부터 보인다)
- 키를 파일에 쓰게 되면 `.gitignore` 에 걸린 위치(`.env`, `.dev.vars`, `*_key`)만 쓴다. 저장소에 절대 넣지 않는다.

## 프리미어에서 열기 (비개발자용)

1. 산돌구름 앱이 켜져 있는지 확인한다(트레이 아이콘). 꺼져 있으면 폰트가 다른 서체로 나온다.
2. 프리미어 프로 실행 → **새 빈 프로젝트**(아무 이름). 같은 소재를 이미 넣어 둔 프로젝트에 다시 임포트하면 **오디오 트랙이 조용히 빠진다**(2026-08-16 실측, 설계/진단일지.md 8절) — 다시 넣을 때도 새 프로젝트.
3. 파일 > 가져오기(Import) → `youstudio_work/<영화>/render/<영화>.xml` 선택 → 열기. 프로젝트 패널에 시퀀스 하나("<제목> 리캡")가 생긴다.
4. 그 시퀀스를 더블클릭해서 연다. V1 원본 컷 · V2 대사 자막 · V3 나레 자막 · A1 원본 소리(살릴 컷) · A2 나레이션 · **A3 덕킹 컷의 원본 소리**(연장·브리지 컷 — 나레와 겹치면 A3 볼륨을 내리거나 음소거)가 이미 놓여 있다.
5. 재생. 자막 글자는 프로그램 모니터에서 더블클릭해 바로 고칠 수 있다.
6. **자막 위치 확인**: XML 의 origin 파라미터로 나레 y≈840 · 대사 y≈980(1920×1080) 에 자동 배치된다(설계/참고_export.md 6-1b, 규격 「자막.위치」). 어긋나면 그 트랙의 자막 클립을 전부 선택(첫 클립 클릭 → 마지막 클립 Shift+클릭) → 창 > Essential Graphics(기본 그래픽) > 편집 → 「정렬 및 변형」의 위치를 manifest.json `프리미어_후속` 의 값으로.
7. 이상하면: 폰트가 다르게 보이면 같은 패널에서 폰트를 직접 고른다(나레 Source Han Serif K Bold, 대사 Sandoll Gwanghwamun) — XML 폰트 이름은 PS 명만 통한다(규격 「자막.폰트.xml명」). 나레가 안 들리면 A2 트랙 음소거를 확인. 원본 소리가 나레와 부딪히면 A3(덕킹 컷) 트랙을 내리거나 음소거한다.
7. 자막을 SRT 로 쓰고 싶으면 `render/subtitle.srt`(합본) 또는 `_nar` / `_dlg` 를 파일 > 가져오기 → 캡션 트랙으로.

## 배포 (아직 안 함)

```bash
npx wrangler login
npx wrangler deploy
```
배포 전에 할 일: 인증(Bearer 토큰) 붙이기, Host/Origin 검증 켜기(SDK 의 `hostHeaderValidationResponse`/`originValidationResponse`). 지금 뼈대는 로컬 전용이라 둘 다 없다.

## 기술 스택

TypeScript · `@modelcontextprotocol/server` 2.0.0 · `zod` · `wrangler` 4 · Node 20+
