/**
 * steps/스케치코미디/flow.ts — 러너 명령 하나짜리 단계 5개 (argvStep 공장 사용).
 *
 *   sk_cut    1차 렌더 — cut.mp4 를 만들려고 돌린다 ★TTS(Typecast) 요금
 *   sk_subs   자막 재추출 — cut.mp4 만 본다 (계획 자막은 성기고 어긋난다)
 *   sk_asr    실제 발화 시각 실측 ★Speechmatics 요금
 *   sk_sync   자막 시각을 발화에 줄 단위로 맞춤 (공짜 · 맞물림 25% 미만이면 스스로 멈춘다)
 *   sk_render 완성 렌더 — TTS 캐시 재사용, 새 요금 없음
 *
 * ★자막은 두 번 뽑고 두 번 굽는다 — 모델 자막 시각은 추정이라 줄마다 -1.1~+1.6초
 *   어긋나고(중앙 +0.12초 — 일괄 보정 불가), 잘라 붙이면 시각이 통째로 달라지기 때문이다.
 */
import { argvStep } from "./lib.js";

function ttsNote(payload: Record<string, unknown>): string {
  const est = payload.tts_est as { chars?: number; est_sec?: number } | undefined;
  return est?.chars
    ? `나레이션 ${est.chars}자 ≈ ${est.est_sec}초 분량`
    : "나레이션 분량은 sk_check 의 metrics 참조";
}

export const skCut = argvStep({
  name: "sk_cut",
  jobName: "render_cut",
  argv: (project, config) => ["python", "make.py", project, "--config", config],
  jobNote: "1차 렌더 — 구간 자르기·층·나레이션 TTS·자막·합성. 러너 make.py 의 자체 검사가 유료 직전 이중 빗장이다.",
  message: (p) => `★유료 단계 — 나레이션 TTS(Typecast) 요금이 나간다 (${ttsNote(p)}).`,
  instructions: (p) => [
    `★유료 API 단계다 — 실행 전에 사장님께 예상 비용(${ttsNote(p)}, Typecast 과금)을 보고하고 승인받는다. 같은 문구·목소리는 캐시(_tts)가 있어 재과금이 없다.`,
    "jobs 의 make.py 를 그대로 실행한다. 로그의 「얼굴 N」 에 ★얼굴 0 이 보이면 멈추고 검출 모델(자산/스케치코미디/models/yunet.onnx)부터 확인한다.",
    "「완성:」 줄이 찍히면 carry 값을 그대로 실어 sk_subs 를 부른다 — ★★이 산출물은 완성본이 아니다. 자막을 다시 뽑아야 한다.",
  ],
  thenCallWith: ["step: 'sk_subs'", "payload: { workdir, project_path, source }"],
});

export const skSubs = argvStep({
  name: "sk_subs",
  jobName: "subs",
  argv: (project, config) => ["python", "-m", "s2pipe.subs", project, "--config", config],
  jobNote: "잘라 붙인 cut.mp4 를 다시 보고 자막을 촘촘하게 다시 뽑는다 (실측 19줄 → 31줄). EvoLink 무료 한도.",
  message: () => "굽고 나서 자막을 반드시 다시 뽑는다 — 계획 단계 자막은 원본 전체 기준이라 성기고 싱크가 어긋난다.",
  instructions: () => [
    "jobs 의 subs 를 그대로 실행한다 — 편.json 의 subs 가 파일에서 갱신된다.",
    "끝나면 carry 값을 그대로 실어 sk_asr 를 부른다.",
  ],
  thenCallWith: ["step: 'sk_asr'", "payload: { workdir, project_path, source }"],
});

export const skAsr = argvStep({
  name: "sk_asr",
  jobName: "asr",
  argv: (project, config) => ["python", "-m", "s2pipe.asr", project, "--config", config],
  jobNote: "cut.mp4 의 실제 발화 시각(단어 단위)을 받는다. 문구는 쓰지 않는다 — 오인식이 많다(「잭팟」→「책팟」).",
  message: () => "★유료 단계 — Speechmatics 요금(완성 길이만큼, 40~75초 1건).",
  instructions: () => [
    "★유료 API 단계다 — 실행 전에 사장님께 예상 비용(Speechmatics, cut.mp4 길이 약 40~75초 1건)을 보고하고 승인받는다.",
    "jobs 의 asr 를 그대로 실행한다.",
    "끝나면 carry 값을 그대로 실어 sk_sync 를 부른다.",
  ],
  thenCallWith: ["step: 'sk_sync'", "payload: { workdir, project_path, source }"],
});

export const skSync = argvStep({
  name: "sk_sync",
  jobName: "sync",
  argv: (project, config) => ["python", "-m", "s2pipe.sync", project, "--config", config],
  jobNote: "자막 **시각만** ASR 발화에 줄 단위로 맞춘다(문구는 모델 것 유지). 맞물린 글자 25% 미만이면 스스로 멈추고 subs_before_sync 에 원본을 남긴다.",
  message: () => "자막 시각을 실측 발화에 맞춘다 (공짜).",
  instructions: () => [
    "jobs 의 sync 를 그대로 실행한다. ★「정렬이 안 맞는다」며 멈추면 손대지 말고 그대로 보고한다 — 진행하면 자막이 통째로 뭉개진다(정답지 G-싱크맞물림).",
    "끝나면 갱신된 편.json 을 다시 읽어 **전체를** payload.project 에 싣고, carry 값과 함께 sk_recheck 를 부른다 — 자막이 바뀌었으니 재검사한다.",
  ],
  thenCallWith: ["step: 'sk_recheck'", "payload: { workdir, project_path, source, project: <갱신된 편.json 전체> }"],
});

export const skRender = argvStep({
  name: "sk_render",
  jobName: "render_final",
  argv: (project, config) => ["python", "make.py", project, "--config", config],
  jobNote: "완성 렌더 — 같은 문구의 나레이션은 TTS 캐시를 재사용하므로 새 요금이 없다(문구를 고쳤다면 그 문장만 재과금).",
  message: () => "완성 렌더 — TTS 는 캐시 재사용(새 요금 없음).",
  instructions: () => [
    "jobs 의 make.py 를 그대로 실행한다.",
    "「완성:」 줄의 산출물 경로(작업 폴더 out/)와 「원본의 어디를 잘랐나」 표를 사람에게 그대로 보여준다.",
    "carry 값을 그대로 실어 sk_deliver 를 부른다.",
  ],
  thenCallWith: ["step: 'sk_deliver'", "payload: { workdir, project_path, source }"],
});
