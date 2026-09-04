# 서버/runner/린박스 — 린박스 프리셋 러너 도구 (볼케이노 키트에서 반입)

유스튜디오 린박스 앞 7단계(lb_probe~lb_blocks)가 부르는 파이썬 도구. 원본은 볼트 `스크립트/린박스/키트/도구/`(2026-09-03 합쳐 승격한 판)이고 **바이트 그대로 반입**한다 — 고칠 것이 있으면 볼트에서 고쳐 다시 가져온다(두 벌로 갈라지지 않게). 절대경로 0곳, 작업 폴더는 인자·cwd 로 받는다.

## 실행 규약
- lb_* 단계의 jobs 는 **편 폴더(`<드라마>/작업/<EP>/`)를 cwd 로** 실행한다 — 응답의 `jobs_cwd` 가 그 자리다. 도구가 `scene_cuts.txt` 같은 산출물을 cwd 에 쓰기 때문이다.
- 도구 경로는 `<repo>/서버/runner/린박스/도구/<이름>.py` 절대경로로 argv 에 박혀 온다 — `payload.repo`(저장소 루트 절대경로)를 start 에서 받아 서버가 잇는다.
- 파이썬은 러너 venv(맥 `~/.volcano/venv/bin/python` · 윈도우 `~/.volcano/venv/Scripts/python.exe`)로. 필요한 꾸러미: numpy · pillow · av(또는 opencv-python).

## 반입한 도구 (단계별)
| 단계 | 도구 | 출처(볼트 키트) | 무엇 |
|---|---|---|---|
| lb_cut | `도구/장면컷.py` · `도구/영상읽기.py` | 도구/장면컷.py · 도구/영상읽기.py | 장면전환 표 `scene_cuts.txt`(화소차+히스토그램+이웃 대비) · 프레임 읽기(av→cv2 사다리) |
| lb_transcript | `도구/전사.py` · `도구/화자표.py` · `자산/yunet.onnx` | 도구/전사.py · 도구/화자표.py · (yunet 은 저장소 자산/스케치코미디/models 것과 같은 파일) | ★Speechmatics 세 벌 전사 → 대사.json·대사표.txt·seg_asr.json (키는 ~/.volcano/keys/speechmatics · 환경변수) · 화자 뭉치별 얼굴 → _화자.jpg·화자.json 틀 |

다음 단계에서 더 가져올 것(설계 5.6.1·지시 ③): 전사.py · 화자표.py(lb_transcript) · 쓸거리검사.py(lb_plan) · author 본보기·나레카드.py·대본검사.py·제목검사.py·구둣점검사.py·편별검사.py(lb_script) · speed_narr.py·narr_align.py(lb_voice) · find_faces.py·인물따라가기.py·reframe.py·fix_cuts.py·컷다듬기.py·번쩍임정리.py·d_sync.py·장면튐검사.py(lb_blocks).
