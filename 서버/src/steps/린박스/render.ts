/**
 * steps/린박스/render.ts — lb_render: 정본 맥 사슬 `신병4/한번에.sh` ⑭ (납품 소리·완성본). 두 번 부른다.
 *
 *   ① render_logs 없음 → jobs (편 폴더 cwd): 영상굽기(균일 배율 · 레터박스 크롭은 lb_probe 값) → 마스터맞춤 → 효과음 믹스(효과음계획.json 있을 때만 add_sfx, 없으면 master_sync 복사)
 *        → 라우드니스(−14.0 / TP −3.4 · 2패스) → 완성굽기(로고판 ass 굽기) → 대조점짓기 → _synccheck --final(완성검사 1) → 완성_ 이름 사본
 *   ② final_log 있음 → 판정: 완성본 1080×1920 · _synccheck 「싱크 검사 통과」 · 라우드니스 결과 I/TP · 마스터 길이 ≈ 영상 길이 → next_step=lb_check
 *
 * 한번에.sh 와 다른 점
 *   · «merged_균일 이 재사슬보다 오래됐으면 다시 굽는다» 캐시 판단은 안 한다 — 매번 굽는다(영상굽기가 컷계획 도장으로 컷 캐시를 관리한다).
 *   · 크롭이 신병4 값(1016:960:452:60) 고정이 아니라 lb_probe 레터박스로 짓는다.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, r3, readCarry, spec, str } from "./lib.js";

const n1 = (s: string, re: RegExp): number | null => { const m = s.match(re); return m ? Number(m[1]) : null; };
const audioSpec = (spec as unknown as { audio?: { target_lufs?: number; true_peak_db?: number; final_peak_db_max?: number } }).audio ?? {};

/** lb_probe 레터박스 → 영상굽기 --크롭 W:H:X:Y (W = round(H×1080/1020) · X 가운데 · Y 위 띠) */
export function cropArg(ps: { width?: number; letterbox?: { top?: number; content_h?: number } | null } | undefined): string | null {
  const h = ps?.letterbox?.content_h;
  const top = ps?.letterbox?.top ?? 0;
  const width = ps?.width;
  if (typeof h !== "number" || h <= 0 || typeof width !== "number" || width <= 0) return null;
  const w = Math.min(width, Math.round((h * 1080) / 1020));
  const x = Math.max(0, Math.floor((width - w) / 2));
  return `${w}:${h}:${x}:${top}`;
}

export const lbRender: StepHandler = {
  name: "lb_render",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string; title?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_render", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_prproj 응답의 carry 값을 payload 에 그대로 실어 lb_render 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_render", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const title = str(payload, "title") || (typeof source.title === "string" && source.title.trim()) || "린박스";
    const master = str(payload, "master") || source.path;
    const assLogo = str(payload, "ass_logo") || join(carry.ep_dir, `captions_${title}_로고.ass`);
    const finalName = `${title}_${carry.ep}_숏폼.mp4`;
    const finalPath = join(carry.ep_dir, finalName);
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const ps = payload.probe_summary as { width?: number; letterbox?: { top?: number; content_h?: number } | null } | undefined;
    const crop = cropArg(ps);
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, 편정보: payload.편정보, authored: payload.authored, clip_secs: payload.clip_secs, total_s: payload.total_s ?? null,
      srt_pick: payload.srt_pick ?? null, title, ass: payload.ass ?? join(carry.ep_dir, `captions_${title}.ass`), ass_logo: assLogo, ass_fp: payload.ass_fp ?? null, 배치계획: payload.배치계획 ?? null,
      xml: payload.xml ?? null, master, prproj: payload.prproj ?? join(carry.ep_dir, `${title}_${carry.ep}.prproj`), final: finalPath,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "편정보", "authored", "clip_secs", "total_s", "srt_pick", "title", "ass", "ass_logo", "ass_fp", "배치계획", "xml", "master", "prproj", "final"];
    const L = (k: string) => String(payload[k] ?? "");

    // ── ② 판정 → lb_check ────────────────────────────────────────────────
    if (payload.final_log !== undefined) {
      const bad: string[] = [];
      const warnings: string[] = [];
      const bake = L("bake_log");
      const bw = n1(bake, /width=(\d+)/), bh = n1(bake, /height=(\d+)/), bf = n1(bake, /nb_frames=(\d+)/);
      if (bw !== 1080 || bh !== 1020) bad.push(`영상굽기: merged_균일.mp4 가 ${bw ?? "?"}×${bh ?? "?"} — 매트 창(1080×1020)이 아니다. 크롭 ${crop ?? "기본"} 을 보라.`);
      const fit = L("fit_log");
      const mLen = n1(fit, /master_sync\.wav\s+([\d.]+)초/), vLen = n1(fit, /\(영상 ([\d.]+)초\)/);
      if (mLen === null || vLen === null) bad.push("마스터맞춤: 「→ blocks/master_sync.wav N초 (영상 N초)」 를 못 읽었다 — blocks/bNN.mp4·concat.txt 가 있는지.");
      else if (Math.abs(mLen - vLen) > 0.1) bad.push(`마스터맞춤: 소리 ${mLen}초 ≠ 영상 ${vLen}초 (0.1초 넘게) — 블록 고아·패딩을 보라.`);
      const loud = L("loud_log");
      const I = n1(loud, /결과\s+— I (-?[\d.]+) LUFS/), TP = n1(loud, /TP (-?[\d.]+) dBFS \(ebur128/);
      if (I === null || TP === null) bad.push(`라우드니스: 「결과 — I … · TP …」 가 없다 — ${loud.split("\n").filter((l) => l.includes("★")).slice(0, 2).join(" | ") || "로그 없음"}.`);
      else {
        const tI = audioSpec.target_lufs ?? -14, tTP = audioSpec.true_peak_db ?? -3.4;
        if (Math.abs(I - tI) > 1.0) bad.push(`라우드니스: I ${I} LUFS — 목표 ${tI}±1 밖.`);
        if (TP > tTP + 0.1) bad.push(`라우드니스: TP ${TP} dBFS — 한계 ${tTP} 를 넘는다.`);
      }
      const fin = L("final_log");
      const fm = fin.match(/완성본 (\S+) · (\d+),(\d+) · ([\d.]+)초/);
      if (!fm) bad.push(`완성굽기: 「완성본 … · 1080,1920 · N초」 가 없다 — ${fin.split("\n").filter((l) => l.includes("★")).slice(0, 2).join(" | ") || "로그 없음"}.`);
      else if (fm[2] !== "1080" || fm[3] !== "1920") bad.push(`완성굽기: 해상도 ${fm[2]}×${fm[3]} ≠ 1080×1920 (완성검사 7).`);
      const dur = fm ? Number(fm[4]) : null;
      const target = (spec as unknown as { edit?: { target_sec?: [number, number] } }).edit?.target_sec ?? [40, 60];
      if (dur !== null && (dur < target[0] || dur > target[1])) warnings.push(`완성본 ${dur}초 — 규격 edit.target_sec ${target[0]}~${target[1]} 밖(완성검사 2 · 신병4 실측 13.8~42.5 라 사장님 확인 전엔 «미완» 판정 안 함).`);
      const sync = L("sync_log");
      if (!/싱크 검사 통과/.test(sync)) bad.push(`_synccheck --final(완성검사 1): ${sync.split("\n").filter((l) => /실패|·|✗/.test(l)).slice(0, 4).map((l) => l.trim()).join(" | ") || "「싱크 검사 통과」 가 없다(도구가 죽었다)"}. 절단·블록·완성본 원음 대조 중 어긋난 단계를 고쳐라(규칙 «절단은 -i 뒤 -ss 재인코딩»).`);
      const points = n1(L("points_log"), /대조점 (\d+)개/);
      if (points === null) warnings.push("대조점짓기 로그를 못 읽었다 — _synccheck 3단계가 «건너뜀» 이면 완성본 원음 대조가 안 된 것이다.");
      if (bad.length) return reject("lb_render", preset, `납품 소리·완성본이 아직 맞지 않다 (${bad.length}건)`, bad.map((x, i) => `${i + 1}) ${x}`).join(" ") + " 고친 뒤 lb_render 를 다시 부르라(final_log 는 빼고).");
      return base("lb_render", preset, {
        status: "execute",
        next_step: "lb_check",
        message: `완성본 ${finalName} · ${dur}초 · 1080×1920 · I ${I} LUFS / TP ${TP} dBFS · 싱크 검사 통과 · 대조점 ${points ?? "?"}개. 이제 lb_check(완성 검사 기계 항목)로.`,
        instructions: ["① carry 의 값(… final·prproj 포함)을 payload 에 그대로 실어 lb_check 를 부른다."],
        then_call_with: ["step: 'lb_check'", "payload: { …carry }"],
        jobs_kind: null, jobs: [], measure: [],
        metrics: { final_s: dur, lufs: I, tp_dbfs: TP, frames: bf, sync_points: points },
        carry: carryKeys,
        ...common,
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ① ⑭ 지시 ─────────────────────────────────────────────────────────
    const warnings: string[] = [];
    if (!crop) warnings.push("probe_summary 에 레터박스(content_h·width)가 없어 영상굽기 크롭을 기본(신병4 1016:960:452:60)으로 둔다 — 다른 소재면 검은 띠가 보일 수 있다.");
    const cropArgs = crop ? ["--크롭", crop] : [];
    const sfxPy = "import os,shutil,subprocess,sys\nif os.path.exists('효과음계획.json') and os.path.exists('add_sfx.py'):\n    r=subprocess.run([sys.executable,'add_sfx.py'],capture_output=True,text=True,encoding='utf-8',errors='replace');print(r.stdout[-600:]);sys.exit(r.returncode)\nshutil.copyfile('blocks/master_sync.wav','blocks/master_sfx.wav');print('효과음 없음 — master_sync 를 master_sfx 로 복사')";
    return base("lb_render", preset, {
      status: "execute",
      next_step: "lb_render",
      message: `납품 소리·완성본(한번에.sh ⑭) — 균일 배율 영상(크롭 ${crop ?? "기본"}) → 마스터 소리 맞춤 → 효과음 믹스 → 라우드니스 ${audioSpec.target_lufs ?? -14}/${audioSpec.true_peak_db ?? -3.4} → 완성굽기(로고판 자막) → 대조점 → _synccheck --final. 로그를 실어 다시 부르라.`,
      instructions: [
        `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 순서대로. 영상굽기는 컷계획.json 대로 마스터(${master})에서 컷을 잘라 이어 붙인다(컷 캐시 _균일컷/ · 컷계획 도장 바뀌면 버림).`,
        "② 효과음: 편 폴더에 효과음계획.json 과 add_sfx.py 가 있으면(효과음낱개굽기.py 로 PLAN 을 채운 편) 그것으로 믹스, 없으면 master_sync 그대로. 라우드니스는 2패스 loudnorm + ebur128 되재기(규격 audio).",
        "③ _synccheck --final 은 완성검사 1(구간 정렬 / 블록 영상·소리 길이 / 완성본 원음 대조 100ms). measure 대로 로그 7개를 실어 lb_render 를 **다시** 부른다 — 실패 rc 라도 로그는 실어 보내라.",
      ],
      then_call_with: ["step: 'lb_render'", "payload: { …carry, bake_log, fit_log, sfx_log, loud_log, final_log, points_log, sync_log }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        { name: "bake", argv: ["python", tool("영상굽기.py"), carry.ep_dir, master, ...cropArgs], out: join(carry.ep_dir, "_bake_log.txt"), note: "균일 배율 영상 → blocks/merged_균일.mp4 (1080×1020 · 30fps). 마지막에 ffprobe width/height/nb_frames." },
        { name: "master_fit", argv: ["python", tool("마스터맞춤.py")], note: "블록 소리를 영상 길이에 맞춰 이어 붙인다(서버 master.wav 는 블록당 ~29ms 밀린다 · EP6 실측) → blocks/master_sync.wav." },
        { name: "sfx", argv: ["python", "-c", sfxPy], optional: true, note: "효과음계획.json + add_sfx.py 가 있으면 믹스, 없으면 복사 → blocks/master_sfx.wav." },
        { name: "loud", argv: ["python", tool("라우드니스.py")], out: join(carry.ep_dir, "_loud_log.txt"), note: `2패스 loudnorm I ${audioSpec.target_lufs ?? -14} · TP ${audioSpec.true_peak_db ?? -3.4} · ebur128 되재기 → blocks/master_sfx_ln.wav. 「결과 — I … LUFS · TP … dBFS」.` },
        { name: "final", argv: ["python", tool("완성굽기.py"), ".", finalName, "--소리", "blocks/master_sfx_ln.wav", "--자막", assLogo], out: join(carry.ep_dir, "_final_log.txt"), note: "매트 창 + 로고판 자막(credit_cta 없음) + 로고 PNG → 완성본 1080×1920. 「완성본 … · 1080,1920 · N초」." },
        { name: "points", argv: ["python", tool("대조점짓기.py")], optional: true, note: "완성본 원음 대조점 → _synccheck_points.json." },
        { name: "sync", argv: ["python", tool("_synccheck.py"), carry.ep_dir, "--final"], optional: true, note: "완성검사 1 — 「싱크 검사 통과」 아니면 반려." },
        { name: "final_copy", argv: ["python", "-c", `import shutil;shutil.copyfile(${JSON.stringify(finalName)},${JSON.stringify("완성_" + finalName)});print('완성_${finalName}')`], optional: true, note: "한번에.sh 의 ln -f 완성_ 이름 사본." },
      ],
      measure: [
        { as: "bake_log", from: "job:bake", unit: "stdout" }, { as: "fit_log", from: "job:master_fit", unit: "stdout" }, { as: "sfx_log", from: "job:sfx", unit: "stdout" },
        { as: "loud_log", from: "job:loud", unit: "stdout" }, { as: "final_log", from: "job:final", unit: "stdout" }, { as: "points_log", from: "job:points", unit: "stdout" }, { as: "sync_log", from: "job:sync", unit: "stdout" },
      ],
      metrics: { crop, target_lufs: audioSpec.target_lufs ?? -14, true_peak_db: audioSpec.true_peak_db ?? -3.4, span_s: r3(carry.end_s - carry.start_s) },
      carry: carryKeys,
      ...common,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
