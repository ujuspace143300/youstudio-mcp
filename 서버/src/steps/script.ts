/**
 * steps/script.ts — 구간을 잇는 나레이션 집필. 명세: 설계/단계상세.md 「5. script」 (need_input 패턴)
 *
 * 두 번 부른다:
 *   ① payload.script 가 없으면 → status "need_input". 서버는 멈추고 지침을 내려보낸다:
 *      나레이션.md 전문 + 규격 「나레이션」(금지 목록) + 정답지 「대본」(대역) + 재료(selection 구간·브리지·시각 사실·장면 묘사·로그라인).
 *      클로드가 대화 안에서 블록(위치·본문·의도)을 쓴다.
 *   ② payload.script.blocks 가 있으면 → 기계 검사. hard 불통이면 어느 블록 어느 문장이 왜인지 + 수리 지침으로 반려.
 *      통과하면 write_files 로 script/script.json, metrics(블록 수·평균 자수·나레:대사 추정 비율 …). next_step=voice
 *
 * 나레 시간은 자수 × 규격 「나레이션.자당초_추정」 — **추정**이다. voice 실측이 생기면 재검한다.
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import answer from "../../../스타일/영화롱폼/정답지.json";
import guideMd from "../../../스타일/영화롱폼/나레이션.md";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";

interface NarSpec {
  문체: string; 결말모드: "spoiler" | "no_spoiler"; 문장_최대자수: number; 자당초_추정: number;
  금지표현: string[]; 금지표현_틀_정규식: string; 상투구: string[];
  나레_레지스터_치환: Record<string, string>; 해석표현: string[]; 선호종결: string[];
  시청자_수사의문_금지: string[]; 아웃트로_정보고지_금지_정규식: string[];
  노스포_금칙: { 반전예고: string[]; 결말노출: string[]; 부정문맥_예외: string[] };
  블록_위치_종류: string[];
}
interface Band { min?: number; max?: number; value?: number; 중앙?: number; 출처?: string; 적용?: string; [k: string]: unknown }
interface ScriptAnswer {
  문장_자수: Band; 조각_자수: Band; 미완결_문장_비율: Band; 어미_배합: Band; 같은어미_연속_max_문장: Band;
  말줄임_한문장_max: Band; 느낌닫기_구간당_max: Band; "G-턴비_나레대사_시간비": Band; "G-턴비_블록수비": Band; 나레_시간점유: Band; 블록_평균_자수: Band;
}
const N = (spec as unknown as { 나레이션: NarSpec })["나레이션"];
const A = (answer as unknown as { 대본: ScriptAnswer })["대본"];

function join(root: string, ...parts: string[]): string {
  return [root.replace(/[\/]+$/, ""), ...parts].join("/");
}
const r3 = (x: number) => Math.round(x * 1000) / 1000;
const norm = (t: string) => t.replace(/\s+/g, " ").trim();

// ── 입력 모양 ────────────────────────────────────────────────────────────
interface Segment { i: number; in: number; out: number; len_s: number; role: string; importance: number; kind: string; src: string[]; why: string }
interface Bridge { start: number; end: number; len_s: number; events: { n: number; summary: string; importance: number }[]; note?: string }
interface Selection { segments?: Segment[]; narration_bridges?: Bridge[]; metrics?: Record<string, unknown> }
interface Pos { kind: "over" | "before" | "after" | "bridge"; seg?: number; bridge?: number }
interface Block { pos: Pos; text: string; intent?: string }

// ── 어미 분류 (문장 끝 기준) ─────────────────────────────────────────────
type EndingClass = "습니다계" | "죠계" | "요계" | "의문형" | "평서체" | "기타";
function endingClass(sentence: string): EndingClass {
  const t = sentence.replace(/[.!?…]+$/g, "").replace(/\.\.!?$/g, "").trim();
  if (/니다$/.test(t)) return "습니다계"; // 습니다·입니다·됩니다·옵니다·갑니다 … (ㅂ니다 전부)
  if (/(죠|지요)$/.test(t)) return "죠계";
  if (/(까요|을까|ㄹ까|나요|가요)$/.test(t)) return "의문형";
  if (/(요)$/.test(t)) return "요계";
  if (/(한다|된다|였다|있다|없다|이다|았다|었다|겠다|다)$/.test(t)) return "평서체";
  return "기타";
}

export const script: StepHandler = {
  name: "script",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; title?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number } | undefined;
    const selection = payload.selection as Selection | undefined;
    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !selection || !Array.isArray(selection.segments)) {
      return reject(
        "script", preset,
        "payload 에 carry 값(source·workdir·probe_summary) 또는 selection(확정 구간)이 없다",
        "select 응답의 carry 값과 함께 payload.selection 에 clips/selection.json 의 내용, payload.visual 에 clips/visual.json 의 내용, payload.facts 에 facts.json, payload.brief 에 brief.json, payload.utterance_spans 에 [start,end] 배열을 실어 script 를 다시 부르라.",
      );
    }
    const segments = selection.segments!;
    const bridges = selection.narration_bridges ?? [];
    const outPath = join(workdir, "script", "script.json");
    const facts = (payload.facts ?? {}) as { visual_facts?: { t_s: number; fact: string }[]; ending_visual_only?: { note?: string } };
    const visual = (payload.visual ?? {}) as { silent?: { stretch?: { start_s: number; end_s: number }; scenes?: { start: number; end: number; what: string; importance: number; visual_facts?: string }[] }[]; ending?: { ending_summary?: string; beats?: { start: number; end: number; what: string; emotion?: string; importance: number; is_ending_beat?: boolean }[] } | null };
    const brief = (payload.brief ?? {}) as { logline?: string | null; events?: { n: number; start: number; end: number; summary: string; importance: number; spoiler?: boolean }[] };
    const spans = (payload.utterance_spans as [number, number][] | undefined) ?? [];

    // ── ① need_input ────────────────────────────────────────────────────
    if (payload.script === undefined) {
      const material = {
        title: source.title ?? null,
        logline: brief.logline ?? null,
        genre_hint: "drama (단편) — 드립 대신 감정 한 줄. 나레이션.md 1절 유머 강도 참조",
        segments: segments.map((s) => ({ i: s.i, in: s.in, out: s.out, len_s: s.len_s, role: s.role, importance: s.importance, src: s.src, why: s.why })),
        bridges: bridges.map((b, k) => ({ k, start: b.start, end: b.end, len_s: b.len_s, events: b.events })),
        visual_facts: facts.visual_facts ?? [],
        scenes: (visual.silent ?? []).flatMap((st, k) => (st.scenes ?? []).map((sc) => ({ stretch: k, start: sc.start, end: sc.end, what: sc.what, importance: sc.importance, visual_facts: sc.visual_facts ?? "" }))),
        ending: visual.ending ? { summary: visual.ending.ending_summary ?? null, beats: (visual.ending.beats ?? []).map((b) => ({ start: b.start, end: b.end, what: b.what, emotion: b.emotion ?? "", importance: b.importance, is_ending_beat: !!b.is_ending_beat })) } : null,
        events: (brief.events ?? []).map((e) => ({ n: e.n, start: e.start, end: e.end, summary: e.summary, importance: e.importance, spoiler: !!e.spoiler })),
      };
      return base("script", preset, {
        status: "need_input",
        next_step: "script",
        message: `나레이션 집필 차례 — guide(나레이션.md)대로 블록을 쓰고 payload.script = { blocks: [...] } 로 script 를 다시 부르라. 구간 ${segments.length}개 · 브리지 ${bridges.length}개.`,
        need_input: { keys: ["script"], why: "짧고 창의적인 집필은 대화 안에서 한다 (단계와게이트.md 「판정을 어디서 하는가」). 지침·재료는 이 응답에 있다." },
        instructions: [
          "① guide(나레이션.md 전문)를 읽는다. 숫자 대역은 answer_bands(정답지 「대본」), 금지 목록은 rules(규격 「나레이션」)에 있다.",
          "② material 의 구간(segments)·브리지(bridges)·시각 사실(visual_facts·scenes·ending)·사건(events)만 근거로 쓴다. 여기 없는 사건·이름·대사는 만들지 않는다.",
          "③ 블록 형식: { pos: {kind:'over'|'before'|'after'|'bridge', seg:<구간 i> | bridge:<브리지 k>}, text:'한 문장(조각은 .. 로 이어 붙임)', intent:'이 블록이 하는 일 한 줄' }. 원본대사 구간(role 원본대사)에는 before/after 로 짧게, 나레이션덮기·시각몽타주 구간에는 over 로, 브리지에는 bridge 로.",
          "④ payload.script = { blocks: [...] } 를 carry 값과 함께 실어 script 를 다시 부른다. 서버가 기계 검사(hard/soft)를 하고 불통이면 어느 블록이 왜인지 돌려준다 — 고쳐서 다시 부른다.",
        ],
        then_call_with: ["step: 'script'", "payload: { …carry, selection, visual, facts, brief, utterance_spans, script: { blocks: [ {pos, text, intent}, … ] } }"],
        jobs_kind: null, jobs: [], measure: [],
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "selection", "visual", "facts", "brief", "utterance_spans"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path,
        selection, visual, facts, brief, utterance_spans: spans,
        guide: guideMd,
        rules: N,
        answer_bands: A,
        material,
      });
    }

    // ── ② 기계 검사 ─────────────────────────────────────────────────────
    const sc = payload.script as { blocks?: Block[] };
    if (!sc || !Array.isArray(sc.blocks) || sc.blocks.length === 0) {
      return reject("script", preset, "payload.script.blocks 가 비었거나 배열이 아니다", "① 의 형식대로 blocks 배열을 채워 다시 부르라.");
    }
    const hard: string[] = [];
    const soft: string[] = [];
    const segById = new Map(segments.map((s) => [s.i, s]));
    const posKey = (p: Pos) => p.kind === "bridge" ? `bridge#${p.bridge}` : `seg#${p.seg}`;
    const bangByPos = new Map<string, number>();
    const endings: EndingClass[] = [];
    let totalChars = 0, sentTotal = 0, sentInBand = 0, incomplete = 0, pieceTotal = 0, pieceInBand = 0;
    const cliche = new RegExp(N.상투구.map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"));
    const bannedTemplate = new RegExp(N.금지표현_틀_정규식);
    const infoNotice = N.아웃트로_정보고지_금지_정규식.map((r) => new RegExp(r));
    const analyzed = sc.blocks.map((b, idx) => {
      const n = idx + 1;
      const label = `블록 ${n}`;
      const text = norm(String(b.text ?? ""));
      const p = b.pos ?? ({} as Pos);
      if (!p.kind || !N.블록_위치_종류.includes(p.kind)) hard.push(`${label}: pos.kind 가 ${N.블록_위치_종류.join("|")} 중 하나가 아니다`);
      else if (p.kind === "bridge") { if (typeof p.bridge !== "number" || !bridges[p.bridge]) hard.push(`${label}: pos.bridge=${p.bridge} 인 브리지가 없다 (0~${bridges.length - 1})`); }
      else { const s = typeof p.seg === "number" ? segById.get(p.seg) : undefined; if (!s) hard.push(`${label}: pos.seg=${p.seg} 인 구간이 없다`); }
      if (!text) { hard.push(`${label}: 본문이 비었다`); return { n, pos: p, text, intent: b.intent ?? "", chars: 0, pieces: [] as string[], ending: "기타" as EndingClass, est_s: 0 }; }
      // 형태 검사
      if (/\.\.\?/.test(text)) hard.push(`${label}: \`..?\` 금지 — 「${text}」`);
      if (/\.{3,}|…|~(?![가-힣])/.test(text)) hard.push(`${label}: \`...\`·\`…\`·\`~\` 금지 — \`..\` 하나뿐이다 — 「${text}」`);
      if (/[,，]/.test(text)) hard.push(`${label}: 쉼표 금지 — 「${text}」`);
      if (/(?<!\.)\.(?!\.)/.test(text)) hard.push(`${label}: 마침표(한 개) 금지 — \`..\` 만 쓴다 — 「${text}」`);
      if (/\?/.test(text)) hard.push(`${label}: 물음표 금지(시청자 향한 질문·엔딩 질문형) — 「${text}」`);
      const bangs = (text.match(/\.\.!/g) ?? []).length;
      const k = posKey(p);
      bangByPos.set(k, (bangByPos.get(k) ?? 0) + bangs);
      const dots = (text.match(/\.\./g) ?? []).length;
      if (dots > (A.말줄임_한문장_max.value ?? 2)) hard.push(`${label}: \`..\` 가 ${dots}개 — 한 문장 최대 ${A.말줄임_한문장_max.value} — 「${text}」`);
      // 금지 표현
      for (const w of N.금지표현) if (text.includes(w)) hard.push(`${label}: 금지 표현 「${w}」 — 「${text}」`);
      if (bannedTemplate.test(text)) hard.push(`${label}: 금지 틀 「이 작품은 단순한 ○○가 아닙니다」 — 「${text}」`);
      for (const w of N.시청자_수사의문_금지) if (text.includes(w)) hard.push(`${label}: 시청자 향한 수사의문 「${w}」 금지 — 「${text}」`);
      for (const rx of infoNotice) if (rx.test(text)) hard.push(`${label}: 정보 고지 사인오프 금지 — 「${text}」`);
      for (const [bad, good] of Object.entries(N.나레_레지스터_치환)) if (new RegExp(`(?<![가-힣])${bad}`).test(text)) hard.push(`${label}: 나레 레지스터 「${bad}」→「${good}」 — 「${text}」`);
      if (N.결말모드 === "no_spoiler") {
        for (const w of N.노스포_금칙.반전예고) if (text.includes(w)) hard.push(`${label}: [노스포] 반전 예고 어휘 「${w}」 — 「${text}」`);
        for (const w of N.노스포_금칙.결말노출) { const i = text.indexOf(w); if (i >= 0) { const tail = text.slice(i + w.length, i + w.length + 12); if (!N.노스포_금칙.부정문맥_예외.some((x) => tail.includes(x))) hard.push(`${label}: [노스포] 결말 노출 어휘 「${w}」 — 「${text}」`); } }
      }
      if (cliche.test(text)) soft.push(`${label}: 정리형 상투구 — 장면에 밀착한 구체적 반응으로 — 「${text}」`);
      // 길이·조각·어미
      const chars = text.length;
      totalChars += chars;
      if (chars > N.문장_최대자수) hard.push(`${label}: ${chars}자 > 문장 상한 ${N.문장_최대자수}자 — 「${text}」`);
      sentTotal++;
      if (chars >= (A.문장_자수.min ?? 0) && chars <= (A.문장_자수.max ?? 999)) sentInBand++;
      const pieces = text.split(/\.\.!?/).map((x) => x.trim()).filter(Boolean);
      if (pieces.length >= 2) incomplete++;
      for (const pc of pieces) { pieceTotal++; if (pc.length >= (A.조각_자수.min ?? 0) && pc.length <= (A.조각_자수.max ?? 999)) pieceInBand++; }
      const ec = endingClass(text);
      endings.push(ec);
      if (ec === "평서체") hard.push(`${label}: 평서체 어미(~다/~된다/~였다) 금지 — \`~습니다\`/\`~죠\` 로 — 「${text}」`);
      return { n, pos: p, text, intent: b.intent ?? "", chars, pieces, ending: ec, est_s: r3(chars * N.자당초_추정) };
    });
    for (const [k, c] of bangByPos) if (c > (A.느낌닫기_구간당_max.value ?? 1)) hard.push(`${k}: \`..!\` 가 ${c}회 — 같은 위치에서 ${A.느낌닫기_구간당_max.value}회까지`);
    // 같은 어미 연속
    let run = 1;
    for (let i = 1; i < endings.length; i++) { if (endings[i] === endings[i - 1] && endings[i] !== "기타") { run++; if (run === (A.같은어미_연속_max_문장.value ?? 3)) soft.push(`블록 ${i - run + 2}~${i + 1}: 같은 어미(${endings[i]}) ${run}문장 연속`); } else run = 1; }
    // 마지막 블록 — 아웃트로 질문형은 위에서 hard. 정보 고지도 위에서.

    // ── 지표 ───────────────────────────────────────────────────────────
    const blocks = analyzed;
    const count = blocks.length;
    const avgChars = r3(totalChars / count);
    const narEst = r3(blocks.reduce((a, b) => a + b.est_s, 0));
    // 원본대사 구간 안 발화 초 (utterance_spans 로)
    const dlgSegs = segments.filter((s) => s.role === "원본대사");
    let dlgS = 0;
    for (const [us, ue] of spans) for (const s of dlgSegs) { const o = Math.min(ue, s.out) - Math.max(us, s.in); if (o > 0) dlgS += o; }
    dlgS = r3(dlgS);
    const turnRatio = dlgS > 0 ? r3(narEst / dlgS) : null;
    const narShare = narEst + dlgS > 0 ? r3(narEst / (narEst + dlgS)) : null;
    const dist: Record<string, number> = {};
    for (const e of endings) dist[e] = (dist[e] ?? 0) + 1;
    const distRatio = Object.fromEntries(Object.entries(dist).map(([k, v]) => [k, r3(v / count)]));
    const coveredSegs = new Set(blocks.map((b) => b.pos.kind !== "bridge" ? b.pos.seg : -1));
    const uncoveredNonDialog = segments.filter((s) => s.role !== "원본대사" && !coveredSegs.has(s.i)).map((s) => s.i);
    const coveredBridges = new Set(blocks.filter((b) => b.pos.kind === "bridge").map((b) => b.pos.bridge));
    const uncoveredBridges = bridges.map((_, k) => k).filter((k) => !coveredBridges.has(k));

    // ── 게이트 ─────────────────────────────────────────────────────────
    const gates: { id: string; pass: boolean | null; hard: boolean; detail: string; fix?: string }[] = [];
    // 시간 기준 hard 게이트 = 나레 시간점유 (가족 G27). 정정 근거: 정답지.json 대본.나레_시간점유.적용 / 단계상세.md script
    const ns = A.나레_시간점유;
    const lo = ns.min ?? 0, hi = ns.max ?? 1;
    const sharePass = narShare === null ? null : narShare >= lo && narShare <= hi;
    // 대역에 들려면 나레 추정초가 [dlg·lo/(1-lo), dlg·hi/(1-hi)] 안이어야 한다
    const narLo = r3(dlgS * lo / (1 - lo)), narHi = r3(dlgS * hi / (1 - hi));
    gates.push({ id: "나레 시간점유(G27, 추정)", pass: sharePass, hard: true,
      detail: narShare === null ? "원본대사 구간 발화 0s — 미판정" : `나레 추정 ${narEst}s(자수 ${totalChars} × ${N.자당초_추정}s/자) ÷ (나레 ${narEst}s + 원본대사 발화 ${dlgS}s) = ${narShare} (대역 ${lo}~${hi} → 나레 ${narLo}~${narHi}s = ${Math.round(narLo / N.자당초_추정)}~${Math.round(narHi / N.자당초_추정)}자). 추정 — voice 실측으로 재검`,
      fix: sharePass === false ? (narShare! > hi ? `나레 과다 — 나레 ${r3(narEst - narHi)}s(≈${Math.round((narEst - narHi) / N.자당초_추정)}자)를 덜어내라: 설명 블록을 줄이거나 문장을 조여라. 구조적으로 대사가 적으면 규격 구간선택.역할규칙.원본대사_최소중요도 를 낮춰 원본대사 구간을 늘린다.` : `나레 부족 — 나레 ${r3(narLo - narEst)}s(≈${Math.round((narLo - narEst) / N.자당초_추정)}자)가 더 필요하다: 브리지·시각몽타주 구간에 원인·의미 블록을 더 써라(나레이션.md 2절).`) : undefined });
    const gt = A["G-턴비_나레대사_시간비"];
    gates.push({ id: "G-턴비(나레:대사 시간비, soft·추정)", pass: turnRatio === null ? null : turnRatio >= (gt.min ?? 0) && turnRatio <= (gt.max ?? 99), hard: false, detail: `${turnRatio} (대역 ${gt.min}~${gt.max} — 참고 지표. 정답지 대본.G-턴비_나레대사_시간비.적용)` });
    const gb = A["G-턴비_블록수비"];
    const dlgUtt = spans.filter(([us, ue]) => dlgSegs.some((s) => us < s.out && ue > s.in)).length;
    const blockRatio = dlgUtt > 0 ? r3(count / dlgUtt) : null;
    gates.push({ id: "G-턴비(블록수비 N÷D, soft)", pass: blockRatio === null ? null : blockRatio >= (gb.min ?? 0) && blockRatio <= (gb.max ?? 99), hard: false, detail: `나레 ${count}블록 ÷ 원본대사 발화 ${dlgUtt}건 = ${blockRatio} (대역 ${gb.min}~${gb.max}, 축 다름 — 검증 필요)` });
    gates.push({ id: "문장 자수 대역(soft)", pass: sentInBand / sentTotal >= 0.7, hard: false, detail: `대역 안 ${sentInBand}/${sentTotal} (대역 ${A.문장_자수.min}~${A.문장_자수.max}자, 평균 ${avgChars})` });
    gates.push({ id: "조각 자수 대역(soft)", pass: pieceTotal > 0 && pieceInBand / pieceTotal >= 0.6, hard: false, detail: `대역 안 ${pieceInBand}/${pieceTotal} (대역 ${A.조각_자수.min}~${A.조각_자수.max}자)` });
    gates.push({ id: "미완결 문장 비율(soft)", pass: incomplete / sentTotal >= (A.미완결_문장_비율.min ?? 0.7), hard: false, detail: `조각 2개 이상 문장 ${incomplete}/${sentTotal} = ${r3(incomplete / sentTotal)} (하한 ${A.미완결_문장_비율.min})` });
    const eb = A.어미_배합 as unknown as { 요계_max: number; 의문형_max: number };
    gates.push({ id: "어미 배합(soft)", pass: (distRatio["요계"] ?? 0) <= eb.요계_max + 0.05 && (distRatio["의문형"] ?? 0) <= eb.의문형_max + 0.05, hard: false, detail: JSON.stringify(distRatio) });
    for (const g of gates) if (g.pass === false && !g.hard) soft.push(`[soft] ${g.id}: ${g.detail}`);
    if (uncoveredNonDialog.length) soft.push(`나레 없는 나레이션덮기/시각몽타주 구간: ${uncoveredNonDialog.join(", ")} — 화면만 흐르는 자리다. 의도된 정적 구간이 아니면 over 블록을 붙여라.`);
    if (uncoveredBridges.length) soft.push(`나레 없는 브리지: ${uncoveredBridges.join(", ")} — 앞뒤가 안 이어진다.`);

    const hardGateFail = gates.filter((g) => g.hard && g.pass === false);
    if (hard.length > 0 || hardGateFail.length > 0) {
      const lines = [...hard, ...hardGateFail.map((g) => `${g.id}: ${g.detail}`)];
      return reject(
        "script", preset,
        `나레이션 검사 불통 ${lines.length}건 — ${lines.slice(0, 8).join(" / ")}${lines.length > 8 ? ` / … (+${lines.length - 8})` : ""}`,
        [
          "위 블록을 나레이션.md 규칙대로 고쳐 payload.script 를 다시 실어 부르라.",
          ...hardGateFail.map((g) => g.fix ?? ""),
          soft.length ? `soft 경고 ${soft.length}건도 함께 본다: ${soft.slice(0, 5).join(" / ")}` : "",
        ].filter(Boolean).join(" "),
      );
    }

    const scriptDoc = {
      source: source.path, title: source.title ?? null, style: N.문체, ending_mode: N.결말모드,
      selection: payload.selection_path ?? null,
      metrics: { block_count: count, avg_chars: avgChars, total_chars: totalChars, nar_est_s: narEst, dialogue_s: dlgS, dialogue_utterances: dlgUtt, nar_share_est: narShare, nar_dialogue_ratio_est: turnRatio, block_ratio_n_over_d: blockRatio, incomplete_ratio: r3(incomplete / sentTotal), ending_dist: distRatio, sec_per_char_est: N.자당초_추정, note: "나레 시간은 자수×자당초 추정 — voice 실측으로 재검" },
      gates, warnings: soft,
      blocks: blocks.map((b) => ({ n: b.n, pos: b.pos, text: b.text, intent: b.intent, chars: b.chars, pieces: b.pieces.length, ending: b.ending, est_s: b.est_s })),
    };
    return base("script", preset, {
      status: "execute",
      next_step: "voice",
      message: `나레이션 통과: 블록 ${count}개 · 평균 ${avgChars}자 · 나레 추정 ${narEst}s / 대사 ${dlgS}s → 나레 시간점유 ${narShare} (추정). write_files 를 쓰고 voice 로 넘어가라.`,
      instructions: [
        `① write_files 의 내용을 그대로 ${outPath} 에 쓴다.`,
        "② metrics 와 gates 를 사람에게 보여준다. 나레이션 전문은 블록 순서대로 위치·본문·의도 표로.",
        "③ carry 의 값을 payload 에 그대로 실어 next_step 을 부른다.",
        "④ voice 는 아직 스텁이다 — TTS 제공자·보이스 결정 대기 (외부서비스.md). 실측 길이가 나오면 G-턴비를 다시 잰다.",
      ],
      then_call_with: ["step: 'voice'", "payload: { workdir, source, probe_summary, transcript_path, brief_path, selection_path, script_path }"],
      jobs_kind: null, jobs: [], measure: [],
      write_files: [{ path: outPath, content: scriptDoc, note: "나레이션 블록. voice 의 입력" }],
      metrics: scriptDoc.metrics,
      gates,
      carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path"],
      source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: outPath,
      ...(soft.length ? { warnings: soft } : {}),
    });
  },
};
