# 개발·검증 상태

2026-10-07 KST 관측 기록입니다. 제품 출시나 해커톤 완료 판정이 아닙니다. 공개 저장소: [jangjunseo05/hangul-donghaeng](https://github.com/jangjunseo05/hangul-donghaeng).

## 구현 및 확인한 결과

| 항목 | 관측·검증 범위 |
|---|---|
| Broker | 세션·사진 정규화/EXIF 제거·작업 배정·검색·결과 검증·세션 소유 다운로드 구현. WSL Ubuntu 22.04 실행, Windows localhost:8000 /api/health 실제 응답 확인 |
| 데이터·agent | 식당 1곳·메뉴 3개와 허용 근거 자료. 사진/질문 → 모델 판단 → 근거/반경 검색 도구 → 구조화 결과 흐름 구현. 테스트 모델 응답은 HTTP stub |
| 웹 | 음성/텍스트·사진·한영 전환·반경 지도·근거/문화/메뉴·한국어 문장·카드 다운로드 구현. 웹 빌드 통과는 통합 담당 확인 |
| Python 자동 테스트 | 수정 후 Windows pytest: **50 passed, 29 subtests passed**. Starlette/httpx deprecation warning 1개 |
| 웹 단위 테스트 | npm test: **7 passed** |
| 브라우저 테스트 | 웹 담당 최종 실행: Playwright desktop/mobile 합계 **10개 통과**. [인계 기록](../web/BUILD-WEB-01.md). 실제 마이크 입력·스피커 성공은 별도 확인 필요 |
| OpenShell | **0.1.2 gateway Connected**, provider policy lint 통과, 정책 설정 테스트 **4개 통과**. 위 Python 42개에 포함 |
| GPU 준비 | 담당자가 Brev CLI 인증과 기존 **NVIDIA L40S, 46068 MiB** 확인. NVIDIA 모델 배포 진행 중, hosted API 키는 없음 |

13:30 시점 health 응답은 `status=ok`, `catalog_count=1`, `worker_connected=false`, `model_configured=false`, `sandbox_verified=false`입니다. 연결·설정 관측용이며 실제 모델 성공이나 정책 차단 증거가 아닙니다. self-hosted 모델 설정은 hosted 키 존재와 별도로 판단해야 합니다.

사용자는 시연 PC Chrome에서 영어·한국어 실제 마이크 입력이 모두 표시됐다고 확인했습니다. 답변의 실제 음성 재생은 별도 확인 대기입니다. 핵심 코드의 독립 재검수는 [코드 검수 승인·구조 검수 CLEAR](qa/core-review-20261007.md)이며 제품 런타임 판정과 구분합니다.

## 남은 제품 검증

- 배포된 NVIDIA 모델 실제 응답과 사진 한 장으로 수행하는 worker·broker·웹·저장 카드 전체 왕복.
- OpenShell 내부 worker의 실효 정책 및 실제 허용·차단 기록. gateway 연결과 설정 테스트만으로 격리 통과를 기록하지 않습니다.
- 실제 장치의 마이크 입력·스피커 출력. 자동 브라우저 검사에서 권한 오류 안내·텍스트 편집을 확인했지만 음성 성공을 증명하지는 않습니다.
- 깨끗한 Windows/WSL 환경에서 README 최초 설치 절차 전체 재현. 기존 환경 실행·테스트 확인과 구분합니다.

직선거리 지도는 도보 경로가 아니며 수록 식당만 다룹니다. 영업·재고·재료·채식/알레르기 안전은 확인 전입니다. 가상 연습 자료와 개발 fixture를 실제 장소·실시간 모델 결과로 표시하지 않습니다. 예약·주문·결제·외부 발송은 범위 밖입니다.

## 당일 마감

**15:30 기능 동결 → 16:15 검증 종료 → 16:30 발표 준비 → 17:20 제출.** 통합 담당이 새 실행 증거를 확인하면 이 기록을 갱신합니다. 확인하지 못한 항목은 미검증으로 남깁니다.
