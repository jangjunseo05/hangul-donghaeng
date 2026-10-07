# 한글동행 · Hangul Donghaeng

한국 문화·역사와 한글을 이해하려는 여행자를 위한 음성·카메라 가이드입니다. 촬영한 장면과 질문을 바탕으로 출처가 있는 문화·장소·메뉴 설명, 수록 장소 안내, 직접 말할 수 있는 한국어 확인 문장을 여행 카드로 정리합니다. 영어 기본·한국어 전환을 지원합니다.

**2026-10-07 15:54 KST: worker12 기본 UI 흐름 PASS, 전체 기능 검증·제출은 미완료입니다.** [공개 GitHub 저장소](https://github.com/jangjunseo05/hangul-donghaeng)에서 코드와 실행 안내를 제공합니다. 실제 HTTPS 브라우저에서 문화 사진 질문 → 사용자 카탈로그 선택 → 주변 식사 안내의 3단계와 HTML·JSON 다운로드를 확인했습니다. 사진 속 장소는 미확정이었고 사용자가 명시적으로 선택했으므로 사진 인식 성공은 아닙니다. 메뉴 후속 실패와 역방향 미검증은 아래에 구분합니다. 현재 수용 범위는 [빌드 상태](docs/BUILD-STATUS.md), [최신 배포 준비 기록](docs/runtime/evidence/latest-readiness.json), [최신 모델 실행 기록](docs/runtime/evidence/latest-model-execution.json)의 시각·버전·판정을 함께 확인하세요.

## 현재 구현 범위

- 브라우저 음성 입력·답변 읽기, 수정 가능한 질문, 사진 업로드와 카메라 촬영을 지원합니다. 연속 카메라 미리보기는 로컬에서 처리하며, 사용자가 캡처하거나 선택적 자동 관찰이 추출한 정지 프레임만 분석 요청으로 전송합니다. 연속 영상 전체를 전송·저장하거나 영상 기억을 유지하지 않습니다. 모델은 선택한 샘플 사진만 분석합니다. 자동 관찰은 수동 질문을 우선하며 사용자가 중지할 수 있습니다. 음성 미지원·권한 거부 시 텍스트로 진행합니다.
- 수록 범위는 **경복궁·광화문 문화 지점 2개와 토속촌 식당 1곳·메뉴 3개**입니다. 광화문은 경복궁의 정문으로 두 문화 지점은 같은 궁궐 단지의 안내 기준점이며, 서로 독립된 관광지 두 곳으로 세지 않습니다. 사진만으로 장소·위치를 확정하지 않으며 모호한 장소나 음식은 사용자에게 확인합니다.
- GPS 허용, 지도·수록 장소 선택 또는 표시된 서촌 시연 위치를 출발점으로 사용합니다. 선택한 장소는 기기 GPS로 표시하지 않습니다. Leaflet/OpenStreetMap 지도에 500m·1km·2km·3km **직선거리 반경**을 적용합니다. 도보 경로나 전국 검색은 제공하지 않습니다.
- 문화·역사·메뉴 설명에 근거 ID와 출처를 표시합니다. 방문 예절과 운영 정보의 자료 시점을 구분하며, 현재 개방·영업·재고·재료·채식/알레르기 안전은 확인 대상으로 남깁니다.
- 한국어 확인 문장과 HTML·JSON 여행 카드 다운로드를 제공합니다. 서버는 Markdown도 지원합니다. 예약·결제·주문·외부 발송은 수행하지 않습니다.

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
2. **카메라 시작** → 미리보기 확인 → **사진 고정 촬영**, 또는 허용된 사진을 업로드합니다. 자동동행은 기본으로 끄고 수동 경로부터 확인합니다. 캡처만으로 질문이 전송되지는 않습니다.
3. 먼저 사진에 대해 질문하고 불확실한 응답을 확인합니다. 이후 사용자가 알고 있는 장소를 수록 카탈로그에서 명시적으로 선택해 한글 이름·문화 맥락을 질문합니다. 검증된 시연은 광화문을 사용자가 선택한 흐름이며, 모델이 사진에서 장소를 알아냈다고 설명하지 않습니다.
4. 같은 문화 기준점 주변 수록 식당을 질문하고 출처·미확인을 확인한 뒤 HTML·JSON 카드를 내려받습니다. 기본 시연은 여기서 종료합니다. 식당 메뉴 추가 질문은 historical_source_mismatch 실패가 남아 있고, 식사→문화 역방향은 최종 UI 재검증에서 실행하지 않았습니다. 앞선 문화 카드는 후속 질문 전에 따로 저장합니다.
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

2026-10-07 root의 최신 보고는 **157 passed + 62 subtests passed (3.96초)**입니다. 이번 README 정리에서 재실행하지 않았습니다. 최신 desktop/mobile 캡처 회귀 **12건 및 빌드 PASS**를 보고받았습니다. 이전 브라우저 52건·단위 12건과 합산하지 않습니다. 상세 판정은 [빌드 상태](docs/BUILD-STATUS.md)를 따릅니다. 모델 HTTP stub·합성 장치 fixture 기반 검사는 실제 추론이나 문화적 사실성의 증거가 아닙니다. 실제 평가는 요청→도구→응답→다운로드 카드의 일치, 문장별 출처 적합성, 불확실성·실패 처리를 확인합니다. **worker12 기본 UI 재검증은 PASS**이며 아래 범위에 한정합니다.

### 실제 UI 검증 범위 · 15:52–15:53 KST

[기본 흐름 실행 영수증](.runtime/qa-ui-real/2026-10-07T06-52-12-176Z/receipt.json): 3단계 **8.238 / 22.325 / 21.498초**, 실제 HTTPS·broker·모델 결과 및 HTML/JSON 다운로드 확인. JS 오류 0건, desktop 1440px·mobile 390px 레이아웃 넘침 없음. 모바일 검사는 같은 결과의 화면 크기 변경이며 별도 실기기 추론 검사가 아닙니다. 시간은 해당 실행 관측값이지 응답 속도 보장이 아닙니다.

입력은 공개 아카이브 사진이며 현장 촬영이 아닙니다. 첫 응답은 장소 후보 없이 확인을 요청했고 이후 **사용자가 광화문을 카탈로그에서 명시적으로 선택**했습니다. 사진 인식 성공·연속 영상 기억·자동 관찰 성공으로 확대하지 않습니다. 이전 전체 흐름의 4번째 메뉴 질문은 **historical_source_mismatch, 32.608초 후 실패**했으며 기본 흐름 PASS가 이를 해결했다는 뜻은 아닙니다. 역방향은 미검증, Android TTS·자동 관찰 실동작은 사용자 확인 대기입니다. 영수증은 로컬 `.runtime` 근거로 공개 저장소 포함을 보장하지 않습니다.

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
| 브라우저 외부 서비스 | 사용자 동의 카메라·마이크·위치, 브라우저 음성 서비스, OpenStreetMap 타일. worker 정책 밖의 기능이며 사용자 사진을 지도 서비스에 보내는 흐름은 없습니다. |

[통제된 경계 시험 11조건 PASS](docs/runtime/evidence/boundary-combined-verdict.json)는 허용·차단 로그와 수신기 카운트를 결합한 결과입니다. 모든 목적지나 모든 제품 시나리오를 시험했다는 뜻은 아닙니다. 정책을 바꾸면 실효 정책과 실행 근거를 다시 확인합니다.

`.env`·개인키·런타임 파일은 로컬에만 두세요. 샘플의 비밀 값은 비워 두며 토큰·키·원본 사용자 사진을 커밋하거나 로그에 출력하지 않습니다. NVIDIA hosted 키와 self-hosted 인증 키를 혼용하지 않습니다.
