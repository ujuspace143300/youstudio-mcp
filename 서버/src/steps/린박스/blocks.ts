/**
 * steps/린박스/blocks.ts — lb_blocks: 얼굴·재프레이밍 → 컷 손질 → 블록 굽기 → captions_서버원본.ass → 장면튐검사. 네 번 부른다.
 *
 * 볼케이노 대응: 규격 §8 4)~8b) + stitch_blocks/stitch_master 산출물(설계 5.6.1). 도구는 편폴더차리기.py 가 편 폴더에 복사·▼편별 값을 박는다(새편.py 방식).
 *   A (authored2 없음)   do 편폴더차리기 → jobs find_faces·인물따라가기·reframe(구간_인물.mp4) → fix_cuts·컷다듬기·번쩍임정리 --쓰기(authored.json 이 바뀐다) → 대본검사 → authored 되읽기
 *   B (clip_secs 없음)   서버가 블록 계획(_block_jobs.json = 볼케이노 꼴)을 짜서 do 로 쓰고 → jobs ffmpeg 블록마다 + concat(merged.mp4) → measure clip_secs
 *   C (ass 없음)         서버가 실측 누적으로 captions_서버원본.ass 를 짓는다(write_files) → jobs 장면튐검사(구운 뒤 · §64) → 로그
 *   D (jump_log 있음)    ✗ 면 반려(번쩍임정리·재조립 지시), 아니면 next_step=lb_subs — 한번에.sh 입력 6개가 편 폴더에 다 있다
 * 유료 없음.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, r3, readCarry, str } from "./lib.js";
import { blockArgv, buildServerAss, planBlocks, type Authored, type WordT } from "./ass.js";
import { fnv1a64 } from "./check.js";

const nn = (i: number) => `b${String(i).padStart(2, "0")}`;

function readAuthored(x: unknown): Authored | null {
  if (typeof x !== "object" || x === null) return null;
  const a = x as Partial<Authored>;
  if (!Array.isArray(a.BLOCKS) || !Array.isArray(a.HEADLINE)) return null;
  return { HEADLINE: a.HEADLINE as string[], CREDIT: (a.CREDIT as string[]) ?? [], BLOCKS: a.BLOCKS as Authored["BLOCKS"], EFFECTS_BY_BLOCK: (a.EFFECTS_BY_BLOCK as Authored["EFFECTS_BY_BLOCK"]) ?? [] };
}

export const lbBlocks: StepHandler = {
  name: "lb_blocks",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_blocks", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_voice 응답의 carry 값을 payload 에 그대로 실어 lb_blocks 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_blocks", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const authored0 = readAuthored(payload.authored);
    if (!authored0) return reject("lb_blocks", preset, "payload.authored(대본)가 없다", "lb_script/lb_voice 응답의 carry(authored 포함)를 그대로 실어 다시 부르라.");
    const wavSecs = (typeof payload.wav_secs === "object" && payload.wav_secs !== null ? payload.wav_secs : {}) as Record<string, number>;
    const ps = payload.probe_summary as { win?: number | null; fps_fraction?: string | null } | undefined;
    const fps = ps?.fps_fraction && ps.fps_fraction !== "0/0" ? ps.fps_fraction : "30000/1001";
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, scene_count: payload.scene_count ?? null, 대사: payload.대사, 편정보: payload.편정보,
      wav_secs: wavSecs, narr_words: payload.narr_words,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "scene_count", "대사", "편정보", "wav_secs", "narr_words", "authored"];
    const nBlocks = authored0.BLOCKS.length;

    // ── D: 장면튐검사 로그 검사 → lb_subs ────────────────────────────────
    if (payload.jump_log !== undefined) {
      const log = String(payload.jump_log ?? "");
      const bad = log.split("\n").filter((l) => l.includes("✗")).map((l) => l.trim());
      if (bad.length || /막힘 \d+건/.test(log) || /블록이 \d+\/\d+ 개뿐/.test(log)) {
        return reject("lb_blocks", preset, `장면튐검사가 막았다 (${bad.length}건)`, "구운 블록으로 잰 튐이다(§47·§64). 번쩍임정리.py --쓰기 로 짧은 조각을 늘려 없애고(§34), 블록을 다시 구워야 하면 payload 에서 clip_secs_*·jump_log 를 빼고 lb_blocks 를 다시 부르라(authored 는 되읽은 것으로). 「블록이 N/M 개뿐」이면 굽기가 덜 됐다. " + bad.slice(0, 8).join(" | "));
      }
      return base("lb_blocks", preset, {
        status: "execute",
        next_step: "lb_subs",
        message: `블록 ${nBlocks}개 굽고 captions_서버원본.ass 를 냈다 — 한번에.sh 입력 6개(서버원본.ass·_block_jobs.json·blocks/·logo/·fonts/·편정보.json)가 편 폴더에 있다. lb_subs(서식·그래픽·계획)로.`,
        instructions: ["① carry 의 값(… authored·clip_secs)을 payload 에 그대로 실어 lb_subs 를 부른다."],
        then_call_with: ["step: 'lb_subs'", "payload: { …carry, authored, clip_secs }"],
        jobs_kind: null, jobs: [], measure: [],
        metrics: { blocks: nBlocks, total_s: payload.total_s ?? null },
        carry: [...carryKeys, "clip_secs", "total_s", "ass_fp"],
        ass_fp: payload.ass_fp ?? null,
        ...common, authored: authored0, clip_secs: payload.clip_secs, total_s: payload.total_s ?? null,
      });
    }

    // ── C: 실측 길이 → ass ──────────────────────────────────────────────
    const clipKeys = Array.from({ length: nBlocks }, (_, i) => `clip_secs_${String(i).padStart(2, "0")}`);
    if (clipKeys.some((k) => typeof payload[k] === "number") || payload.clip_secs !== undefined) {
      const clipSecs: Record<string, number> = {};
      const given = (typeof payload.clip_secs === "object" && payload.clip_secs !== null ? payload.clip_secs : {}) as Record<string, number>;
      const missing: number[] = [];
      for (let i = 0; i < nBlocks; i++) {
        const v = typeof payload[clipKeys[i]] === "number" ? (payload[clipKeys[i]] as number) : given[String(i)];
        if (typeof v !== "number" || !(v > 0)) missing.push(i); else clipSecs[String(i)] = v;
      }
      if (missing.length) return reject("lb_blocks", preset, `구운 블록 길이가 없는 블록: ${missing.join(", ")}`, "ffmpeg 블록 굽기가 그 블록에서 실패했다(로그를 보라). 고친 뒤 payload 의 clip_secs_* 를 다시 실어 lb_blocks 를 부르라.");
      const narrWords = (typeof payload.narr_words === "object" && payload.narr_words !== null ? payload.narr_words : {}) as Record<string, WordT[]>;
      const dlgWords = ((payload.대사 as { words?: { s: number; e: number; t: string }[] } | undefined)?.words ?? []).filter((w) => typeof w?.s === "number");
      let ass: string;
      try {
        ass = buildServerAss({ authored: authored0, clipSecs, wavSecs, narrWords, dlgWords });
      } catch (e) {
        return reject("lb_blocks", preset, `ass 를 못 지었다: ${(e as Error).message}`, "authored·wav_secs·clip_secs 가 carry 그대로인지 보고 다시 부르라.");
      }
      const total = r3(Object.values(clipSecs).reduce((x, y) => x + y, 0));
      const cardCount = (ass.match(/^Dialogue: 2,/gm) ?? []).length;
      const perMin = total ? r3((cardCount / total) * 60) : 0;
      const warnings: string[] = [];
      if (perMin < 9.1) warnings.push(`자막 ${cardCount}장 · 분당 ${perMin}장 — 서버 규칙 «분당 9.1장 이상»(caption cards_per_min) 에 못 미친다. 같은 내용을 더 잘게 끊어라(«|»)`);
      return base("lb_blocks", preset, {
        status: "execute",
        next_step: "lb_blocks",
        message: `블록 ${nBlocks}개 실측 합 ${total}초 · 자막 카드 ${cardCount}장(분당 ${perMin}). captions_서버원본.ass 를 쓰고 장면튐검사(구운 뒤)를 돌려 로그를 실어 다시 부르라.`,
        instructions: [
          "① write_files 대로 편 폴더에 captions_서버원본.ass 와 captions.ass(같은 내용 — 서버 원본 자리)를 쓴다. 채널 서식은 lb_subs 의 서식.py 가 입힌다.",
          `② jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로: 장면튐검사.py — 구운 블록 길이로 배율 순환·나레 화면·조각 길이를 잰다(§47·§64). 블록이 다 없으면 통과를 주지 않는다(rc 2).`,
          "③ measure 대로 payload.jump_log 를 실어 lb_blocks 를 **다시** 부른다.",
        ],
        then_call_with: ["step: 'lb_blocks'", "payload: { …carry, authored, clip_secs, total_s, jump_log: <stdout> }"],
        jobs_kind: "argv",
        jobs_cwd: carry.ep_dir,
        jobs: [{ name: "jump_check", argv: ["python", "장면튐검사.py"], optional: true, note: "편 폴더에 복사된 사본(편폴더차리기)을 돌린다. rc 1 = 막힘(✗ 줄), rc 2 = 블록 부족." }],
        write_files: [
          { path: join(carry.ep_dir, "state_payload.json"), content: { clip_secs: clipSecs, total_s: total, wav_secs: wavSecs, ass_fp: fnv1a64(ass) }, note: "볼케이노 서버가 남기던 state_payload.json 의 clip_secs 꼴 — 대조점짓기.py(lb_render)가 읽는다(2026-09-04 실호출: 없어서 _synccheck 3단계가 건너뜀)." },
          { path: join(carry.ep_dir, "captions_서버원본.ass"), content: ass, note: "볼케이노 stitch_master 가 내던 captions.ass 와 같은 꼴(스타일 8종 · 실측 누적 시각). 한번에.sh 입력 ①" },
          { path: join(carry.ep_dir, "captions.ass"), content: ass, note: "서버 원본 자리 — 완성검사 [8] sha256 대조용" },
        ],
        measure: [{ as: "jump_log", from: "job:jump_check", unit: "stdout" }],
        metrics: { blocks: nBlocks, total_s: total, cards: cardCount, cards_per_min: perMin },
        carry: [...carryKeys, "clip_secs", "total_s", "ass_fp"],
        ...common, authored: authored0, clip_secs: clipSecs, total_s: total, ass_fp: fnv1a64(ass), // 완성검사 8 — 러너가 같은 FNV-1a 64 로 파일을 재서 견준다(check.ts)
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── B: 블록 계획 → 굽기 ─────────────────────────────────────────────
    if (payload.authored2 !== undefined || payload.blocks_ready === true) {
      const a2 = readAuthored(payload.authored2) ?? authored0;
      const log2 = String(payload.script_log2 ?? "");
      const mlog2 = String(payload.missing_log2 ?? "");
      const bad = [...log2.split("\n"), ...mlog2.split("\n")].filter((l) => l.includes("✗")).map((l) => l.trim());
      if (bad.length || /막힘 \d+건/.test(log2) || /막힘 \d+건/.test(mlog2)) {
        return reject("lb_blocks", preset, `컷 손질 뒤 대본검사·대사빠짐검사가 막았다 (${bad.length}건)`, "원음 블록이 전환을 가로지르거나 짧은 조각이 남았거나(대본검사), 말은 나는데 자막이 그 말을 안 담았다(대사빠짐검사 §94 — SRT 글자를 넣거나 블록을 그 말 뒤에서 열어라). 편 폴더의 authored.json 을 보고 그 블록의 시작·끝을 옮기거나 대사를 뺀 뒤(§20·§30), 고친 authored 를 lb_script 부터 다시 태우거나 lb_blocks A 를 다시 부르라. " + bad.slice(0, 8).join(" | "));
      }
      let plan;
      try {
        plan = planBlocks(a2, wavSecs);
      } catch (e) {
        return reject("lb_blocks", preset, `블록 계획을 못 짰다: ${(e as Error).message}`, "lb_voice 의 wav_secs(나레 블록마다 길이)가 carry 로 왔는지 보라.");
      }
      const jobs = plan.map((p) => ({ index: p.index, kind: p.kind, seconds: p.seconds, cuts: 1, out: join(carry.ep_dir, "blocks", `${nn(p.index)}.mp4`), argv: blockArgv(p, carry.ep_dir, fps) }));
      // ★볼케이노 꼴 그대로 **절대경로** — 마스터맞춤.py 가 편 폴더(cwd)에서 이 줄을 그대로 열므로 상대경로면 못 찾는다(2026-09-04 실호출)
      const concatTxt = plan.map((p) => `file '${join(carry.ep_dir, "blocks", `${nn(p.index)}.mp4`)}'`).join("\n") + "\n";
      const plannedTotal = r3(plan.reduce((x, p) => x + p.seconds, 0));
      return base("lb_blocks", preset, {
        status: "execute",
        next_step: "lb_blocks",
        message: `블록 ${plan.length}개(N ${plan.filter((p) => p.kind === "N").length} · D ${plan.filter((p) => p.kind === "D").length}) 계획 ${plannedTotal}초 — 편 폴더에 _block_jobs.json 을 쓰고 블록을 굽고 이어 붙인 뒤, 블록마다 실측 길이를 실어 다시 부르라.`,
        instructions: [
          `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로. do 가 _block_jobs.json(볼케이노 stitch_blocks jobs 꼴 그대로)과 blocks/concat.txt 를 먼저 쓴다. blocks/ 폴더를 만든다.`,
          `② 블록 argv ${plan.length}개를 그대로 실행한다(한 글자도 고치지 않는다 · 동시 6개까지). 소재 프레임률 ${fps} 로 굽는다(§82). 이미 있는 bNN.mp4 도 다시 굽는다(입력이 바뀌었을 수 있다).`,
          "③ concat 으로 blocks/merged.mp4 를 잇는다. measure 대로 블록마다 실측 길이(초)를 payload.clip_secs_NN 에 실어 lb_blocks 를 **다시** 부른다 — 자막 시각은 이 실측으로 짓는다.",
        ],
        then_call_with: ["step: 'lb_blocks'", `payload: { …carry, authored: <되읽은 authored>, ${plan.map((p) => `clip_secs_${String(p.index).padStart(2, "0")}`).slice(0, 3).join(", ")}, … }`],
        jobs_kind: "argv",
        jobs_cwd: carry.ep_dir,
        do: [
          { name: "write_block_jobs", argv: ["python", "-c", "import json,sys,os;os.makedirs('blocks',exist_ok=True);json.dump(json.loads(sys.argv[1]),open('_block_jobs.json','w',encoding='utf-8'),ensure_ascii=False,indent=1);open('blocks/concat.txt','w',encoding='utf-8').write(sys.argv[2]);print('_block_jobs.json',len(json.loads(sys.argv[1])))", JSON.stringify(jobs), concatTxt], out: join(carry.ep_dir, "_block_jobs_log.txt"), note: "볼케이노 _block_jobs.json 꼴(index·kind·seconds·cuts·out·argv). 계획짓기.py(lb_subs)가 argv 의 trim=end_frame 과 -ss 를 읽는다." },
        ],
        jobs: [
          ...jobs.map((j) => ({ name: nn(j.index), argv: j.argv, note: `${j.kind} 블록 ${j.seconds}초` })),
          { name: "concat", argv: ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", join(carry.ep_dir, "blocks", "concat.txt"), "-c", "copy", join(carry.ep_dir, "blocks", "merged.mp4"), "-loglevel", "error"], note: "볼케이노 concat_argv 그대로 — 블록 이어 붙임(서버 merged.mp4)." },
        ],
        measure: plan.map((p) => ({ as: `clip_secs_${String(p.index).padStart(2, "0")}`, from: `job:${nn(p.index)}`, unit: "seconds" as const })),
        metrics: { blocks: plan.length, planned_total_s: plannedTotal, fps },
        carry: carryKeys,
        ...common, authored: a2,
        block_plan: plan,
      });
    }

    // ── A: 편 폴더 차리기 → 얼굴·재프레이밍 → 컷 손질 ────────────────────
    const win = ps?.win ?? null;
    if (!win) return reject("lb_blocks", preset, "probe_summary.win(재프레이밍 창 폭)이 없다", "lb_probe 응답의 probe_summary 를 carry 그대로 실어 다시 부르라.");
    const forbid = Array.isArray(payload.forbidden_ranges) ? (payload.forbidden_ranges as unknown[]) : [];
    return base("lb_blocks", preset, {
      status: "execute",
      next_step: "lb_blocks",
      message: `편 폴더에 도구·글꼴·yunet 을 놓고(▼편별 WIN ${win}) 얼굴 → 재프레이밍(구간_인물.mp4) → 컷 손질(fix_cuts·컷다듬기·번쩍임정리) → 대본검사 를 차례로 돌리라. 끝나면 되읽은 authored 와 로그를 실어 다시 부른다.`,
      instructions: [
        `① do 의 편폴더차리기가 도구 사본을 ${carry.ep_dir} 에 놓고 WIN·SRC·금지구간을 박는다(새편.py 방식 — 러너 원본은 안 건드린다). 글꼴은 저장소 자산/린박스/fonts 에서.`,
        "② jobs 순서대로: find_faces(촬영본마다 얼굴 → faces.json) → 인물따라가기 --쓰기(한 사람이 촬영본 안에서 벗어나는 자리, ease 0.35 · optional) → reframe(인물을 창 가운데로 → 구간_인물.mp4) → fix_cuts(나레 컷을 촬영본 안·이웃과 다른 촬영본으로 §7) → 컷다듬기(원음 블록을 촬영본 안으로, 무대사 꼬리 제거) → 번쩍임정리 --쓰기(짧은 조각을 늘려서 §34) → 자막경계맞춤 --쓰기(§94 · 경계가 줄어 블록 밖으로 나간 말을 자막에서 뺀다) → 대사빠짐검사(§94 · srt원본 있을 때) → 대본검사(§64 · optional, 로그만).",
        "③ measure 대로 payload.authored2(되읽은 authored.json — 손질로 시각이 바뀌었다)·script_log2·missing_log2·reframe_log 를 실어 lb_blocks 를 **다시** 부른다.",
      ],
      then_call_with: ["step: 'lb_blocks'", "payload: { …carry, authored2: <authored.json>, script_log2: <대본검사 stdout>, reframe_log: <stdout> }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      do: [{ name: "setup_ep", argv: ["python", tool("편폴더차리기.py"), carry.ep_dir, "--repo", repo, "--win", String(win), "--금지구간", JSON.stringify(forbid)], out: join(carry.ep_dir, "_setup_ep_log.txt"), note: "도구 11개 + yunet.onnx + fonts/ → 편 폴더. ▼편별: find_faces/reframe WIN · fix_cuts 금지구간(payload.forbidden_ranges — 제목 카드·로고·예고편 자리, 규격 §27)." }],
      jobs: [
        { name: "faces", argv: ["python", "find_faces.py"], note: "촬영본마다 얼굴(프레임별 최대 얼굴 중앙값) → faces.json. 「얼굴 0」 이 많으면 yunet.onnx 확인." },
        { name: "follow", argv: ["python", "인물따라가기.py", "--쓰기"], optional: true, note: "한 사람이 촬영본 안에서 움직여 벗어나는 자리를 나눈다(1-7편 촬영본 33개 중 15개)." },
        { name: "reframe", argv: ["python", "reframe.py"], out: join(carry.ep_dir, "_reframe_log.txt"), note: "인물을 창 가운데로 → 구간_인물.mp4 (1080×1020). 창 이동 ≤ 260px/초." },
        { name: "fix_cuts", argv: ["python", "fix_cuts.py"], note: "나레 정지컷을 촬영본 안 · 이웃 원음 블록과 다른 촬영본으로(§7). authored.json 을 고쳐 쓴다." },
        { name: "trim_cuts", argv: ["python", "컷다듬기.py"], note: "원음 블록을 촬영본 안으로 조이고 무대사 꼬리·번쩍임 조각을 잘라낸다(§7). authored.json 을 고쳐 쓴다." },
        { name: "deflicker", argv: ["python", "번쩍임정리.py", "--쓰기"], optional: true, note: "남은 짧은 조각을 늘려서 없앤다(§34 · 목표 1.30 · 막힘 1.00 · 낱말 안 가름)." },
        { name: "bound_fix", argv: ["python", tool("자막경계맞춤.py"), "--쓰기"], optional: true, note: "§94 — 컷 손질이 블록 경계를 줄여도 자막이 블록 안에서 나는 말만 담게(판정 근거 srt대사.txt · 없으면 건너뜀). authored.json 을 고쳐 쓴다." },
        { name: "dlg_missing2", argv: ["python", tool("대사빠짐검사.py")], optional: true, note: "§94 게이트(손질 뒤 다시) — srt원본 이 있으면 D 블록 안 SRT 말이 자막에 담겼는가. ✗ 면 서버가 반려한다." },
        { name: "script_check2", argv: ["python", "대본검사.py"], optional: true, note: "손질 뒤 다시 — ✗ 가 남으면 서버가 반려한다." },
        { name: "read_authored", argv: ["python", "-c", "import io;print(io.open('authored.json',encoding='utf-8').read())"], note: "손질된 authored.json 을 되읽는다 — 이 값으로 블록을 계획한다." },
      ],
      measure: [
        { as: "authored2", from: "job:read_authored", unit: "json_stdout" },
        { as: "script_log2", from: "job:script_check2", unit: "stdout" },
        { as: "missing_log2", from: "job:dlg_missing2", unit: "stdout" },
        { as: "reframe_log", from: "job:reframe", unit: "stdout" },
      ],
      metrics: { blocks: nBlocks, win },
      carry: carryKeys,
      ...common, authored: authored0,
    });
  },
};
