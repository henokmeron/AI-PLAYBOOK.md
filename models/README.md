# Model registry

Git tracks model **metadata and serving profiles**. Multi-gigabyte weights stay on `/workspace` and Azure Blob.

- `registry.yaml` — candidates, production default, runtime profiles
- `registry_loader.py` — load/validate + public catalog helpers
- `requirements.txt` — `PyYAML` for the loader
- `tests/` — no-GPU unit tests

Qwen (`qwen3.5-27b`) is the production default. Gemma (`gemma-4-31b-it`) stays optional and is not selected when Qwen is unavailable.

Qwen weights path (not in Git):

`/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`
