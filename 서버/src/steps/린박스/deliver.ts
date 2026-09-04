/**
 * steps/린박스/deliver.ts — lb_deliver: 완성/<EP>/ 조립 (정본 `신병4/완성검사.sh` 조립부). 두 번 부른다.
 *
 *   ① payload.deliver_log 없음 → human_ok 가 아니면 반려(사람 확인 9·10 은 lb_check 가 안내) → jobs: 조립(python -c) — prproj·완성본·「<제목>(최종본).mp4」·납품 SRT 4벌·편집소스(그래픽·원음·효과음·나레 wav)
 *   ② deliver_log 있음 → 「완성/<EP>: …」 되읽기 → status=done (next_step=null). NAS 납품은 작품 카드 「NAS 납품」 절 — 여기서는 안 한다.
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, readCarry, str } from "./lib.js";

const DELIVER_PY = `import io,json,os,re,shutil,subprocess,sys,gzip,glob
ep_dir,out,prproj,mp4,ass,title,ep,srt_tool=sys.argv[1:9]
os.chdir(ep_dir)
for d in ('편집소스/그래픽','편집소스/나레이션','편집소스/원음','편집소스/효과음'): os.makedirs(os.path.join(out,d),exist_ok=True)
for p in glob.glob(os.path.join(out,'*(최종본).mp4')): os.remove(p)
shutil.copy2(prproj,out);shutil.copy2(mp4,out)
t=json.load(io.open('편정보.json',encoding='utf-8')).get('제목') or []
final_name=(' '.join(t)+'(최종본).mp4') if t else (os.path.basename(mp4).replace('.mp4','')+'(최종본).mp4')
shutil.copy2(mp4,os.path.join(out,final_name))
r=subprocess.run([sys.executable,srt_tool,title+'_'+ep,ass,out],capture_output=True,text=True,encoding='utf-8',errors='replace');print(r.stdout.strip()[-300:])
n={'그래픽':0,'원음':0,'효과음':0,'나레':0}
for p in glob.glob('그래픽/*.png'): shutil.copy2(p,os.path.join(out,'편집소스/그래픽'));n['그래픽']+=1
for p in glob.glob('편집소스/원음/*.wav'): shutil.copy2(p,os.path.join(out,'편집소스/원음'));n['원음']+=1
for p in glob.glob('효과음/*.wav'): shutil.copy2(p,os.path.join(out,'편집소스/효과음'));n['효과음']+=1
for p in glob.glob(os.path.join(out,'편집소스/나레이션/*.wav')): os.remove(p)
try:
    xml=gzip.decompress(open(prproj,'rb').read()).decode('utf-8','replace')
    for p in sorted(set(re.findall(r'<(?:FilePath|ActualMediaFilePath)>([^<]+)</',xml))):
        if '/blocks/n' in p.replace(chr(92),'/') and p.endswith('.wav'):
            src=p if os.path.exists(p) else p.lstrip('/')
            if os.path.exists(src): shutil.copy2(src,os.path.join(out,'편집소스/나레이션'));n['나레']+=1
except Exception as e: print('나레 wav 못 모음:',e)
print('완성/%s: %s'%(ep,' | '.join(sorted(os.listdir(out)))))
print('편집소스: 그래픽 %d · 나레 %d · 원음 %d · 효과음 %d'%(n['그래픽'],n['나레'],n['원음'],n['효과음']))
print('최종본:',final_name)`;

export const lbDeliver: StepHandler = {
  name: "lb_deliver",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string; title?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_deliver", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_check 응답의 carry 값을 payload 에 그대로 실어 lb_deliver 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_deliver", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const title = str(payload, "title") || (typeof source.title === "string" && source.title.trim()) || "린박스";
    const final = str(payload, "final") || join(carry.ep_dir, `${title}_${carry.ep}_숏폼.mp4`);
    const prproj = str(payload, "prproj") || join(carry.ep_dir, `${title}_${carry.ep}.prproj`);
    const ass = str(payload, "ass") || join(carry.ep_dir, `captions_${title}.ass`);
    const outDir = join(carry.workdir, "완성", carry.ep);
    const common = { source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s, repo, title, final, prproj, ass, deliver_dir: outDir };
    const carryKeys = [...CARRY_KEYS, "repo", "title", "final", "prproj", "ass", "deliver_dir"];

    // ── ② 되읽기 → done ─────────────────────────────────────────────────
    if (payload.deliver_log !== undefined) {
      const log = String(payload.deliver_log ?? "");
      const m = log.match(/완성\/(\S+): (.+)/);
      const files = m ? m[2].trim().split(/ \| /).map((x) => x.trim()).filter(Boolean) : []; // 파일 이름에 띄어쓰기가 있어(「<제목>(최종본).mp4」) 구분자는 " | "
      const bad: string[] = [];
      if (!m) bad.push("조립 로그에 「완성/<EP>: …」 가 없다 — 조립이 죽었다(편정보.json·완성본·prproj 가 있는지).");
      if (!files.some((f) => f.endsWith(".prproj"))) bad.push("완성 폴더에 prproj 가 없다.");
      if (!files.some((f) => f.includes("(최종본).mp4"))) bad.push("「<제목>(최종본).mp4」 가 없다 — 편정보.json «제목» 을 보라.");
      const srt = files.filter((f) => f.endsWith(".srt")).length;
      if (srt < 4) bad.push(`납품 SRT 가 ${srt}벌 — 4벌(전체·나레·대사·효과)이어야 한다(규격 output.srt_sets).`);
      const src = log.match(/편집소스: 그래픽 (\d+) · 나레 (\d+) · 원음 (\d+) · 효과음 (\d+)/);
      if (src && Number(src[1]) === 0) bad.push("편집소스/그래픽 이 비었다 — 그래픽짓기(lb_subs) 산출물이 없다.");
      if (src && Number(src[3]) === 0) bad.push("편집소스/원음 이 비었다 — 원음스템(lb_subs) 산출물이 없다.");
      if (bad.length) return reject("lb_deliver", preset, `완성 폴더가 아직 맞지 않다 (${bad.length}건)`, bad.map((x, i) => `${i + 1}) ${x}`).join(" ") + " 고친 뒤 lb_deliver 를 다시 부르라(deliver_log 는 빼고).");
      return base("lb_deliver", preset, {
        status: "done",
        next_step: null,
        message: `납품 준비 끝 — ${outDir}: ${files.length}개 파일(prproj · 완성본 · 최종본 · SRT ${srt}벌) · ${src ? `편집소스 그래픽 ${src[1]} · 나레 ${src[2]} · 원음 ${src[3]} · 효과음 ${src[4]}` : ""}. NAS 납품은 작품 카드 「NAS 납품」 절대로 사람이 한다.`,
        instructions: [
          "① 완성 폴더를 열어 최종본을 한 번 재생한다(사람 확인 9·10 은 lb_check 에서 봤다).",
          "② NAS 납품·승격은 여기서 하지 않는다 — 작업규칙 「/승격」 은 사장님이 완성본을 보고 «이대로 가자» 한 뒤에만.",
        ],
        then_call_with: [],
        jobs_kind: null, jobs: [], measure: [],
        metrics: { files: files.length, srt_sets: srt, graphics: src ? Number(src[1]) : null, narr_wavs: src ? Number(src[2]) : null, stems: src ? Number(src[3]) : null, sfx: src ? Number(src[4]) : null },
        carry: carryKeys,
        ...common,
        deliver_files: files,
      });
    }

    // ── ① 조립 지시 (사람 확인 뒤) ─────────────────────────────────────────
    if (payload.human_ok !== true) {
      return reject("lb_deliver", preset, "사람 확인(완성검사 9 마무리 프레임 인물 · 10 자막 소리 내어 읽기 · 2 길이)이 아직이다", "lb_check 가 안내한 세 가지를 눈과 귀로 확인한 뒤 payload.human_ok: true 로 lb_deliver 를 다시 부르라. 검사 통과 ≠ 완성 — 사람이 본 뒤에만 «완성» 이라 한다.");
    }
    return base("lb_deliver", preset, {
      status: "execute",
      next_step: "lb_deliver",
      message: `완성/${carry.ep}/ 를 조립한다 — prproj · 완성본 · 「<제목>(최종본).mp4」 · 납품 SRT 4벌 · 편집소스(그래픽·나레이션·원음·효과음). 로그를 실어 다시 부르라.`,
      instructions: [
        `① jobs 의 assemble 이 ${outDir} 를 만들고 채운다(완성검사.sh 조립부 그대로 · 나레 wav 는 prproj 가 가리키는 blocks/nNN.wav 기준).`,
        "② measure 대로 payload.deliver_log 를 실어 lb_deliver 를 **다시** 부른다.",
      ],
      then_call_with: ["step: 'lb_deliver'", "payload: { …carry, human_ok: true, deliver_log: <assemble stdout> }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        { name: "assemble", argv: ["python", "-c", DELIVER_PY, carry.ep_dir, outDir, prproj, final, ass, title, carry.ep, join(repo, RUNNER_DIR, "도구", "납품SRT4벌.py")], out: join(carry.ep_dir, "_deliver_log.txt"), note: "완성/<EP>/ 조립 + 납품SRT4벌.py(전체·나레·대사·효과). 「완성/<EP>: <파일들>」 「편집소스: …」 「최종본: …」." },
      ],
      measure: [{ as: "deliver_log", from: "job:assemble", unit: "stdout" }],
      metrics: { deliver_dir: outDir },
      carry: [...carryKeys, "human_ok"],
      ...common,
      human_ok: true,
    });
  },
};
