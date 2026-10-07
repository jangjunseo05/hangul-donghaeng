# 한글동행 · Hangul Donghaeng

한국 문화·역사와 한글을 이해하려는 여행자를 위한 음성·카메라 가이드입니다. 촬영한 장면과 질문을 바탕으로 출처가 있는 문화·장소·메뉴 설명, 수록 장소 안내, 직접 말할 수 있는 한국어 확인 문장을 여행 카드로 정리합니다. 영어 기본·한국어 전환을 지원합니다.

**2026-10-07 개발 중입니다.** 기존 음식·식당 흐름은 실제 OpenShell worker와 NVIDIA GPU로 사진 해석·조회·카드 저장을 확인했습니다. 새 문화·카메라 확장의 실제 GPU 왕복은 아직 미검증이며 기존 실행 결과를 그대로 적용하지 않습니다. 검증 기록은 [빌드 상태](docs/BUILD-STATUS.md)와 [OpenShell 실측 근거](docs/runtime/SECURITY-EVIDENCE.md)를 참고하세요.

## 현재 구현 범위

- 브라우저 음성 입력·답변 읽기, 수정 가능한 질문, 사진 업로드와 카메라 촬영을 지원합니다. 연속 카메라 미리보기는 로컬에서 처리하며, 사용자가 캡처하거나 선택적 자동 관찰이 추출한 정지 프레임만 분석 요청으로 전송합니다. 연속 영상 전체를 전송·저장하거나 실시간 영상 전체를 추론하는 기능은 아닙니다. 자동 관찰은 수동 질문을 우선하며 사용자가 중지할 수 있습니다. 음성 미지원·권한 거부 시 텍스트로 진행합니다.
- 수록 범위는 **경복궁·광화문 문화 지점 2개와 토속촌 식당 1곳·메뉴 3개**입니다. 광화문은 경복궁의 정문으로 두 문화 지점은 같은 궁궐 단지의 안내 기준점이며, 서로 독립된 관광지 두 곳으로 세지 않습니다. 사진만으로 장소·위치를 확정하지 않으며 모호한 장소나 음식은 사용자에게 확인합니다.
- GPS 허용, 지도·수록 장소 선택 또는 표시된 서촌 시연 위치를 출발점으로 사용합니다. 선택한 장소는 기기 GPS로 표시하지 않습니다. Leaflet/OpenStreetMap 지도에 500m·1km·2km·3km **직선거리 반경**을 적용합니다. 도보 경로나 전국 검색은 제공하지 않습니다.
- 문화·역사·메뉴 설명에 근거 ID와 출처를 표시합니다. 방문 예절과 운영 정보의 자료 시점을 구분하며, 현재 개방·영업·재고·재료·채식/알레르기 안전은 확인 대상으로 남깁니다.
- 한국어 확인 문장과 HTML·JSON 여행 카드 다운로드를 제공합니다. 서버는 Markdown도 지원합니다. 예약·결제·주문·외부 발송은 수행하지 않습니다.

별도 가상 연습 모드는 공개된 가상 자료로 일정 초안을 만들며 실제 장소·사진·지도와 분리합니다. 개발용 fixture와 모델 stub은 실제 추론 증거가 아닙니다.

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

빌드 후 broker를 다시 시작하면 `web/dist`를 제공합니다. 마이크·위치 권한은 버튼을 누를 때 요청합니다. 음성 인식은 브라우저의 외부 서비스를 사용할 수 있고 지도 타일은 OpenStreetMap에서 받습니다. 시연 PC의 한국어·영어 실제 마이크 입력과 TTS 음성 재생은 사용자 확인 PASS이며, Android 실기기 동작은 아직 미검증입니다.

## 검증

저장소 루트에서 Python 단위·통합·정책 설정 테스트를 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration tests/security/test_policy.py -q
```

`web`에서 웹 테스트를 실행합니다. Playwright는 broker·웹 개발 서버가 실행 중이고 Chrome이 설치된 환경에서 사용합니다.

```powershell
npm test
npx playwright test
```

2026-10-07 통합 담당의 최신 Python 테스트 보고는 **113 passed, 47 subtests passed**입니다. 기존 웹 검증 기록은 단위 테스트 **7개**, 기본 Playwright **10개**, GPS 경합 회귀 **12개**와 빌드 통과입니다. 시연 PC의 한국어·영어 실제 마이크 입력 및 TTS 음성 재생은 사용자 확인 PASS이며 **Android 실기기는 미검증**입니다. 단위·통합 테스트의 모델 응답은 HTTP stub이고 브라우저 테스트도 fixture를 사용하므로, 이 결과가 새 문화·카메라 흐름의 실제 GPU 추론 성공을 증명하지는 않습니다.

## 데이터·실행 경계

브라우저 → 신뢰하는 FastAPI broker → worker → NVIDIA 호환 모델·허용된 근거/문화 지점·식당 검색 도구 순서로 처리합니다. broker는 사진 방향·크기를 정규화하고 EXIF를 제거하며 요청 소유권·근거 ID·장소 좌표를 검사한 뒤 `.runtime/output`에 결과를 저장합니다. worker는 결과 파일을 직접 쓰지 않습니다. 출처 ID 검사만으로 모델 문장의 사실성까지 증명되지는 않습니다.

OpenShell 정책은 worker의 코드·자료 읽기, 임시 공간 쓰기, 지정 broker·모델 호스트 통신으로 제한합니다. [실제 경계 검증](docs/runtime/SECURITY-EVIDENCE.md)에서는 자체 무해한 fixture와 수신기를 사용해 파일 접근 거부, 허용 통신, 금지 예약 POST·비허용 목적지 차단을 실효 정책·런타임 로그·수신기 카운트와 대조했습니다. [결합 판정 11개 조건이 PASS](docs/runtime/evidence/boundary-combined-verdict.json)이며 실제 모델 호출 근거도 보존되어 있습니다. 이는 해당 배포와 시험 조건의 결과로, 새 문화·카메라 흐름의 실제 GPU 검증이나 전체 제품 품질 보증은 아닙니다. gateway 연결·정책 lint·`RUN_CONTEXT=openshell` 표시만으로 검증을 대신하지 않습니다. 브라우저 음성·위치·지도 요청은 worker 샌드박스 밖에서 실행됩니다. [런타임 인계](docs/runtime/README.md), [정책 안내](policy/README.md), [API 계약](shared/api-contract.md)을 참고하세요.

`.env`·개인키·런타임 파일은 로컬에만 두세요. 샘플의 비밀 값은 비워 두며 토큰·키·원본 사용자 사진을 커밋하거나 로그에 출력하지 않습니다. NVIDIA hosted 키와 self-hosted 인증 키를 혼용하지 않습니다.
