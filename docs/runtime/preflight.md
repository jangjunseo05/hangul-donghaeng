# BUILD-OPEN-SHELL-01 preflight — current status

Owner w1:pM; reviewer root/w1:p7. Updated 2026-10-07 14:25 KST.
Mission day-of-v1-20261007. Latest user deadline: development, verification and push by **16:00**; official submission 17:20.
API contract SHA256: `e1233c6e82b987385722d2d682794aeb3149cb660edc0330d0e3e85de0fd5518` (matched).

## Measured state

- WSL Ubuntu 22.04.5, Docker 29.8.2, OpenShell CLI/gateway/prover 0.1.2. Actual gateway mTLS connected.
- User completed Brev login. Existing GPU inspected: NVIDIA L40S 46,068 MiB, 45,458 MiB free before model load; Docker 29.1.5 with NVIDIA runtime. No new GPU resource.
- Public `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16` serves through vLLM 0.12.0. No hosted NVIDIA API key. GPU instance, organization, SSH alias and credentials remain private.
- Actual OpenShell model probe: HTTP 200 and choices. File write/delete/read and controlled network denials are joined with independent receiver counts and policy logs: PASS.
- Worker03 is deployed with final core SHA `9ecfae38f844961e45c7f3b0430e06294517e06ebe0d01e096f16d328b30f2db`; the same hash was read inside its container.
- Worker02 is stopped, workspace preserved. Docker listing shows worker03 and its supervisor only. Root's broker and SSH tunnel remain running.
- Actual worker03 model metadata records configured model ID and exact response-model match. One observed job saved; a later Draft call reached `model_timeout` after 20.02 seconds. Full product QA belongs to root.
- Root's broker health reports worker_connected=true. Model/sandbox flags remain false pending root's evidence integration; environment flags alone do not prove isolation.
- Worker03 installed runtime dependencies match the relevant exact versions in root requirements-lock.txt. Policy configuration tests: 4 PASS.

## Installation and recovery history

Initial Windows tools were absent; authorized WSL installation resolved this. Official OpenShell 0.1.2 Debian package SHA256:
`1f5416ea08f32fdc621f20a2cc0324298e60aba8bbe996459d9e3b44195f23df`.
Initial login/network blockers are resolved. The measured gateway resolves host.openshell.internal to loopback, so the SSH forward must listen there.
A long host/tool pause was followed by a missing forward listener; root restored it in a persistent session. See [runbook](README.md) for lifecycle and reconnect instructions.

## Evidence and limits

[Security evidence](SECURITY-EVIDENCE.md) and [captured evidence](evidence/).
read_write permits deletion; only scratch paths are writable. Audit records without blocking; current endpoint rules use enforce.
Actual inference and isolation do not establish cultural correctness, translation accuracy, dietary safety, demand or NIM/NeMo qualification. Product QA acceptance and final push remain root responsibilities.

## Official sources checked 2026-10-07

- [OpenShell installation, v0.1.2](https://docs.nvidia.com/openshell/v0.1.2/about/installation)
- [OpenShell policy schema, v0.1.2](https://docs.nvidia.com/openshell/v0.1.2/how-it-works/policies/schema)
- [Provider profiles, v0.1.2](https://docs.nvidia.com/openshell/v0.1.2/how-it-works/providers/profiles)
- [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/)
- [Brev CLI authentication](https://docs.nvidia.com/brev/cli/getting-started)
- [Brev existing-instance connectivity](https://docs.nvidia.com/brev/cli/connectivity)
