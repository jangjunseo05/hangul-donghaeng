# BUILD-AGENT-DATA-01 handoff

2026-10-07, owner w1:pN, reviewer root. Contract e1233c6e82b987385722d2d682794aeb3149cb660edc0330d0e3e85de0fd5518.

Implemented catalog helpers (service/catalog.py), one restaurant / three menus,
3 real evidence records and 9 anonymized fictional-input summaries, bounded real
HTTP model worker, .env loading, explicit self-hosted no-key opt-ins, history,
confirmation/unknowns, mode boundaries, approved evidence and server-only saving.

Executed on Windows Python 3.12.10:
- `.venv/Scripts/python.exe -B -m unittest discover -s tests/unit -p "test_catalog*.py" -v`: 4 passed.
- `.venv/Scripts/python.exe -B -m unittest discover -s tests/unit -p "test_agent*.py" -v`: 15 passed.
- Two of the 15 use the actual FastAPI service and actual worker core with only the
  provider replaced by an HTTP stub: photo/search/result/poll/download and fictional
  itinerary/evidence validation. Those flows reached saved/completed.

Live model/vision/latency/OpenShell/network deny/UI/audio remains UNVERIFIED.
pM's confirmed serving endpoint/model ID and effective policy are the next integration
input. No model/API credentials are recorded here; no live provider was called.
Update 13:21 KST: pE obtained the CC0 960px Commons thumbnail with HTTP200 and verified its hash. See data/samples/license-manifest.json. It is a generic food sample; live model recognition is still unverified.

BUILD-AGENT-HARDEN-02: official NVIDIA credentials are restricted to their HTTPS origin; self-hosted credentials use SELF_HOSTED_API_KEY and never travel over HTTP. Broker HTTP is opt-in for the exact OpenShell gateway hostname. The model system prompt uses /no_think. Agent unittest coverage now passes 24 tests with HTTP stubs; live GPU timing remains unverified.

Changed only agent/, data/, service/catalog.py and tests/unit/test_agent* / test_catalog*.
No shared/root/service-other file edits, Git writes, pane controls or deployments.
