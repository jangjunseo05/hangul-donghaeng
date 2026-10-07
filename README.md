# 한글동행 · Hangul Donghaeng

한국 음식과 메뉴를 이해하려는 여행자를 위한 음성·사진 가이드입니다. 사진 한 장과 질문으로 출처가 있는 메뉴·문화 설명, 주변 수록 식당, 직접 말할 수 있는 한국어 확인 문장을 여행 카드로 정리합니다. 영어 기본·한국어 전환을 지원합니다.

**2026-10-07 개발 중입니다.** UI·API·에이전트 코드와 자동 테스트는 구현했으며, 실제 NVIDIA 모델과 OpenShell을 연결한 제품 전체 실행은 아직 검증 전입니다. 최신 결과는 [빌드 상태](docs/BUILD-STATUS.md)에 기록합니다.

## 첫 구현 범위

- 브라우저 음성 입력·답변 읽기, 수정 가능한 질문, 사진 한 장 업로드. 음성 미지원·권한 거부 시 텍스트로 진행합니다.
- 출처를 정리한 **식당 1곳·메뉴 3개**만 검색합니다. 사진만으로 식당이나 위치를 확정하지 않으며 모호한 음식은 사용자에게 확인합니다.
- GPS 허용, 지도 선택 또는 표시된 서촌 시연 위치를 출발점으로 사용합니다. Leaflet/OpenStreetMap 지도에 500m·1km·2km·3km **직선거리 반경**을 적용합니다. 도보 경로나 전국 검색은 제공하지 않습니다.
- 메뉴·문화 설명에 근거 ID와 출처를 표시합니다. 재료·영업·재고·채식/알레르기 안전은 확인 대상으로 남깁니다.
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

빌드 후 broker를 다시 시작하면 `web/dist`를 제공합니다. 마이크·위치 권한은 버튼을 누를 때 요청합니다. 음성 인식은 브라우저의 외부 서비스를 사용할 수 있고 지도 타일은 OpenStreetMap에서 받습니다. 실제 마이크·스피커 동작은 별도 검증이 필요합니다.

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

문서 갱신 시 Python **42개 + 하위 테스트 29개**, 웹 단위 테스트 **7개** 통과를 확인했습니다. 웹 담당의 최종 빌드와 Playwright **10개 실행이 통과**했습니다. 통합 테스트의 모델 응답은 HTTP stub이므로 실제 NVIDIA 추론·품질·지연이나 OpenShell 격리를 증명하지 않습니다.

## 데이터·실행 경계

브라우저 → 신뢰하는 FastAPI broker → worker → NVIDIA 호환 모델·허용된 근거/식당 도구 순서로 처리합니다. broker는 사진 방향·크기를 정규화하고 EXIF를 제거하며 요청 소유권·근거 ID·장소 좌표를 검사한 뒤 `.runtime/output`에 결과를 저장합니다. worker는 결과 파일을 직접 쓰지 않습니다. 출처 ID 검사만으로 모델 문장의 사실성까지 증명되지는 않습니다.

OpenShell 정책은 worker의 코드·자료 읽기, 임시 공간 쓰기, 지정 broker·모델 호스트 통신으로 제한하도록 구성했습니다. provider 규칙을 포함한 실효 정책과 실제 허용·차단 로그 검증이 남아 있습니다. gateway 연결·정책 lint·`RUN_CONTEXT=openshell` 표시는 제품 샌드박스 검증을 대신하지 않습니다. 브라우저 음성·위치·지도 요청은 worker 샌드박스 밖에서 실행됩니다. 자세한 경계는 [policy/README.md](policy/README.md), API는 [shared/api-contract.md](shared/api-contract.md)를 참고하세요.

`.env`·개인키·런타임 파일은 로컬에만 두세요. 샘플의 비밀 값은 비워 두며 토큰·키·원본 사용자 사진을 커밋하거나 로그에 출력하지 않습니다. NVIDIA hosted 키와 self-hosted 인증 키를 혼용하지 않습니다.
