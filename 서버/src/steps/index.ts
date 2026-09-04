/**
 * steps/index.ts — 파이프라인 등록표: 프리셋마다 「단계 → 처리기」 지도.
 *
 * 단계 순서(상태 기계)는 styles.ts 의 steps 가 정본이고, 여기는 그 단계를
 * 어느 처리기가 맡는지만 적는다. 새 단계를 구현하면 해당 프리셋 지도에 한 줄.
 * 프리셋끼리 단계가 겹치면 처리기를 공유해도 된다 (setup 처럼).
 */
import { STYLES, type Preset } from "../styles.js";
import type { Step } from "../schema.js";
import { setup } from "./setup.js";
import { start } from "./start.js";
import { probe } from "./probe.js";
import { transcript } from "./transcript.js";
import { brief } from "./brief.js";
import { select } from "./select.js";
import { script } from "./script.js";
import { voice } from "./voice.js";
import { subtitle } from "./subtitle.js";
import { exportStep } from "./export.js";
import { stub } from "./_stub.js";
import { skStart } from "./스케치코미디/start.js";
import { skPlan } from "./스케치코미디/plan.js";
import { skCheck, skRecheck } from "./스케치코미디/check.js";
import { skAsr, skCut, skRender, skSubs, skSync } from "./스케치코미디/flow.js";
import { skDeliver } from "./스케치코미디/deliver.js";
import { lbStart } from "./린박스/start.js";
import { lbProbe } from "./린박스/probe.js";
import { lbCut } from "./린박스/cut.js";
import { lbTranscript } from "./린박스/transcript.js";
import { lbPlan } from "./린박스/plan.js";
import { lbScript } from "./린박스/script.js";
import { lbVoice } from "./린박스/voice.js";
import { lbBlocks } from "./린박스/blocks.js";
import { lbSubs } from "./린박스/subs.js";
import { lbXml } from "./린박스/xml.js";
import type { StepHandler } from "./types.js";

const PIPELINES: Record<Preset, Partial<Record<Step, StepHandler>>> = {
  영화롱폼: {
    setup,
    start,
    probe,
    transcript,
    brief,
    select,
    script,
    voice,
    subtitle,
    export: exportStep,
  },
  스케치코미디: {
    setup, // 공유 — workDirs·spec 은 등록표에서 프리셋별로 온다
    start: skStart,
    sk_plan: skPlan,
    sk_check: skCheck,
    sk_cut: skCut,
    sk_subs: skSubs,
    sk_asr: skAsr,
    sk_sync: skSync,
    sk_recheck: skRecheck,
    sk_render: skRender,
    sk_deliver: skDeliver,
  },
  린박스: {
    setup, // 공유 — workDirs·spec 은 등록표에서 온다. lb_* 처리기는 한 단계씩 만들어 여기 한 줄씩 (그 전엔 stub 이 «아직 구현 안 됨» 을 돌려준다)
    start: lbStart, // 드라마 로컬 영상 + 편 이름 + 구간 → ffprobe·cropdetect 지시
    lb_probe: lbProbe, // 소재 확인 · 구간 범위 · 레터박스·WIN · «프레임률» 파일
    lb_cut: lbCut, // 구간 절단(-i 뒤 -ss 재인코딩) · 구간_원본 사본 · 절단본 재기 · 장면컷.py
    lb_transcript: lbTranscript, // ★유료 Speechmatics 3벌 전사(전사.py) + 화자표.py · 두 번 부름(지시 → 검사)
    lb_plan: lbPlan, // 쓸거리(§83)·밀도 게이트 → 하단 need_input → 편정보.json(§70) · 두 번 부름
    lb_script: lbScript, // 대본·제목(need_input, 사장님 선택) → 서버 검사 → authored.json + 대본검사·제목검사 게이트 → 편정보 제목 · 세 번 부름
    lb_voice: lbVoice, // ★유료 Typecast 나레 합성(볼케이노 stitch_narr 꼴·raw 캐시·정규화 2단계) → wav 검사 → ★Speechmatics narr_align → narr_words · 세 번 부름
    lb_blocks: lbBlocks, // 얼굴·재프레이밍·컷 손질 → 블록 계획(_block_jobs 꼴)·굽기 → 실측으로 captions_서버원본.ass → 장면튐검사 · 네 번 부름
    lb_subs: lbSubs, // 한번에.sh ①·①.5 — 자막말머리맞춤(§93) → 서식.py → 폭맞춤·ass자리검사·구둣점검사 → 그래픽짓기·계획짓기 → 자막끝맞춤 → 원음스템 · 두 번 부름
    lb_xml: lbXml, // 한번에.sh ② — xml짓기.py(작품·자막·배율 인자) → FCP7 XML · 로그로 컷·제목·나레 수 대조 · 두 번 부름
  },
};

/** 이 프리셋 파이프라인에 이 단계가 있는가 — 없으면 서버가 반려한다 */
export function stepInPipeline(preset: Preset, step: Step): boolean {
  return (STYLES[preset].steps as readonly string[]).includes(step);
}

/** 처리기를 찾는다. 파이프라인에는 있는데 아직 안 만든 단계면 stub */
export function handlerOf(preset: Preset, step: Step): StepHandler {
  return PIPELINES[preset][step] ?? stub(step);
}
