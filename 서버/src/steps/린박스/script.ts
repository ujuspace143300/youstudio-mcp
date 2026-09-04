/**
 * steps/린박스/script.ts — lb_script: 블록 대본(N/D)·제목(지침서 절차)·강조·모션자막 → authored.json + 게이트.
 *
 * 볼케이노 키트 대응: author.py(본보기) · 제목 지침서 [단계 2] · 대본검사.py · 제목검사.py · 구둣점검사(작품 카드) · 규격 §11·§16·§28·§33·§60·§85·§89·§90.
 * 세 번 부른다 (payload 로 가른다):
 *   ① authored 없음 → need_input: 대본(authored)·제목 후보(≥4, 앵글 달리)·사장님이 고른 제목(title_choice). 집필 지침은 스타일/린박스/대본.md 가 정본.
 *   ② authored 있음·script_log 없음 → 서버 검사(구조·제목 2줄 10자·구두점·모션자막 안전대·길이 어림) → do[] 로 authored.json 쓰기 → jobs 대본검사.py·제목검사.py → 로그를 재 온다.
 *   ③ script_log 있음 → ✗ 가 있으면 반려(고치는 길), 없으면 편정보.json 제목 갱신(write_files) → next_step=lb_voice.
 * 유료 없음.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, ours, r3, readCarry, spec, str } from "./lib.js";

type NBlock = ["N", string, [number, number][]];
type DSeg = [number, number, string, string, string];
type DBlock = ["D", DSeg[]];
type Block = NBlock | DBlock;
interface Authored { HEADLINE?: unknown; CREDIT?: unknown; BLOCKS?: unknown; EFFECTS_BY_BLOCK?: unknown; 강조?: unknown }

const S = spec as unknown as {
  edit: { target_sec: [number, number] };
  layout: { title: { lines: number; max_chars: number }; motion_sub: { safe_y: [number, number]; per_episode: number }; subtitle: { card_chars_narr: number; 구두점_금지: string[] } };
  narration: { style: string };
};
const O = ours as unknown as { tts: { chars_per_sec: number } };
const 구두점 = S.layout.subtitle.구두점_금지;
const 이모지 = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

function hasPunct(t: string): boolean {
  return 구두점.some((c) => t.includes(c));
}

/** 대본 한 벌을 검사한다 — 반려 사유(hard)·경고(soft)·어림값 */
export function judgeAuthored(a: Authored, spanS: number, credit: string[]) {
  const bad: string[] = [];
  const warn: string[] = [];
  const H = Array.isArray(a.HEADLINE) ? (a.HEADLINE as unknown[]).map((x) => String(x ?? "").trim()) : [];
  if (H.length !== S.layout.title.lines || H.some((l) => !l)) bad.push(`HEADLINE 은 ${S.layout.title.lines}줄이라야 한다 — 지금 ${H.length}줄 (제목 지침서 [단계 2] ①)`);
  H.forEach((l, i) => {
    if (l.length > S.layout.title.max_chars) bad.push(`제목 ${i + 1}줄 「${l}」 가 ${l.length}자 — ${S.layout.title.max_chars}자 이내(띄어쓰기 포함)`);
    if (이모지.test(l)) bad.push(`제목 ${i + 1}줄 「${l}」 에 이모지 — 헤드라인엔 넣지 않는다`);
  });
  const C = Array.isArray(a.CREDIT) ? (a.CREDIT as unknown[]).map((x) => String(x ?? "").trim()).filter((x) => x) : [];
  if (!C.length) bad.push("CREDIT 이 비었다 — 편정보의 크레딧 두 줄을 그대로 넣어라(서버가 필수로 받는다)");
  else if (credit.length && JSON.stringify(C) !== JSON.stringify(credit)) warn.push(`CREDIT 이 편정보의 크레딧과 다르다 — 편정보 «${credit.join(" / ")}» 가 정본이다(§70)`);

  const B = Array.isArray(a.BLOCKS) ? (a.BLOCKS as unknown[]) : [];
  if (!B.length) bad.push("BLOCKS 가 비었다");
  let nCount = 0, dCount = 0, narrChars = 0, dlgSec = 0, cards = 0;
  const narrTexts: string[] = [];
  B.forEach((b, i) => {
    if (!Array.isArray(b) || (b[0] !== "N" && b[0] !== "D")) { bad.push(`BLOCKS[${i}] 는 ['N', 문장, [[화면초, 1]]] 또는 ['D', [[시작, 끝, 자막, 'quote', 읽는말]]] 이어야 한다`); return; }
    if (b[0] === "N") {
      const [, text, at] = b as NBlock;
      nCount++;
      const t = String(text ?? "").trim();
      narrTexts.push(t);
      narrChars += t.replace(/\s/g, "").length;
      if (!t) bad.push(`BLOCKS[${i}] 나레 문장이 비었다`);
      if (hasPunct(t)) bad.push(`BLOCKS[${i}] 나레 「${t}」 에 구두점(${구두점.join(" ")}) — 나레·자막에 쓰지 않는다`);
      if (!Array.isArray(at) || !at.length || !Array.isArray(at[0]) || typeof at[0][0] !== "number") bad.push(`BLOCKS[${i}] 나레 화면 시각 [[초, 1]] 이 없다`);
      else if (at[0][0] < 0 || at[0][0] > spanS) bad.push(`BLOCKS[${i}] 나레 화면 시각 ${at[0][0]}초가 구간(0~${spanS}) 밖`);
      const cardLen = Math.ceil(t.replace(/\s/g, "").length / S.layout.subtitle.card_chars_narr);
      cards += Math.max(1, cardLen);
    } else {
      const [, segs] = b as DBlock;
      dCount++;
      if (!Array.isArray(segs) || !segs.length) { bad.push(`BLOCKS[${i}] 원음 블록에 대사가 없다`); return; }
      segs.forEach((sg, j) => {
        if (!Array.isArray(sg) || typeof sg[0] !== "number" || typeof sg[1] !== "number" || typeof sg[2] !== "string") { bad.push(`BLOCKS[${i}][${j}] 는 [시작, 끝, 자막, 'quote', 읽는말]`); return; }
        const [s, e, cap] = sg;
        if (e <= s) bad.push(`BLOCKS[${i}][${j}] 끝(${e}) ≤ 시작(${s})`);
        if (s < 0 || e > spanS + 0.5) bad.push(`BLOCKS[${i}][${j}] ${s}~${e}초가 구간(0~${spanS}) 밖 — 구간 기준 초로 적는다(소재 초 아님)`);
        dlgSec += Math.max(0, e - s);
        if (hasPunct(cap)) bad.push(`BLOCKS[${i}][${j}] 자막 「${cap}」 에 구두점 — 쉼표는 공백으로, 마침표는 지운다(«|» 로 카드를 나눈다)`);
        cards += Math.max(1, cap.split("|").length);
        const longest = Math.max(...cap.split("|").map((c) => c.replace(/\s/g, "").length));
        if (longest > 10) warn.push(`BLOCKS[${i}][${j}] 카드 「${cap}」 한 토막이 ${longest}자 — 원음 카드는 5~8자(§90), «|» 로 나눈다`);
      });
    }
  });
  const narrSec = r3(narrChars / O.tts.chars_per_sec);
  const est = r3(dlgSec + narrSec);
  const [lo, hi] = S.edit.target_sec;
  if (B.length && est < lo) bad.push(`대본 어림 ${est}초(원음 ${r3(dlgSec)} + 나레 ${narrSec}) — 규격 최소 ${lo}초에 못 미친다. 대목을 더 담아라(결말까지)`);
  if (est > hi) warn.push(`대본 어림 ${est}초 — 규격 ${lo}~${hi}초를 넘는다. 늘어지는 블록을 빼라`);
  if (nCount && (nCount < 15 || nCount > 19)) warn.push(`나레 ${nCount}장 — 채널 말투는 한 편 15~19장(카드 3절)`);
  narrTexts.forEach((t) => { const n = t.replace(/\s/g, "").length; if (n > 16) warn.push(`나레 「${t}」 ${n}자 — 한 장 6~10자, 카드 16자 이내(§16)`); });
  const ratio = est ? Math.round((dlgSec / est) * 100) : 0;

  const FX = Array.isArray(a.EFFECTS_BY_BLOCK) ? (a.EFFECTS_BY_BLOCK as unknown[]) : [];
  const [y0, y1] = S.layout.motion_sub.safe_y;
  FX.forEach((f, i) => {
    if (!Array.isArray(f) || f.length < 7) { bad.push(`EFFECTS_BY_BLOCK[${i}] 는 [블록, 늦출초, 길이, 색, 문구, x, y] 7칸`); return; }
    const [blk, , , , text, , y] = f as [number, number, number, string, string, number, number];
    if (typeof blk !== "number" || blk < 0 || blk >= B.length) bad.push(`EFFECTS_BY_BLOCK[${i}] 블록 번호 ${blk} 가 BLOCKS 밖`);
    if (typeof y !== "number" || y < y0 || y > y1) bad.push(`EFFECTS_BY_BLOCK[${i}] 「${text}」 y=${y} — 안전대 ${y0}~${y1} 안이어야 한다(작업규칙 완성검사 5)`);
  });
  if (FX.length && (FX.length < 4 || FX.length > 6)) warn.push(`모션자막 ${FX.length}장 — 한 편 4~6장(§5)`);
  const emph = Array.isArray(a.강조) ? (a.강조 as unknown[]).map(String) : [];
  if (emph.length > 2) warn.push(`강조 ${emph.length}장 — 한 편에 한두 장(§28)`);
  const allCaps = B.flatMap((b) => (Array.isArray(b) && b[0] === "D" ? (b[1] as DSeg[]).map((s) => s[2]) : []));
  emph.forEach((e) => { if (!allCaps.some((c) => c.includes(e))) warn.push(`강조 「${e}」 가 어느 자막 글자에도 없다 — 카드 문구와 글자가 똑같아야 한다(§28)`); });

  return { bad, warn, metrics: { n_blocks: nCount, d_blocks: dCount, dlg_sec: r3(dlgSec), narr_chars: narrChars, narr_sec: narrSec, est_sec: est, dlg_ratio_pct: ratio, cards_est: cards, effects: FX.length, emph: emph.length } };
}

export const lbScript: StepHandler = {
  name: "lb_script",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_script", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_plan 응답의 carry 값을 payload 에 그대로 실어 lb_script 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    const spanS = r3(carry.end_s - carry.start_s);
    const 편정보 = (typeof payload.편정보 === "object" && payload.편정보 !== null ? payload.편정보 : null) as { 크레딧?: unknown } | null;
    const credit = Array.isArray(편정보?.크레딧) ? (편정보!.크레딧 as unknown[]).map(String) : [];
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, scene_count: payload.scene_count ?? null, 대사: payload.대사, 편정보: payload.편정보,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "scene_count", "대사", "편정보"];

    // ── ③ 게이트 로그 검사 ──────────────────────────────────────────────
    if (payload.script_log !== undefined) {
      const log = String(payload.script_log ?? "");
      const tlog = String(payload.title_log ?? "");
      const bad = [...log.split("\n"), ...tlog.split("\n")].filter((l) => l.includes("✗")).map((l) => l.trim());
      if (bad.length || /막힘 \d+건/.test(log)) {
        return reject("lb_script", preset, `굽기 전 게이트가 막았다 (${bad.length}건)`, "대본검사.py: 원음 블록의 시작이 장면전환에 붙지 않았거나 전환을 가로질러 짧은 조각이 남는다 — 그 블록의 시작·끝을 scene_cuts.txt 의 전환 앞뒤로 옮기거나 그 대사를 빼라(§20·§30). 제목검사.py: 지침서 [단계 2] 대로 다시 짓는다. 고친 authored 를 실어 lb_script 를 다시 부르라(script_log 는 빼고). " + bad.slice(0, 8).join(" | "));
      }
      const a = payload.authored as Authored | undefined;
      const H = Array.isArray(a?.HEADLINE) ? (a!.HEADLINE as unknown[]).map(String) : [];
      const 편정보새 = { ...(편정보 ?? {}), 제목: H };
      return base("lb_script", preset, {
        status: "execute",
        next_step: "lb_voice",
        message: `대본 게이트 통과 — 제목 「${H.join(" / ")}」. 편정보.json 의 제목을 맞추고 lb_voice(★유료 TTS)로.`,
        instructions: [
          "① write_files 대로 편정보.json 을 다시 쓴다(제목 = authored HEADLINE — 다르면 서버 자막과 우리 제목이 갈린다, 한번에.sh 첫 관문).",
          "② carry 의 값(… authored 포함)을 payload 에 그대로 실어 lb_voice 를 부른다 — 유료(Typecast) 단계라 그 응답이 먼저 비용을 묻는다.",
        ],
        then_call_with: ["step: 'lb_voice'", "payload: { …carry, authored, 편정보 }"],
        jobs_kind: null,
        jobs: [],
        write_files: [{ path: join(carry.ep_dir, "편정보.json"), content: 편정보새 as Record<string, unknown>, note: "제목을 authored HEADLINE 으로 (규격 §70·§39)" }],
        measure: [],
        metrics: (payload.script_metrics as Record<string, unknown> | undefined) ?? {},
        carry: [...carryKeys, "authored"],
        ...common,
        편정보: 편정보새,
        authored: payload.authored,
      });
    }

    // ── ② 대본 검사 → 파일 쓰기 + 게이트 도구 ─────────────────────────────
    if (payload.authored !== undefined) {
      if (!repo) return reject("lb_script", preset, "payload.repo(저장소 루트 절대경로)가 없다", "carry 의 repo 를 실어 다시 부르라.");
      const a = (typeof payload.authored === "object" && payload.authored !== null ? payload.authored : {}) as Authored;
      const choice = Array.isArray(payload.title_choice) ? (payload.title_choice as unknown[]).map((x) => String(x ?? "").trim()) : null;
      const H = Array.isArray(a.HEADLINE) ? (a.HEADLINE as unknown[]).map((x) => String(x ?? "").trim()) : [];
      const v = judgeAuthored(a, spanS, credit);
      if (!choice) v.bad.unshift("payload.title_choice(사장님이 고른 제목 2줄)가 없다 — 후보 4개 이상을 제시하고 사장님이 고른 것을 실어라(작업규칙 2026-09-01). 클로드가 혼자 확정하지 않는다");
      else if (JSON.stringify(choice) !== JSON.stringify(H)) v.bad.unshift(`authored.HEADLINE 「${H.join(" / ")}」 이 사장님이 고른 제목 「${choice.join(" / ")}」 과 다르다`);
      if (v.bad.length) {
        return reject("lb_script", preset, `대본이 아직 맞지 않다 (${v.bad.length}건)`, v.bad.map((x, i) => `${i + 1}) ${x}`).join(" ") + (v.warn.length ? " ▲경고: " + v.warn.join(" · ") : ""));
      }
      const authored = { HEADLINE: H, CREDIT: Array.isArray(a.CREDIT) ? a.CREDIT : credit, BLOCKS: a.BLOCKS, EFFECTS_BY_BLOCK: a.EFFECTS_BY_BLOCK ?? [], ...(Array.isArray(a.강조) ? { 강조: a.강조 } : {}) };
      return base("lb_script", preset, {
        status: "execute",
        next_step: "lb_script",
        message: `대본 서버 검사 통과 — 원음 ${v.metrics.dlg_sec}초 + 나레 ${v.metrics.narr_chars}자(${v.metrics.narr_sec}초) ≈ ${v.metrics.est_sec}초 · 원음:나레 ${v.metrics.dlg_ratio_pct}:${100 - v.metrics.dlg_ratio_pct} · 블록 N${v.metrics.n_blocks}/D${v.metrics.d_blocks} · 모션자막 ${v.metrics.effects}장. 이제 편 폴더에 authored.json 을 쓰고 굽기 전 게이트(대본검사·제목검사)를 돌려 로그를 실어 다시 부르라.`,
        instructions: [
          `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 실행한다. do 의 write_authored 가 먼저 authored.json 을 쓴다.`,
          "② 대본검사.py — 원음 블록이 장면전환(scene_cuts.txt)에 붙었는가·전환을 가로지르는 짧은 조각(<1.00초)이 없는가 (§64·§8 7c «건너뛸 수 없다»). 제목검사.py — 지침서 [단계 2](2줄·10자·이모지·음슴체·대화체 금지).",
          "③ measure 대로 두 로그를 payload.script_log·payload.title_log 에 실어 lb_script 를 **다시** 부른다. ✗ 가 있으면 서버가 반려한다 — 실패 rc 라도 로그는 실어 보내라.",
        ],
        then_call_with: ["step: 'lb_script'", "payload: { …carry, authored, title_choice, script_log: <대본검사 stdout>, title_log: <제목검사 stdout> }"],
        jobs_kind: "argv",
        jobs_cwd: carry.ep_dir,
        do: [{
          name: "write_authored",
          argv: ["python", "-c", "import json,sys;json.dump(json.loads(sys.argv[1]),open('authored.json','w',encoding='utf-8'),ensure_ascii=False,indent=1);print('authored.json')", JSON.stringify(authored)],
          out: join(carry.ep_dir, "_authored_log.txt"),
          note: "블록 대본 → 편 폴더 authored.json (author.py 가 내던 꼴 그대로: HEADLINE·CREDIT·BLOCKS·EFFECTS_BY_BLOCK·강조).",
        }],
        jobs: [
          { name: "script_check", argv: ["python", tool("대본검사.py")], optional: true, note: "굽기 전 대본 게이트 — 막힘이면 rc 1 + «✗» 줄. optional 은 러너가 멈추지 말고 로그를 실어 오라는 뜻(판정은 서버)." },
          { name: "title_check", argv: ["python", tool("제목검사.py")], optional: true, note: "제목 지침서 [단계 2] 게이트 — rc 1 + «✗» 줄." },
        ],
        measure: [
          { as: "script_log", from: "job:script_check", unit: "stdout" },
          { as: "title_log", from: "job:title_check", unit: "stdout" },
        ],
        metrics: v.metrics,
        carry: [...carryKeys, "authored", "title_choice", "script_metrics"],
        ...common,
        authored,
        title_choice: choice,
        script_metrics: v.metrics,
        ...(v.warn.length ? { warnings: v.warn } : {}),
      });
    }

    // ── ① 집필 지시 (need_input) ────────────────────────────────────────
    const guide = String((spec as unknown as { _guide?: string })._guide ?? "");
    return base("lb_script", preset, {
      status: "need_input",
      next_step: "lb_script",
      message: `대본과 제목을 쓸 차례 — 구간 ${spanS}초 · 대사 낱말 ${Array.isArray((payload.대사 as { words?: unknown[] })?.words) ? ((payload.대사 as { words: unknown[] }).words.length) : "?"}개 · 장면전환 ${payload.scene_count ?? "?"}개. 집필 지침은 스타일/린박스/대본.md(setup 의 guideMd). 제목은 후보 4개 이상을 사장님께 보이고 고른 것을 실어라.`,
      need_input: {
        keys: ["authored", "title_candidates", "title_choice"],
        why: "대본(누가·무엇을)과 제목은 사람·클로드 몫이다. 서버는 꼴·규격·게이트만 잰다. 제목은 사장님이 고른다(작업규칙 2026-09-01) — 클로드가 혼자 확정하지 않는다.",
      },
      instructions: [
        "① 화자.json/화자줄.json 에 이름이 적혀 있는지 먼저 본다(§33). 대사표.txt 의 ★ 는 귀로 확인. 공식 SRT 가 있으면 자막 글자는 SRT 그대로(§85).",
        "② authored 를 짠다 — 본보기 꼴: {HEADLINE:[2줄], CREDIT:[편정보 크레딧], BLOCKS:[['N','나레 한 줄',[[화면초,1]]], ['D',[[시작,끝,'자막|카드','quote','읽는 말']]], …], EFFECTS_BY_BLOCK:[[블록,늦출초,길이,'#F070C0','한 마디',540,640] ×4~6], 강조:['카드 글자와 똑같은 한 줄']}. 시각은 **구간 기준 초**(소재 초 아님). 대목은 한 통으로 결말까지(§60·§89). 원음 카드는 «|» 로 5~8자(§90) · 나레는 조각체 ~죠 계열, 한 편 15~19장 · 한 장 6~10자, 관계를 짚는다(§89). 구두점 금지. 원음 77 : 나레 23 안팎.",
        "③ 제목 — 지침서 단계 0(웹 검색으로 팩트) → 템플릿 어미(~의 정체 · ~하면 벌어진 일 · ~해야 하는 이유 · ~하는 법) → **후보 4개 이상을 앵글 달리해 사장님께 제시** → 사장님이 고른 2줄(각 10자 이내·이모지 없음·원문에 없는 값 금지)을 title_choice 에, 같은 값을 authored.HEADLINE 에 넣는다.",
        "④ carry 와 함께 authored·title_candidates·title_choice 를 실어 lb_script 를 다시 부른다.",
      ],
      then_call_with: ["step: 'lb_script'", "payload: { …carry, authored: {…}, title_candidates: [[2줄],[2줄],[2줄],[2줄]], title_choice: [2줄] }"],
      jobs_kind: null,
      jobs: [],
      measure: [],
      metrics: { span_s: spanS, narr_style: S.narration.style },
      carry: carryKeys,
      ...common,
      ...(guide ? { guide } : {}),
    });
  },
};
