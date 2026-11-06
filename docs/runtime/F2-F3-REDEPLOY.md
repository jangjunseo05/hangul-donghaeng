# 인계: F2 자료 판단 · F3 차단 시연 배포 절차 (L40S · OpenShell)

> **배포 대상 커밋: `________` (최종 push 뒤 오케스트레이터가 채움)**
> 이 문서의 명령은 작성자가 **한 번도 실행하지 않았다(실배포 미적용).** 로컬에서는 단위 테스트와 판정 로직만 확인했다. 맨 아래 "검증 범위"를 참고한다.
> 대상 독자: 이 저장소를 처음 보는 운영 팀원(2026-10-07 root 운영자). 위에서부터 순서대로 따라 하면 된다.

## 0. 한눈에 보기

이번 배포가 바꾸는 것은 세 곳이다. **세 곳 모두 갱신해야** 웹의 "자료 판단(F2)"과 "차단 시연(F3)"이 동작한다.

| # | 갱신 지점 | 이유 | 절 |
|---|---|---|---|
| A | **worker 이미지 재빌드** | 새 코드(`agent/review.py`, `agent/probe.py`, `agent/worker.py`)와 데모 자료(`data/review-demo/`)가 이미지에 들어가야 한다 | 3 |
| B | **정책 재생성·적용** | worker가 결과를 보낼 경로 `POST /worker/review-results`, `POST /worker/probe-results`가 정책에 새로 추가됐다. 적용 전에는 OpenShell이 이 요청을 거부해 F2·F3가 실패한다 | 3 (A와 같은 명령) |
| C | **broker 호스트: `git pull` → `web` 빌드 → broker 재시작** | 새 API 엔드포인트와 새 화면 | 4 |

- A와 B는 `infra/deploy_worker.py` 한 번 실행으로 함께 처리된다. 이 스크립트는 이미지를 빌드하고 새 정책으로 새 worker를 띄운다.
- `/worker/canary`는 **일부러 정책에 넣지 않았다.** F3는 이 경로가 거부되는지 시험한다.
- 기존 기능(카메라 → 장소 설명 → 주변 음식점)의 API 형식은 바뀌지 않았다.

용어:
- **broker**: `service/` FastAPI. 브라우저와 worker 사이에서 검증·저장을 맡는다. 포트는 8000이다.
- **worker**: OpenShell 샌드박스 안에서 도는 `agent.worker`. 이름은 `hangul-worker-NN`이다.

## 1. 준비 (읽기만 함, 2분)

L40S 호스트의 WSL/Linux 셸에서 실행한다.

```bash
cd ~/hangul-donghaeng                      # 제품 저장소 경로. 실제 경로는 운영자 환경에 맞춘다.
export VENV_PY="$HOME/.venvs/hangul-broker/bin/python"
"$VENV_PY" -c "import dotenv, fastapi; print('venv-ok')"
# 기대 출력: venv-ok

docker ps --format '{{.Names}}' | grep openshell-default--hangul-worker-
# 기대 출력: openshell-default--hangul-worker-NN-…  (정확히 1줄)

export OLD=hangul-worker-NN                # 위에서 확인한 현재 worker. ★롤백에 필요하니 꼭 기록해 둔다.
export NEW=hangul-worker-$(printf %02d $((10#${OLD: -2} + 1)))   # deploy_worker.py는 반드시 OLD+1을 요구한다
docker ps -a --format '{{.Names}}' | grep -c "openshell-default--$NEW-"
# 기대 출력: 0  (이미 써 본 번호는 다시 쓰지 않는다)

export PREV_COMMIT=$(git rev-parse HEAD)   # 지금 배포돼 있는 코드. ★롤백용으로 기록한다.
curl -s http://127.0.0.1:8000/api/health
# 기대 출력: "status":"ok" … "worker_connected":true
curl -s http://127.0.0.1:8001/v1/models | grep -o 'NVIDIA-Nemotron-Nano-12B-v2-VL-BF16'
# 기대 출력: NVIDIA-Nemotron-Nano-12B-v2-VL-BF16
```

- QA·시연 요청을 멈추고, 진행 중인 요청이 없는지 확인한다. 아래 `--qa-idle`은 "확인했다"는 운영자의 증언이다.
- broker와 모델 SSH 터널(`infra/open_model_tunnel.sh`)은 3절까지 건드리지 않는다.

## 2. 코드 받기와 현재 정책 백업 (3분)

```bash
git fetch origin && git status
# 기대 출력: working tree clean
git checkout main && git pull --ff-only
git log --oneline -1
# 기대 출력: 맨 위 "배포 대상 커밋"과 같은 해시

export STAMP=$(date -u +%Y%m%dT%H%M%SZ)
export REF="docs/runtime/evidence/${OLD#hangul-}-effective-policy-predeploy-$STAMP.json"
openshell policy get "$OLD" --full -o json > "$REF"
"$VENV_PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['status'],d['sandbox'],d['hash'])" "$REF"
# 기대 출력: effective hangul-worker-NN <64자리 해시>
```

`$REF`는 현재 worker의 실효 정책이다. 다음 두 용도로 쓴다.
- 새 정책이 "이것 + 추가 경로"와 정확히 같은지 비교하는 기준
- 롤백할 때 되돌아갈 기준

새 정책을 미리 보려면 다음을 실행한다. 생성만 하고 적용하지 않는다.

```bash
"$VENV_PY" infra/render_policy.py --server-url http://host.openshell.internal:8000 \
  --model-url http://host.openshell.internal:8001/v1 --out /tmp/policy-preview
grep -o '"path": "/worker/[a-z/*-]*"' /tmp/policy-preview/*.json | sort -u
# 기대 출력: … jobs/next, photos/*, search, results, fail, progress, wiki, review-results, probe-results
#            (canary는 없어야 한다)
```

## 3. [A+B] worker 이미지 재빌드와 새 정책 적용 (5~8분)

```bash
export CORE_SHA=$(sha256sum agent/core.py | cut -d' ' -f1)
export CONTRACT_SHA=$(sha256sum shared/api-contract.md | cut -d' ' -f1)
"$VENV_PY" infra/deploy_worker.py --from-worker "$OLD" --to-worker "$NEW" \
  --reference-policy "$REF" --allow-added-worker-routes \
  --core-sha "$CORE_SHA" --contract-sha "$CONTRACT_SHA" --qa-idle
```

이 명령은 다음을 순서대로 수행한다.
1. 보안 단위 테스트
2. 이미지 빌드(`hangul-worker:${NEW#hangul-}-<core sha 12자>`)
3. 이미지 안의 코드·의존성 대조
4. 기존 worker 정지
5. 새 worker 실행
6. polling·정책 적용 확인

`--allow-added-worker-routes`의 동작:
- 새 정책이 "`$REF` + 허용된 경로 추가"와 정확히 같은지 확인한다. 규칙 순서는 무시한다.
- 추가해도 되는 경로는 progress, wiki, review-results, probe-results 네 개로 고정돼 있다. 그 밖의 경로, 와일드카드, canary는 BLOCKED로 끝난다.

**기대 출력** (마지막 줄 JSON):
- `"stage": "READY_FOR_REVIEW"`, `"worker": "$NEW"`
- `"added_worker_routes": [...]`: `$REF`에 없던 경로만 들어 있다. 기준이 worker-12와 같다면 `POST /worker/progress`, `POST /worker/wiki`, `POST /worker/review-results`, `POST /worker/probe-results`이다.
- `"same_validated_allowlist": false`: 경로를 추가했으므로 기준 정책과 완전히 같지는 않다는 뜻이다. 정상이다.

영수증은 `infra/evidence-local/$NEW-<시각>/receipt.json`에 저장된다(git에서 제외되는 로컬 폴더).

**BLOCKED일 때** (`"result": "BLOCKED"`, 상세는 `failure.json`): 스크립트는 자동으로 재시작하지 않는다. `stage` 값에 따라 대응한다.

| `stage` | 상태 | 할 일 |
|---|---|---|
| `preflight`, `build` | 기존 worker가 그대로 동작 중 | 원인(`reason`)을 해결한 뒤 같은 NEW로 재시도해도 된다. 단, `infra/generated/$NEW`가 이미 있으면 번호를 하나 올린다 |
| `stop_old`, `launch_new`, `readiness` | 기존 worker가 멈췄을 수 있음 | **6절 롤백** |

## 4. [C] broker 호스트 갱신: git pull → web 빌드 → broker 재시작 (5분)

broker를 다시 시작하면 메모리의 세션·작업이 사라진다. 시연용 카드가 필요하면 먼저 내려받는다.

```bash
cd ~/hangul-donghaeng                       # broker가 도는 저장소 (worker와 같은 호스트라면 이미 최신)
git pull --ff-only && git log --oneline -1
# 기대 출력: 배포 대상 커밋
"$VENV_PY" -m pip install -r requirements.txt -q   # 새 의존성은 없지만 확인 차원에서 실행
cd web && npm ci && npm run build && cd ..
# 기대 출력: "✓ built in …"  →  web/dist가 갱신된다 (broker가 이 폴더를 서빙한다)
```

broker 재시작은 운영 중인 방식 그대로 한다.
- **Windows에서 관리하는 경우:** `.\infra\local-demo.ps1 -Action Stop -Component Broker -Distro <배포판> -RootGo`를 실행한 다음 `.\infra\local-demo.ps1 -Action Start -Component Broker -Distro <배포판> -RootGo`를 실행한다.
- **WSL 셸에서 직접 띄운 경우:** 기존 `python -m service` 프로세스를 멈추고 `"$VENV_PY" -m service`로 다시 띄운다.
- 어느 경우든 Windows와 WSL에서 broker를 **동시에** 실행하지 않는다.

```bash
curl -s http://127.0.0.1:8000/api/health | "$VENV_PY" -m json.tool
# 기대 출력: "worker_connected": true, "sandbox_evidence": {…}
curl -s -c /tmp/c -X POST http://127.0.0.1:8000/api/sessions -H 'content-type: application/json' -d '{}' >/dev/null
curl -s -b /tmp/c http://127.0.0.1:8000/api/reviews/inputs | grep -o '"path":"[^"]*"'
# 기대 출력: 데모 파일 5개 (01-haeon-palace-notice-2026.md … 05-visitor-forum-post.txt)
```

## 5. 동작 확인 (웹에서, 5분)

브라우저로 broker 주소(또는 운영 중인 HTTPS 주소)를 연다.

**F3 차단 시연**: "차단 시연" 화면에서 실행한다. 기대 결과:

| 시도 | 결과 | 상세 | broker 수신 |
|---|---|---|---|
| 허용 목록 밖 읽기 (`read_outside_allowlist`) | denied | EACCES 또는 EPERM | – |
| 코드 폴더 쓰기 (`write_code_dir`) | denied | EACCES·EPERM·EROFS | – |
| 미허용 외부 접속 (`egress_unlisted_host`) | denied | ConnectError | – |
| broker 미허용 경로 (`broker_unlisted_path`) | denied | 403 | **0** |

- 화면 판정이 "OpenShell이 차단함"이어야 한다.
- 하나라도 allowed이면 정책이 적용되지 않은 것이다. "근거 불일치"가 나오면 broker 수신이 1 이상이라는 뜻이다. 두 경우 모두 시연에 쓰지 말고 6절로 간다.
- 읽기 시도가 `error`(ENOENT)로 나오면 이미지에 `/home`이 없는 것이다. `export PROBE_READ_PATH=/root`처럼 실제로 존재하고 허용 목록 밖인 경로를 정한 뒤, 1~3절을 OLD=$NEW로 다시 실행한다. 이 값은 worker를 만들 때만 전달된다(`infra/launch_worker.py`).

**F2 자료 판단**: "자료 판단" 화면에서 예시 질문(예: "해온궁 휴궁일과 관람시간은?")을 실행한다. 기대 결과:
- `05-visitor-forum-post.txt`는 "지시문 포함(untrusted_instruction)"으로 제외된다.
- `04-seaside-food-list.md`는 "무관(irrelevant)"으로 제외된다.
- 2019 블로그는 outdated, 충돌 또는 사용 중 하나로 처리된다. 모델 판단이라 실행마다 다를 수 있다.
- "broker 검증 입력" 표시가 있다(`verified_input: true`).
- 실패하면 진행 표시줄의 `grounding_check` 단계에 오류 코드가 남는다.

## 6. 실패 시 되돌리기 (10분)

원칙:
- 이전 worker의 **이름(`$OLD`)과 정책(`$REF`), 커밋(`$PREV_COMMIT`)을 기준으로** 되돌린다.
- 새 worker는 항상 새 번호로 만든다. 같은 이름 재사용과 `openshell sandbox start`처럼 이 저장소에서 써 보지 않은 명령은 쓰지 않는다.
- `deploy_worker.py`는 기준과 다른 worker에서 출발하는 교체를 막는다. 그래서 그 스크립트가 내부에서 쓰는 명령을 같은 환경 변수로 직접 실행한다.

```bash
# 6-1. 기준 정책을 저장소 밖에 복사해 둔 뒤, 커밋하지 않은 근거 파일을 보관한다 (checkout이 거부되지 않도록)
cp "$REF" /tmp/ref-policy.json
git stash push -u -m "redeploy-evidence-$STAMP" -- docs/runtime/evidence || true

# 6-2. 이전 이미지 찾기: 태그 형식은 hangul-worker:worker-NN-<core sha 12자>
docker images hangul-worker --format '{{.Repository}}:{{.Tag}}  {{.ID}}' | grep "${OLD#hangul-}-"
export PREV_IMAGE=hangul-worker:${OLD#hangul-}-<위 출력의 12자>

# 6-3. 새 worker 정지 → 소비자 0개 확인
openshell sandbox stop "$NEW"
docker ps --format '{{.Names}}' | grep -c openshell-default--hangul-worker-
# 기대 출력: 0

# 6-4. 이전 커밋 상태에서(이전 정책 생성기로) 이전 이미지를 새 번호로 실행
git checkout "$PREV_COMMIT"
export BACK=hangul-worker-$(printf %02d $((10#${NEW: -2} + 1)))
GUIDE_SERVER_URL=http://host.openshell.internal:8000 \
NVIDIA_BASE_URL=http://host.openshell.internal:8001/v1 \
NVIDIA_MODEL=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16 \
  "$VENV_PY" infra/launch_worker.py --name "$BACK" --image "$PREV_IMAGE" --env-file .env

# 6-5. 확인
openshell policy get "$BACK" --full -o json > /tmp/back-policy.json
"$VENV_PY" -c "import json,sys; r,b=(json.load(open(p)) for p in sys.argv[1:3]); o,n=sys.argv[3][-2:],sys.argv[4][-2:]; e=json.loads(json.dumps(r['policy']).replace('_'+o+'_','_'+n+'_')); print('matches previous policy:', b['status']=='effective' and b['policy']==e)" /tmp/ref-policy.json /tmp/back-policy.json "$OLD" "$BACK"
# 기대 출력: matches previous policy: True
sleep 20; openshell logs "$BACK" -n 300 | grep -c "ALLOWED GET http://host.openshell.internal:8000/worker/jobs/next"
# 기대 출력: 2 이상
curl -s http://127.0.0.1:8000/api/health | grep -o '"worker_connected":[a-z]*'
# 기대 출력: "worker_connected":true

# 6-6. 원래 브랜치로 복귀, 보관한 근거 복원
git checkout main && git stash pop || true
```

- broker와 web(4절)은 되돌리지 않아도 된다. 기존 기능의 API는 그대로이고, 이전 worker는 F2·F3 작업을 `invalid_job_or_result`로 실패 처리할 뿐이다. 시연에서 F2·F3 화면만 쓰지 않으면 된다.
- **가장 가벼운 대안:** 5절에서 F3만 실패했다면 새 worker를 그대로 두고 차단 시연만 시연에서 뺀다.

## 7. 새 근거 저장과 커밋 (5분)

배포가 성공한 뒤 저장한다. 기존 근거 파일은 덮어쓰지 않는다. `latest-*` 두 파일만 의도적으로 교체하고, 이전 내용은 git 이력에 남긴다.

```bash
E=docs/runtime/evidence
openshell policy get "$NEW" --full -o json > "$E/${NEW#hangul-}-effective-policy.json"
cp "$E/${NEW#hangul-}-effective-policy.json" "$E/latest-effective-policy.json"
openshell logs "$NEW" -n 300 | grep "CONFIG:LOADED"      # 새 정책 해시의 ACK 줄 (아래에 붙여 넣는다)
```

`$E/latest-readiness.json`은 기존 형식을 유지한 채 값만 바꾼다. 값은 `infra/evidence-local/$NEW-*/receipt.json`에서 가져온다.

| 필드 | 넣을 값 |
|---|---|
| `worker` | `$NEW` |
| `core_sha256` | receipt의 `core_sha256` |
| `contract_sha256` | receipt의 `contract_sha256` |
| `image_id` | receipt의 `image_id` |
| `effective_policy_hash` | receipt의 `policy_hash` |
| `effective_policy_file_sha256` | `sha256sum $E/latest-effective-policy.json`의 앞부분 |
| `captured_at` | 현재 UTC 시각 |
| `runtime_policy_ack` | 위에서 grep한 ACK 줄(배열) |
| `same_validated_allowlist` | `false` |
| `deployment_receipt_sha256` | `sha256sum infra/evidence-local/$NEW-*/receipt.json`의 앞부분 |

5절 시연 결과도 저장한다. 브라우저 개발자 도구의 Network 탭에서 `GET /api/sandbox-probe/<id>`와 `GET /api/reviews/<id>` 응답을 각각 저장한다.
- `$E/f3-probe-$STAMP.json`
- `$E/f2-review-$STAMP.json`

```bash
git add "$E/${NEW#hangul-}-effective-policy.json" "$E/latest-effective-policy.json" "$E/latest-readiness.json" \
        "$REF" "$E/f3-probe-$STAMP.json" "$E/f2-review-$STAMP.json"
git commit -m "Record $NEW deployment evidence (F2/F3 routes, probe and review runs)"
git push   # 팀 규칙대로 push 전 확인을 받는다
```

커밋한 뒤 broker를 한 번 더 재시작하면 `/api/health`의 `sandbox_evidence`와 화면 상단 OpenShell 배지가 새 worker 기준으로 표시된다. 경계 시험(11조건, probe `hangul-matrix-01`)은 이번에 다시 실행하지 않았으므로 화면에도 예전 결과로 표시된다.

## 8. (선택) 행사 입력 `/hackathon/input`을 F2에 쓰려면

이 절은 기본 배포 범위 밖이며 별도 확인이 필요하다.
1. 운영자가 `/hackathon/input`을 worker에 **읽기 전용**으로 마운트하고 정책의 `read_only`에 추가해야 한다. 이는 파일 권한 변경이라 3절의 `--allow-added-worker-routes` 검사를 통과하지 못한다. 기준 정책을 새로 만들고 사용자 확인을 다시 받아야 한다.
2. worker를 만들 때 `REVIEW_INPUT_DIR=/hackathon/input`, `REVIEW_INPUT_LABEL=hackathon-input`을 설정한다. broker에는 `REVIEW_ALLOW_EXTERNAL_INPUT=true`를 설정한다. 설정이 없으면 broker가 결과를 거부한다.
3. broker는 이 파일을 볼 수 없다. 그래서 인용이 worker가 보낸 발췌 안에 있는지만 검사한다. 화면에는 "broker 미검증 입력"으로 표시된다.
4. `restricted`·`secrets` 경로는 읽지 않는다(`agent/challenge.py`의 `FORBIDDEN`). 공식 산출물(`/hackathon/output`)은 기존 CLI(`infra/launch_challenge.py`)로 만든다.

## 검증 범위 (작성자 기준, 2026-11-06)

**로컬에서 확인한 것**
- `tests/unit/test_review_probe.py` (21건, 오프라인 모델 stub, in-process broker)
  - 데모 판정
  - broker가 다음을 거부하는지:
    - 위조 인용, 두 발췌에 걸친 인용, 변조 해시
    - 지시문 자료를 used로 표시한 결과
    - 무관 판정·날짜 위조
    - 데모 파일명을 쓰는 외부 입력
    - 미허용 외부 입력
  - worker가 `verified_input`이나 `broker_received`를 스스로 설정할 수 없는지
  - Markdown 줄바꿈 주입이 막히는지
  - 세션당 작업 보존 상한이 지켜지는지
  - 인증 없이 들어온 canary 요청도 집계되는지
  - 로컬 probe가 allowed로 정직하게 보고되는지
  - 오프라인 egress가 denied로 표시되지 않는지
  - 403만 denied로 인정되는지
- `tests/security/test_deploy_routes.py` (6건)
  - 실제 배포 판정 함수 `added_routes_check`를 그대로 시험한다.
  - 선언된 경로만 추가되는지, 규칙 순서가 달라도 통과하는지 확인한다.
  - 다음은 각각 거부되는지 확인한다: 다른 엔드포인트 규칙 추가, 쓰기 권한 확대, canary, 와일드카드, 목록에 없는 경로.

**확인하지 못한 것**
- 실제 Nemotron 응답 품질
- OpenShell의 실제 차단
- 이미지 빌드
- `deploy_worker.py`·`launch_worker.py` 실행
- 6절 롤백
- broker 재시작
- `openshell` CLI의 출력 형식: 이 저장소의 기존 스크립트 사용례에만 근거한다.
