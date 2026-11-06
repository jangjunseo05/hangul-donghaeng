# 인계: F2 자료 판단 · F3 차단 시연 배포 절차 (OpenShell worker · broker)

> **배포 대상 커밋: `27dbf57`** (F2·F3 백엔드 `cc6f926` + web U1~U6·F2·F3 `3d7655f`·`77fcda7`·`27dbf57`). 이 문서를 고친 커밋이 그 뒤에 올 수 있는데, 문서 외에는 바뀌지 않는다.
> 작성자는 이 문서의 명령을 **한 번도 실행하지 않았다(실배포 미적용).** 로컬에서는 단위 테스트와 판정 로직만 확인했다(맨 아래 "검증 범위").
> 대상 독자: 이 저장소를 처음 보는 운영 팀원. 위에서부터 순서대로 따라 한다. **기대 출력과 다르면 그 자리에서 멈추고 root에 보고한다.** 프로세스 강제 종료나 이름 재사용 같은 임의 복구는 하지 않는다.
> AGENTS.md 규칙에 따라 커밋·push는 root만 한다.

## 0. 구성과 이번 변경

**어디서 실행하나.** 모든 명령은 broker·Docker·OpenShell이 설치된 **Windows PC의 WSL 배포판(Ubuntu 22.04)** 에서 실행한다. 단, 4절의 `local-demo.ps1`만 Windows PowerShell에서 실행한다. **L40S GPU 서버에는 접속하지 않는다.** 모델은 WSL의 SSH 터널로만 쓴다.

```
브라우저 → WSL broker(FastAPI :8000, 0.0.0.0) → OpenShell worker(docker) → WSL SSH 터널 127.0.0.1:8001 → L40S vLLM
```

이번 배포에서 갱신할 곳은 세 군데다. 세 곳을 모두 갱신해야 웹의 "자료 판단(F2)"과 "차단 시연(F3)"이 동작한다.

| # | 갱신 지점 | 이유 | 절 |
|---|---|---|---|
| A | worker 이미지 재빌드 | 새 코드(`agent/review.py`, `agent/probe.py`, `agent/worker.py`)와 데모 자료(`data/review-demo/`)가 이미지에 들어가야 한다 | 3 |
| B | 정책 재생성·적용 | worker가 결과를 보낼 `POST /worker/review-results`, `/worker/probe-results` 경로를 정책에 추가했다. 적용 전에는 OpenShell이 이 요청을 거부한다 | 3 (A와 한 번에 처리) |
| C | broker 쪽 `git pull` → `web` 빌드 → broker 재시작 | 새 API와 새 화면 | 2, 4 |

- `/worker/canary`는 **일부러 정책에 넣지 않았다.** F3는 이 경로가 거부되는지 시험한다.
- 기존 기능(카메라 → 장소 설명 → 주변 음식점)의 API 형식은 바뀌지 않았다.

## 1. 준비 (읽기만 함, 5분)

**1-1. WSL 배포판 확인.** Windows PowerShell에서 실행한다.

```powershell
wsl -l -v                                   # broker를 돌리는 배포판 이름(예: Ubuntu-22.04) 확인
# 1-2에서 찾을 checkout의 Windows 경로(예: C:\Users\<user>\…\hangul-donghaeng)에서 실행한다.
# ps1은 자기 checkout 기준으로 소유 여부를 판단한다. checkout이 WSL 내부(ext4)에 있으면 owned_running은 항상 false다.
.\infra\local-demo.ps1 -Action Status -Distro <배포판>
# 기대 출력: broker 항목의 "port_listening": true
#   "owned_running": true  → ps1이 띄운 broker (4절에서 ps1로 재시작)
#   "owned_running": false → 다른 방식으로 띄운 broker (4절 참조)
```

**1-2. broker가 도는 checkout으로 이동.** 이후 명령은 모두 WSL 셸에서 실행한다. deploy·pull·build는 **반드시 broker가 도는 바로 그 checkout에서** 한다. 다른 clone에서 하면 broker는 옛 코드를 계속 서비스하고, 배포는 다른 `.env`를 읽는다.

```bash
PID=$(ss -ltnp 'sport = :8000' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
D=$([ -n "$PID" ] && readlink "/proc/$PID/cwd")
[ -f "$D/service/__main__.py" ] && cd "$D" && pwd || echo "STOP: broker checkout 확인 실패 (다른 사용자로 실행 중일 수 있음) → root 보고"
# 기대 출력: 저장소 경로 (예: /mnt/c/Users/<user>/…/hangul-donghaeng). STOP이 나오면 멈추고 보고한다.
git status --short
# 기대 출력: 빈 출력. 무엇이든 나오면 stash·reset하지 말고 root에 보고한다.
# (5절의 재시도로 다시 왔다면 docs/runtime/evidence/…-predeploy-….json 한 줄만 있는 것은 정상이다.)
```

**1-3. 변수 정하기와 저장.** 비밀값은 넣지 않는다. 새 터미널이나 다른 절에서는 `. ~/redeploy-vars.sh`로 다시 불러온다.

```bash
export REPO=$(pwd)
export VENV_PY="$HOME/.venvs/hangul-broker/bin/python"
"$VENV_PY" -c "import dotenv, fastapi; print('venv-ok')"            # 기대 출력: venv-ok
export OLD=$(docker ps --format '{{.Names}}' | grep -v -- '-supervisor$' \
  | sed -nE 's/^openshell-default--(hangul-worker-[0-9]{2})-.*/\1/p')
echo "$OLD"                                  # 기대 출력: hangul-worker-NN 한 줄. 0줄이거나 2줄 이상이면 멈추고 보고한다.
export NEW=hangul-worker-$(printf %02d $((10#${OLD: -2} + 1)))      # deploy_worker.py는 반드시 OLD+1을 요구한다
docker ps -a --format '{{.Names}}' | grep -v -- '-supervisor$' | grep -c "openshell-default--$NEW-"
# 기대 출력: 0. 1 이상이면 이미 시도한 번호이므로 멈추고 보고한다.
export OLD_IMAGE=$(docker inspect --format '{{.Config.Image}}' \
  "$(docker ps --format '{{.Names}}' | grep -v -- '-supervisor$' | grep "openshell-default--$OLD-")")
echo "$OLD_IMAGE"                            # 기대 출력: hangul-worker:worker-NN-xxxxxxxxxxxx (롤백에 쓴다)
export PREV_COMMIT=$(git rev-parse HEAD)     # 현재 배포돼 있는 코드 (롤백용)
export STAMP=$(date -u +%Y%m%dT%H%M%SZ)
declare -p REPO VENV_PY OLD NEW OLD_IMAGE PREV_COMMIT STAMP > ~/redeploy-vars.sh
```

**1-4. broker와 모델 터널 확인.**

```bash
curl -s http://127.0.0.1:8000/api/health
# 기대 출력: "status":"ok" … "worker_connected":true
curl -s http://127.0.0.1:8001/v1/models | grep -o 'NVIDIA-Nemotron-Nano-12B-v2-VL-BF16'
# 기대 출력: NVIDIA-Nemotron-Nano-12B-v2-VL-BF16
```

- 모델 확인에서 출력이 없으면 **멈춘다.** 터널은 root가 개인 환경 변수 `GPU_SSH_ALIAS`(SSH 설정의 별칭이며 문서·커밋에 쓰지 않는다)로만 연다(`infra/open_model_tunnel.sh`). 기존 listener가 있으면 새 터널을 띄우지 않는다(README "중복 터널 금지").
- QA·시연 요청을 멈추고 진행 중인 요청이 없는지 확인한다. 3절의 `--qa-idle`은 이 확인을 했다는 운영자의 증언이다.

## 2. 코드 받기와 현재 정책 백업 (3분)

```bash
. ~/redeploy-vars.sh && cd "$REPO"
git fetch origin && git checkout main && git pull --ff-only
git merge-base --is-ancestor 27dbf57 HEAD && echo target-ok      # 기대 출력: target-ok
git diff --stat 27dbf57 HEAD -- . ':!docs'                         # 기대 출력: 빈 출력 (그 뒤 커밋은 문서뿐)
export REF="docs/runtime/evidence/${OLD#hangul-}-effective-policy-predeploy-$STAMP.json"
openshell policy get "$OLD" --full -o json > "$REF"
"$VENV_PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['status'],d['sandbox'],d['hash'])" "$REF"
# 기대 출력: effective hangul-worker-NN <64자리 해시>
cp "$REF" ~/redeploy-ref-policy.json        # 롤백 때 쓸 사본 (저장소 밖)
echo "export REF=$REF" >> ~/redeploy-vars.sh
```

새 정책을 미리 보려면(선택) 다음을 실행한다. 생성만 하고 적용하지 않는다.

```bash
"$VENV_PY" infra/render_policy.py --server-url http://host.openshell.internal:8000 \
  --model-url http://host.openshell.internal:8001/v1 --out /tmp/policy-preview
grep -o '"path": "/worker/[a-z/*-]*"' /tmp/policy-preview/*.json | sort -u
```

기대 출력: `jobs/next`, `photos/*`, `search`, `results`, `fail`, `progress`, `wiki`, `review-results`, `probe-results`.
- `/worker/**` 한 줄도 함께 보이는데, 이는 provider endpoint 범위 표기라 허용 규칙이 아니다.
- `canary`는 없어야 한다.

## 3. [A+B] worker 이미지 재빌드와 새 정책 적용 (5~8분)

```bash
. ~/redeploy-vars.sh && cd "$REPO"
"$VENV_PY" infra/deploy_worker.py --from-worker "$OLD" --to-worker "$NEW" \
  --reference-policy "$REF" --allow-added-worker-routes \
  --core-sha "$(sha256sum agent/core.py | cut -d' ' -f1)" \
  --contract-sha "$(sha256sum shared/api-contract.md | cut -d' ' -f1)" --qa-idle
```

스크립트는 다음 순서로 동작한다.
1. 보안 단위 테스트
2. 이미지 빌드(`hangul-worker:${NEW#hangul-}-<core sha 12자>`)
3. 이미지 안의 코드·의존성 대조
4. 기존 worker 정지
5. 새 worker 실행
6. polling·정책 ACK 확인

`--allow-added-worker-routes`는 새 정책이 "`$REF` + 허용된 경로 추가"와 정확히 같은지 확인한다. 추가할 수 있는 경로는 progress, wiki, review-results, probe-results 네 개로 고정돼 있다. 그 밖의 경로, 와일드카드, canary가 들어 있으면 BLOCKED로 끝난다.

**기대 출력** (마지막 줄 JSON):
- `"stage": "READY_FOR_REVIEW"`, `"worker": "<NEW>"`
- `"added_worker_routes"`: `$REF`에 없던 경로만 들어 있다. 현재 worker가 progress·wiki가 이미 들어간 코드로 배포돼 있다면 `POST /worker/review-results`, `POST /worker/probe-results` 두 개가 나온다. worker-12 수준의 정책이라면 progress·wiki까지 네 개가 나온다.
- `"same_validated_allowlist": false`: 경로를 추가했으므로 정상이다.

영수증은 `infra/evidence-local/$NEW-<시각>/`의 `receipt.json`과 `runtime.log`에 남는다(`infra/.gitignore`로 git에서 제외됨). **성공했든 실패했든** 바로 이 폴더를 `$EVID`로 저장한다(7절에서 쓴다).

```bash
D=$(ls -d infra/evidence-local/$NEW-* 2>/dev/null | tail -1); [ -n "$D" ] && echo "export EVID=$D" >> ~/redeploy-vars.sh
echo "${D:-증거 폴더 없음: 인자 검사 단계에서 실패했으므로 배포된 것이 없다 → reason을 root에 보고}"
```

**BLOCKED일 때** (`"result": "BLOCKED"`, 상세는 같은 폴더의 `failure.json`): 스크립트는 자동 재시작을 하지 않는다. 먼저 상태를 확인한다.

```bash
. ~/redeploy-vars.sh && cd "$REPO"
cat "$EVID/failure.json"                     # stage, old_stopped, new_launched, reason 확인
docker ps --format '{{.Names}}' | grep -v -- '-supervisor$' | grep openshell-default--hangul-worker-
```

| 상태 | 판단 | 할 일 |
|---|---|---|
| `old_stopped: false`이고 위 목록에 `$OLD`가 보임 | 기존 worker가 그대로 동작 중 | 롤백하지 않는다. `/api/health`의 `worker_connected:true`만 확인하고 `reason`을 root에 보고한다. **같은 NEW로 재시도하지 않는다.** |
| `old_stopped: true` | 기존 worker가 멈춤 | 6절 롤백 |

## 4. [C] web 빌드와 broker 재시작 (5분)

broker를 재시작하면 메모리의 세션·작업이 사라진다. 시연용 카드가 필요하면 먼저 내려받는다.

```bash
. ~/redeploy-vars.sh && cd "$REPO"           # 2절에서 이미 최신 코드를 받았다
cp -a web/dist "/tmp/web-dist-$STAMP"        # 빌드 실패 대비 백업 (vite는 빌드 시작 시 dist를 비운다)
"$VENV_PY" -m pip install -r requirements.txt -q      # 새 의존성은 없다. 확인 차원
(cd web && npm ci && npm run build)
ls web/dist/index.html                       # 기대 출력: web/dist/index.html
```

빌드가 실패하면 즉시 백업을 되돌린다(`cd "$REPO" && rm -rf web/dist && cp -a "/tmp/web-dist-$STAMP" web/dist`). 실행 중인 broker가 비워진 dist를 서비스하고 있기 때문이다. 되돌린 뒤 root에 보고한다.

**broker 재시작**은 1-1의 Status 결과에 따라 다르다.

`owned_running: true`(ps1이 띄운 broker)이면 Windows PowerShell에서 실행한다.

```powershell
.\infra\local-demo.ps1 -Action Stop -Component Broker -Distro <배포판> -RootGo
.\infra\local-demo.ps1 -Action Start -Component Broker -Distro <배포판> -RootGo
.\infra\local-demo.ps1 -Action Status -Distro <배포판>    # 기대 출력: owned_running true, port_listening true
```

`owned_running: false`(다른 방식으로 띄운 broker)이면:
- ps1의 Stop은 자기가 띄운 프로세스만 멈춘다. 그대로 Start하면 "Port occupied"로 실패한다.
- **임의로 프로세스를 종료하지 말고** root에게 기존 broker를 멈춰 달라고 요청한다.
- 멈춘 뒤 다시 띄울 때는 반드시 `0.0.0.0`에 바인딩해야 worker가 접속할 수 있다.

```bash
. ~/redeploy-vars.sh && cd "$REPO" && GUIDE_BIND=0.0.0.0 GUIDE_PORT=8000 setsid nohup "$VENV_PY" -m service > "/tmp/broker-$STAMP.log" 2>&1 &
```

Windows와 WSL에서 broker를 **동시에** 실행하지 않는다.

**재시작 확인.**

```bash
sleep 5; curl -s http://127.0.0.1:8000/api/health | "$VENV_PY" -m json.tool
# 기대 출력: "worker_connected": true, "sandbox_evidence": {…}  (재시작 직후에는 false일 수 있다. 몇 초 뒤 다시 확인한다)
```

브라우저에서 broker 주소를 열어 상단 OpenShell 배지와 "자료 판단" 화면이 보이는지 확인한다.

## 5. 동작 확인 (웹에서, 5분)

**F3 차단 시연** 기대 결과:

| 시도 | 결과 | 상세 | broker 수신 |
|---|---|---|---|
| 허용 목록 밖 읽기 (`read_outside_allowlist`) | denied | EACCES 또는 EPERM | – |
| 코드 폴더 쓰기 (`write_code_dir`) | denied | EACCES·EPERM·EROFS | – |
| 미허용 외부 접속 (`egress_unlisted_host`) | denied | ConnectError 또는 ProxyError | – |
| broker 미허용 경로 (`broker_unlisted_path`) | denied | 403 | **0** |

- 화면 판정이 "OpenShell이 차단함"이어야 한다. 앞의 세 줄은 worker 보고이고, 마지막 줄만 broker가 직접 관측한 값이다.
- 하나라도 allowed이거나 "근거 불일치"(broker 수신 1 이상)이면 정책 적용 실패다. 시연에 쓰지 말고 6절로 간다.
- 읽기 시도가 `error`(ENOENT)이면 이미지에 `/home`이 없는 것이다.
  - `/root`는 OpenShell이 아니라 파일 권한(700) 때문에 거부되므로 쓰지 않는다. 누구나 읽을 수 있고 허용 목록 밖인 `/var`를 쓴다.
  - 재시도 절차:
    1. broker 롤백에 쓸 원래 값을 보관한다: `cp ~/redeploy-vars.sh ~/redeploy-vars-broker.sh` (6-6은 이 파일을 쓴다).
    2. 1-2(predeploy 파일 한 줄은 허용)와 1-3을 다시 실행한다. 1-3이 끝난 직후 `echo 'export PROBE_READ_PATH=/var' >> ~/redeploy-vars.sh`를 실행한다.
    3. 2절은 `git pull`을 건너뛰고 REF 저장 부분만 실행한다.
    4. 3절을 `export PROBE_READ_PATH=/var`가 설정된 셸에서 실행한다.

**F2 자료 판단**에서 예시 질문 "해온궁 휴궁일과 관람시간은?"을 실행한다. 기대 결과:
- `05-visitor-forum-post.txt`는 "지시문 포함"으로 제외된다.
- `04-seaside-food-list.md`는 "무관"으로 제외된다.
- 01·02·03은 사용되거나 outdated·충돌로 처리된다. 모델 판단이라 실행마다 다를 수 있다.
- "broker 검증 입력"으로 표시된다.
- 실패하면 진행 표시의 `grounding_check`에 오류 코드가 남는다.

## 6. 실패 시 되돌리기 (10분)

원칙:
- 이전 worker의 **이름(`$OLD`), 이미지(`$OLD_IMAGE`), 정책(`~/redeploy-ref-policy.json`), 커밋(`$PREV_COMMIT`)을 기준으로** 되돌린다.
- worker 롤백은 이전 커밋을 별도 worktree(`/tmp/prev-$STAMP`)에서 실행한다. 실행 중인 broker의 checkout은 바꾸지 않고 stash도 쓰지 않는다.
- 각 블록은 따로 붙여 넣는다. 앞 블록의 기대 출력이 맞을 때만 다음 블록으로 간다.
- 새 worker는 항상 새 번호로 만든다. `openshell sandbox start`처럼 이 저장소에서 써 보지 않은 명령은 쓰지 않는다.
- `deploy_worker.py`는 기준과 다른 worker에서 출발하는 교체를 막는다. 그래서 그 스크립트가 내부에서 쓰는 명령을 같은 환경 변수로 직접 실행한다.

```bash
. ~/redeploy-vars.sh && cd "$REPO"
# 6-1. 새 worker가 실행됐다면 로그를 먼저 회수한다 (정지하면 사라질 수 있다)
openshell logs "$NEW" -n 3000 > "/tmp/$NEW-$STAMP.log" 2>&1 || echo "no $NEW logs"
# 6-2. 새 worker가 떠 있을 때만 멈춘다
docker ps --format '{{.Names}}' | grep -v -- '-supervisor$' | grep -q "openshell-default--$NEW-" && openshell sandbox stop "$NEW"
docker ps --format '{{.Names}}' | grep -v -- '-supervisor$' | grep -c openshell-default--hangul-worker-
# 기대 출력: 0. 1 이상이면 직접 멈추지 말고 root에 보고한다 (아래 블록도 실행되지 않게 막혀 있다).
```

```bash
# 6-3. 이전 커밋을 별도 worktree에 꺼내, 실행 중인 broker의 checkout은 건드리지 않고 이전 이미지를 새 번호로 실행한다
. ~/redeploy-vars.sh && cd "$REPO"
[ "$(docker ps --format '{{.Names}}' | grep -v -- '-supervisor$' | grep -c openshell-default--hangul-worker-)" = 0 ] \
  || { echo "STOP: 소비자가 남아 있음 → root 보고"; false; } && {
  git worktree add "/tmp/prev-$STAMP" "$PREV_COMMIT" && cd "/tmp/prev-$STAMP" &&
  export BACK=hangul-worker-$(printf %02d $((10#${NEW: -2} + 1))) &&
  GUIDE_SERVER_URL=http://host.openshell.internal:8000 \
  NVIDIA_BASE_URL=http://host.openshell.internal:8001/v1 \
  NVIDIA_MODEL=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16 \
    "$VENV_PY" infra/launch_worker.py --name "$BACK" --image "$OLD_IMAGE" --env-file "$REPO/.env" &&
  echo "export BACK=$BACK" >> ~/redeploy-vars.sh
}
```

```bash
# 6-4. 확인
. ~/redeploy-vars.sh
openshell policy get "$BACK" --full -o json > /tmp/back-policy.json
"$VENV_PY" -c "import json,sys; r,b=(json.load(open(p)) for p in sys.argv[1:3]); o,n=sys.argv[3][-2:],sys.argv[4][-2:]; e=json.loads(json.dumps(r['policy']).replace('_'+o+'_','_'+n+'_')); print('matches previous policy:', b['status']=='effective' and b['policy']==e)" ~/redeploy-ref-policy.json /tmp/back-policy.json "$OLD" "$BACK"
# 기대 출력: matches previous policy: True   (False이면 openshell sandbox stop "$BACK" 후 root 보고)
sleep 20; openshell logs "$BACK" -n 3000 | grep -c "ALLOWED GET http://host.openshell.internal:8000/worker/jobs/next"
# 기대 출력: 2 이상
curl -s http://127.0.0.1:8000/api/health | grep -o '"worker_connected":[a-z]*'
# 기대 출력: "worker_connected":true
# 6-5. 정리: 확인이 끝나면 worktree를 지운다 (생성된 정책은 /tmp/prev-$STAMP/infra/generated/$BACK에 있으니 필요하면 먼저 보관)
cd "$REPO" && git worktree remove --force "/tmp/prev-$STAMP"
```

**6-6. broker 쪽 실패**(4절 재시작 뒤 `/api/health` 실패, 화면 오류 등)이면 다음 순서로 되돌린다. 5절 재시도를 했다면 1번에서 `~/redeploy-vars-broker.sh`를 불러온다.
1. `. ~/redeploy-vars.sh && cd "$REPO"`로 변수를 불러오고, broker를 멈춘다(4절과 같은 방식).
2. `git checkout "$PREV_COMMIT" && rm -rf web/dist && cp -a "/tmp/web-dist-$STAMP" web/dist`를 실행한다.
3. broker를 다시 시작하고 `/api/health`를 확인한다.
4. 이전 코드로 서비스해야 하므로 checkout은 그대로 둔다. root에 보고하고, main 복귀는 root가 정한다.

이전 broker에는 F2·F3 엔드포인트가 없을 뿐, 새 worker와 기존 기능은 함께 동작한다.

- worker를 되돌릴 때 broker는 되돌리지 않아도 된다. 이전 worker는 F2·F3 작업을 `invalid_job_or_result`로 실패 처리할 뿐이다.
- **가장 가벼운 대안:** F3만 실패했다면 새 worker를 그대로 두고, 차단 시연만 시연에서 뺀다.

## 7. 새 근거 저장 (5분, 커밋은 root)

배포에 성공한 뒤에 저장한다.
- 기존 근거 파일은 덮어쓰지 않는다. `latest-*` 두 파일만 의도적으로 교체한다(이전 내용은 git 이력에 남는다).
- README 규칙에 따라 공개 기록에는 응답 본문, 사진, 개인 접속주소, 자격 증명을 넣지 않는다.

```bash
. ~/redeploy-vars.sh && cd "$REPO" && E=docs/runtime/evidence
openshell policy get "$NEW" --full -o json > "$E/${NEW#hangul-}-effective-policy.json"
cp "$E/${NEW#hangul-}-effective-policy.json" "$E/latest-effective-policy.json"
H=$("$VENV_PY" -c "import json;print(json.load(open('$EVID/receipt.json'))['policy_hash'])")
[ -n "$H" ] && grep "CONFIG:LOADED" "$EVID/runtime.log" | grep "hash:$H"
# 기대 출력: ACK 줄 1개 이상. deploy_worker가 준비 확인 때 저장한 로그를 쓴다.
# worker는 1초마다 polling하므로, 지금 openshell logs로 다시 받으면 초기 ACK가 이미 밀려나 있을 수 있다.
```

`$E/latest-readiness.json`은 기존 필드를 유지해 값을 바꾸고, 아래 표의 `added_worker_routes`와 `reference_policy` 두 필드를 새로 추가한다. 해시는 `sha256sum` 출력의 첫 번째 열(64자 전체)을 넣는다. receipt는 `$EVID/receipt.json`이다.

| 필드 | 넣을 값 |
|---|---|
| `worker` | `$NEW` |
| `core_sha256`, `contract_sha256`, `image_id` | receipt의 같은 이름 필드 |
| `effective_policy_hash` | receipt의 `policy_hash` |
| `effective_policy_file_sha256` | `sha256sum $E/latest-effective-policy.json` |
| `deployment_receipt_sha256` | `sha256sum "$EVID/receipt.json"` |
| `captured_at` | 현재 UTC 시각 |
| `runtime_policy_ack` | 위에서 grep한 ACK 줄(배열) |
| `same_validated_allowlist` | `false` |
| `added_worker_routes`, `reference_policy` (새 필드) | receipt의 같은 필드 / `$REF` |
| `model_execution`, `semantic_acceptance` | `"미검증(새 worker)"` |

5절 시연 결과는 **요약만** 저장한다. 질문 본문·답변 문장·인용문은 넣지 않는다.
- `$E/f3-probe-$STAMP.json`: 시도 id별 `observed`·`detail`·`broker_received`, `run_context`, 시각
- `$E/f2-review-$STAMP.json`: 출처 id·경로별 `verdict`·`reason`, `status`, `verified_input`, 오류 코드

```bash
rm -f /tmp/c                                 # 세션 쿠키 파일을 만들었다면 지운다
git status --short docs/runtime/evidence     # 새 파일·변경 파일 목록을 root에 전달한다
```

커밋과 push는 root가 한다(예시 메시지: `Record <NEW> deployment evidence (F2/F3 routes, probe and review summaries)`). 커밋한 뒤 broker를 한 번 더 재시작하면 `/api/health`의 `sandbox_evidence`와 상단 배지가 새 worker 기준으로 표시된다(시작할 때 읽는 값이다). 경계 시험(11조건, probe `hangul-matrix-01`)은 이번에 다시 실행하지 않았으므로 화면에도 예전 결과로 표시된다.

## 8. (선택·기본 아님) 행사 입력 `/hackathon/input`

기본은 **제품 worker에 붙이지 않는다.** AGENTS.md 규칙에 따라 공식 제공 자료는 별도 CLI(`agent.challenge`, `infra/launch_challenge.py`)로 처리하고, 공식 산출물(`/hackathon/output`)도 그 CLI가 만든다.

발표 중 웹에서 꼭 보여야 하는 경우에만 root·사용자 확인을 받고 다음을 진행한다.
1. `/hackathon/input`을 worker에 **읽기 전용**으로 마운트하고 정책의 `read_only`에 추가한다. 이는 파일 권한 변경이라 3절의 `--allow-added-worker-routes` 검사를 통과하지 못하므로, 기준 정책을 새로 정하는 별도 작업이 필요하다.
2. worker를 만들 때 `REVIEW_INPUT_DIR=/hackathon/input`, `REVIEW_INPUT_LABEL=hackathon-input`을 설정한다(`launch_worker.py`가 전달한다).
3. broker 환경에 `REVIEW_ALLOW_EXTERNAL_INPUT=true`를 설정하고 **broker를 재시작한다.** 설정이 없으면 broker가 결과를 거부한다.
4. broker는 이 파일을 볼 수 없다. 그래서 인용이 worker가 보낸 발췌 안에 있는지만 검사하고, 화면에는 "broker 미검증 입력"으로 표시된다.
5. `restricted`·`secrets` 경로는 읽지 않는다(`agent/challenge.py`의 `FORBIDDEN`).

## 검증 범위 (작성자 기준, 2026-11-06)

**로컬에서 확인한 것**

`tests/unit/test_review_probe.py` (21건, 오프라인 모델 stub, in-process broker):
- 데모 판정
- broker가 다음을 거부하는지:
  - 위조 인용, 두 발췌에 걸친 인용, 변조 해시
  - 지시문 자료를 used로 표시한 결과
  - 무관·미선택·읽기불가 판정 위조, 날짜 위조
  - 데모 파일명을 쓰는 외부 입력, 미허용 외부 입력
- worker가 `verified_input`·`broker_received`를 스스로 설정할 수 없는지
- Markdown 주입이 막히는지
- 세션당 작업 보존 상한, 그리고 observe가 ask 결과를 밀어내지 않는지
- 인증 없는 canary 요청도 집계되는지, canary 범람이 trace를 밀어내지 않는지
- 로컬 probe가 allowed로 정직하게 보고되는지, 오프라인 egress를 denied로 표시하지 않는지, 403만 denied로 인정하는지

`tests/security/test_deploy_routes.py` (6건):
- 실제 판정 함수 `added_routes_check`를 그대로 시험한다.
- 선언된 경로만 추가되는지, 규칙 순서가 달라도 통과하는지 확인한다.
- 다음은 각각 거부되는지 확인한다: 다른 엔드포인트 규칙 추가, 쓰기 권한 확대, canary, 와일드카드, 목록에 없는 경로.

**확인하지 못한 것**
- 실제 Nemotron 응답 품질
- OpenShell의 실제 차단
- 이미지 빌드
- `deploy_worker.py`·`launch_worker.py`·`local-demo.ps1` 실행, `git worktree`를 쓴 롤백
- 6절 롤백
- broker 재시작
- `openshell` CLI의 출력 형식 (이 저장소의 기존 스크립트 사용례에만 근거한다)
- `ss`·`readlink`로 broker checkout을 찾는 방법
