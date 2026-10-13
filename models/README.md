# Model registry

Git tracks model **metadata and serving profiles**. Multi-gigabyte weights stay on `/workspace` and Azure Blob.

- `registry.yaml` — candidates, production default, runtime profiles
- `registry_loader.py` — load/validate + public catalog helpers
- `requirements.txt` — `PyYAML` for the loader
- `tests/` — no-GPU unit tests

Gemma (`gemma-4-31b-it`) remains the production default until Qwen live validation passes and an explicit switch is approved.

Qwen weights path (not in Git):

`/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654`
