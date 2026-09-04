/**
 * steps/린박스/xml.ts — lb_xml: 정본 맥 사슬 `신병4/한번에.sh` ② (xml짓기.py → FCP7 XML). 두 번 부른다.
 *
 *   ① payload.xml_log 가 없으면 → jobs: xml짓기.py <편폴더> <편집용마스터> <작품_EP.xml> --작품 --자막 --배율
 *      편집용마스터 = source.path(lb_cut 이 구간을 잘라낸 그 파일 — V1 컷이 여기서 in/out 으로 문다).
 *      배율 = 1020 / 레터박스 뺀 그림 높이(lb_probe probe_summary.letterbox.content_h) × 100 — 검은 띠가 매트 뒤로 숨는 값(신병4 960 → 106.25%).
 *   ② payload.xml_log 가 있으면 → 「V1 컷 N · 제목 a+b · 나레 · 대사 · 효과 · A1 · A2」 와 「→ <xml> N 바이트」 를 읽어
 *      배치계획·자막과 대조(컷 수 = 컷계획, 제목 2줄, 나레 = narr 수) → next_step=lb_prproj
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, r3, readCarry, str } from "./lib.js";

export function parseXmlLog(log: string): { v1: number; h1: number; h2: number; narr: number; dlg: number; fx: number; a1: number; a2: number; a3: number; bytes: number | null; path: string | null } | null {
  const m = log.match(/V1 컷 (\d+) · 제목 (\d+)\+(\d+) · 나레 (\d+) · 대사 (\d+) · 효과 (\d+) · A1 (\d+) · A2 (\d+) · A3\(sfx\) (\d+)/);
  if (!m) return null;
  const b = log.match(/→ (.+?) (\d+) 바이트/);
  return { v1: +m[1], h1: +m[2], h2: +m[3], narr: +m[4], dlg: +m[5], fx: +m[6], a1: +m[7], a2: +m[8], a3: +m[9], bytes: b ? Number(b[2]) : null, path: b ? b[1].trim() : null };
}

export const lbXml: StepHandler = {
  name: "lb_xml",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string; title?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_xml", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_subs 응답의 carry 값을 payload 에 그대로 실어 lb_xml 을 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_xml", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const title = str(payload, "title") || (typeof source.title === "string" && source.title.trim()) || "린박스";
    const ass = str(payload, "ass") || join(carry.ep_dir, `captions_${title}.ass`);
    const xml = join(carry.ep_dir, `${title}_${carry.ep}.xml`);
    const plan = (typeof payload.배치계획 === "object" && payload.배치계획 !== null ? payload.배치계획 : null) as { total?: unknown; blocks?: unknown[]; narr?: unknown[] } | null;
    const ps = payload.probe_summary as { letterbox?: { content_h?: number } | null } | undefined;
    const contentH = typeof ps?.letterbox?.content_h === "number" && ps.letterbox.content_h > 0 ? ps.letterbox.content_h : null;
    const scalePct = contentH ? Math.round((1020 / contentH) * 10000) / 100 : null;
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, 편정보: payload.편정보, authored: payload.authored, clip_secs: payload.clip_secs, total_s: payload.total_s ?? null,
      srt_pick: payload.srt_pick ?? null, title, ass, ass_logo: payload.ass_logo ?? join(carry.ep_dir, `captions_${title}_로고.ass`), 배치계획: payload.배치계획 ?? null, xml, master: source.path,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "편정보", "authored", "clip_secs", "total_s", "srt_pick", "title", "ass", "ass_logo", "배치계획", "xml", "master"];

    // ── ② 로그 판정 → lb_prproj ────────────────────────────────────────────
    if (payload.xml_log !== undefined) {
      const log = String(payload.xml_log ?? "");
      const p = parseXmlLog(log);
      if (!p) return reject("lb_xml", preset, "xml짓기.py 로그에서 「V1 컷 N · 제목 …」 을 못 읽었다", "xml짓기.py 가 죽었다 — 로그 첫 줄(★자막 ass 가 없다 / 배치계획.json / 컷계획.json)을 보고 lb_subs 산출물이 편 폴더에 있는지 확인한 뒤 lb_xml 을 다시 부르라. " + log.split("\n").filter((l) => l.trim()).slice(0, 3).join(" | "));
      const bad: string[] = [];
      const warnings: string[] = [];
      if (!p.bytes || p.bytes < 2000) bad.push(`XML 이 ${p.bytes ?? "?"}바이트다 — 트랙이 비었다.`);
      if (p.v1 === 0) bad.push("V1 컷이 0개 — 컷계획.json 이 비었다(계획짓기.py 가 _block_jobs.json 을 못 읽음).");
      if (p.h1 !== 1 || p.h2 !== 1) bad.push(`제목 트랙이 ${p.h1}+${p.h2} — 헤드라인 2줄이 각각 한 클립이어야 한다(V4·V4b). captions_<작품>.ass 의 headline_l1/l2 를 보라.`);
      if (p.a1 !== p.v1) bad.push(`A1 원음 ${p.a1} ≠ V1 컷 ${p.v1}.`);
      const narrN = Array.isArray(plan?.narr) ? plan!.narr!.length : null;
      if (narrN !== null && p.a2 !== narrN) bad.push(`A2 나레 ${p.a2} ≠ 배치계획 narr ${narrN} — blocks/nNN.wav 가 빠졌다.`);
      if (p.dlg === 0) warnings.push("대사자막 0장 — D 블록이 없는 편인가? 아니면 서식.py 가 band_dlg 를 못 바꿨다.");
      if (bad.length) return reject("lb_xml", preset, `XML 이 아직 맞지 않다 (${bad.length}건)`, bad.map((x, i) => `${i + 1}) ${x}`).join(" ") + " 고친 뒤 lb_xml 을 다시 부르라(xml_log 는 빼고).");
      return base("lb_xml", preset, {
        status: "execute",
        next_step: "lb_prproj",
        message: `FCP7 XML 통과 — V1 컷 ${p.v1} · 제목 ${p.h1}+${p.h2} · 나레자막 ${p.narr} · 대사자막 ${p.dlg} · 효과 ${p.fx} · A2 ${p.a2}${p.a3 ? ` · A3 효과음 ${p.a3}` : ""} · ${p.bytes} 바이트 → ${xml}. 이제 lb_prproj(프리미어가 prproj 로)로.`,
        instructions: [
          "① carry 의 값(… xml·master·title 포함)을 payload 에 그대로 실어 lb_prproj 를 부른다.",
          "② lb_prproj 는 프리미어(CEP 확장 auto_prproj.jsx)를 띄운다 — 프리미어가 깔려 있고 확장이 설치돼 있어야 한다(setup 안내). 한 컴퓨터에 한 번에 한 편만(대기줄 잠금).",
        ],
        then_call_with: ["step: 'lb_prproj'", "payload: { …carry }"],
        jobs_kind: null,
        jobs: [],
        measure: [],
        metrics: { v1_cuts: p.v1, headline_clips: p.h1 + p.h2, narr_caps: p.narr, dlg_caps: p.dlg, fx_caps: p.fx, a2_narr: p.a2, a3_sfx: p.a3, xml_bytes: p.bytes, scale_pct: scalePct },
        carry: carryKeys,
        ...common,
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ① XML 짓기 지시 ─────────────────────────────────────────────────
    if (!plan || typeof plan.total !== "number") {
      return reject("lb_xml", preset, "payload.배치계획(lb_subs 가 되읽은 배치계획.json)이 없다", "lb_subs ② 응답의 carry(배치계획 포함)를 그대로 실어 lb_xml 을 부르라.");
    }
    const warnings: string[] = [];
    if (!scalePct) warnings.push("probe_summary.letterbox.content_h 가 없어 V1 배율을 기본 106.25%(신병4 EPK, 그림 960px)로 둔다 — 레터박스가 다른 소재면 매트 창에 검은 띠가 보일 수 있다. lb_probe 의 cropdetect 를 확인하라.");
    const scaleArgs = scalePct ? ["--배율", String(scalePct)] : [];
    return base("lb_xml", preset, {
      status: "execute",
      next_step: "lb_xml",
      message: `FCP7 XML 을 짓는다(한번에.sh ②) — 편집용마스터 ${source.path} 를 V1/A1 으로 물고(in/out), 매트·로고 PNG, 제목 2줄(트랙 분리)·나레·대사·효과 텍스트 제너레이터, A2 나레 wav. 배율 ${scalePct ?? "106.25(기본)"}%. 로그를 실어 다시 부르라.`,
      instructions: [
        `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로. xml짓기.py 는 같은 폴더의 make_xml.py 를 쓴다(규격 §52 — 자막은 <generatoritem> 텍스트 제너레이터 · 크기는 480/1920 배 · 나레 블록의 원음 클립은 −25.1dB).`,
        `② 편집용마스터는 소재 파일 그대로(${source.path}) — 프리미어에서 앞뒤로 늘릴 수 있게 원본을 문다. 총 ${plan.total}프레임(배치계획).`,
        "③ measure 대로 표준출력을 payload.xml_log 에 실어 lb_xml 을 **다시** 부른다 — 서버가 컷·제목·나레 수를 배치계획과 대조한다.",
      ],
      then_call_with: ["step: 'lb_xml'", "payload: { …carry, xml_log: <xml짓기 stdout> }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        { name: "xml", argv: ["python", join(repo, RUNNER_DIR, "도구", "xml짓기.py"), carry.ep_dir, source.path, xml, "--작품", title, "--자막", ass, ...scaleArgs], out: join(carry.ep_dir, "_xml_log.txt"), note: "정본 신병4/xml짓기.py 의 유스튜디오판 — 작품·자막·배율을 인자로(정본은 captions_신병4·106.25 가 박혀 있었다). 「V1 컷 N · 제목 1+1 · 나레 · 대사 · 효과 · A1 · A2 · A3」 + 「→ xml N 바이트」." },
      ],
      measure: [{ as: "xml_log", from: "job:xml", unit: "stdout" }],
      metrics: { total_frames: plan.total, scale_pct: scalePct, content_h: contentH, span_s: r3(carry.end_s - carry.start_s) },
      carry: carryKeys,
      ...common,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
