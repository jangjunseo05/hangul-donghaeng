# OpenShell access boundary

Generate version-1 sandbox policy and custom provider profiles with `infra/render_policy.py`.
The pinned runtime is OpenShell 0.1.2. Generated host-specific files are ignored under infra/generated.

- Worker code/data are read-only; trusted FastAPI alone saves permanent results.
- /tmp and /dev/null are writable. **read_write permits deletion**; it is not delete protection.
- Landlock hard_requirement; non-root UID/GID 1000. Inspect applied/skipped paths in runtime logs.
- Network REST rules explicitly use enforce. Audit permits violations and cannot prove blocking.
- GUIDE credentials bind only to /worker/** at the fixed service host; server still enforces session/request/photo ownership.
- Local model has no NVIDIA hosted credential. Hosted mode binds NVIDIA_API_KEY only to integrate.api.nvidia.com:443 chat completion.
- Provider rules are part of effective policy. Inspect effective policy after attachment; base policy alone is insufficient.
- No browser speech, microphone, geolocation or map requests pass through this worker sandbox. They remain client capabilities.
- Profile lint is gateway validation, not proof of a live sandbox or successful model request.
