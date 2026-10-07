# OpenShell 실행 인계

2026-10-07. 담당 w1:pM, 실행·통합 root. 사용자 마감 16:00, 공식 제출 17:20.

## 현재 상태

[최신 readiness](evidence/latest-readiness.json)에서 worker·core/계약 SHA·이미지·실효 정책 ACK를 확인한다.
[실제 모델 실행](evidence/latest-model-execution.json)은 별도 근거다. 두 문서의 worker와 core가 일치해야 같은 빌드의 증거로 사용할 수 있다.
worker12 UI 검증 진행 중이며 전체 의미 검수 PASS를 선언하지 않는다. 저장 성공과 사실·근거·대화 품질 검수는 구분한다.

## 구성

브라우저 → 단일 WSL FastAPI:8000 → OpenShell worker → WSL SSH forward:8001 → 기존 GPU localhost vLLM.
WSL Ubuntu22.04 / Docker29.8.2 / OpenShell0.1.2. 실제 gateway의 host.openshell.internal은 127.0.0.1로 연결된다.
기존 L40S 46,068MiB에서 vLLM0.12.0으로 nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16을 서빙한다. 새 GPU를 생성하지 않았다.
모델 revision: ca9543b126e8bf3176916d3d305ccc415f89fd4d.
모델 카드의 지원 언어는 English이며 브라우저 음성·한국어 품질은 별도 검증 대상이다.

## 교체·복구

root가 QA 중단과 활성 작업 없음을 확인한 뒤 infra/deploy_worker.py에 명시적 from/to worker, core/contract SHA, --qa-idle을 전달한다.
이 플래그는 운영자 확인이며 자동 작업 조회가 아니다. 스크립트는 빌드·소스/lock 대조 후 기존 worker를 정지하고 새 worker의 단일 소비자·정책·polling을 확인한다.
기존 이름으로 재실행하지 않는다. 실패 상태는 자동 롤백하지 않으며 root가 근거를 보고 후속 조치한다.
Docker top은 pid,args가 필요하다. 격리 환경에서 헤더만 보이면 실제 polling·broker 연결·시작 오류 로그로 검증한다.

root의 broker와 지속 SSH 터널을 보존한다. 긴 호스트 중단 뒤 forward listener가 사라졌던 이력이 있다.
infra/open_model_tunnel.sh는 독립 foreground SSH와 ExitOnForwardFailure, keepalive를 사용한다.
연결 별칭은 로컬 GPU_SSH_ALIAS로만 공급한다. 기존 listener 소유권 확인 없이 중복 터널이나 임의 PID 종료를 하지 않는다.
모델 목록 HTTP200은 추론 성공 증거가 아니다.

## 정책·기록

WORKER_TOKEN은 제외된 로컬 환경과 gateway provider에만 둔다. 비밀 값을 argv·공개 로그에 넣지 않는다.
자체 서빙에는 NVIDIA_API_KEY를 전달하지 않는다. 별도 인증이 필요하면 SELF_HOSTED_API_KEY를 사용한다.
Provider 합성 후의 실효 정책을 확인한다. read_write는 삭제도 허용하며 audit는 차단하지 않는다.
앱/자료는 읽기 전용, scratch /tmp와 /dev/null만 쓰기 허용. 결과는 trusted broker가 검증하여 저장한다.
Docker context는 .env, .env.*, *.pem, *.key를 제외한다. worker 의존성은 root lock의 정확한 부분집합이다.

로그 회수는 openshell sandbox exec --name NAME --no-tty --no-login-shell -- cat /tmp/worker-events.jsonl.
정책은 openshell policy get NAME --full -o json, 실행 로그는 openshell logs NAME -n 3000.
정지 전에 회수한다. 기본 200행은 초기 정책 ACK를 누락할 수 있다.
공개 기록은 모델명 일치·토큰 수·종료 사유·지연·오류 코드만 남긴다. 원본 사진·응답 본문·개인 접속주소·자격은 제외한다.
[경계 검증 근거](SECURITY-EVIDENCE.md)를 참고한다. 배포 준비·실제 호출·API 완료·의미 검수는 각각 판정한다.
