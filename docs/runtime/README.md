# 실제 런타임 인계 — BUILD-OPEN-SHELL-01

확인일 2026-10-07 KST. 담당 w1:pM, 검수 root. 개발·검증·푸시 최신 마감 **16:00**, 행사 제출 17:20.
공개 제품 저장소의 infra/, policy/, tests/security/, docs/runtime/만 담당한다. infra/mobile-preview.ps1은 pK 소유다.

## 현재 실행 상태

- WSL Ubuntu 22.04 / Docker 29.8.2 / OpenShell 0.1.2. Gateway는 mTLS 연결.
- 기존 Brev L40S 46,068 MiB, Docker 29.1.5 및 NVIDIA runtime 실측. 새 GPU 생성 없음.
- vLLM 0.12.0 + 공개 `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16` 실제 서빙.
- OpenShell `hangul-model-03`에서 실제 모델 HTTP 200, choices 확인. 짧은 합성 요청 1회 0.683초이며 일반 성능 수치가 아니다.
- 제품 consumer는 `hangul-worker-02` 하나. 01은 workspace 보존 stop 완료. root QA가 진행 중이며 다음 pN 수정 수령 후 03으로 교체 예정.
- root가 단일 WSL broker와 지속 SSH 터널을 관리한다. 현재 root 도구 세션: broker 92522, tunnel 50918. 다른 consumer/broker를 추가하지 않는다.
- 브라우저 음성 인식은 모델/샌드박스 기능과 별개다. 모델 카드는 English only이며 한국어 품질·안전성을 이 연결 검증으로 보증하지 않는다.

## 연결 구조

브라우저 → WSL FastAPI:8000 → OpenShell worker → WSL SSH forward:8001 → 기존 GPU의 localhost vLLM:8001.
Worker는 고정 broker의 /worker/*만 호출하고 영구 파일은 trusted server가 검증 후 생성한다.
이 gateway의 실측 `host.openshell.internal` 목적지는 **127.0.0.1**이다. 초기 Docker bridge 전용 터널은 실패했다.

## 재현 명령 (WSL, 저장소 루트)

아래 명령은 실행 중인 제품 worker와 경쟁할 수 있다. root가 QA를 멈추고 교체를 지시한 때만 실행한다.

```sh
openshell status
docker build --progress=plain -f infra/Dockerfile.worker -t hangul-worker:day-of .

# .env의 WORKER_TOKEN만 기존 값으로 사용한다. 값은 출력하지 않는다.
# 유일한 기존 consumer를 가역적으로 정지한 뒤 새 이름을 사용한다.
openshell sandbox stop hangul-worker-02
GUIDE_SERVER_URL=http://host.openshell.internal:8000 \
NVIDIA_BASE_URL=http://host.openshell.internal:8001/v1 \
NVIDIA_MODEL=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16 \
"$HOME/.venvs/hangul-broker/bin/python" infra/launch_worker.py \
  --name hangul-worker-03 --env-file .env
```

실행기는 provider 생성 시 환경변수의 이름만 CLI에 전달한다. 비밀 값은 argv나 Docker ENV에 쓰지 않는다.
provider 생성 출력은 버린다. 샌드박스에는 WORKER_TOKEN의 opaque placeholder가 전달된다.
호스트별 생성 정책은 infra/generated/에만 저장하며 Git 제외다. 기존 profile을 덮어쓰지 않도록 실행별 고유 ID를 쓴다.
현재 자체 모델은 SSH로 제한된 무인증 endpoint이며 NVIDIA hosted key를 전달하지 않는다.
초기 정책 동기화가 진행 중인 연결을 닫는 현상이 실측되어 workload 시작 전 12초를 둔다. 향후 정책 변경 중 연결 종료까지 방지한다는 보장은 아니다.

## 모델/터널 유지와 복구

- `infra/serve_nemotron.sh`: 기존 GPU에서만 실행. 이미 같은 컨테이너가 있으면 교체하지 않고 중단한다.
- 모델 revision: `ca9543b126e8bf3176916d3d305ccc415f89fd4d`.
- vLLM 이미지 digest: `sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe`.
- GPU SSH 별칭/조직/인스턴스 정보는 로컬 셸 설정으로만 전달한다. 공개 문서·스크립트에 넣지 않는다.
- root가 유지 중인 터널을 보존한다. 약 9분 도구 중단 후 이전 8001 리스너가 사라졌고 root가 복구했다. 모델/worker 재설치 문제와 구분한다.
- 재연결이 필요하면 root 소유 세션/프로세스와 활성 요청부터 확인한다. 포트를 소유한 임의 PID를 종료하지 않는다.
- 복구용 `infra/open_model_tunnel.sh`는 독립 SSH 연결을 **foreground**에서 유지하며 ControlMaster 재사용/자동 background를 끈다. WSL의 지속 터미널 또는 관리되는 exec 세션에서 실행한다. 창/세션을 닫으면 재확인이 필요하다.
- `ExitOnForwardFailure=yes`, server alive 15초/3회. 이미 8001이 사용 중이면 두 번째 터널을 띄우지 않는다.

```sh
# GPU_SSH_ALIAS는 승인된 기존 별칭을 로컬에서 설정한다.
bash infra/open_model_tunnel.sh
# 별도 터미널:
curl --max-time 5 http://127.0.0.1:8001/v1/models
```

모델 목록 200은 추론 성공과 다르다. 검증 시 짧은 합성 추론 → OpenShell 경로 → 실제 제품 요청 순으로 확인한다.
재시도는 root QA와 조율한다. API 호출 실패 시 모의 답변으로 대체하지 않는다.

## 정책 근거

[검증 결과](SECURITY-EVIDENCE.md), [실측 파일](evidence/) 참조.
read_write는 삭제도 허용한다. writable은 임시 /tmp, /dev/null뿐이며 영구 결과 경로는 노출하지 않는다.
REST endpoint는 enforce다. audit는 허용하며 기록하므로 차단 증거로 사용할 수 없다.
Provider가 합성한 권한까지 포함한 `openshell policy get NAME --full -o json`을 검수한다.

## 미완료/범위

제품 전체 5개 시나리오 최종 수용·새 worker03·최종 푸시는 root 인계 후 확인한다.
모델 연결 성공으로 한국 문화 사실성, 번역 정확도, 식이 안전성, 사용자 수요, NIM/NeMo 적격을 증명하지 않는다.

## Worker03 인계 — 2026-10-07 14:31 KST (이전 예정 상태 대체)

- worker03 단일 consumer 가동, worker02 정상 stop 및 workspace 보존. root broker/tunnel과 GPU 모델 유지. worker04는 root 신호 전 배포하지 않는다.
- [배포 결합 근거](evidence/worker-03-deployment.json): 실제 컨테이너/image, 내부 core SHA, root lock의 14개 런타임 의존성 일치, 실효 정책 hash.
- [실제 model_call](evidence/worker-03-model-events.jsonl): NVIDIA-Nemotron-Nano-12B-v2-VL-BF16의 configured_model과 응답 envelope.model exact match=true 3회. finish_reason/usage만 보존하며 응답 본문·인증 값은 제외했다. source SHA의 core.py가 실제 동등 비교 후 출력한다.
- [실효 정책](evidence/worker-03-effective-policy.json) 내부 hash `2f77a3a26bf5edec4a531b6f66017b68254f3426033595a8b746ad0caad30df1`; 파일 SHA `7f16e3bc3dad1077ba3ba55822679cf8f2bed7963cf276358c006f4a24161069`와 구분한다. [runtime 발췌](evidence/worker-03-runtime.log)에 동일 hash ACK와 모델 POST 허용이 있다.
- worker scratch 로그 회수: `openshell sandbox exec --name hangul-worker-03 --no-tty --no-login-shell -- cat /tmp/worker-events.jsonl`. runtime 로그 기본 200행은 초기 ACK를 누락할 수 있어 `openshell logs hangul-worker-03 -n 3000`으로 회수했다.
- [경계 결합 판정](evidence/boundary-combined-verdict.json) 11조건 PASS. 새 matrix는 내부 기대값 충족 때도 외부 수신/정책 로그 대조 전 exit3 INCOMPLETE. 검증기의 verdict-only JSON행 처리와 금지 목적지 실제 수신에 대한 실패 회귀를 포함해 security 단위 검증 6개 PASS.
- Dockerignore에 **/.env.*, **/*.key 추가. 실행 컨테이너의 [source/freeze](evidence/worker-03-source-freeze.txt) 보존. 기존 이미지 보존.
- 첫 관측 작업 저장 성공, 다음 Draft 호출은 20.02초 model_timeout. root 보고: far 13.3초 성공 / fictional 26.5초 timeout. 전체 제품 QA 통과를 주장하지 않는다. 응답 모델 식별 gap은 해소했고 제품 timeout은 root/pN 검수 대상이다.
