# NVIDIA 기술 근거 — 발표용 3개 주장

확인: 2026-10-07 15:25 KST · 미션 day-of-v1-20261007 · 검수/발표 반영: root.
공식 페이지를 실제 열어 확인하고 기존 제품 문서·코드를 읽은 조사 결과다. 이번 작업에서 모델·GPU·샌드박스·테스트를 실행하지 않았다.

## 슬라이드 1 — 에이전트 최소 권한 경계

**슬라이드 한 문장:** “한글동행은 OpenShell의 파일·네트워크 정책으로 worker의 접근 범위를 제한하고, 통제된 시험에서 금지 접근의 실제 차단을 확인했습니다.”

- **공식 설명·URL:** [OpenShell Sandbox Policies](https://docs.nvidia.com/openshell/latest/how-it-works/policies/overview)는 파일 접근을 Landlock으로, 네트워크 목적지·요청을 정책으로 통제하며 명시적으로 허용되지 않은 접근을 거부한다고 설명한다. provider가 더한 권한까지 합성한 effective policy가 실제 집행 대상이다. [NVIDIA/OpenShell GitHub](https://github.com/NVIDIA/OpenShell)의 How It Works도 모델 외부의 런타임 집행을 설명한다.
- **우리 구현 매핑:** [policy/README](../../../policy/README.md): 코드·자료는 읽기 전용, 임시 경로만 쓰기 허용, Landlock hard requirement, 비루트 실행, REST `enforce`. [SECURITY-EVIDENCE](../../runtime/SECURITY-EVIDENCE.md)의 실효 정책·런타임 로그·수신기 카운트를 함께 대조한다. [경계 결합 판정](../../runtime/evidence/boundary-combined-verdict.json)은 11조건 PASS를 기록한다.
- **발표에서 보여줄 증거:** 정책 밖 무해한 파일 읽기 거부와 일반 컨테이너 대조; 보호 fixture의 쓰기·삭제 거부 및 전후 해시 동일; 허용 health 요청 수신 1; 금지 예약 요청 403과 수신 0; 비허용 목적지의 정책 거부 로그와 수신 0.
- **한계:** 자체 fixture에서 시험한 권한 경계다. 모든 프롬프트 인젝션·데이터 유출·컨테이너 탈출 방지를 입증하지 않는다. `read_write` 경로에서는 삭제도 가능하다. 브라우저 카메라·마이크·위치·지도는 worker 샌드박스 밖이다. 정책 파일 존재나 실행 컨텍스트 문자열만으로 차단을 주장하지 않는다.

## 슬라이드 2 — Nemotron VL과 L40S의 역할

**슬라이드 한 문장:** “기존 L40S에서 실제 호출이 확인된 NVIDIA Nemotron VL을 시각 관찰과 근거 기반 답변에 연결하며, 문화·카메라 시나리오의 최종 품질은 별도로 검수합니다.”

- **공식 설명·URL:** [NVIDIA 공식 BF16 모델 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16)는 이미지·텍스트 및 영상 이해, 시각 질의응답을 설명하고 지원 하드웨어에 L40S를 명시한다. 영상 예제는 추출한 프레임을 사용하며 영상 디코딩 자체는 포함하지 않는다. 카드상 지원 언어는 English only, 모델 버전은 v1.0이다.
- **우리 구현 매핑:** [runtime README](../../runtime/README.md)의 기존 Brev L40S·vLLM 0.12.0·공개 BF16 모델 서빙 기록과 [SECURITY-EVIDENCE](../../runtime/SECURITY-EVIDENCE.md)의 실제 호출 기록을 연결한다. worker03의 [모델 이벤트](../../runtime/evidence/worker-03-model-events.jsonl)는 설정 모델과 응답 모델의 일치 3회를 기록한다. [agent/core.py](../../../agent/core.py)는 관찰/판단 → 허용 자료·장소 조회 → 근거를 포함한 결과 생성을 구성한다.
- **왜 시각 입력인가:** 사용자 앞의 장면에서 후보와 불확실성을 얻고 확인 질문의 대상을 좁히는 역할이다. 사진만으로 문화 장소·GPS를 확정하지 않는다. 우리 제품은 로컬 카메라 미리보기와 수동 캡처·선택 샘플 사진 분석을 구분하며, 연속 영상 전체 추론을 주장하지 않는다.
- **실행 상태·한계:** [BUILD-STATUS](../../BUILD-STATUS.md)의 15:17 갱신본에서 worker08 문화 GPU QA는 진행 중이며 PASS 미확정이다. 기존 모델 호출 성공은 새 자동 관찰·문화↔식당 안내·한국어 사실성의 성공 증거가 아니다. 합성 1회 0.683초를 제품 지연시간으로 사용하지 않는다.
- **키·제품명 표현:** 자체 GPU 모델 서빙 경로는 NVIDIA hosted API 키를 사용하지 않으며, broker 인증은 별도다. “무인증 제품”이라고 표현하지 않는다. 실제 사용을 확인한 명칭은 OpenShell + NVIDIA Nemotron VL + vLLM + L40S다. NIM API 형식 참고나 NVIDIA 모델 사용만으로 NIM·NeMoClaw 사용을 주장하지 않는다.

## 슬라이드 3 — 도구 허용과 모델 출력 검증

**슬라이드 한 문장:** “실행 가능한 도구와 통신을 제한하고, 모델 결과의 형식·근거·요청 소유권을 별도로 검사한 뒤 trusted broker가 영구 카드를 저장합니다.”

- **공식 설명·URL:** [OpenShell Security Best Practices](https://docs.nvidia.com/openshell/latest/security/best-practices)의 L4-Only vs L7 Inspection 및 Enforcement Mode는 목적지 허용과 HTTP method/path 허용이 다른 통제이며, `audit`는 기록 후 전달하고 `enforce`가 위반 요청을 차단한다고 설명한다.
- **우리 구현 매핑·구분:** 아래는 공식 정책 설명과 제품 코드에서 도출한 설계 구분이며, NVIDIA가 우리 답변의 정확성을 인증했다는 뜻이 아니다.

| 통제 | 검사 대상 | 우리 근거 |
|---|---|---|
| 앱의 도구·자료 허용 목록 | 승인한 source/place/food ID와 제한된 카탈로그 조회 | [agent/core.py](../../../agent/core.py)의 decision 검사·API search; [agent README](../../../agent/README.md) |
| OpenShell 실행 정책 | worker 프로세스의 파일·목적지·HTTP 요청 권한 | [policy README](../../../policy/README.md), [실측 경계 증거](../../runtime/SECURITY-EVIDENCE.md) |
| 모델 출력 검증 | JSON/schema, 승인 근거 레코드·인용 ID, 검색 결과와 장소 일치, 요청·세션·실제/가상 모드 | [agent/core.py](../../../agent/core.py), [service/main.py](../../../service/main.py)의 `validate_grounding` |
| 영구 산출물 작성 | 현재 활성 요청 검사 후 새 카드 저장 | [service/main.py](../../../service/main.py)의 `save_result`: broker가 JSON/HTML/Markdown을 생성; worker는 내용만 제안하며 파일명을 정하지 않음 |

- **한계:** 스키마와 허용된 인용 ID를 통과해도 문장의 의미·역사 사실·사용자 수요가 증명되지는 않는다. 허용된 API에 잘못된 내용을 보내는 위험은 네트워크 허용 목록만으로 해결되지 않는다. [BUILD-STATUS](../../BUILD-STATUS.md)에 보존된 저장 성공 후 의미 검수 실패 이력이 이 구분의 실제 사례다. 전체 인젝션 안전성 PASS·모든 환각 방지 표현은 쓰지 않는다.

## 확인일·버전과 인계 기준

- 공식 웹 확인: 2026-10-07. OpenShell `latest` 문서의 표시 버전은 **v0.1.2**였으며 제품 고정 런타임도 0.1.2다. GitHub `main`과 웹 문서는 변할 수 있다. v0.1.2 직접 schema/tag URL은 이번 웹 도구에서 열리지 않아 실제 열린 공식 latest 문서와 GitHub 본문을 근거로 사용했다.
- 모델 카드 v1.0과 제품 배포 revision은 서로 다른 표기다. 배포 revision은 [runtime README](../../runtime/README.md)에 기록되어 있다. 공식 카드의 일반 기능·설치 예제를 우리 배포의 전 기능 통과로 확대하지 않는다.
- 읽은 실행 정본 SHA256: `SECURITY-EVIDENCE.md = a960d3ac7472ba601848ca6daf8273f2b313b46b049bfd111f1293dfcb9745e7`; `BUILD-STATUS.md = 777dc80c5f77e0b5dafdaa5cd0034819077fcf1bd604e82d18521f7e3d00c253`.
- 이전 agent/runtime README의 미검증·교체 예정 문구와 후속 인계가 다르면, 날짜가 붙은 후속 실행 증거와 최신 BUILD-STATUS를 우선한다. 새 배포의 통과를 과거 증거로 대체하지 않는다.
- **root 인계:** 위 3개 문장은 현재 근거 범위로 사용 가능하다. 문화·카메라 완료/PASS 문구로 바꾸려면 최신 실제 GPU 결과·내용 검수·Android 자동 관찰 결과를 확인해야 한다. 이 문서는 발표 자료 조사만 완료하며 제품 실행·제출 완료를 선언하지 않는다.
