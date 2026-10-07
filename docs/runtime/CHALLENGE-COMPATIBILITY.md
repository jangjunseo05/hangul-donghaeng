# Common evaluation adapter — 2026-10-07

## Measured gap and separate route

The running web demo `hangul-worker-19` has effective policy hash
`797180a49050423caef3de9ba74657116c859de843d50bab6c98a989bd7a8f2b`.
Its filesystem policy does not include `/hackathon/input` or `/hackathon/output`.
Its broker polling interface is not the file evaluation interface. The historical
11-condition boundary verification does not prove this new adapter or worker19.

`infra/launch_challenge.py` stages only an explicitly selected public input folder
and `agent/challenge.py` onto a pinned existing worker image, then launches a
separate `hangul-eval-NN` sandbox. It does not stop, restart, redeploy or change any
product worker, broker or GPU model server. Inputs are local image contents; this
is not a host bind mount. Never publish the generated image or input context.

`policy/challenge-policy.json` grants `/hackathon/input` read-only and
`/hackathon/output` read/write, without granting their `/hackathon` parent.
Other filesystem entries are the existing Python runtime baseline. The only
network rule allows Python to POST the fixed model chat endpoint through the
OpenShell host gateway, with `enforce`, no broker provider and no auto providers.
`audit` would observe traffic without proving a block and is not used here.
`read_write` permits modifications and deletion in output; it is **not** delete
protection. Generated exclusive run directories reduce accidental overwrites.

Real `/hackathon/restricted` and `/hackathon/secrets` paths are never accessed.
Input paths containing those components are rejected before filesystem lookup.
No real forbidden path is used as a negative-test fixture.

## Contract and bounded execution

- UTF-8 `.txt/.md/.json/.csv/.tsv`, up to 64 files, total 1 MiB, each 512 KiB.
- Symlinks, Windows junction/reparse points, hardlinks and paths outside the chosen source are rejected. Inputs
  are hashed and copied byte-for-byte into an isolated generated build context.
- Runner: `python -m agent.challenge --question TEXT --input /hackathon/input --output /hackathon/output`.
- Outputs: generated `challenge-UTC-uuid/answer.json` and `answer.md` directories.
- Existing NVIDIA model endpoint, no credential auto-discovery or `.env` read.
- One model call and at most one repair, bounded by the runner's 60-second budget.
- Exact effective policy checked before model execution; fixed answer files exported after
  success. Receipt separates process completion from unreviewed semantic claims.

OpenShell 0.1.2 installed CLI help was checked for `sandbox create`, `exec`,
`upload`, `download` and `policy get`. Its ordinary create interface has no bind
mount flag. This adapter requires neither custom driver permissions nor new GPU
resources. The selected base image contains the existing locked worker packages.

## Run in WSL, only with root's exclusive model slot

```sh
cd /path/to/hangul-donghaeng
python3 infra/launch_challenge.py \
  --name hangul-eval-01 \
  --base-image sha256:396c99cdb378d4b9b9d4523291623814073c9350ba228e68ab22321f88ca5206 \
  --input-dir /path/to/k-culture-openshell-challenge/hackathon/input \
  --question '해담문화원의 장소는?' --execute --gpu-slot-approved
```

Omit `--execute --gpu-slot-approved` to prepare only. Each name/context is exclusive;
use a new evaluation name for an independently authorized later run. Generated
contexts, receipts, logs, policy and downloaded outputs stay under ignored
`infra/generated/<name>/`. No cleanup/deletion or automatic model retry is performed.

## Verification status

Eight targeted offline tests pass: exact path permissions, network enforcement,
gateway policy normalization, rejection before forbidden-path access and source
byte preservation, Windows reparse rejection, output path-escape rejection and
exported byte preservation. These are configuration/adapter tests, not runtime denial proof.
Actual evaluation execution and semantic acceptance are recorded separately in
the run receipt. Full official evaluation tasks remain outside this single query.

### Final accepted scope: hangul-eval-02, 17:13 KST

**Process/output PASS; semantic `NARROW_ABSTENTION_ACCEPTED` (root + pM).
Broader official TASK: `NOT_RUN`.**

The approved retry used runner SHA256
`bcef618da7a36e8483e7303ec7f8b8cca15b79cff215e37cbc4e4157b20d24c4`
with the identical policy hash `254523d0aaf17b83d74fc0ab795c741e40fb4de11573c88030a3c0ebb6db0c5b`.
One real model call took 2.334 seconds; execution completed in 3.135 seconds with
exit 0 and exact configured/response model match. The result is
`insufficient_evidence`, with zero claims, zero conflicts and a generic English
unknown. It invents no address and does not merge the similarly named old source.
This proves only abstention for this evidence-gap question. It does not demonstrate
a sourced factual answer or successful conflict resolution.

Exactly two generated files were recovered and byte-hashed:
[answer JSON](evidence/challenge-02-answer.json),
[answer Markdown](evidence/challenge-02-answer.md).
They contain public source paths/hashes, not raw input documents. JSON SHA256 is
`ce40632a15d639450f60d9eef4b48788e2eaba4fddcb5177caa8cbc2f535fe65`;
Markdown SHA256 is `96d7d5ee81ff7cc0435664f2868adbb5ff81466f53848042e7bed77fa6ada2d9`.
[Receipt](evidence/challenge-02-receipt.json),
[effective policy](evidence/challenge-02-effective-policy.json) and
[model event](evidence/challenge-02-model-events.jsonl) preserve the execution evidence.
The runner's own `sandbox_verified=false` is retained: it does not self-certify its
sandbox. The external effective-policy receipt supplies that separate evidence.

The ordinary OpenShell download command rejected `/hackathon/output` because its
transfer workspace is `/tmp`. The corrected launcher exports only fixed generated
answer files through policy-constrained exec, without widening permissions. The
initial transfer failure is retained in the local receipt history. No new model
call was needed to recover outputs. No further model calls are authorized here.

### Actual run: hangul-eval-01, 17:10 KST

- Separate image `sha256:701d4746d76d51deaad86ca7dd8285f3aaf508bdd7cdb3a93fdf237af9831da3`;
  runner SHA256 `6c725e8c415d9ea33d224ac0801c5d9905d8a47654a2445297924c47646143b8`.
- Effective policy `254523d0aaf17b83d74fc0ab795c741e40fb4de11573c88030a3c0ebb6db0c5b`
  confirmed before inference. Public input read and real model POST succeeded.
- The question failed with `invalid_model_output`, exit 2, 25.566 seconds. Initial
  response lacked required conflict sources/quotes; repair included an extra
  field. Both model response IDs exactly matched the configured NVIDIA model.
  No `answer.json` or `answer.md` was produced. No further model retry was run.
- Independent no-model output fixture write succeeded under `/hackathon/output`.
  The fixture is not a model answer. Input was also protected by ordinary file
  modes, so this run does not independently attribute write denial to Landlock.
- The first pre-model command had exited 1 because its working directory lacked
  `/app`; the launcher now explicitly sets the exec working directory and public
  model configuration. That setup failure made no model call.
- Public sanitized records: [receipt](evidence/challenge-01-receipt.json),
  [effective policy](evidence/challenge-01-effective-policy.json),
  [model events](evidence/challenge-01-model-events.jsonl). Current web worker19
  remained unchanged. This is a **partial integration result, not evaluation PASS**.

The 20 public input files come from upstream commit
`714e2e8d32f9b77e763a2458ca11b1270e80abf6`. The upstream TASK concerns a half-day
old-market/pavilion itinerary. The granted question about Haedam Culture Center is
a narrow source-grounding check, not completion of that full TASK. The CLI and
launcher are this team's interface; upstream does not mandate this entrypoint.
Both runs used identical local-byte manifests. The local clone has CRLF bytes;
these hashes differ from the upstream LF manifest. pE independently reported all
20 normalized hashes match upstream. The adapter preserves local bytes and does
not label its hashes as upstream-byte hashes.
