/**
 * steps/린박스/plan.ts — lb_plan: 착수 게이트(쓸거리·대사 밀도·형제 편 겹침) + 하단(로고/문구) 묻기 + 편정보.json.
 *
 * 볼케이노 키트 대응: 쓸거리검사.py(규격 §83 절대 규칙) · 편정보.py 틀/묻기/검사(규격 §70 · 작업규칙 「하단은 묻고 나서 시작한다」).
 * 두 번 부른다:
 *   ① payload.편정보 가 없으면 → 게이트를 재고(막히면 error — 다른 구간을 떠 와라), 통과면 status need_input 으로 하단을 묻는다.
 *      (판정은 서버 — 대사.json 은 lb_transcript 가 실어 왔다. 러너 명령 없음.)
 *   ② payload.편정보 가 있으면 → 편정보.py 검사()를 그대로 옮긴 검사 → write_files 편정보.json(+로고 복사 job) → next_step=lb_script
 * 유료 없음.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, answer, join, r3, readCarry, spec, str } from "./lib.js";

interface Word { s: number; e: number; t: string; sure?: boolean; spk?: string }
type Range = [number, number];

const E = (spec as unknown as { edit: { min_usable_speech_sec: number; target_sec: [number, number]; dlg_narr_ratio: [number, number] } }).edit;
const B = (spec as unknown as { layout: { bottom: { logo_ink_h_px: number; logo_top_y: number; credit_with_logo: boolean } } }).layout.bottom;
const MAT = (spec as unknown as { layout: { mat_bottom: { y0: number; y1: number } } }).layout.mat_bottom;
const 최소완성 = E.target_sec[0];
const 원음비 = E.dlg_narr_ratio[0] / 100;
/** 쓸거리검사.py 말아님 — 웃음·숨소리·추임새는 말이 아니다 */
const 말아님 = /^[\s하핳흐허아어음응윽헉웃음★]*$/;
const 크레딧최대줄 = 5; // 편정보.py 최대줄 — 아래 매트(1470~1920)에 들어가는 줄 수
const 안채운표시 = ["<작품명>", "여기에"];

function words(payload: Record<string, unknown>): Word[] {
  const d = payload.대사 as { words?: Word[] } | undefined;
  return Array.isArray(d?.words) ? d!.words!.filter((w) => w && typeof w.s === "number" && typeof w.e === "number" && typeof w.t === "string") : [];
}

/** 쓸거리 — 말초(추임새 제외) · 형제 편이 쓴 구간과 겹친 초 · 완성본 어림 */
export function usable(ws: Word[], used: Range[], offset: number) {
  let 말초 = 0;
  let 겹초 = 0;
  for (const w of ws) {
    if (말아님.test(w.t)) continue;
    const d = Math.max(0, w.e - w.s);
    말초 += d;
    const s = offset + w.s, e = offset + w.e;
    for (const [a, b] of used) {
      if (e <= a || s >= b) continue;
      겹초 += Math.min(e, b) - Math.max(s, a);
      break;
    }
  }
  const 남은 = Math.max(0, 말초 - 겹초);
  return { 말초: r3(말초), 겹초: r3(겹초), 남은: r3(남은), 어림: r3(남은 / 원음비) };
}

/** 30초 창마다 글자 수 · 가장 긴 말 없는 틈 (규격 정답지 G-대사밀도 · 01편 140초 무음 사고) */
export function density(ws: Word[], spanS: number) {
  const win = 30;
  const n = Math.max(1, Math.ceil(spanS / win));
  const chars = new Array<number>(n).fill(0);
  for (const w of ws) {
    if (말아님.test(w.t)) continue;
    const k = Math.min(n - 1, Math.max(0, Math.floor(w.s / win)));
    chars[k] += w.t.replace(/\s/g, "").length;
  }
  const sorted = [...ws].filter((w) => !말아님.test(w.t)).sort((a, b) => a.s - b.s);
  let gap = sorted.length ? sorted[0].s : spanS;
  let gapAt = 0;
  for (let i = 1; i < sorted.length; i++) {
    const g = sorted[i].s - sorted[i - 1].e;
    if (g > gap) { gap = g; gapAt = sorted[i - 1].e; }
  }
  if (sorted.length) { const tail = spanS - sorted[sorted.length - 1].e; if (tail > gap) { gap = tail; gapAt = sorted[sorted.length - 1].e; } }
  return { windows: chars.map((c, i) => ({ from_s: i * win, chars: c })), empty_windows: chars.filter((c) => c === 0).length, max_gap_s: r3(gap), max_gap_at_s: r3(gapAt) };
}

interface 편정보 {
  제목?: unknown; 크레딧?: unknown; 방영정보?: unknown; 뱃지?: unknown; 완성본?: unknown; 로고?: unknown;
  로고높이?: unknown; 로고y?: unknown; 크레딧함께?: unknown; 하단확인?: unknown;
}

export const lbPlan: StepHandler = {
  name: "lb_plan",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_plan", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_transcript 응답의 carry 값을 payload 에 그대로 실어 lb_plan 을 다시 부르라.");
    }
    const ws = words(payload);
    if (!ws.length) {
      return reject("lb_plan", preset, "payload.대사(대사.json)가 없다", "lb_transcript ② 응답의 carry(대사·scene_count·repo·probe_summary)를 payload 에 그대로 실어 lb_plan 을 다시 부르라.");
    }
    const spanS = r3(carry.end_s - carry.start_s);
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo: str(payload, "repo"), probe_summary: payload.probe_summary, scene_count: payload.scene_count ?? null, 대사: payload.대사,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "scene_count", "대사"];
    const masterName = source.path.replace(/\\/g, "/").split("/").pop() ?? source.path;

    // ── ② 편정보 검사 → 파일 쓰기 ────────────────────────────────────────
    if (payload.편정보 !== undefined) {
      const p = (typeof payload.편정보 === "object" && payload.편정보 !== null ? payload.편정보 : {}) as 편정보;
      const 탈: string[] = [];
      const 크레딧 = Array.isArray(p.크레딧) ? (p.크레딧 as unknown[]).map((x) => String(x ?? "").trim()).filter((x) => x) : [];
      const 로고 = typeof p.로고 === "string" ? p.로고.trim() : "";
      const 방영정보 = typeof p.방영정보 === "string" ? p.방영정보.trim() : "";
      const 로고높이 = Number(p.로고높이 ?? B.logo_ink_h_px);
      const 로고y = Number(p.로고y ?? B.logo_top_y);
      const 크레딧함께 = p.크레딧함께 === true;
      if (!크레딧.length) 탈.push("크레딧 문구가 비었다 — 화면에 안 내더라도 서버가 CREDIT 을 필수로 받는다(규격 layout.bottom). 두 줄을 적어라 (정해진 틀 없음 · 쓴 적 있는 것: «<신병4 사보타주> / 지금 정주행!» · «<더 글로리>는 / 넷플릭스에서!»).");
      if (크레딧.length > 크레딧최대줄) 탈.push(`크레딧이 ${크레딧.length}줄이다 — 아래 매트(${MAT.y0}~${MAT.y1})에는 ${크레딧최대줄}줄까지.`);
      if (크레딧.some((c) => 안채운표시.some((t) => c.includes(t)))) 탈.push("크레딧이 보기 문구(«<작품명>»·«여기에…») 그대로다 — 이 편 것으로 바꿔라.");
      if (!로고) 탈.push("로고 칸이 비었다 — 흰 로고 PNG 의 절대경로를 적거나, 로고를 안 쓰면 '없음' 이라고 적어라.");
      else if (로고 !== "없음" && !/\.png$/i.test(로고)) 탈.push(`로고는 PNG 여야 한다: ${로고}`);
      if (로고 !== "없음" && (로고y < MAT.y0 || 로고y + 로고높이 > MAT.y1)) 탈.push(`로고가 아래 매트(y${MAT.y0}~${MAT.y1}) 밖으로 나간다 — 로고y ${로고y} · 높이 ${로고높이}`);
      if (p.하단확인 !== true) 탈.push("하단확인 이 true 가 아니다 — 사람이 로고/문구/방영정보를 눈으로 보고 «맞다» 고 한 뒤 true 로. (작업규칙 2026-08-26 사장님 지시 — 묻지 않으면 지난 편 것이 그대로 나간다)");
      if (탈.length) {
        return reject("lb_plan", preset, `편정보가 아직 맞지 않다 (${탈.length}건)`, 탈.map((x, i) => `${i + 1}) ${x}`).join(" "));
      }
      const 편정보 = {
        제목: Array.isArray(p.제목) && (p.제목 as unknown[]).length ? (p.제목 as unknown[]).map((x) => String(x)) : ["", ""],
        크레딧, 방영정보, 뱃지: typeof p.뱃지 === "string" ? p.뱃지 : "",
        완성본: "자동",
        로고: 로고 === "없음" ? "없음" : "logo/logo_bottom.png",
        로고높이, 로고y, 크레딧함께, 하단확인: true,
        편: carry.ep, 마스터: masterName, 구간오프셋: carry.start_s,
        구간오프셋_근거: `start ${carry.start_s}~${carry.end_s}초 (lb_plan 2026)`,
        완성본접두: "린박스_",
        나레TTS: { voice: "Ina tc_62686be9deec4c1bb7fd077c", tempo: 1.2, 근거: "규격 narration — 사장님 2026-09-04 청취 확정" },
      };
      const jobs = 로고 !== "없음"
        ? [{
            name: "copy_logo",
            argv: ["python", "-c", "import shutil,os,sys;os.makedirs('logo',exist_ok=True);shutil.copyfile(sys.argv[1],'logo/logo_bottom.png');print('logo/logo_bottom.png')", 로고],
            note: "흰 로고를 편 폴더 logo/logo_bottom.png 로 (검은 매트에 검은 로고는 안 보인다 — 흰 로고만). 한번에.sh 가 이 이름을 본다.",
          }]
        : [];
      return base("lb_plan", preset, {
        status: "execute",
        next_step: "lb_script",
        message: `하단 확정: ${로고 === "없음" ? "로고 없음 → 크레딧 글자" : "로고 " + 로고} · 크레딧 ${크레딧.join(" / ")}${방영정보 ? " · 방영정보 " + 방영정보 : ""}${크레딧함께 ? " · 크레딧함께" : ""}. 편정보.json 을 쓰고 lb_script(대본·제목)로.`,
        instructions: [
          `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 실행한다 (로고 복사). write_files 대로 편정보.json 을 쓴다 — 제목은 lb_script 가 채운다.`,
          "② carry 의 값을 payload 에 그대로 실어 lb_script 를 부른다.",
        ],
        then_call_with: ["step: 'lb_script'", "payload: { source, workdir, ep, ep_dir, start_s, end_s, repo, probe_summary, scene_count, 대사, 편정보 }"],
        jobs_kind: jobs.length ? "argv" : null,
        jobs_cwd: carry.ep_dir,
        jobs,
        write_files: [{ path: join(carry.ep_dir, "편정보.json"), content: 편정보 as unknown as Record<string, unknown>, note: "편 값 한 곳(규격 §70). 한번에.sh 가 제목·마스터·로고·구간오프셋을 읽는다." }],
        measure: [],
        metrics: { credit_lines: 크레딧.length, logo: 로고 !== "없음", air_info: Boolean(방영정보) },
        carry: [...carryKeys, "편정보"],
        ...common,
        편정보,
      });
    }

    // ── ① 게이트 + 하단 묻기 ─────────────────────────────────────────────
    const used = Array.isArray(payload.used_ranges) ? (payload.used_ranges as unknown[]).filter((r): r is Range => Array.isArray(r) && r.length === 2 && typeof r[0] === "number" && typeof r[1] === "number") : [];
    const u = usable(ws, used, carry.start_s);
    const d = density(ws, spanS);
    const metrics = { span_s: spanS, speech_s: u.말초, overlap_s: u.겹초, usable_s: u.남은, est_final_s: u.어림, min_final_s: 최소완성, empty_30s_windows: d.empty_windows, max_gap_s: d.max_gap_s, max_gap_at_s: d.max_gap_at_s, windows_chars: d.windows.map((w) => w.chars) };
    if (u.어림 < 최소완성) {
      return base("lb_plan", preset, {
        status: "error",
        next_step: "start",
        message: `★막힘 — 이 구간으로는 한 편이 안 나온다(규격 §83 절대 규칙). 안 겹치는 말 ${u.남은}초 → 완성본 어림 ${u.어림}초 (규격 최소 ${최소완성}초${u.겹초 ? ` · 형제 편과 겹친 말 ${u.겹초}초` : ""}). 대본을 짜기 전에 여기서 멈춘다 — 다른 구간을 떠 와라.`,
        instructions: [
          "① 소재 전체를 전사해 대목 순위표를 만들고 말이 많은 통(촬영본이 긴 통)을 고른다 — 재밌는 부분을 남기지 않는다(메모리 batch-pick-best-hooks).",
          "② 새 구간(start_s·end_s)으로 start 부터 다시 부른다. (어림은 말이 뜸한 대목에서 실제보다 짧게 나온다 — 이미 쓴 대본이 있으면 그 길이가 정답이다)",
        ],
        metrics,
        ...common,
      });
    }
    const warnings: string[] = [];
    if (u.겹초 > 0) warnings.push(`형제 편이 이미 쓴 구간과 말 ${u.겹초}초가 겹친다 — 같은 대사를 두 편에 내지 않도록 대본에서 그 자리는 피하라.`);
    if (d.max_gap_s >= 20) warnings.push(`말 없는 틈이 ${d.max_gap_s}초(${d.max_gap_at_s}초부터)다 — 01편은 140초 무음 구간을 통째로 버렸다. 그 자리는 그림만 있으니 대본에서 쓰지 말거나 구간을 줄여라.`);
    if (d.empty_windows) warnings.push(`30초 창 ${d.windows.length}개 중 ${d.empty_windows}개에 말이 없다.`);

    const 틀 = {
      제목: ["", ""],
      크레딧: [],
      방영정보: "",
      뱃지: "",
      완성본: "자동",
      로고: "",
      로고높이: B.logo_ink_h_px,
      로고y: B.logo_top_y,
      크레딧함께: B.credit_with_logo,
      하단확인: false,
      편: carry.ep, 마스터: masterName, 구간오프셋: carry.start_s,
    };
    const answers = (answer as unknown as { 착수?: Record<string, unknown> }).착수 ?? {};
    return base("lb_plan", preset, {
      status: "need_input",
      next_step: "lb_plan",
      message: `쓸거리 통과: 말 ${u.말초}초${u.겹초 ? `(겹침 ${u.겹초}초 제외 ${u.남은}초)` : ""} → 완성본 어림 ${u.어림}초 (최소 ${최소완성}) · 30초 창 글자 수 [${d.windows.map((w) => w.chars).join(", ")}]. ★이제 하단(로고냐 문구냐)을 사람에게 묻고 편정보를 채워 lb_plan 을 다시 부르라.`,
      need_input: {
        keys: ["편정보.로고", "편정보.크레딧", "편정보.방영정보", "편정보.크레딧함께", "편정보.하단확인"],
        why: "편마다 바뀌는 자리다. 묻지 않으면 지난 편의 로고·문구가 그대로 나간다 (작업규칙 2026-08-26 사장님 지시). 값은 편정보.json 한 곳(규격 §70).",
      },
      instructions: [
        "① 드라마 폴더에서 로고(*로고*.png · *logo*.png)를 찾아 경로를 보여 주고 «이게 맞습니까» 를 묻는다. 여럿이면 흰 로고(_w) — 검은 매트에 검은 로고는 안 보인다. 로고를 안 쓰면 문구를 묻는다(줄 수 자유·정해진 틀 없음).",
        "② 로고를 써도 크레딧 값은 비우지 않는다(서버가 CREDIT 필수). 로고와 문구를 둘 다 내려면 크레딧함께: true. 로고 아래 방영정보 한 줄도 묻는다 — 비우면 그 층을 안 만든다.",
        "③ 이 편만인지 드라마 전체인지 확인한다. 사람이 «맞다» 고 하면 하단확인: true 로 두고, 채운 편정보(payload.편정보)를 carry 와 함께 실어 lb_plan 을 다시 부른다.",
        "④ 형제 편이 이미 쓴 구간이 있으면 payload.used_ranges: [[소재초 시작, 끝], …] 로 실어 오면 겹침을 뺀다(규격 정답지 G-쓸거리).",
      ],
      then_call_with: ["step: 'lb_plan'", "payload: { …carry, 편정보: { 로고: '<흰 로고 절대경로>' | '없음', 크레딧: ['줄1','줄2'], 방영정보: '', 크레딧함께: false, 하단확인: true } }"],
      jobs_kind: null,
      jobs: [],
      measure: [],
      metrics,
      carry: carryKeys,
      ...common,
      편정보_틀: 틀,
      gates: { "G-쓸거리": answers["G-쓸거리"] ?? null, "G-대사밀도": answers["G-대사밀도"] ?? null },
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
