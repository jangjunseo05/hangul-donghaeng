# 알려진 실패: heritage 입력 해시 불일치

- 상태: **미해결, 의도적으로 실패 상태로 둠** (2026-11-06, 저장소 소유자 결정)
- 실패 테스트: `tests/unit/test_catalog.py::CatalogTests::test_approved_heritage_integration_and_evidence_links`
- 영향: 데모·서비스 동작과 무관합니다. 단위 테스트 1건이 계속 실패합니다. 이 실패를 새 회귀로 오인하지 마세요.

## 무엇이 실패하나

테스트(`tests/unit/test_catalog.py:48-50`)는 `data/heritage-proposal.json` 파일 바이트의 SHA-256이
`data/catalog.json`의 `heritage_integration.input_sha256`(검수 시점에 기록한 입력 해시)과 같은지 검사합니다.

| 대상 | SHA-256 |
|---|---|
| `catalog.json`에 기록된 값 (`input_sha256`) | `79326ab2336fc2f75fc8fc9bcbd1f72c76f5a775ea976e880f3aafd7ae563879` |
| git blob(LF) 그대로 | `347538097c299dd96d82e98a757201d19f1b668d5f2a4a268abcaa7d2b3ec5eb` |
| Windows 작업 트리(CRLF, `core.autocrlf=true`) | `da345ecd37da74d41cf100a116cdc49b7f34ff8657208496b95a3345c460287a` |

기록된 값은 LF와 CRLF 어느 쪽과도 일치하지 않습니다. 따라서 **줄끝(CRLF) 문제가 아닙니다.**
(`.gitattributes`에 `-text`를 지정해 LF로 다시 체크아웃해도 실패하는 것을 2026-11-06에 확인했고, 그 변경은 되돌렸습니다.)

## 원인 (확인된 사실)

- `data/heritage-proposal.json`과 `catalog.json`의 `input_sha256`은 같은 커밋 `196536c`(2026-10-07)에서 처음 들어왔습니다.
  그 뒤로 proposal 파일 내용은 한 번도 바뀌지 않았습니다(`git log -- data/heritage-proposal.json`).
- 즉 **처음 커밋된 시점부터 해시가 맞지 않았습니다.** 검수(`reviewed_at: 2026-10-07`, `proposal_version: heritage-20261007.1`) 때 해시를 계산한 파일이
  커밋된 파일과 다른 버전이었을 가능성이 큽니다. 다만 어느 쪽이 실제 검수본인지는 확인되지 않았습니다.

## 왜 고치지 않았나

`input_sha256`은 "이 입력을 검수했다"는 기록입니다. 현재 파일의 해시로 덮어쓰면 테스트는 통과하지만,
검수하지 않았을 수도 있는 파일을 검수본으로 인정하는 셈이 됩니다. 그래서 검수본이 확인될 때까지 실패로 남겨 둡니다.
`AGENTS.md`의 "실패를 숨기지 않는다" 원칙과도 맞습니다. `data/`의 소유는 `AGENTS.md`의 pN 역할입니다.

## 해결 방법 (결정 후)

1. 검수 당시 파일을 찾으면, 그 내용으로 `data/heritage-proposal.json`을 복원하고 해시가 `79326ab…`와 일치하는지 확인합니다.
2. 현재 파일이 맞는 검수본이라고 저장소 소유자가 확인하면, `input_sha256`을 **LF blob 해시** `347538…`로 갱신합니다.
   이때 Windows에서도 통과하려면 `.gitattributes`에 `data/heritage-proposal.json -text`를 추가하거나, 테스트가 줄끝을 정규화해야 합니다.
   `reviewed_at`·`notes`에 재확인 사실을 함께 남기세요.

## 재현

```bash
python -m pytest -q tests/unit/test_catalog.py -k heritage
sha256sum data/heritage-proposal.json                                   # 작업 트리
git cat-file -p HEAD:data/heritage-proposal.json | sha256sum            # LF blob
```
