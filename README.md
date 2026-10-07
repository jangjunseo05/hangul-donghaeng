# 한글동행 · Hangul Donghaeng

한국 문화·역사와 한글을 이해하려는 여행자를 위한 음성·카메라 가이드입니다. 촬영한 장면과 질문을 바탕으로 출처가 있는 문화·장소·메뉴 설명, 수록 장소 안내, 여행 카드를 정리합니다. 한국어 확인 문장은 필요한 경우 반환되며 모든 응답에 포함되지는 않습니다. 영어 기본·한국어 전환을 지원합니다.

**2026-10-07 최신 상태: worker19 흐름 사용자 확인 — 이번 root 인계 기준.** 카메라 장면 관찰·잠정 랜드마크 제안 → 같은 대상의 후속 문화 설명 → 실시간 주변 음식점·지도 → 여행 카드와 선택적 한국어 확인 문장으로 이어지는 현재 흐름을 다룹니다. 사용자 확인과 독립 자동 테스트·문장별 사실 검수는 구분합니다. worker12의 3단계 영수증은 아래 보존 이력이며 현재 기능의 상한이 아닙니다. [코드 저장소](https://github.com/jangjunseo05/hangul-donghaeng), [빌드 상태](docs/BUILD-STATUS.md), [최신 API 계약](shared/api-contract.md), [worker19 변경 근거](docs/runtime/nearby-restaurants-20261007.md)를 함께 확인하세요.

## 제출 코드·문서와 공통 제공자료

제품 코드는 [독립 공개 개발 저장소](https://github.com/jangjunseo05/hangul-donghaeng)에 있습니다. 별도의 [공식 챌린지 fork](https://github.com/jangjunseo05/k-culture-openshell-challenge)는 root가 `isFork:true`, parent [seriousran/k-culture-openshell-challenge](https://github.com/seriousran/k-culture-openshell-challenge)로 확인했습니다. 기준 원본은 `714e2e8`이며, 별도 로컬 챌린지 체크아웃은 `origin`이 이 fork, `upstream`이 공식 원본입니다. 제품 저장소 자체를 챌린지 fork로 표시하지 않습니다. fork의 [SUBMISSION.md](https://github.com/jangjunseo05/k-culture-openshell-challenge/blob/adf0e4e/SUBMISSION.md)는 커밋 `adf0e4e`로 push 완료했다는 root 확인을 반영했습니다. 원출처·라이선스 표기를 유지하며 push와 행사 제출 접수는 구분합니다.

[제출 안내](docs/submission/제출_요약.md), [주요 로직·발표 원고](docs/submission/주요로직_발표설명.md), [심사기준 대응표](docs/submission/심사기준_대응표.md)를 제공합니다. **공통 제공자료용 일반 CLI [agent/challenge.py](agent/challenge.py)**는 문화카메라/OSM 제품과 별도 진입점입니다. 집중 테스트 17건·정책·출력 회수 테스트 8건 PASS 보고를 회수했습니다. [eval01](docs/runtime/evidence/challenge-01-receipt.json)은 응답 형식 오류로 실패했고, 프롬프트 보강 후 [eval02](docs/runtime/evidence/challenge-02-receipt.json)는 **3.135초, NVIDIA 모델 1회 호출로 JSON·Markdown 생성 및 회수 성공**했습니다. ‘해담문화원의 장소는?’에 `insufficient_evidence`를 반환해 근거 없는 주소를 만들지 않았습니다. 이 한 건의 미확인 처리만 수용했으며 일반 질문 정확도·전체 TASK·한국어 응답 품질의 통과를 뜻하지 않습니다. [실행법·정책·실측](docs/runtime/CHALLENGE-COMPATIBILITY.md)을 참고하세요. GitHub push와 행사 제출 접수는 별개입니다.

## 발표·핵심 시연 자료

- [발표 PPTX](docs/presentation/한글동행_발표.pptx)
- [최신 근거 반영 PDF](docs/presentation/한글동행_발표_근거반영.pdf)
- [PDF 본문 Markdown](docs/presentation/발표자료_PDF본문.md)
- [데모 핵심 시나리오](docs/presentation/데모_핵심시나리오.md)

기존 `한글동행_발표.pdf`는 잠긴 이전본으로 보존하며 최신본은 위 **근거 반영 PDF**입니다. 기존 발표물에 남아 있는 worker12 기본 시연 수치와 현재 worker19 사용자 확인 범위는 구분합니다. 현재 전체 흐름과 남은 제출 항목은 빌드 상태를 우선합니다.

## 현재 구현 범위

- 브라우저 음성 입력·답변 읽기, 수정 가능한 질문, 사진 업로드와 카메라 촬영을 지원합니다. 연속 카메라 미리보기는 로컬에서 처리하며, 사용자가 캡처하거나 선택적 자동 관찰이 추출한 정지 프레임만 분석 요청으로 전송합니다. 연속 영상 전체를 전송·저장하거나 영상 기억을 유지하지 않습니다. 모델은 선택한 샘플 사진만 분석합니다. 자동 관찰은 수동 질문을 우선하며 사용자가 중지할 수 있습니다. 음성 미지원·권한 거부 시 텍스트로 진행합니다.
- **검수된 기본 카탈로그 3곳**(경복궁·광화문·토속촌)과 **실시간 OSM 주변 음식점 검색**을 구분합니다. 광화문은 경복궁의 정문이며 같은 단지의 기준점입니다. 기본 카탈로그의 개수가 외부 검색 범위를 뜻하지 않습니다. 승인 문화 자료에는 카탈로그 밖 랜드마크 설명도 있으며, 자료가 부족한 대상은 부족하다고 답합니다. 시각적으로 제안된 장소명은 잠정 정보로 사용자 확인·GPS와 구분합니다.
- 사용자가 허용한 GPS, 지도에서 선택한 지점 또는 인식된 랜드마크의 조회 좌표를 검색 기준점으로 사용합니다. 지도 선택·랜드마크 좌표를 기기 GPS로 표시하지 않습니다. Leaflet/OpenStreetMap 지도에 500m·1km·2km·3km **직선거리 반경**을 적용합니다. 실시간 검색은 공개지도 수록 범위에서 거리순 최대 3개 음식점을 제시합니다. 도보 경로·맛/평점 순위·전국 전체 수록을 보장하지 않습니다.
- 문화·역사·메뉴 설명에 근거 ID와 출처를 표시합니다. 방문 예절과 운영 정보의 자료 시점을 구분하며, 현재 개방·영업·재고·재료·채식/알레르기 안전은 확인 대상으로 남깁니다.
- HTML·JSON 여행 카드 다운로드를 제공합니다. 한국어 확인 문장은 선택적으로 반환되며 항상 생성되지는 않습니다. 서버는 Markdown도 지원합니다. 예약·결제·주문·외부 발송은 수행하지 않습니다.

별도 가상 연습 모드는 공개된 가상 자료로 일정 초안을 만들며 실제 장소·사진·지도와 분리합니다. 개발용 fixture와 모델 stub은 실제 추론 증거가 아닙니다.

## 환경과 학습 여부

실제 확인한 추론 구성은 **NVIDIA L40S · vLLM 0.12.0 · `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16` · NVIDIA OpenShell 0.1.2**입니다. 모델 호출과 경계 시험 근거는 [실측 문서](docs/runtime/SECURITY-EVIDENCE.md)에 있습니다. 이 구현은 **NIM·NeMoClaw를 사용하지 않습니다.**

**학습 절차: 해당 없음.** 사전 학습된 모델로 추론하며 추가 학습·미세조정·가중치 갱신은 하지 않았습니다. [카탈로그](data/catalog.json)와 [근거 자료](data/evidence.json)는 검색·응답 검증용 입력입니다. 모델 revision·서빙 이미지·옵션은 [서빙 스크립트](infra/serve_nemotron.sh), worker의 Python 3.11 환경은 [Dockerfile](infra/Dockerfile.worker)과 [고정 의존성](infra/requirements-worker.txt), Python 평가 환경은 [requirements-lock.txt](requirements-lock.txt)에 기록합니다.

## 로컬 실행

확인한 환경은 Windows Python 3.12, WSL Ubuntu 22.04 Python 3.10, Node.js 24·npm 11입니다. **깨끗한 환경에서 아래 설치 절차 전체 재현은 아직 검증하지 않았습니다.** 기존 설치 환경에서 서비스 응답·Python 테스트·웹 테스트를 확인했습니다.

### Windows PowerShell

저장소 루트에서 실행합니다. 기존 `.env`가 있으면 복사하지 마세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m service
```

서비스는 기본 `http://127.0.0.1:8000`에서 실행합니다. 시작 시 `.env`를 읽고 비어 있는 `WORKER_TOKEN`을 로컬 파일에 생성합니다. 세션·작업 상태는 메모리에 있으므로 단일 프로세스로 실행합니다. 재시작 전에 필요한 카드를 내려받으세요.

모델 설정을 로컬 `.env`에 지정한 후 별도 터미널에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m agent.worker
```

기본 NVIDIA hosted API는 `NVIDIA_API_KEY`가 필요합니다. 별도 GPU의 OpenAI 호환 모델 서버 설정·인증 규칙은 [agent/README.md](agent/README.md)를 따르세요. 실제 모델 서버나 필요한 키가 없으면 답변 생성은 진행되지 않습니다. 로컬 worker 실행은 OpenShell 검증이 아닙니다.

### WSL Ubuntu 22.04

WSL 터미널에서 저장소 루트로 이동합니다. Linux 가상환경은 Windows `.venv`와 분리합니다. `.env` 복사는 파일이 없을 때만 수행하세요.

```bash
python3 -m venv "$HOME/.venvs/hangul-broker"
"$HOME/.venvs/hangul-broker/bin/python" -m pip install -r requirements.txt
cp .env.example .env
"$HOME/.venvs/hangul-broker/bin/python" -m service
```

worker는 `asyncio.timeout`을 사용하므로 **Python 3.11 이상**이 필요합니다. Ubuntu 22.04의 기본 Python 3.10 환경은 broker에만 사용하세요. Python 3.11 이상으로 만든 별도 환경이라면 같은 저장소의 다른 WSL 터미널에서 실행할 수 있습니다.

```bash
"$HOME/.venvs/hangul-broker/bin/python" -m agent.worker
```

현재 통합 환경은 WSL broker이며 Windows `http://127.0.0.1:8000/api/health` 응답을 확인했습니다. Windows·WSL에서 broker를 동시에 실행하지 마세요. OpenShell worker의 내부 broker 연결은 별도 배포 설정이 필요합니다.

### 웹 개발·빌드

broker를 먼저 실행한 뒤 별도 터미널에서 진행합니다.

```powershell
cd web
npm ci
npm run dev
```

`http://localhost:5173`에서 엽니다. Vite는 `/api`를 `http://127.0.0.1:8000`으로 전달합니다. `web`에서 제품 빌드를 실행합니다.

```powershell
npm run build
```

빌드 후 broker를 다시 시작하면 `web/dist`를 제공합니다. 마이크·위치 권한은 버튼을 누를 때 요청합니다. 음성 인식은 브라우저의 외부 서비스를 사용할 수 있고 지도 타일은 OpenStreetMap에서 받습니다. 시연 PC의 한·영 마이크와 TTS, Android 후면 카메라·캡처 유지·한·영 음성 입력은 사용자 확인 PASS입니다. Android TTS·자동 관찰 실동작과 최신 수정본의 검증 상태는 [빌드 상태](docs/BUILD-STATUS.md)를 따릅니다.

## 데모 실행 가이드

위 절차로 broker와 모델 worker 각 1개, 웹을 실행합니다. 행사 OpenShell 배포는 [런타임 인계](docs/runtime/README.md)와 [정책 안내](policy/README.md)를 따르며 기존 GPU·worker를 중복 기동하지 않습니다. 최신 계약은 [shared/api-contract.md](shared/api-contract.md), 장치 인계와 실패 시 대체 흐름은 [데모 runbook](docs/DEMO-RUNBOOK.md)입니다. 이전 인계의 버전별 상태보다 최신 실행 근거를 우선합니다.

1. PC에서 `http://localhost:5173` 또는 빌드 제공 broker `http://127.0.0.1:8000`을 엽니다. 휴대폰은 운영자가 확인한 HTTPS 주소를 사용합니다. 임시 공개 주소는 문서에 고정하지 않습니다.
2. **카메라 시작** → 미리보기 확인 → **사진 고정 촬영**, 또는 허용된 사진을 업로드합니다. 자동동행은 기본으로 끄고 수동 경로부터 확인합니다. 캡처만으로 질문이 전송되지는 않습니다. 사진 고정은 선택 사항입니다. 로컬 카메라가 켜져 있고 사진을 고정하지 않았다면 수동 질문을 보낼 때 현재 프레임을 캡처합니다. 명시적으로 촬영·업로드한 사진은 고정해 후속 질문에 사용하며 연속 영상을 기억하지 않습니다.
3. 장면 관찰이나 사진 질문으로 잠정 장소·확인 질문을 받습니다. “응 알려줘” 같은 후속 질문은 직전 관찰 대상의 맥락을 이어갑니다. 새 사진의 장소가 확인됐다는 뜻은 아닙니다. 잘못된 후보는 수정하고, 카탈로그 밖 장소를 광화문 등 기존 ID로 바꾸지 않습니다. 필요하면 GPS를 허용하거나 지도에서 검색 기준점을 선택합니다. 현재 UI에는 서촌 시연 버튼·카탈로그 선택 기능이 없습니다.
4. 문화 설명을 확인한 뒤 “주변 맛집 추천해줘” 또는 주변 음식점 찾기로 이어갑니다. broker가 고정 Nominatim/Overpass 서비스에서 주변 후보를 조회합니다. 지도 중심이 랜드마크 조회 좌표인지 사용자 위치인지 확인하고, 외부 음식점은 OSM 원문을 엽니다. 맛·영업·메뉴·알레르기 안전은 확인 대상으로 남깁니다. 반환된 경우 한국어 현장 문장을 확인하고 HTML·JSON 카드를 저장하며 필요한 이전 카드는 후속 질문 전에 보존합니다.
5. 자동 관찰은 해당 배포의 실제 QA 통과 후 명시적으로 선택합니다. 이전 응답 완료 후 최소 20초가 지난 뒤 샘플 프레임을 분석하며, 시연 종료 시 자동동행과 카메라를 끕니다. 실패·시간 초과는 실패로 표시하고, 예비 저장 결과를 보여 줄 때는 사전 결과임을 밝힙니다.

## 평가·검증

저장소 루트에서 평가 의존성을 설치한 뒤 Python 단위·통합·정책/경계 판정 테스트를 실행합니다. 세션·확인 ID·출처/좌표·이력·가상 모드 경계와 결과 저장을 검증합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration tests/security/test_policy.py tests/security/test_boundary_evidence.py -q
```

`web`에서 웹 테스트를 실행합니다. Playwright는 broker·웹 개발 서버가 실행 중이고 Chrome이 설치된 환경에서 사용합니다.

```powershell
npm test
npx playwright test
```

이전 버전에서 root가 보고한 검사는 **157 passed + 62 subtests passed (3.96초)**입니다. worker19의 새 회귀 결과로 재사용하지 않습니다. 이번 README 정리에서 재실행하지 않았습니다. 당시 desktop/mobile 캡처 회귀 **12건 및 빌드 PASS**도 과거 결과입니다. 이전 브라우저 52건·단위 12건과 합산하지 않습니다. 상세 판정은 [빌드 상태](docs/BUILD-STATUS.md)를 따릅니다. 모델 HTTP stub·합성 장치 fixture 기반 검사는 실제 추론이나 문화적 사실성의 증거가 아닙니다. 실제 평가는 요청→도구→응답→다운로드 카드의 일치, 문장별 출처 적합성, 불확실성·실패 처리를 확인합니다. **현재 worker19는 최신 사용자 확인**, 아래 worker12 영수증은 별도 과거 실행 근거입니다. 이번 작업에서는 테스트·외부 검색·모델 호출을 실행하지 않았습니다.

### 보존 이력: worker12 UI 검증 · 15:52–15:53 KST

[기본 흐름 실행 영수증](.runtime/qa-ui-real/2026-10-07T06-52-12-176Z/receipt.json): 3단계 **8.238 / 22.325 / 21.498초**, 실제 HTTPS·broker·모델 결과 및 HTML/JSON 다운로드 확인. JS 오류 0건, desktop 1440px·mobile 390px 레이아웃 넘침 없음. 모바일 검사는 같은 결과의 화면 크기 변경이며 별도 실기기 추론 검사가 아닙니다. 시간은 해당 실행 관측값이지 응답 속도 보장이 아닙니다.

입력은 공개 아카이브 사진이며 현장 촬영이 아닙니다. 첫 응답은 장소 후보 없이 확인을 요청했고 이후 **사용자가 광화문을 카탈로그에서 명시적으로 선택**했습니다. 사진 인식 성공·연속 영상 기억·자동 관찰 성공으로 확대하지 않습니다. 이전 전체 흐름의 4번째 메뉴 질문은 **historical_source_mismatch, 32.608초 후 실패**했으며 기본 흐름 PASS가 이를 해결했다는 뜻은 아닙니다. 이는 당시 회차의 역방향·장치별 확인 한계입니다. 최신 worker19 사용자 확인과 혼합하지 않으며 개별 Android TTS·역방향·메뉴 실패의 재현/해결 판정은 별도 근거가 필요합니다. 영수증은 로컬 `.runtime` 근거로 공개 저장소 포함을 보장하지 않습니다.

pJ의 최종 기본 흐름 의미 검수에서는 남문·복원에 관한 근본적 오류는 발견되지 않았습니다. 다만 영어 문화 설명의 `symbolic motifs`는 제시한 인용 근거로 뒷받침되지 않고, 삼복을 `three hot summer days in Korean calendar`로 설명한 표현은 지나치게 단순화되어 문구 검수가 남아 있습니다. **UI PASS는 모든 문화적 사실·문장별 출처 적합성 PASS가 아닙니다.** 기본 출처·위치·지도·카드 기능의 통과와 이 한계를 함께 제시합니다. 이 문서 갱신을 위해 재배포하지 않았습니다.

## 데이터·실행 경계

브라우저 → 신뢰하는 FastAPI broker → worker → NVIDIA 호환 모델·허용된 근거/문화 지점·식당 검색 도구 순서로 처리합니다. broker는 사진 방향·크기를 정규화하고 EXIF를 제거하며 요청 소유권·근거 ID·장소 좌표를 검사한 뒤 `.runtime/output`에 결과를 저장합니다. worker는 결과 파일을 직접 쓰지 않습니다. 출처 ID 검사만으로 모델 문장의 사실성까지 증명되지는 않습니다.

OpenShell 정책은 worker의 코드·자료 읽기, 임시 공간 쓰기, 지정 broker·모델 호스트 통신으로 제한합니다. [실제 경계 검증](docs/runtime/SECURITY-EVIDENCE.md)에서는 자체 무해한 fixture와 수신기를 사용해 파일 접근 거부, 허용 통신, 금지 예약 POST·비허용 목적지 차단을 실효 정책·런타임 로그·수신기 카운트와 대조했습니다. [결합 판정 11개 조건이 PASS](docs/runtime/evidence/boundary-combined-verdict.json)이며 실제 모델 호출 근거도 보존되어 있습니다. 이는 해당 배포와 시험 조건의 결과로, 새 문화·카메라 흐름의 실제 GPU 검증이나 전체 제품 품질 보증은 아닙니다. gateway 연결·정책 lint·`RUN_CONTEXT=openshell` 표시만으로 검증을 대신하지 않습니다. 브라우저 음성·위치·지도 요청은 worker 샌드박스 밖에서 실행됩니다. [런타임 인계](docs/runtime/README.md), [정책 안내](policy/README.md), [API 계약](shared/api-contract.md)을 참고하세요.

## 정책 경로·권한과 이유

정책 원본 생성기는 [infra/render_policy.py](infra/render_policy.py)입니다. 운영자가 확인한 broker·모델 endpoint를 인자로 주어 `infra/generated/worker-policy.json`, `guide-profile.json`을 생성합니다. hosted API 선택 시에만 `nvidia-profile.json`이 추가됩니다. 생성본·인증 값은 공개하지 않으며, 실제 적용한 provider 합성 정책은 [latest-effective-policy.json](docs/runtime/evidence/latest-effective-policy.json), 배포 대응 관계는 [latest-readiness.json](docs/runtime/evidence/latest-readiness.json)으로 확인합니다.

| 권한 | 경로·범위와 허용 이유 |
|---|---|
| 읽기 전용 | `/app`의 코드·근거, `/usr`, `/lib`, `/lib64`, `/etc`, `/proc`, `/dev/urandom`: Python 실행·라이브러리·시스템 정보·난수 사용. 코드와 자료 변경 권한은 부여하지 않습니다. |
| 임시 쓰기 | `/tmp`, `/dev/null`: 실행 중 임시 파일·출력 처리. `read_write`에는 삭제도 포함되므로 이 공간의 삭제 차단을 주장하지 않습니다. |
| broker 통신 | 고정 host의 `GET /api/health`, 작업·배정 사진 조회, `POST /worker/search`, `/worker/results`, `/worker/fail`: 작업 수행·검증된 검색·결과 반환에 필요합니다. broker가 세션/작업 소유권을 별도 검사합니다. |
| 모델 통신 | 고정 모델 host의 `GET /v1/models`, `POST /v1/chat/completions`: 모델 확인·추론만 허용합니다. 실제 구성은 자체 GPU이며 hosted API를 선택하면 NVIDIA 인증은 해당 공식 endpoint에만 결합합니다. 임의 목적지·예약 API는 허용하지 않습니다. |
| 실행·영구 결과 | non-root UID/GID 1000, Landlock 필수·REST `enforce`. worker는 영구 결과를 직접 쓰지 않고 broker가 검증 후 `.runtime/output`에 저장합니다. |
| broker의 실시간 OSM 조회 | 고정 HTTPS Nominatim/Overpass endpoint에서 장소 이름·좌표로 주변 음식점을 조회합니다. 사진·인증정보·모델이 정한 임의 URL/쿼리는 전달하지 않습니다. 결과와 출처를 작업에 결합해 검사하며 외부 식당을 기본 카탈로그 확인 ID로 위장하지 않습니다. 이 조회는 trusted broker 경계이며 worker allowlist 확장이 아닙니다. |
| 브라우저 외부 서비스 | 사용자 동의 카메라·마이크·위치, 브라우저 음성 서비스, OpenStreetMap 타일. worker 정책 밖의 기능이며 사용자 사진을 지도 서비스에 보내는 흐름은 없습니다. |

[통제된 경계 시험 11조건 PASS](docs/runtime/evidence/boundary-combined-verdict.json)는 허용·차단 로그와 수신기 카운트를 결합한 결과입니다. 모든 목적지나 모든 제품 시나리오를 시험했다는 뜻은 아닙니다. 정책을 바꾸면 실효 정책과 실행 근거를 다시 확인합니다.

`.env`·개인키·런타임 파일은 로컬에만 두세요. 샘플의 비밀 값은 비워 두며 토큰·키·원본 사용자 사진을 커밋하거나 로그에 출력하지 않습니다. NVIDIA hosted 키와 self-hosted 인증 키를 혼용하지 않습니다.
