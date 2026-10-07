# OpenShell 검증 범위

2026-10-07, day-of-v1-20261007.

## 최신 빌드

[readiness](evidence/latest-readiness.json)와 [모델 실행](evidence/latest-model-execution.json)의 worker/core SHA를 대조한다.
다른 빌드의 호출 성공을 최신 빌드의 증거로 사용하지 않는다. 준비 상태·실제 추론·API 완료·의미 검수는 각각 판단한다.

## 실제 경계 검증

[결합 판정](evidence/boundary-combined-verdict.json)은 기록된 controlled probe의 11조건 PASS다. 모든 새 worker에서 재실행했다는 뜻이 아니다.

- [fixture](evidence/boundary-matrix-01.log): UID1000, 파일0666/부모0777에서 쓰기·삭제 거부, 전후 SHA 동일.
- [일반 컨테이너 대조](evidence/dac-control-01.json): UID1000에서 같은 무해한0444 파일 읽기 성공. OpenShell의 allowlist 밖 읽기는 거부.
- [수신기8012](evidence/receiver-8012-counts.json): 허용 GET health 수신1, 예약 POST 수신0.
- [수신기8013](evidence/receiver-8013-counts.json): 비허용 목적지 수신0.
- [실행 로그](evidence/boundary-matrix-01-runtime.log): 예약403/L7 DENIED, 비허용 목적지 transport denial과 정책 거부.

fixture SHA: fc10513238b72da23f37d8d2554c71e50420da6d4cc551a5578e1494edd13373.
실제 제한·비밀 경로는 읽지 않았다. 전용 무해한 fixture와 수신기만 사용했다.
matrix는 내부 기대값 충족 시에도 외부 증거 결합 전 exit3/INCOMPLETE다. verify_boundary_evidence.py가 수신기·일반 권한 대조·거부 로그를 결합한다.
verdict-only JSON행 처리와 금지 수신1회 실패 검증을 포함해 security 단위 검증6개가 통과했다. 이는 실제 sandbox 관측과 별개다.

## 해석

read_write는 삭제를 허용하고 audit는 차단하지 않는다. Provider가 추가한 권한을 포함한 실효 정책과 enforce를 확인한다.
후속 배포의 동일 allowlist 대조는 기존 probe 재실행이 아니다.
샌드박스 밖 직접 모델 진단은 OpenShell 경로 증거에 포함하지 않는다.
API 결과 저장은 사실성·역사 근거·번역·식이 안전·UI 전체 수용을 증명하지 않는다.

공식 확인(2026-10-07):
[OpenShell0.1.2 schema](https://docs.nvidia.com/openshell/v0.1.2/how-it-works/policies/schema),
[provider 합성](https://docs.nvidia.com/openshell/v0.1.2/how-it-works/providers/profiles),
[NVIDIA 모델 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16).
