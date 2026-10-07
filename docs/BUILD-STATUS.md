# 개발·검증 상태

**2026-10-07 최신 root 인계: worker19 사용자 확인 범위를 현재 기준으로 사용합니다.** worker12의 15:52 기본 UI 영수증·당시 테스트·실패는 보존 이력입니다. 사용자 확인, 코드/배포 기록, 독립 테스트와 문화적 사실 검수를 구분합니다. 공통 제공자료 별도 어댑터의 단일 실제 질문·파일 출력 확인까지 완료했습니다. 전체 공식 평가와 행사 접수는 별개입니다.

## 현재 상태

| 항목 | 확인 범위와 한계 |
|---|---|
| 현재 제품 흐름 | **worker19 사용자 확인 — 최신 root 인계.** 로컬 카메라/선택 프레임 관찰 → 잠정 랜드마크·확인 질문 → 같은 대상의 문화 후속 설명 → 실시간 주변 음식점·지도 → 카드와 선택적 한국어 현장 문장. 한국어 문장은 모든 응답에 반환되지는 않습니다. 이번 문서 작업에서 새 실행 검증은 하지 않았습니다. |
| 관찰 맥락 | 직전 잠정 장소명과 관찰 문맥을 같은 세션·모드의 후속 질문에 전달합니다. 카메라 중지 후 마지막 관찰 사진을 유지하며 카탈로그 밖 이름을 광화문 등으로 대체하지 않습니다. 사진에서 GPS·확정 신원을 얻거나 전체 영상을 기억하는 기능이 아닙니다. [변경 근거](runtime/visual-followup-hotfix-20261007.md). |
| OSM 실시간 검색 | broker가 고정 Nominatim/Overpass를 통해 인식된 랜드마크 조회 좌표, 사용자가 허용한 GPS 또는 지도 선택 기준점 주변 음식점을 거리순 최대 3개 조회합니다. 작업별 이름·좌표·OSM 출처를 검증하고 외부 식당 클릭은 OSM 상세로 연결합니다. 맛·평점·현재 영업·식이 안전은 확인하지 않습니다. [worker19 기록](runtime/nearby-restaurants-20261007.md), [최신 API 계약](../shared/api-contract.md). |
| 기본 카탈로그 | 경복궁·광화문(같은 궁궐 단지)·토속촌 3곳은 검수된 기준 데이터입니다. **3곳이 실시간 외부 검색의 상한은 아닙니다.** 현재 UI의 서촌 시연 버튼·카탈로그 선택 기능은 제거됐으며 해당 조작을 안내하지 않습니다. 승인 문화 설명 자료와 지도 카탈로그도 동일 범위가 아닙니다. |
| 현재 확인의 출처 | worker19 개발 기록의 “새 테스트/실제 조회 미실행”은 해당 작성 시점의 상태입니다. 이후 사용자 확인은 최신 root 인계에 근거하며 독립 자동 테스트·속도 측정으로 바꾸지 않습니다. |
| 테스트 | **새 worker19 PASS 수치는 제공받지 않았습니다.** 157 tests + 62 subtests(3.96초), 캡처 12건/빌드 및 이전 52 browser/12 unit PASS는 이전 버전 이력입니다. 합산하거나 최신 회귀 결과로 표시하지 않습니다. |
| 공통 제공자료 테스트 | **challenge 집중 테스트 17건·정책·출력 회수 테스트 8건 PASS — root 보고.** 문화카메라·OSM 제품 흐름과 별도 CLI이며, 테스트 통과가 실제 모델 답안 성공을 뜻하지 않습니다. 문서 작업에서 재실행하지 않았습니다. |
| eval01 실제 실행 | **FAIL — strict schema / FAILED_INVALID_MODEL_OUTPUT.** 모델 2회 호출, 25.566초, 답안 파일 생성 없음. 정책 검증·fixture 쓰기 probe는 확인됐지만 답안 성공은 아닙니다. [실행 영수증](runtime/evidence/challenge-01-receipt.json), [CLI](../agent/challenge.py). |
| eval02 실제 실행 | **단일 질문 실행·출력 PASS.** 전체 3.135초, 모델 1회 2.334초. JSON/Markdown 회수, insufficient_evidence로 없는 주소 생성 없음. 영어 일반 문구이며 전체 TASK·QA 정확도는 미검증. [영수증](runtime/evidence/challenge-02-receipt.json). |
| 코드·제출 문서 | [제품 저장소](https://github.com/jangjunseo05/hangul-donghaeng)는 독립 저장소입니다. 별도 [챌린지 fork](https://github.com/jangjunseo05/k-culture-openshell-challenge)는 root가 `isFork:true`, parent `seriousran/k-culture-openshell-challenge`, 원본 `714e2e8`을 확인했습니다. 로컬 챌린지 체크아웃의 origin=fork, upstream=공식 원본입니다. [fork SUBMISSION.md](https://github.com/jangjunseo05/k-culture-openshell-challenge/blob/adf0e4e/SUBMISSION.md) `adf0e4e` push 완료 — root 확인. [제출 패키지](submission/)·[심사기준 대응표](submission/심사기준_대응표.md)는 작성·공개됐으며 행사 접수는 미확인입니다. |
| NVIDIA·OpenShell | L40S/vLLM/Nemotron VL 실제 호출, OpenShell 통제된 11조건 검증은 기존 근거를 보존합니다. [실측](runtime/SECURITY-EVIDENCE.md), [결합 판정](runtime/evidence/boundary-combined-verdict.json), [배포](runtime/evidence/latest-readiness.json), [모델 실행](runtime/evidence/latest-model-execution.json). 파일별 worker·시각·수용 상태를 대조하며 과거 로그를 worker19 검증으로 바꾸지 않습니다. |
| 장치 확인 | PC 한·영 마이크/TTS, Android 후면 카메라·캡처 유지·한영 마이크는 기존 사용자 확인입니다. 최신 전체 흐름 확인을 Android TTS·모든 자동 관찰 예외·역방향·메뉴 회귀 각각의 PASS로 확대하지 않습니다. |

## 이전 실행·결함 이력

- **worker12 기본 UI:** [15:52–15:53 영수증](../.runtime/qa-ui-real/2026-10-07T06-52-12-176Z/receipt.json), 3단계 8.238 / 22.325 / 21.498초, HTML/JSON 다운로드, JS 오류 0건·desktop/mobile 넘침 없음. 공개 아카이브 사진에서 후보가 나오지 않아 사용자가 광화문을 직접 선택했습니다. 이는 당시 사진 인식 성공이나 현재 기능 범위의 상한이 아닙니다.
- **worker12 전체 시도:** 4번째 메뉴 질문 historical_source_mismatch, 32.608초 실패. 최종 기본 회차에서 메뉴·역방향을 재검증하지 않았습니다. [UI 실행 이력](../.runtime/qa-ui-real/). 현재 최신 사용자 확인으로 개별 결함의 독립 재검증까지 완료했다고 쓰지 않습니다.
- **문화 문구:** pJ는 당시 남문·복원의 근본적 오류를 발견하지 않았으나 symbolic motifs 인용 근거 부족, 삼복을 three hot summer days in Korean calendar로 단순화한 표현을 지적했습니다. 현재 UI 작동 확인은 모든 문화적 사실·문장별 출처 적합성 PASS가 아닙니다.
- **worker11:** observe completed 8.140초, 문화→식당 ready 22.344초, 음식→문화 unknown_menu 실패. **worker07:** evidence_scope_mismatch 실패. **worker04~06:** [가상 과제 실패](runtime/evidence/worker-04-fictional-diagnosis.json), [timeout](runtime/evidence/worker-04-culture-diagnosis.json), [저장·의미 검수](runtime/evidence/worker-06-evidence.json).
- **세션 복구:** 당시 빈 WSL 환경 변수의 origin 403 원인 수정 후 session POST 200을 root가 확인했습니다. 현재 운영 설정 값은 공개하지 않습니다.

`.runtime` 링크는 로컬 근거입니다. 원본 로그·다른 담당 파일·앱 코드·AGENTS는 이 작업에서 변경하지 않았습니다. health나 latest 파일명만으로 현재 모델/정책 PASS를 판정하지 않습니다.

## 제출 준비와 남은 확인

[README 실행·평가 안내](../README.md), [데모 runbook](DEMO-RUNBOOK.md), [발표 PPTX](presentation/한글동행_발표.pptx), [근거 반영 PDF](presentation/한글동행_발표_근거반영.pdf), [PDF 본문](presentation/발표자료_PDF본문.md), [핵심 시연](presentation/데모_핵심시나리오.md)을 제공합니다. 발표물의 worker12 제한·측정값은 당시 근거로 읽고 현재 worker19 설명과 구분합니다. 잠긴 기본 PDF는 이전본으로 보존합니다.

공통 제공자료 CLI는 eval01 실패 이후 eval02에서 3.135초·모델 1회로 답변 JSON/Markdown 생성과 회수를 완료했습니다. 자료에 없는 해담문화원 주소를 생성하지 않는 한 건의 처리만 root와 pN이 수용했습니다. 실제 답변 문장은 영어이며 전체 TASK·일반 QA 정확도는 미검증입니다. [실행 증거](runtime/CHALLENGE-COMPATIBILITY.md). 최종 행사 접수는 사용자 팀이 진행합니다. 공식 fork 관계와 SUBMISSION.md push는 확인됐지만 실제 CLI 실행 성공이나 제출 접수의 증거는 아닙니다. 공식 제출 17:20까지 실제 제출은 사용자 팀이 확인합니다. 제품 저장소·문서 작성만으로 제출 완료나 전체 평가 적격을 선언하지 않습니다. 예약·주문·결제·외부 발송은 제품 범위 밖입니다.
