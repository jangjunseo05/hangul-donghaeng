# OpenShell 실측 근거

2026-10-07. 미션 day-of-v1-20261007. API 계약 SHA256:
`e1233c6e82b987385722d2d682794aeb3149cb660edc0330d0e3e85de0fd5518`.

## 실제 결과

| 항목 | 결과 | 근거 |
|---|---|---|
| 샌드박스 내 실제 NVIDIA 추론 | HTTP 200, choices=true, 0.683초/합성 1회 | [model-03.log](evidence/model-03.log) |
| 실제 서빙 모델 식별 | BF16 12B VL 모델 ID, /v1/models 응답에서 추출 | [metadata](evidence/model-server-metadata.json) |
| 초기 probe 수신기 카운트 | GET=1, POST=0 | [counts](evidence/boundary-02-receiver-counts.json) |
| 파일 쓰기/삭제 | 모두 거부, 전후 SHA 동일 | [matrix](evidence/boundary-matrix-01.log) |
| 일반 권한 대조 | UID1000, 파일0666/부모0777 | [matrix](evidence/boundary-matrix-01.log) |
| 정책 밖 무해한 파일 읽기 | 0444 파일이 OpenShell에서 거부됨 | [matrix](evidence/boundary-matrix-01.log) |
| 같은 파일 일반 컨테이너 읽기 | UID1000에서 성공 | [DAC 대조](evidence/dac-control-01.json) |
| 허용 GET /api/health | 200, 수신 1 | [receiver8012](evidence/receiver-8012-counts.json) |
| 금지 POST /reservations | 403, 예약 수신 0; L7 DENIED | [runtime](evidence/boundary-matrix-01-runtime.log) |
| 비허용 목적지 host:8013 | ConnectError + transparent_tcp_mapping_denied; 수신 0 | [runtime](evidence/boundary-matrix-01-runtime.log), [receiver8013](evidence/receiver-8013-counts.json) |

모든 경계 공격은 자체 무해한 fixture/수신기만 대상으로 했다. 실제 제한/비밀 경로를 열지 않았다.
거부 상태 코드만으로 PASS하지 않고 수신기 카운트와 OpenShell 로그를 대조했다.
파일은 `/app/probe/sentinel`, 비허용 읽기는 `/probe-denied/sentinel`이다.
전후 SHA256 `fc10513238b72da23f37d8d2554c71e50420da6d4cc551a5578e1494edd13373`.

## 실제 합성 정책

- 모델 probe hash: `909ea57fa76855acb044a93f880e6e9500955e8834d6d704e90468cdef3d2b08`.
  [policy](evidence/model-03-effective-policy.json), [runtime](evidence/model-03-runtime.log).
- 제품 worker02 hash: `818ee3c743d77dc32191485db205d2c2136c734ae6d62f1a6368f510fcab7927`.
  [provider 권한을 포함한 policy](evidence/worker-02-effective-policy.json).
- worker03 정책은 아래 최신 인계에서 실측했다.
- 테스트 설정 단위 검증 4개 PASS. 이는 위 실제 샌드박스 근거와 별개다.
- read_write의 삭제 금지를 주장하지 않는다. audit를 차단으로 간주하지 않는다.

## 호출 기록의 한계

model-03 probe는 응답 본문을 저장하지 않고 HTTP 상태/choices/시간만 기록했다.
model ID는 요청 환경 및 별도 실제 /v1/models 메타데이터와 연결된다.
추가 응답 finish_reason/usage가 필요할 때 `tests/security/model_evidence.py`로 합성 16토큰 요청의 메타데이터만 남길 수 있다. 제품 QA와 경쟁하지 않도록 root와 실행 순서를 맞춘다.
제품 사진/식당/식이/지역 밖/가상 TASK의 최종 결과는 root의 실제 QA 정본을 따른다.

## 실패와 수정 이력

1. /app WORKDIR의 UNIX 쓰기 권한으로 sandbox 시작 거부 → WORKDIR /tmp, PYTHONPATH /app.
2. SSH forward가 Docker bridge에만 존재 → 실측 gateway loopback 경로와 정렬.
3. 초기 10초 정책 generation 갱신이 추론 연결 종료 → 12초 초기 유예 후 실제 호출 성공.
4. 제품 10초 모델 제한시간 실패 → pN의 20초 수정으로 worker02 재빌드. 전체 작업 제한은 30초.
5. 호스트 장시간 중단 뒤 SSH listener 소실 → root가 지속 세션에서 복구. GPU/worker 재설치하지 않음.

확인한 upstream: [OpenShell 0.1.2 정책](https://docs.nvidia.com/openshell/v0.1.2/how-it-works/policies/schema),
[provider 합성](https://docs.nvidia.com/openshell/v0.1.2/how-it-works/providers/profiles),
[NVIDIA 모델 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16),
[vLLM 0.12.0 모델 등록 코드](https://github.com/vllm-project/vllm/blob/v0.12.0/vllm/model_executor/models/registry.py).

## Worker03 인계 — 2026-10-07 14:31 KST (이전 예정 상태 대체)

- worker03 단일 consumer 가동, worker02 정상 stop 및 workspace 보존. root broker/tunnel과 GPU 모델 유지. worker04는 root 신호 전 배포하지 않는다.
- [배포 결합 근거](evidence/worker-03-deployment.json): 실제 컨테이너/image, 내부 core SHA, root lock의 14개 런타임 의존성 일치, 실효 정책 hash.
- [실제 model_call](evidence/worker-03-model-events.jsonl): NVIDIA-Nemotron-Nano-12B-v2-VL-BF16의 configured_model과 응답 envelope.model exact match=true 3회. finish_reason/usage만 보존하며 응답 본문·인증 값은 제외했다. source SHA의 core.py가 실제 동등 비교 후 출력한다.
- [실효 정책](evidence/worker-03-effective-policy.json) 내부 hash `2f77a3a26bf5edec4a531b6f66017b68254f3426033595a8b746ad0caad30df1`; 파일 SHA `7f16e3bc3dad1077ba3ba55822679cf8f2bed7963cf276358c006f4a24161069`와 구분한다. [runtime 발췌](evidence/worker-03-runtime.log)에 동일 hash ACK와 모델 POST 허용이 있다.
- worker scratch 로그 회수: `openshell sandbox exec --name hangul-worker-03 --no-tty --no-login-shell -- cat /tmp/worker-events.jsonl`. runtime 로그 기본 200행은 초기 ACK를 누락할 수 있어 `openshell logs hangul-worker-03 -n 3000`으로 회수했다.
- [경계 결합 판정](evidence/boundary-combined-verdict.json) 11조건 PASS. 새 matrix는 내부 기대값 충족 때도 외부 수신/정책 로그 대조 전 exit3 INCOMPLETE. 검증기의 verdict-only JSON행 처리와 금지 목적지 실제 수신에 대한 실패 회귀를 포함해 security 단위 검증 6개 PASS.
- Dockerignore에 **/.env.*, **/*.key 추가. 실행 컨테이너의 [source/freeze](evidence/worker-03-source-freeze.txt) 보존. 기존 이미지 보존.
- 첫 관측 작업 저장 성공, 다음 Draft 호출은 20.02초 model_timeout. root 보고: far 13.3초 성공 / fictional 26.5초 timeout. 전체 제품 QA 통과를 주장하지 않는다. 응답 모델 식별 gap은 해소했고 제품 timeout은 root/pN 검수 대상이다.
