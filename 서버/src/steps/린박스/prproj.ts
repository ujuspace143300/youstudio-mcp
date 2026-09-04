/**
 * steps/린박스/prproj.ts — lb_prproj: 정본 맥 사슬 `신병4/한번에.sh` ③~⑬.5 를 처리기 지시로. 세 번 부른다.
 *
 *   ① ppro_log 없음 → jobs: 프리미어돌리기.py <xml> <prproj> (잠금 → 프리미어 끄기 → 대기줄 → 프리미어 실행 → CEP 확장이 prproj 로 → 잠잠해질 때까지 → 끄기 → _갓지은판 사본)
 *   ② ppro_log 있음·endcheck_log 없음 → 「✓ prproj N 경로」 확인 → jobs ④~⑬.5:
 *        본떠서만들기(곳간) → 서식입히기 → 자리잡기 → 꾸미기 → 가로비율 → 그림자빼기 → 주입검사(--기준 갓지은판) → 자막자리검사(관문 ⑪)
 *        → 마스터효과심기(--도너) + --확인만(완성검사 11) → 주입검사 → 아모르입히기(--팝 부품) → 주입검사(--본 부품 --기준 .아모르전) → 제목끝맞춤 --확인만(완성검사 12)
 *   ③ endcheck_log 있음 → 로그 전부 판정(못 찾은 0 · 탈 0 · 마스터 효과 rc 0 · 아모르 달았다 · 클립 끝 rc 0) → next_step=lb_render
 *
 * 한번에.sh 와 다른 점
 *   · 셸의 잠금·대기줄·pkill 루프를 프리미어돌리기.py 한 도구로(맥·윈도우 둘 다). 곳간·아모르 부품·마스터 도너는 저장소 서버/runner/린박스/스타일/ 에서.
 *   · 곳간 이름은 「신병4」 고정(본떠서만들기 짝표에 있는 것 — 불륜도 신병4 짝을 쓴다). 작품별 곳간은 다음 과제.
 *   · --확인만 같은 «종료코드가 답» 인 도구는 python -c 래퍼로 「확인만 rc=N」 을 찍어 서버가 읽는다(러너 measure 는 stdout 만 준다).
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, readCarry, str } from "./lib.js";

const RC_WRAP = "import subprocess,sys;r=subprocess.run([sys.executable]+sys.argv[1:],capture_output=True,text=True,encoding='utf-8',errors='replace');print(r.stdout);print(r.stderr[-400:]);print('확인만 rc=%d'%r.returncode)";
const n1 = (s: string, re: RegExp): number | null => { const m = s.match(re); return m ? Number(m[1]) : null; };
const KOTGAN = "신병4";

export const lbPrproj: StepHandler = {
  name: "lb_prproj",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string; title?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_prproj", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_xml 응답의 carry 값을 payload 에 그대로 실어 lb_prproj 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_prproj", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const title = str(payload, "title") || (typeof source.title === "string" && source.title.trim()) || "린박스";
    const xml = str(payload, "xml") || join(carry.ep_dir, `${title}_${carry.ep}.xml`);
    const ass = str(payload, "ass") || join(carry.ep_dir, `captions_${title}.ass`);
    const prproj = join(carry.ep_dir, `${title}_${carry.ep}.prproj`);
    const fresh = join(carry.ep_dir, "_갓지은판.prproj");
    const kit = (name: string) => join(repo, RUNNER_DIR, name);
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const style = (name: string) => join(repo, RUNNER_DIR, "스타일", name);
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, 편정보: payload.편정보, authored: payload.authored, clip_secs: payload.clip_secs, total_s: payload.total_s ?? null,
      srt_pick: payload.srt_pick ?? null, title, ass, ass_logo: payload.ass_logo ?? join(carry.ep_dir, `captions_${title}_로고.ass`), 배치계획: payload.배치계획 ?? null, xml, master: payload.master ?? source.path, prproj,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "편정보", "authored", "clip_secs", "total_s", "srt_pick", "title", "ass", "ass_logo", "배치계획", "xml", "master", "prproj"];
    const L = (k: string) => String(payload[k] ?? "");

    // ── ③ 손질·관문 로그 판정 → lb_render ───────────────────────────────
    if (payload.endcheck_log !== undefined) {
      const bad: string[] = [];
      const warnings: string[] = [];
      const kot = L("kot_log");
      const km = kot.match(/되읽기 확인 — (\d+)\/(\d+) 정상/);
      if (!km) bad.push("본떠서만들기(④ 곳간 서식): 「되읽기 확인 — N/N 정상」 이 없다 — 곳간(스타일/신병4_本.json)을 못 찾았거나 프로젝트를 못 열었다.");
      else if (km[1] !== km[2]) bad.push(`본떠서만들기: 되읽기 ${km[1]}/${km[2]} — 서식이 일부 안 들어갔다.`);
      for (const [k, label, re] of [["style_log", "서식입히기(⑤)", /못 찾은 것 (\d+)장/], ["place_log", "자리잡기(⑥)", /못 찾은 것 (\d+)장/]] as const) {
        const miss = n1(L(k), re);
        if (miss === null) bad.push(`${label}: 「못 찾은 것 N장」 을 못 읽었다 — 도구가 죽었다(로그를 보라).`);
        else if (miss > 0) bad.push(`${label}: ass 의 카드 ${miss}장을 프로젝트에서 못 찾았다 — XML 텍스트와 ass 글자가 다르다(폭맞춤·자막끝맞춤 뒤 ass 로 XML 을 지었는지).`);
      }
      if (!/넣었다/.test(L("deco_log"))) warnings.push("꾸미기(⑦) 로그에 「넣었다」 가 없다 — 그림자·등장 팝이 안 들어갔을 수 있다.");
      const shadowLeft = n1(L("shadow_log"), /아직 남은 것 (\d+)장/);
      if (shadowLeft === null) warnings.push("그림자빼기(⑨) 로그를 못 읽었다.");
      else if (shadowLeft > 0) bad.push(`그림자빼기: 그림자가 아직 ${shadowLeft}장 남았다.`);
      for (const [k, label] of [["inject_log", "주입검사(⑩ 파일 성함)"], ["inject2_log", "주입검사(⑫ 마스터 효과 뒤)"], ["inject3_log", "주입검사(⑬ 아모르 뒤 · --본 부품)"]] as const) {
        const log = L(k);
        if (!/탈 없다/.test(log)) bad.push(`${label}: 「탈 없다」 가 아니다 — ${log.split("\n").filter((l) => /✗|★/.test(l)).slice(0, 3).map((l) => l.trim()).join(" | ") || "로그 없음"}. 프리미어가 이 파일을 못 연다 — 그 단계 도구를 되돌리고(사본 *전_*.prproj) 다시.`);
      }
      const subpos = L("subpos_log");
      const tal = n1(subpos, /\*\*탈 (\d+)장\*\*/);
      if (tal === null) bad.push("자막자리검사(⑪ 관문): 「탈 N장」 을 못 읽었다 — 도구가 죽었다.");
      else if (tal > 0) bad.push(`자막자리검사(⑪ 관문): 자막 ${tal}장이 ass 자리와 다르다 — 납품 금지. 자리잡기 로그와 ass 의 \\pos 를 대조하라.`);
      const master = L("master_log");
      if (!/파라미터 값 도너와 동일 ✓|이미 다 걸려 있다/.test(master)) bad.push(`마스터효과심기(⑫): 「파라미터 값 도너와 동일 ✓」 도 「이미 다 걸려 있다」 도 아니다 — ${master.split("\n").filter((l) => /★/.test(l)).slice(0, 2).join(" | ") || "도너(스타일/마스터효과_도너.prproj)를 확인"}.`);
      const mrc = n1(L("master_check_log"), /확인만 rc=(\d+)/);
      if (mrc !== 0) bad.push(`마스터 트랙 효과 확인(완성검사 11): 멀티밴드 «브로드캐스트» + 선택적 제한 −3dB 가 안 걸려 있다(rc ${mrc ?? "?"}) — prproj 미완.`);
      const amor = L("amor_log");
      const amorN = n1(amor, /달았다 — 벡터 모션 (\d+)장/);
      if (amorN === null) bad.push(`아모르입히기(⑬): 「달았다 — 벡터 모션 N장」 이 없다 — ${amor.split("\n").filter((l) => /못 찾|★|건너뛴/.test(l)).slice(0, 2).map((l) => l.trim()).join(" | ") || "부품(스타일/아모르_부품.prproj) 확인"}.`);
      else if (amorN === 0) warnings.push("아모르 0장 — 나레·대사 층을 못 찾았다(서식 이름이 곳간과 다른가).");
      const erc = n1(L("endcheck_log"), /확인만 rc=(\d+)/);
      if (erc !== 0) bad.push(`제목끝맞춤 --확인만(⑬.5 · 완성검사 12): 영상 끝을 넘는 클립이 있다(rc ${erc ?? "?"}) — 자막끝맞춤이 안 돌았거나 곳간 서식이 늘렸다. ${L("endcheck_log").split("\n").find((l) => /넘는 End/.test(l)) ?? ""}`);
      if (bad.length) {
        return reject("lb_prproj", preset, `prproj 손질·관문이 막았다 (${bad.length}건)`, bad.map((x, i) => `${i + 1}) ${x}`).join(" ") + " 고친 뒤 lb_prproj 를 다시 부르라(ppro_log 부터 빼면 프리미어부터, endcheck_log 만 빼면 손질부터).");
      }
      return base("lb_prproj", preset, {
        status: "execute",
        next_step: "lb_render",
        message: `prproj 완성 — ${prproj} · 곳간 서식 ${km![2]}장 · 아모르 ${amorN}장 · 자막 자리 관문 통과 · 마스터 효과(브로드캐스트 −3dB) 확인 · 클립 끝 관문 통과. 이제 lb_render(⑭ 납품 소리·완성본)로.`,
        instructions: [
          "① carry 의 값(… prproj 포함)을 payload 에 그대로 실어 lb_render 를 부른다.",
          "② prproj 는 프리미어로 열어 눈으로 확인할 수 있다(작업규칙 완성검사 11 — 마스터 트랙 효과 슬롯). 지금 열면 잠금은 없다(④ 이후는 프리미어가 필요 없다).",
        ],
        then_call_with: ["step: 'lb_render'", "payload: { …carry }"],
        jobs_kind: null,
        jobs: [],
        measure: [],
        metrics: { kot_ok: Number(km![1]), amor: amorN, shadow_left: shadowLeft ?? 0, subpos_bad: tal ?? 0 },
        carry: carryKeys,
        ...common,
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ② 프리미어 결과 확인 → ④~⑬.5 ────────────────────────────────────
    if (payload.ppro_log !== undefined) {
      const log = L("ppro_log");
      const m = log.match(/✓ prproj (\d+) (.+)/);
      if (!m) {
        return reject("lb_prproj", preset, "프리미어가 prproj 를 안 만들었다", "프리미어돌리기 로그를 보라 — ✗ 줄: " + (log.split("\n").filter((l) => l.includes("✗")).slice(0, 3).map((l) => l.trim()).join(" | ") || "없음") + ". 확장(com.volcano.prproj)이 깔렸는지·~/.volcano/prproj_log.txt 를 확인하고 lb_prproj 를 다시 부르라(ppro_log 빼고).");
      }
      const bytes = Number(m[1]);
      if (bytes < 10000) return reject("lb_prproj", preset, `prproj 가 ${bytes}바이트뿐이다 — 껍데기다`, "확장이 XML 을 못 가져왔다(newProject 거부·가져오기 미완). ~/.volcano/prproj_log.txt 를 보고 다시.");
      const donor = style("마스터효과_도너.prproj");
      const part = style("아모르_부품.prproj");
      return base("lb_prproj", preset, {
        status: "execute",
        next_step: "lb_prproj",
        message: `프리미어가 prproj 를 만들었다(${bytes} 바이트, _갓지은판 사본 있음). 이제 ④ 곳간 서식 → ⑤ ass 서식 → ⑥ 자리 → ⑦ 꾸미기 → ⑧ 가로비율 → ⑨ 그림자빼기 → ⑩ 주입검사 → ⑪ 자막 자리 관문 → ⑫ 마스터 효과(브로드캐스트 −3dB) → ⑬ 아모르 → ⑬.5 클립 끝 관문 을 순서대로 돌리고 로그를 실어 다시 부르라.`,
        instructions: [
          `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 순서대로. 프리미어는 필요 없다(④ 이후는 파일만 고친다). 각 도구는 고치기 전 사본(*전_*.prproj)을 남긴다.`,
          `② 곳간 = ${KOTGAN}(저장소 스타일/신병4_본.json — 본떠서만들기 짝표) · 아모르 부품 = 스타일/아모르_부품.prproj · 마스터 효과 도너 = 스타일/마스터효과_도너.prproj(사장님이 프리미어에서 걸어 저장한 EP1 · 프리셋 카드 「prproj 오디오 마스터」).`,
          "③ measure 대로 로그 13개를 실어 lb_prproj 를 **다시** 부른다 — 실패 rc 라도 로그는 실어 보내라(판정은 서버). --확인만 도구는 「확인만 rc=N」 줄로 판정한다.",
        ],
        then_call_with: ["step: 'lb_prproj'", "payload: { …carry, ppro_log, kot_log, style_log, place_log, deco_log, ratio_log, shadow_log, inject_log, subpos_log, master_log, master_check_log, inject2_log, amor_log, inject3_log, endcheck_log }"],
        jobs_kind: "argv",
        jobs_cwd: carry.ep_dir,
        jobs: [
          { name: "kot", argv: ["python", kit("본떠서만들기.py"), prproj, KOTGAN, ass], out: join(carry.ep_dir, "_kot_log.txt"), note: "④ 곳간 서식 — 색·크기·선·그림자를 곳간(신병4_본)에서 통째로 베낀다. 「되읽기 확인 — N/N 정상」." },
          { name: "style", argv: ["python", kit("서식입히기.py"), prproj, ass], optional: true, note: "⑤ ass 서식 — 「입힐 것 N장 · 못 찾은 것 0장」 이어야." },
          { name: "place", argv: ["python", kit("자리잡기.py"), prproj, ass], optional: true, note: "⑥ 자리 — 「옮길 것 N장 · 못 찾은 것 0장」." },
          { name: "deco", argv: ["python", kit("꾸미기.py"), prproj, ass], optional: true, note: "⑦ 그림자 + 등장 팝 — 「넣었다」." },
          { name: "ratio", argv: ["python", tool("가로비율.py"), prproj, ass], optional: true, note: "⑧ ass 의 \\fscx(폭맞춤) 를 프로젝트 가로비율로." },
          { name: "shadow", argv: ["python", tool("그림자빼기.py"), prproj, ass], optional: true, note: "⑨ 「아직 남은 것 0장」." },
          { name: "inject1", argv: ["python", tool("주입검사.py"), prproj, "--기준", fresh], optional: true, note: "⑩ 파일 성함 — 「탈 없다 — 열어 봐도 좋다」." },
          { name: "subpos", argv: ["python", tool("자막자리검사.py"), prproj, ass], optional: true, note: "⑪ 자막 자리 관문 — 「되읽은 자막 N장 · **탈 0장**」 아니면 납품 금지." },
          { name: "master", argv: ["python", tool("마스터효과심기.py"), prproj, "--도너", donor], optional: true, note: "⑫ 멀티밴드 «브로드캐스트» + 선택적 제한 −3dB 를 도너에서 베낀다(완성검사 11). 「파라미터 값 도너와 동일 ✓」 또는 「이미 다 걸려 있다」." },
          { name: "master_check", argv: ["python", "-c", RC_WRAP, tool("마스터효과심기.py"), prproj, "--확인만"], optional: true, note: "⑫ 확인 — 「확인만 rc=0」." },
          { name: "inject2", argv: ["python", tool("주입검사.py"), prproj, "--기준", fresh], optional: true, note: "⑫ 뒤 주입검사." },
          { name: "amor", argv: ["python", tool("아모르입히기.py"), prproj, ass, "--팝", "부품"], optional: true, note: "⑬ 팝업자막(아모르) — 나레·대사 층, 팝 모양은 부품(150→175). 「달았다 — 벡터 모션 N장」. 고치기 전 사본 <prproj>.아모르전." },
          { name: "inject3", argv: ["python", tool("주입검사.py"), prproj, "--본", part, "--기준", `${prproj}.아모르전`], optional: true, note: "⑬ 뒤 주입검사 — --본 으로 «무는 태그 종류» 까지." },
          { name: "end_check", argv: ["python", "-c", RC_WRAP, tool("제목끝맞춤.py"), prproj, "--확인만"], optional: true, note: "⑬.5 클립 끝 관문(완성검사 12) — 「확인만 rc=0」." },
        ],
        measure: [
          { as: "kot_log", from: "job:kot", unit: "stdout" }, { as: "style_log", from: "job:style", unit: "stdout" }, { as: "place_log", from: "job:place", unit: "stdout" },
          { as: "deco_log", from: "job:deco", unit: "stdout" }, { as: "ratio_log", from: "job:ratio", unit: "stdout" }, { as: "shadow_log", from: "job:shadow", unit: "stdout" },
          { as: "inject_log", from: "job:inject1", unit: "stdout" }, { as: "subpos_log", from: "job:subpos", unit: "stdout" }, { as: "master_log", from: "job:master", unit: "stdout" },
          { as: "master_check_log", from: "job:master_check", unit: "stdout" }, { as: "inject2_log", from: "job:inject2", unit: "stdout" }, { as: "amor_log", from: "job:amor", unit: "stdout" },
          { as: "inject3_log", from: "job:inject3", unit: "stdout" }, { as: "endcheck_log", from: "job:end_check", unit: "stdout" },
        ],
        metrics: { prproj_bytes: bytes, kotgan: KOTGAN },
        carry: [...carryKeys, "ppro_log"],
        ...common,
        ppro_log: log,
      });
    }

    // ── ① 프리미어 실행 지시 ─────────────────────────────────────────────
    return base("lb_prproj", preset, {
      status: "execute",
      next_step: "lb_prproj",
      message: `프리미어가 ${xml} 을 prproj 로 만든다(한번에.sh ③) — 한 컴퓨터에 한 번에 한 편(잠금 ~/.volcano/prproj.lock). 프리미어가 떠 있으면 끈다. 끝나면 로그를 실어 다시 부르라.`,
      instructions: [
        `① 프리미어(2026)와 CEP 확장 com.volcano.prproj(저장소 프리미어확장/ · 설치는 setup 안내)가 깔려 있어야 한다. 실행파일 자리가 기본과 다르면 환경변수 PPRO 로 알려 준다.`,
        "② 프리미어돌리기.py 가 잠금 → 프리미어 끄기 → 옛 prproj 지우기 → 대기줄(~/.volcano/prproj_queue.txt)에 XML 보태기(남의 줄은 그대로) → 프리미어 실행 → 확장이 줄을 지울 때까지(최대 8분) → 저장이 잠잠해질 때까지 → 프리미어 끄기 → _갓지은판.prproj 사본 → 잠금 해제. 마지막 줄 「✓ prproj <바이트> <경로>」.",
        "③ measure 대로 payload.ppro_log 를 실어 lb_prproj 를 **다시** 부른다. ✗ 면 ~/.volcano/prproj_log.txt(확장 로그)를 보라.",
      ],
      then_call_with: ["step: 'lb_prproj'", "payload: { …carry, ppro_log: <프리미어돌리기 stdout> }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        { name: "premiere", argv: ["python", tool("프리미어돌리기.py"), xml, prproj, "--누구", `${title}_${carry.ep}`, "--기다림", "480"], out: join(carry.ep_dir, "_ppro_log.txt"), note: "한번에.sh ③ 의 유스튜디오판 — 잠금(프리미어잠금.sh 원리)·대기줄·CEP 확장·_갓지은판. 맥·윈도우 둘 다." },
      ],
      measure: [{ as: "ppro_log", from: "job:premiere", unit: "stdout" }],
      metrics: { xml, prproj },
      carry: carryKeys,
      ...common,
    });
  },
};
