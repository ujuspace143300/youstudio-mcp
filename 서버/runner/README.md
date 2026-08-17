# runner — 파이프라인 실행 스크립트

서버(MCP)가 **지시**하고, 이 스크립트들이 **실행**한다. 단계마다 하나씩 있고, 서버 응답의 `jobs`(외부 API 호출)와 `write_files`(파일 쓰기)를 그대로 수행한다.

> **왜 저장소 안에 있나** — 2026-08-17 주간정비: 이 스크립트들이 임시 폴더에만 있었다. 「보이지 않으면 존재하지 않는다」(HARNESS §1) 위반이고, 실제로 `run_voice.mjs` 의 캐시 버그가 나레 음성·자막 불일치 14/27 사고를 냈는데 코드가 저장소에 없어 아무도 검토할 수 없었다.

| 파일 | 단계 | 외부 호출 |
| :-- | :-- | :-- |
| `run_brief.mjs` | brief | EvoLink(judge) |
| `run_select.mjs` | select | EvoLink·Gemini(영상 판정) |
| `run_script.mjs` | script | — (need_input 대본) |
| `run_voice.mjs` | voice | ElevenLabs(합성) · Groq(ASR 문구 대조) |
| `run_transcript_sm.mjs` | transcript | Speechmatics(batch v2 제출·폴링) |
| `run_subtitle.mjs` | subtitle | — |
| `run_export.mjs` | export | — |

## 키

**키는 코드에 쓰지 않는다.** 윈도우 사용자 환경변수에서만 읽는다(`process.env` → 없으면 PowerShell `GetEnvironmentVariable(...,'User')`). 이름은 `설계/외부서비스.md` 참조.

## 주의 — 재사용 캐시

`run_voice.mjs` 는 합성 비용을 아끼려 이전 결과를 재사용한다(`REUSE=1`). 재사용 키는 **직전 실행본의 파일 해시**다. 대본이 바뀌면 캐시를 버린다 — 텍스트만 키로 쓰면 옛 판 경로의 현재 파일을 읽어 **대본이 통째로 밀린다**(2026-08-17 사고). 게이트 `G-나레문구일치` 가 이 사고를 막는다.
