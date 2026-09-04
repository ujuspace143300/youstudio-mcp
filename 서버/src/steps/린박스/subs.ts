/**
 * steps/린박스/subs.ts — lb_subs: 정본 맥 사슬 `신병4/한번에.sh` ①·①.5 를 처리기 지시(jobs)로 편 것. 두 번 부른다.
 *
 *   ① payload.배치계획 이 없으면 → jobs (편 폴더 cwd, 순서대로):
 *        자막말머리맞춤 --쓰기 → 자막말머리맞춤(재기 · §93/완성검사 14) → 서식.py(채널 서식 · captions.ass → captions_<작품>.ass)
 *        → 폭맞춤 → 로고판(credit_cta 뺀 ass) → ass자리검사 → 구둣점검사 → 그래픽짓기 → 계획짓기 → 자막끝맞춤 ×2(완성검사 12) → 원음스템
 *        → 배치계획.json 되읽기. 로그를 measure 로 실어 다시 자기 자신.
 *   ② payload.배치계획 이 있으면 → 로그 판정(✗·벗어남·초과가 하나라도 있으면 반려) → next_step=lb_xml
 *
 * 한번에.sh 와 다른 점
 *   · 자막말머리맞춤은 볼케이노 서버사슬(한편.py ②굽기)에 있던 것 — 2026-09-04 승격 제안 A 를 여기서 함께 반영(이식원칙 ⑤).
 *     captions.ass(= 서버 ass 상당, lb_blocks C 가 씀)를 고치고, captions_서버원본.ass 는 그대로 둔다(EP19 대조 게이트).
 *   · 서식.py 의 값은 신병4 곳간(키트 스타일/신병4_본)이다 — 작품별 곳간은 아직 없다(README 「알아 둘 것」).
 *   · 편정보.json 제목 ≠ authored HEADLINE 검사(한번에.sh 첫 관문)는 lb_script ③ 이 이미 맞춰 둔다.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, r3, readCarry, str } from "./lib.js";

const num1 = (s: string, re: RegExp): number | null => { const m = s.match(re); return m ? Number(m[1]) : null; };

export const lbSubs: StepHandler = {
  name: "lb_subs",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string; title?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_subs", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_blocks 응답의 carry 값을 payload 에 그대로 실어 lb_subs 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_subs", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const title = (typeof source.title === "string" && source.title.trim()) || "린박스";
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const ass = join(carry.ep_dir, `captions_${title}.ass`);
    const assLogo = join(carry.ep_dir, `captions_${title}_로고.ass`);
    const fonts = join(carry.ep_dir, "fonts");
    const 편정보 = (typeof payload.편정보 === "object" && payload.편정보 !== null ? payload.편정보 : {}) as { 로고?: unknown };
    const useLogo = typeof 편정보.로고 === "string" && 편정보.로고 !== "없음" && 편정보.로고 !== "";
    const totalS = typeof payload.total_s === "number" ? payload.total_s : null;
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, 편정보: payload.편정보, authored: payload.authored, clip_secs: payload.clip_secs, total_s: totalS,
      srt_pick: payload.srt_pick ?? null, ass_fp: payload.ass_fp ?? null, title, ass, ass_logo: assLogo,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "편정보", "authored", "clip_secs", "total_s", "srt_pick", "title", "ass", "ass_logo", "ass_fp"];

    // ── ② 로그 판정 → lb_xml ─────────────────────────────────────────────
    if (payload.배치계획 !== undefined) {
      const L = (k: string) => String(payload[k] ?? "");
      const bad: string[] = [];
      const warnings: string[] = [];
      const head = L("head_log");
      if (head.includes("✗")) bad.push(`자막말머리맞춤(§93·완성검사 14): --쓰기 뒤에도 말과 어긋난 카드가 남았다 — ${head.split("\n").filter((l) => l.includes("✗")).slice(0, 4).map((l) => l.trim()).join(" | ")}. blocks/bNN.mp4 소리가 비었거나(포락 없음) 카드가 0.5초보다 짧아 못 옮긴 것이다 — 그 블록의 대사를 빼거나 시작을 말머리로 옮겨라.`);
      const posOut = num1(L("pos_log"), /벗어난 것 (\d+)장/);
      if (posOut === null) warnings.push("ass자리검사 로그에서 「벗어난 것 N장」을 못 읽었다 — 글꼴방(fonts/)·libass(ffmpeg-full) 확인.");
      else if (posOut > 0) bad.push(`ass자리검사: 자막 ${posOut}장이 화면·매트를 벗어난다 — 로그의 «무엇이 벗어났나» 대로 그 카드의 글자를 줄이거나(효과자막은 x·y §5) 나눠라.`);
      const punct = L("punct_log");
      if (punct.includes("✗")) bad.push(`구둣점검사: 나레·대사에 구둣점이 있다 — ${punct.split("\n").filter((l) => l.includes("✗")).slice(0, 4).map((l) => l.trim()).join(" | ")}. 대본(authored)을 고쳐 lb_script 부터 다시(서버는 구둣점을 안 걸러 준다 · EP5 「하나, 그리고 거기」).`);
      for (const [k, label] of [["endfit_log", "captions"], ["endfit_logo_log", "로고판"]] as const) {
        const over = num1(L(k), /되읽기 초과 (\d+)/);
        if (over === null) bad.push(`자막끝맞춤(${label}) 로그를 못 읽었다 — 배치계획.json 이 없거나 ass 를 못 열었다.`);
        else if (over > 0) bad.push(`자막끝맞춤(${label}): 영상 끝을 넘는 줄이 ${over}개 남았다(완성검사 12) — 배치계획.json 의 total 과 ass 끝을 대조하라.`);
      }
      const plan = payload.배치계획 as { total?: unknown } | null;
      const totalFrames = typeof plan?.total === "number" ? plan.total : null;
      if (totalFrames === null) bad.push("배치계획.json 에 total(총 프레임)이 없다 — 계획짓기.py 가 _block_jobs.json 을 못 읽었다(lb_blocks B 가 쓴 파일인지 확인).");
      else if (totalS !== null && Math.abs(totalFrames / 30 - totalS) > 0.25) warnings.push(`배치계획 총 ${totalFrames}프레임(${r3(totalFrames / 30)}초)과 블록 실측 합 ${totalS}초가 0.25초 넘게 다르다 — 계획짓기는 30fps 로 세고 블록은 소재 프레임률로 구웠다(§82). 자막끝맞춤이 계획 쪽에 맞췄으니 완성본 끝을 눈으로 본다.`);
      const stems = num1(L("stems_log"), /원음 스템 (\d+)개/);
      if (stems === null) warnings.push("원음스템 로그에서 개수를 못 읽었다 — 편집소스/원음 이 비었으면 lb_xml 의 A1 이 빈다.");
      const width = num1(L("width_log"), /좁힌 줄 (\d+)개/);
      if (bad.length) {
        return reject("lb_subs", preset, `자막 서식 관문이 막았다 (${bad.length}건)`, bad.map((x, i) => `${i + 1}) ${x}`).join(" ") + " 고친 뒤 lb_subs 를 다시 부르라(배치계획 은 빼고).");
      }
      return base("lb_subs", preset, {
        status: "execute",
        next_step: "lb_xml",
        message: `자막 서식 ①·①.5 통과 — 총 ${totalFrames}프레임 · 좁힌 줄 ${width ?? "?"} · 원음 스템 ${stems ?? "?"}개 · 그래픽/·컷계획·배치계획 있음. 이제 lb_xml(FCP7 XML)로.`,
        instructions: [
          "① carry 의 값(… ass·ass_logo·title 포함)을 payload 에 그대로 실어 lb_xml 을 부른다.",
          "② 편집용 마스터(편정보.json 의 «마스터»)가 소재 폴더에 있어야 한다 — lb_xml 이 그 파일로 V1 컷을 문다.",
        ],
        then_call_with: ["step: 'lb_xml'", "payload: { …carry, 배치계획 }"],
        jobs_kind: null,
        jobs: [],
        measure: [],
        metrics: { total_frames: totalFrames, total_s: totalS, narrowed_lines: width, stems, pos_out: posOut ?? 0 },
        carry: [...carryKeys, "배치계획"],
        ...common,
        배치계획: payload.배치계획,
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ① 서식·그래픽·계획 지시 ───────────────────────────────────────────
    const logoArgs = useLogo ? ["--로고", join(carry.ep_dir, "logo", "logo_bottom.png")] : [];
    return base("lb_subs", preset, {
      status: "execute",
      next_step: "lb_subs",
      message: `자막 서식 차례(한번에.sh ①·①.5) — 자막 말머리를 소리로 맞추고(§93), 채널 서식(서식.py)으로 captions_${title}.ass 를 짓고, 폭·자리·구둣점을 재고, 그래픽/·컷계획·배치계획 을 지은 뒤 자막 끝을 영상 끝 안으로 자른다. 로그를 실어 다시 부르라.`,
      instructions: [
        `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 순서대로. head_fix 가 captions.ass 의 원음 카드 시작을 blocks/bNN.mp4 소리 말머리에 맞춘다(--쓰기) — captions_서버원본.ass 는 안 건드린다. head_check 가 다시 재서 ✗ 면 서버가 반려한다(완성검사 14).`,
        `② 서식.py 는 편정보.json 의 «제목»(2줄)을 headline 에 넣고 신병4 곳간 서식(Paperlogy·강원교육모두·Gmarket)으로 바꾼다 — 그 글꼴이 이 컴퓨터에 깔려 있어야 폭맞춤·ass자리검사가 맞게 잰다(fonts/ 에는 Gmarket 만 있다). 없으면 setup 안내대로 깐다.`,
        "③ 폭맞춤(1000px 넘는 줄을 fscx 로 좁힘) → 로고판(credit_cta 를 뺀 captions_<작품>_로고.ass) → ass자리검사(여백 20) → 구둣점검사 → 그래픽짓기(매트·로고·제목·효과 PNG + 효과계획.json) → 계획짓기(컷계획·배치계획, 오프셋은 편정보 «구간오프셋») → 자막끝맞춤 ×2 → 원음스템(편집소스/원음).",
        "④ measure 대로 로그 9개와 배치계획.json 을 실어 lb_subs 를 **다시** 부른다 — 실패 rc 라도 로그는 실어 보내라(판정은 서버).",
      ],
      then_call_with: ["step: 'lb_subs'", "payload: { …carry, head_log, width_log, pos_log, punct_log, graphics_log, plan_log, endfit_log, endfit_logo_log, stems_log, 배치계획 }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        { name: "head_fix", argv: ["python", tool("자막말머리맞춤.py"), "--쓰기"], optional: true, note: "§93 — 블록 소리로 말머리를 찾아 원음 첫 카드를 양방향으로 맞춘다(captions.ass). 나레·제목·크레딧은 안 건드린다." },
        { name: "head_check", argv: ["python", tool("자막말머리맞춤.py")], optional: true, note: "재기만 — 어긋나면 ✗ + rc 1(볼트 승격판). 서버가 판정한다." },
        { name: "restyle", argv: ["python", tool("서식.py"), join(carry.ep_dir, "captions.ass"), ass], note: "채널 서식(신병4 곳간) + 편정보 제목 → captions_<작품>.ass. 「서식 N줄 · 자리 N줄 · 제목 N줄 바꿈」." },
        { name: "fit_width", argv: ["python", tool("폭맞춤.py"), ass, fonts, "1000"], out: join(carry.ep_dir, "_width_log.txt"), note: "2400 화포에서 참 폭을 재서 1000px 넘는 줄을 \\fscx 로 좁힌다." },
        { name: "logo_ass", argv: ["python", "-c", "import io,sys;ls=[l for l in io.open(sys.argv[1],encoding='utf-8').read().split(chr(10)) if 'credit_cta' not in l];io.open(sys.argv[2],'w',encoding='utf-8').write(chr(10).join(ls));print(sys.argv[2],len(ls))", ass, assLogo], note: "한번에.sh 의 grep -v credit_cta — 로고판 ass(크레딧 줄 없음)." },
        { name: "pos_check", argv: ["python", tool("ass자리검사.py"), ass, fonts, "20"], optional: true, note: "낱장을 제자리 그대로 그려 화면·매트를 벗어나는 줄 — 「벗어난 것 N장」. N>0 이면 rc 1." },
        { name: "punct_check", argv: ["python", tool("구둣점검사.py"), ass], optional: true, note: "나레·대사 구둣점 — ✗ 줄 + rc 1 (EP5 「하나, 그리고 거기」 가 납품까지 갔다)." },
        { name: "graphics", argv: ["python", tool("그래픽짓기.py"), carry.ep_dir, "--자막", ass, ...logoArgs], out: join(carry.ep_dir, "_graphics_log.txt"), note: "그래픽/ 매트.png·로고.png·제목.png·효과NN.png + 효과계획.json (로고 윗선·높이는 편정보.json)." },
        { name: "plan", argv: ["python", tool("계획짓기.py"), carry.ep_dir], out: join(carry.ep_dir, "_plan_log.txt"), note: "_block_jobs.json + 효과계획.json → 컷계획.json · 배치계획.json (30fps · 오프셋 = 편정보 «구간오프셋»)." },
        { name: "end_fit", argv: ["python", tool("자막끝맞춤.py"), ass, join(carry.ep_dir, "배치계획.json")], optional: true, note: "완성검사 12 — 자막 끝을 총 프레임 안으로. 「되읽기 초과 0」 이어야 한다." },
        { name: "end_fit_logo", argv: ["python", tool("자막끝맞춤.py"), assLogo, join(carry.ep_dir, "배치계획.json")], optional: true, note: "로고판도 같이." },
        { name: "stems", argv: ["python", tool("원음스템.py"), carry.ep_dir], out: join(carry.ep_dir, "_stems_log.txt"), note: "블록마다 나레를 걷어낸 원음 wav → 편집소스/원음 (프리미어 A1). 서버 argv 에서 나레 입력만 도려내 같은 필터로 굽는다." },
        { name: "read_plan", argv: ["python", "-c", "import io;print(io.open('배치계획.json',encoding='utf-8').read())"], note: "배치계획.json 을 measure 로." },
      ],
      measure: [
        { as: "head_log", from: "job:head_check", unit: "stdout" },
        { as: "width_log", from: "job:fit_width", unit: "stdout" },
        { as: "pos_log", from: "job:pos_check", unit: "stdout" },
        { as: "punct_log", from: "job:punct_check", unit: "stdout" },
        { as: "graphics_log", from: "job:graphics", unit: "stdout" },
        { as: "plan_log", from: "job:plan", unit: "stdout" },
        { as: "endfit_log", from: "job:end_fit", unit: "stdout" },
        { as: "endfit_logo_log", from: "job:end_fit_logo", unit: "stdout" },
        { as: "stems_log", from: "job:stems", unit: "stdout" },
        { as: "배치계획", from: "job:read_plan", unit: "json_stdout" },
      ],
      metrics: { total_s: totalS, logo: useLogo },
      carry: carryKeys,
      ...common,
    });
  },
};
