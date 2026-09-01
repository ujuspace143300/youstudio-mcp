/**
 * steps/스케치코미디/check.ts — 구조 게이트 판정 (sk_check · sk_recheck).
 *
 * 러너 make.py check() 의 이식 — **판정의 정본은 여기(서버)다.** 대역은
 * 정답지.json(판정 전용 값)과 규격.json(제작·판정 겸용 값)에서 온다.
 * 러너 make.py 의 검사는 유료 렌더 직전의 이중 빗장으로 남아 있고, 그 상수도
 * 생성 config 의 `_정답지` 에서 읽는다 — 값의 원천은 한 곳이다.
 *
 * sk_check  = 계획 직후 (통과 → sk_cut, 1차 렌더)
 * sk_recheck = 자막 싱크 뒤 (통과 → sk_render, 완성 렌더)
 * ★원본 mp4 존재는 서버가 못 본다 — 러너 make.py 가 잡는다(파일 검사는 러너 몫).
 */
import { base } from "../../response.js";
import type { Step } from "../../schema.js";
import type { StepHandler } from "../types.js";
import { answer, isProject, ours, spec, str, type Project, type Segment } from "./lib.js";

const E = spec.edit;
const PHASES = new Map(E.phases.map((p) => [p.no, p]));
const G구조 = answer.구조;
const G나레 = answer.나레이션["G-나레이션"];
const G자막 = answer.자막;
const SEC_PER_CHAR = ours.tts.sec_per_char;

export interface Verdict {
  bad: string[];
  warn: string[];
  metrics: Record<string, unknown>;
}

/** make.py check() 의 서버판 — 반려(bad)·주의(warn)·지표(metrics) */
export function judge(proj: Project): Verdict {
  const bad: string[] = [];
  const warn: string[] = [];

  const segs: Segment[] = (proj.segments ?? []).filter((s) => s.keep !== false);
  if (!segs.length) return { bad: ["구간이 하나도 없다"], warn, metrics: {} };

  // ★sketch(1호) 대본 혼입 — 표식은 phase 하나뿐이다
  if (!segs.some((s) => "phase" in s)) {
    return {
      bad: [
        "★이건 sketch 대본이다 — 스케치코미디(sketch2)는 다른 채널이다. 조각에 `phase` 가 없으면 저쪽 형식이다(5-Phase 는 여기에만 있다). sk_plan 으로 새로 계획하라.",
      ],
      warn,
      metrics: {},
    };
  }

  const total = segs.reduce((a, s) => a + (s.t1 - s.t0), 0);
  const [lo, hi] = E.target_sec;

  // ── 길이 (정답지 G-길이, hard) — ★절대 규칙(2026-09-01): 기승전결을 담을 최소 길이
  if (!(lo <= total && total <= hi))
    bad.push(
      `★완성 길이 ${total.toFixed(0)}초 — 절대 규칙 ${lo}~${hi}초 밖이다. ${total < lo ? "짧으면 기승전결이 안 담긴다 — 클러스터 안에서 핑퐁·절정을 더 담아라" : "길면 늘어진다 — 처지는 조각을 잘라라"}`,
    );

  // ── 5-Phase (정답지 G-Phase완비)
  const used = segs.map((s) => s.phase ?? 0);
  const missing = [1, 2, 3, 4, 5].filter((p) => !used.includes(p));
  if (missing.length) {
    const names = missing.map((p) => `${p} ${PHASES.get(p)?.name}`).join(", ");
    bad.push(`Phase 가 빠졌다 — ${names}. 기승전결이 서지 않는다`);
  }
  if (used.join() !== [...used].sort((a, b) => a - b).join()) bad.push(`Phase 가 순서대로 배열되지 않았다 — [${used}]`);

  const p1 = PHASES.get(1)!;
  if (segs[0].phase !== 1) bad.push(`첫 조각이 Phase 1(Hook)이 아니다 — P${segs[0].phase}`);
  else if ((segs[0].punch ?? 0) < p1.min_punch)
    bad.push(
      `★훅이 약하다 — 첫 조각 punch ${segs[0].punch} (Hook 은 ${p1.min_punch} 이상이어야 한다). 상황 설명으로 열지 말고 센 대사를 앞으로 끌어와라`,
    );

  // ── ★훅은 대사다 (정답지 G-훅대사, hard · 2026-09-01) — 무언 컷 훅 금지
  const hookTimes = (proj.hooks ?? [])
    .map((h) => (typeof h === "object" && h !== null ? h.t0 : undefined))
    .filter((t): t is number => typeof t === "number");
  if (segs[0].phase === 1 && !hookTimes.some((t) => segs[0].t0 <= t && t <= segs[0].t1))
    bad.push(
      `★훅 조각(원본 ${segs[0].t0.toFixed(1)}~${segs[0].t1.toFixed(1)}초) 안에 hooks 의 대사가 없다 — 말 없는 컷은 화면이 좋아도 훅이 아니다. 전제가 서는 가장 센 대사를 훅으로 끌어와라 (제목이 던진 질문을 첫 대사가 받아야 한다)`,
    );

  // ── 조각 겹침 (정답지 G-조각겹침)
  const ovMax = G구조["G-조각겹침"].겹침_max_sec;
  const order = [...segs].sort((a, b) => a.t0 - b.t0);
  for (let i = 1; i < order.length; i++) {
    const ov = order[i - 1].t1 - order[i].t0;
    if (ov > ovMax)
      bad.push(
        `★조각이 ${ov.toFixed(1)}초 겹친다 — 원본 ${order[i].t0.toFixed(1)}~${order[i - 1].t1.toFixed(1)} 이 두 번 나온다. 한쪽 끝을 물러라`,
      );
  }

  // ── ★★★밀도 (정답지 G-밀도) — 결말 점프(마지막 P5 조각 ≤ 규격 결말점프_최대_s)는 스팬에서 제외 (2026-09-01 A안)
  const [loD, hiD] = E.density;
  const tail = segs[segs.length - 1];
  const isEndingJump = segs.length > 1 && tail.phase === 5 && tail.t1 - tail.t0 <= E.결말점프_최대_s;
  const spanSegs = isEndingJump ? segs.slice(0, -1) : segs;
  const span = Math.max(...spanSegs.map((s) => s.t1)) - Math.min(...spanSegs.map((s) => s.t0));
  const clusterTotal = spanSegs.reduce((a, s) => a + (s.t1 - s.t0), 0);
  const dens = span > 0 ? clusterTotal / span : 1.0;
  if (dens < loD)
    bad.push(
      `★밀도 ${(dens * 100).toFixed(0)}% — 원본 ${span.toFixed(0)}초에 걸쳐 ${total.toFixed(0)}초를 뽑았다. ${(loD * 100).toFixed(0)}% 이상이어야 한다. **넓게 퍼뜨리면 맥락이 끊겨 이야기가 안 이어진다** — 좋은 대목이 몰린 곳으로 범위를 좁혀라`,
    );
  else if (dens > hiD) warn.push(`밀도 ${(dens * 100).toFixed(0)}% — 한 구간을 통으로 쓴 것에 가깝다. 원본의 늘어짐이 그대로 남는다`);

  // ── Phase 몫 (정답지 G-Phase몫) — 시간표는 「예시」, 통째로 먹는 것만 막는다
  const shareMax = G구조["G-Phase몫"].배수_max;
  const span50 = PHASES.get(5)!.sec[1] || 50;
  for (const [no, p] of PHASES) {
    const got = segs.filter((s) => s.phase === no).reduce((a, s) => a + (s.t1 - s.t0), 0);
    if (!got) continue;
    const want = (p.sec[1] - p.sec[0]) / span50;
    if (got / total > want * shareMax)
      bad.push(
        `★P${no} ${p.name} 가 ${got.toFixed(0)}초(${((got / total) * 100).toFixed(0)}%)를 차지한다 — 한 칸이 편을 통째로 먹었다. 나머지 Phase 가 밀려난다. 짧게 자르거나 쪼개라`,
      );
  }

  // ── Climax 위치 (정답지 G-Climax위치)
  const minPos = G구조["G-Climax위치"].min_pos;
  let at = 0;
  let climaxAt: number | null = null;
  for (const s of segs) {
    if (s.phase === 4 && climaxAt === null) climaxAt = at;
    at += s.t1 - s.t0;
  }
  if (climaxAt !== null && total && climaxAt / total < minPos)
    bad.push(
      `★Climax 가 너무 빠르다 — ${climaxAt.toFixed(0)}초(${((climaxAt / total) * 100).toFixed(0)}% 지점). 전체의 ${minPos * 100}% 를 지나서 와야 한다`,
    );

  // ── ★결말 (정답지 G-결말, hard) — 절대 지침: 끝에는 반전 또는 결론이 반드시 있다 (2026-09-01)
  const last = segs[segs.length - 1];
  if (last.phase !== 5) bad.push(`마지막 조각이 Phase 5(Punchline)가 아니다 — P${last.phase}`);
  else if ((last.punch ?? 0) < PHASES.get(5)!.min_punch)
    bad.push(
      `★결말이 약하다 — 마지막 조각 punch ${last.punch} (Punchline 은 ${PHASES.get(5)!.min_punch} 이상). 딱지가 아니라 결말이 필요하다 — 상황이 뒤집히거나(반전) 닫히는(결론) 대목을 원본에서 찾아 마지막 조각으로 넣어라. 그 클러스터에 결말이 없으면 다른 클러스터(focus_sec)로 편을 다시 잡는다`,
    );
  const endType = (proj.ending?.type ?? "").trim();
  const endDesc = (proj.ending?.desc ?? "").trim();
  if (!["반전", "결론"].includes(endType) || !endDesc)
    bad.push(
      `★ending 이 없다(또는 type 이 반전/결론이 아니다) — 이 편이 무엇으로 끝나는지 한 문장(desc)으로 적어야 한다. 한 문장으로 적을 수 없다면 결말이 없는 것이다 — 결말 대목까지 범위를 잡거나 클러스터를 바꿔라. 없는 결말을 지어내지는 않는다`,
    );

  for (const s of segs) {
    const ph = PHASES.get(s.phase ?? 0);
    if (ph && (s.punch ?? 0) < ph.min_punch) warn.push(`P${s.phase} ${ph.name} 조각의 punch ${s.punch} — 이 자리는 ${ph.min_punch} 이상이 어울린다`);
  }

  // ── 나레이션 (정답지 G-나레이션) — 패딩 법칙
  const narrMax = spec.narration.max_sec;
  const padSlack = G나레.패딩_여유_soft_sec;
  let narrChars = 0;
  segs.forEach((s, i) => {
    const nr = (s.narration ?? "").trim();
    if (!nr) return;
    narrChars += nr.length;
    const need = nr.length * SEC_PER_CHAR;
    if (need > narrMax) bad.push(`조각 ${i} 나레이션이 ${need.toFixed(1)}초짜리다 — ${narrMax.toFixed(0)}초 이내로 줄여라: ${nr.slice(0, 30)}`);
    const segSpan = s.t1 - s.t0;
    if (segSpan < need) bad.push(`★조각 ${i} 패딩 부족 — 나레이션은 ${need.toFixed(1)}초인데 화면은 ${segSpan.toFixed(1)}초다. 다음 대사가 겹쳐 튀어나온다`);
    else if (segSpan < need + padSlack) warn.push(`조각 ${i} 패딩이 빠듯하다 (나레 ${need.toFixed(1)}초 / 화면 ${segSpan.toFixed(1)}초)`);
  });
  const nrs = segs.filter((s) => (s.narration ?? "").trim());
  if (!nrs.length) warn.push("나레이션이 하나도 없다 — 이 채널의 핵심 장치다");
  else if (nrs.length > G나레.개수_권장[1] + 1) warn.push(`나레이션 ${nrs.length}개 — ${G나레.개수_권장.join("~")}개면 충분하다. 많으면 설명이 된다`);
  for (const s of nrs) {
    const ph = s.phase ?? 0;
    if ((G나레.금지_phase as number[]).includes(ph))
      bad.push(
        `★P${ph} ${PHASES.get(ph)?.name} 에 나레이션이 있다 — 그 구간은 원음이 죽는다. **훅과 펀치라인은 배우 말이 들려야 한다**: ${(s.narration ?? "").slice(0, 24)}`,
      );
    else if ((s.punch ?? 0) >= 9) warn.push(`punch ${s.punch} 조각에 나레이션이 있다 — 웃음이 터지는 대사를 덮는 것은 아닌지 본다`);
  }

  // ── 제목 (정답지 G-제목) — 화면에 박히는 title 만 hard, 후보는 soft
  const tb = spec.layout.title;
  const title: string[] = typeof proj.title === "string" ? [proj.title] : (proj.title ?? []);
  const titles = proj.title_candidates ?? (title.length ? [title] : []);
  if (!title.length) bad.push("제목이 없다");
  else {
    if (title.length !== tb.lines) bad.push(`제목이 ${title.length}줄 — 이 채널은 항상 ${tb.lines}줄이다: ${title.join(" / ")}`);
    for (const ln of title) if (ln.length > tb.max_chars) bad.push(`제목 한 줄이 ${ln.length}자 — 상한 ${tb.max_chars}자다: ${ln}`);
    const end = spec.title_formula.end_mark;
    if (title.length && !end.some((m) => title[title.length - 1].endsWith(m)))
      bad.push(`★제목 끝이 ? ! ... 이 아니다 — 호기심이 안 남는다: ${title[title.length - 1]}`);
  }
  const over = titles.filter((t) => (Array.isArray(t) ? t : [t]).some((ln) => ln.length > tb.max_chars));
  if (over.length) warn.push(`후보 ${over.length}개가 한 줄 ${tb.max_chars}자를 넘는다 — 고를 때 뺀다`);
  if (titles.length < spec.output.titles) warn.push(`제목 후보 ${titles.length}개 — ${spec.output.titles}개를 뽑는다`);
  if (!(proj.hashtag ?? "").trim()) warn.push("서브 해시태그가 없다");
  if ((proj.hooks ?? []).length < spec.output.hook_lines) warn.push(`후킹 대사 ${(proj.hooks ?? []).length}개 — ${spec.output.hook_lines}개를 뽑는다`);

  // ── ★구두점 금지 (정답지 G-구두점, hard · 2026-09-01 절대 규칙) — 나레이션·자막에 마침표·쉼표 등 금지
  const banned: string[] = spec.layout.subtitle.구두점_금지 ?? [];
  const hasBanned = (t: string) => banned.some((ch) => t.includes(ch));
  const dirtySubs = (proj.subs ?? []).filter((s) => hasBanned(s.text ?? ""));
  const dirtyNarr = segs.filter((s) => hasBanned(s.narration ?? ""));
  if (dirtySubs.length || dirtyNarr.length)
    bad.push(
      `★구두점 금지(절대 규칙) — 자막 ${dirtySubs.length}줄·나레이션 ${dirtyNarr.length}건에 금지 글자(${banned.join(" ")})가 있다. 마침표·말줄임은 지우고 쉼표는 공백으로 바꿔라 (예: ${(dirtySubs[0]?.text ?? dirtyNarr[0]?.narration ?? "").slice(0, 20)})`,
    );

  // ── 자막 (정답지 G-자막공백·G-자막자수)
  const subs = [...(proj.subs ?? [])].sort((a, b) => a.t - b.t);
  const gapWarn = G자막["G-자막공백"].빈구간_warn_sec;
  const gaps: [number, number][] = [];
  for (let i = 1; i < subs.length; i++) if (subs[i].t - subs[i - 1].t >= gapWarn) gaps.push([subs[i - 1].t, subs[i].t]);
  if (gaps.length) warn.push(`자막이 ${gapWarn}초 이상 비는 곳 ${gaps.length}군데 (예: ${gaps[0][0].toFixed(0)}~${gaps[0][1].toFixed(0)}초)`);
  const longs = subs.filter((s) => (s.text ?? "").length > spec.layout.subtitle.max_chars);
  if (longs.length) warn.push(`자막 ${longs.length}줄이 ${spec.layout.subtitle.max_chars}자를 넘는다`);

  // ── 원본 (정답지 G-원본) — fps 는 서버가, 파일 존재는 러너(make.py)가 잡는다
  if (!proj.source?.fps) bad.push("원본 fps 가 없다 — 마진이 프레임 단위라 fps 없이는 못 굽는다");

  return {
    bad,
    warn,
    metrics: {
      total_sec: Math.round(total * 10) / 10,
      density: Math.round(dens * 1000) / 1000,
      ending: endDesc ? `${endType} — ${endDesc}` : null,
      phase_seq: used,
      seg_count: segs.length,
      narr_count: nrs.length,
      narr_chars: narrChars,
      tts_est_sec: Math.round(narrChars * SEC_PER_CHAR * 10) / 10,
      sub_count: subs.length,
      fps: proj.source?.fps ?? null,
    },
  };
}

function mkCheck(name: Step, next: Step, when: string): StepHandler {
  return {
    name,
    run({ preset, payload }) {
      const workdir = str(payload, "workdir");
      const projectPath = str(payload, "project_path");
      const proj = payload.project;
      if (!isProject(proj)) {
        return base(name, preset, {
          status: "error",
          next_step: name,
          message: "payload.project 가 없거나 편.json 모양이 아니다 (segments 필요)",
          instructions: [
            `plan 이 만든 projects/<슬러그>.json 을 **한 글자도 고치지 말고** JSON 그대로 payload.project 에 싣고, 그 경로를 payload.project_path 에, 작업 폴더를 payload.workdir 에 실어 ${name} 을 다시 부르라.`,
          ],
        });
      }
      const v = judge(proj);
      if (v.bad.length) {
        return base(name, preset, {
          status: "error",
          next_step: name,
          message: `게이트 불통 ${v.bad.length}건 — 고쳐야 굽는다 (${when})`,
          instructions: [
            "① 아래 반려 목록대로 편.json(프로젝트 파일)을 고친다 — 원문에 없는 값을 지어내지 않는다. 구간·phase·나레이션은 원본과 대본 규칙(대본.md)에서만 온다.",
            `② 고친 편.json 전체를 payload.project 에 다시 실어 ${name} 을 부른다.`,
            "③ 구간(t0·t1)을 고쳤다면 이후 자막·나레이션도 다시 뽑아야 한다 — 시각이 어긋난 채로 남는다.",
          ],
          then_call_with: [`step: '${name}'`, "payload: { workdir, project_path, project: <고친 편.json 전체> }"],
          metrics: v.metrics,
          rejected: v.bad,
          ...(v.warn.length ? { warnings: v.warn } : {}),
        });
      }
      return base(name, preset, {
        status: "execute",
        next_step: next,
        message: `게이트 통과 (${when})${v.warn.length ? ` — 주의 ${v.warn.length}건` : ""}. ${next} 를 부르라.`,
        instructions: [
          "① metrics 는 이 단계가 잰 숫자다. 사람에게 한 줄로 보여준다 (특히 밀도·길이·ending — 결말이 사람 마음에 안 들면 여기서 세운다, 렌더 뒤가 아니라).",
          ...(next === "sk_cut"
            ? [
                "② ★★렌더 전 사장님 승인(2026-09-01 절차) — 계획 표(조각·what·punch·ending·제목 후보)를 보여 드리고 「이대로 가자」를 받은 뒤에만 sk_cut 로 간다. 게이트는 산수만 보고 punch 는 모델 자기채점이다 — 재미의 판정자는 사람이다.",
              ]
            : []),
          `${next === "sk_cut" ? "③" : "②"} carry 값(workdir·project_path·source·tts_est)을 payload 에 그대로 실어 ${next} 를 부른다. project 본문은 다시 싣지 않는다 — 러너가 파일에서 읽는다.`,
        ],
        then_call_with: [`step: '${next}'`, "payload: { workdir, project_path, source, tts_est }"],
        metrics: v.metrics,
        carry: ["workdir", "project_path", "source", "tts_est"],
        workdir,
        project_path: projectPath,
        source: payload.source,
        tts_est: { chars: v.metrics.narr_chars, est_sec: v.metrics.tts_est_sec },
        ...(v.warn.length ? { warnings: v.warn } : {}),
      });
    },
  };
}

/** 계획 직후 판정 — 통과하면 1차 렌더(sk_cut) */
export const skCheck = mkCheck("sk_check", "sk_cut", "계획 검사");
/** 자막 싱크 뒤 재판정 — 통과하면 완성 렌더(sk_render) */
export const skRecheck = mkCheck("sk_recheck", "sk_render", "싱크 후 재검사");
