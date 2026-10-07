# 개발·검증 상태

**최신 스냅샷: 2026-10-07 15:54 KST, root·p8 최종 인계.** worker12의 기본 UI 3단계와 다운로드는 PASS입니다. 전체 기능·모든 문화적 사실성·대외 제출 완료 판정은 아닙니다. [공개 저장소](https://github.com/jangjunseo05/hangul-donghaeng)의 root 코드 `ab0794b` push는 보고받았으며 이번 문서 변경의 커밋·push는 root가 수행합니다.

## 최신 상태

| 항목 | 판정과 확인 범위 |
|---|---|
| 제품 범위 | 한국 문화·역사·한글 동행. 경복궁·광화문은 같은 궁궐 단지의 문화 기준점 2개이며 토속촌 식당 1곳을 함께 안내합니다. 로컬 카메라 미리보기와 선택적 샘플 사진 분석이며 연속 영상 기억은 아닙니다. |
| Python | **157 passed + 62 subtests passed, 3.96초 — root 보고.** 문서 정리 과정에서 재실행하지 않았습니다. |
| worker12 | **배포 완료 — root 보고.** 승인된 출처 기반 메뉴 처리 수정 포함. 배포·코드 수정과 아래 실제 시나리오의 성공/실패를 구분합니다. |
| 기본 실제 UI 흐름 | **PASS_PRIMARY_UI_JOURNEY.** 실제 HTTPS 브라우저의 사진 질문 **8.238초**, 사용자 장소 선택 후 문화 질문 **22.325초**, 문화→주변 식사 **21.498초**. HTML·JSON 다운로드 성공. [영수증](../.runtime/qa-ui-real/2026-10-07T06-52-12-176Z/receipt.json). |
| 장소 확인의 한계 | 첫 응답은 `need_confirmation`, 장소 후보 없음. **사용자가 광화문을 카탈로그에서 명시적으로 선택**했습니다. 모델의 사진 인식 성공이 아닙니다. 입력은 공개 아카이브 사진이며 팀의 현장 촬영이 아닙니다. |
| 메뉴 추가 질문 | **미해결 실패 보존.** 이전 worker12 전체 흐름의 4번째 restaurant-menu 질문은 `historical_source_mismatch`로 **32.608초 후 실패**. 최종 기본 흐름에서는 재실행하지 않았으며 PASS가 아닙니다. |
| 식사→문화 역방향 | **최종 UI에서 미실행·미검증.** 이전 실패를 기본 흐름 PASS로 해결 처리하지 않습니다. |
| 브라우저·레이아웃 | 최종 기본 UI에서 **JS 오류 0건**, desktop 1440px·mobile 390px 넘침 없음. 모바일은 같은 결과의 viewport 변경이며 별도 모바일 모델 호출은 없습니다. |
| 프런트엔드 회귀 | **desktop/mobile 캡처 테스트 12건 및 빌드 PASS — 보고 수령.** 이전 브라우저 52건·단위 12건과 합산하지 않습니다. |
| Broker origin | WSL의 빈 환경 변수가 `.env` 설정을 덮어쓴 403 원인을 수정했고 **세션 POST 200 확인 — root 보고**. 운영 설정 값·임시 공개 주소는 기록하지 않습니다. |
| PC 실기기 | **사용자 PASS:** 한국어·영어 마이크 입력 및 TTS 출력. 해당 장치·당시 실행에 한정합니다. |
| Android 실기기 | **사용자 PASS:** 후면 카메라, 카메라 중지 후 캡처 유지, 한국어·영어 음성 입력. **Android TTS·자동 관찰 실동작은 사용자 확인 대기.** 최종 UI 검사는 아카이브 사진 업로드이며 실물 카메라·오디오·자동 프레임 검사가 아닙니다. |
| NVIDIA 실제 호출 | 실제 모델 응답·저장 근거 존재. [최신 실행 근거](runtime/evidence/latest-model-execution.json)에서 worker·캡처 시각·수용 상태를 함께 확인합니다. 호출·저장 성공은 문장별 사실성 보증이 아닙니다. |
| OpenShell | **통제된 경계 시험 11조건 PASS.** [실측 설명](runtime/SECURITY-EVIDENCE.md), [결합 판정](runtime/evidence/boundary-combined-verdict.json), [최신 배포 준비](runtime/evidence/latest-readiness.json), [실효 정책](runtime/evidence/latest-effective-policy.json). UI 영수증만으로 worker 정책을 검증했다고 주장하지 않습니다. |
| 설치 재현 | 기존 환경 실행과 별개로 깨끗한 Windows/WSL 환경에서 [README](../README.md) 설치 전체 재현은 미검증입니다. |

관측 시간은 해당 요청의 실제 UI 처리 시간이며 성능 보장이 아닙니다. 기본 흐름 영수증은 15:52:12 시작·15:53:13 종료입니다. 다운로드 [HTML](../.runtime/qa-ui-real/2026-10-07T06-52-12-176Z/result.html)·[JSON](../.runtime/qa-ui-real/2026-10-07T06-52-12-176Z/result.json)은 최종 문화→식사 요청에 대응합니다. 출처 표시가 역사 문장의 사실성·현재 개방/영업·재료 안전을 자동 증명하지 않습니다.

## 보존한 실패·이전 실행

- **worker12 이전 전체 UI 시도:** 첫 3단계 8.344 / 18.363 / 24.302초 완료, 4번째 메뉴 질문 `historical_source_mismatch` 실패 32.608초. 이 시도에서는 역방향·다운로드를 실행하지 않았습니다. 이후 기본 3단계+다운로드만 별도로 재검증한 것이 위 PASS입니다. [로컬 UI 실행 기록](../.runtime/qa-ui-real/).
- **worker11 API:** 관찰 completed 8.140초, 문화→식당 ready 22.344초, 음식→문화 `unknown_menu` 실패. 메뉴 승인 출처 수정 후 worker12가 배포됐지만 최종 UI에서는 역방향을 재검증하지 않았습니다.
- **worker08:** 소스 SHA 접두 `abdf2236…`, 단일 consumer·동일 allowlist 준비 PASS는 과거 인계입니다. [당시 API 기록](../.runtime/culture-qa/20261007T061502909648Z/metrics.json).
- **worker07:** observe·heritage의 `evidence_scope_mismatch` 실패 진단은 root 보고입니다. [15:10 관찰](../.runtime/culture-qa/20261007T061009843107Z/metrics.json), [15:12 문화→식당](../.runtime/culture-qa/20261007T061256067109Z/metrics.json).
- **worker04~06:** [가상 과제 실패](runtime/evidence/worker-04-fictional-diagnosis.json), [문화 Draft timeout](runtime/evidence/worker-04-culture-diagnosis.json), [저장 성공과 의미 검수 실패](runtime/evidence/worker-06-evidence.json).
- **초기 실행:** [음식·식당 metrics](../.runtime/qa/20261007T045727704776Z/metrics.json), [먼 지역·가상 과제 metrics](../.runtime/qa/20261007T052048255340Z/metrics.json), [worker03 이벤트](runtime/evidence/worker-03-model-events.jsonl), [이전 웹 인계](../web/BUILD-WEB-01.md), [15:02 합성 카메라 체크박스 검사](../.runtime/qa/pf-auto-eligibility-20261007/evidence.json). 과거 수치·미검증 문구는 최신 판정을 대체하지 않습니다.

`.runtime` 링크는 로컬 근거이며 공개 저장소 포함을 보장하지 않습니다. latest 파일도 worker·캡처 시각을 대조해야 하며 이름만으로 현재 배포의 근거로 간주하지 않습니다. 원본 로그는 변경하지 않았습니다. health의 `model_configured`·`sandbox_verified`는 자체 GPU·독립 정책 실측과 구분합니다.

## 남은 범위와 마감

기본 시연은 **사진 질문 → 사용자 명시적 장소 선택 → 문화→주변 식사 → HTML/JSON 저장**으로 한정합니다. 메뉴 후속 실패, 식사→문화 역방향, Android TTS·자동 관찰은 완료로 표시하지 않습니다. 운영 순서는 [데모 runbook](DEMO-RUNBOOK.md), API 경계는 [최신 계약](../shared/api-contract.md)을 따릅니다. 직선거리 지도는 도보 경로가 아니며, 예약·주문·결제·외부 발송은 범위 밖입니다.

**16:00은 개발·검증·커밋·push 완료의 상한이며 기다리는 시각이 아닙니다.** 준비된 결과는 즉시 root에 인계합니다. 공식 제출은 17:20이며 현재 문서는 전체 기능·제출 완료를 선언하지 않습니다.
