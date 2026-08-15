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
| 나머지 6개 | 스텁 | `status: "not_implemented"` — 설계/단계상세.md 의 명세대로 하나씩 만든다 |

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

검사 항목: `/health` · `initialize`(서버 이름·지시문) · `tools/list`(도구 1개, step enum 10개) · `setup`(argv 2개·spec·폴더 목록) · `start`(ffprobe argv·out 경로·measure/carry) · `start` 반려(고치는 법 포함) · 미구현 스텁 · `probe` 정상(metrics·carry·jobs 없음·ASR 대기 지시) · `probe` 오디오 없음(hard_fail+수리 지침) · `probe` payload 없음(반려) · `transcript`① 지시(do[]·transcribe job·auth 에 키 값 없음·상한 안내) · `transcript`② 결과(metrics·write_files·클램프·carry) · 발화 0건 hard_fail · carry 없음 반려. 39항목 전부 `✓` 면 "전부 통과".

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
jobs[]         기계 일감. jobs_kind 가 종류를 선언 (argv | transcribe | synthesize | judge | …). transcribe 는 {request, auth:{env}, out} — 키 값은 절대 안 담는다
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
│       └── _stub.ts    미구현 자리표
└── test/smoke.mjs      살아 있는지 + 말이 통하는지 검사
```

## 규격이 서버에 실려 가는 방식

`src/steps/setup.ts` 가 `../../../스타일/영화롱폼/규격.json` 을 **import** 한다. wrangler 가 번들할 때 JSON 이 코드 안에 박히므로 배포본에도 그대로 실려 간다. 규격을 고치면 다시 `wrangler dev`/`deploy` 해야 반영된다.

## API 키

서버는 키를 **보관하지 않는다.** 응답의 `auth` 가 "어느 환경변수에서 읽어라"만 말한다.
- Groq: 로컬 사용자 환경변수 `GROQ_API_KEY`. (윈도우: `[Environment]::SetEnvironmentVariable('GROQ_API_KEY','<키>','User')` — 새 터미널부터 보인다)
- 키를 파일에 쓰게 되면 `.gitignore` 에 걸린 위치(`.env`, `.dev.vars`, `*_key`)만 쓴다. 저장소에 절대 넣지 않는다.

## 배포 (아직 안 함)

```bash
npx wrangler login
npx wrangler deploy
```
배포 전에 할 일: 인증(Bearer 토큰) 붙이기, Host/Origin 검증 켜기(SDK 의 `hostHeaderValidationResponse`/`originValidationResponse`). 지금 뼈대는 로컬 전용이라 둘 다 없다.

## 기술 스택

TypeScript · `@modelcontextprotocol/server` 2.0.0 · `zod` · `wrangler` 4 · Node 20+
