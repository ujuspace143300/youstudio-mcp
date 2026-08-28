/**
 * steps/스케치코미디/deliver.ts — sk_deliver: 마무리 안내.
 *
 * 기계 게이트는 sk_check·sk_recheck 가 이미 통과시켰다. 여기서는 **기계가 못 잡는
 * 것**(정답지 「사람확인」)을 사람에게 안내하고, A/B 두 편 규칙을 알린다.
 * 완성 판정은 사람 몫이다 — 검사 통과 ≠ 사장님 마음에 듦.
 */
import { base } from "../../response.js";
import type { StepHandler } from "../types.js";
import { answer, join, str } from "./lib.js";

export const skDeliver: StepHandler = {
  name: "sk_deliver",
  run({ preset, payload }) {
    const workdir = str(payload, "workdir");
    const source = payload.source as { slug?: string; url?: string } | undefined;
    const isA = !source?.slug || !/_B$/i.test(source.slug);
    return base("sk_deliver", preset, {
      status: "done",
      next_step: null,
      message: `산출물: ${workdir ? join(workdir, "out") : "<작업 폴더>/out"}/ 의 mp4. 아래 사람 확인을 통과하기 전에는 「완성」이라 말하지 않는다.`,
      instructions: [
        "① 완성본을 열어 사람확인 목록을 하나씩 본다 — 기계는 이것을 못 본다.",
        "② 업로드용 재료는 편.json 에 있다 — title_candidates(제목 후보 5)·hashtag·hooks(후킹 대사 3, 수정 없이 타임코드와 함께).",
        ...(isA
          ? [
              "③ ★이 소재는 두 편을 만든다 — B 편은 start 부터 다시: source 에 slug '<id>_B' 와 focus_sec(다른 웃음 클러스터의 초, 댓글 타임스탬프 참고)을 실어 부른다.",
            ]
          : ["③ A/B 두 편이 모두 나왔다 — 두 채널에 나눠 올린다."]),
        "④ 사람 확인까지 통과하면 그때가 완성이다.",
      ],
      metrics: {},
      사람확인: answer.사람확인.항목,
    });
  },
};
