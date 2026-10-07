# Runtime preflight — 최종 인계

2026-10-07 KST. 담당 w1:pM, 검수·실행 root. day-of-v1-20261007.
사용자 개발·검증·푸시 마감16:00, 공식 제출17:20.

WSL Ubuntu22.04, Docker29.8.2, OpenShell0.1.2 gateway와 기존 L40S GPU의 Nemotron12B VL BF16/vLLM0.12.0 연결을 실제 구축했다. 로그인·초기 네트워크 병목은 해결됐다. 새 GPU를 생성하지 않았다.
root의 단일 broker·지속 SSH forward를 유지한다. 새 배포는 root만 실행한다.

[최신 readiness](evidence/latest-readiness.json)는 worker12의 정확한 source/image/실효 정책 ACK를 기록한다.
[모델 실행 근거](evidence/latest-model-execution.json)는 별도 기록이며 worker/core 일치 여부를 먼저 확인한다.
실제 UI의 저장 성공·실패와 의미 검수 제한을 보존한다. 현재 전체 제품 PASS를 선언하지 않는다.
원본 사진·모델 본문·자격·개인 접속주소는 공개 근거에 포함하지 않는다.

[실행·복구](README.md) · [경계 검증](SECURITY-EVIDENCE.md).
