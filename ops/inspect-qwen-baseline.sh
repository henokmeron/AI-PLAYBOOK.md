#!/usr/bin/env bash
set -euo pipefail
echo "=== HOST ==="
hostname; date -u; uname -a
echo "=== GPU ==="
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,driver_version --format=csv || true
nvidia-smi || true
echo "=== DISK ==="
df -h /workspace / /tmp 2>/dev/null || true
du -sh /workspace/* 2>/dev/null | sort -h | tail -40 || true
echo "=== PORTS ==="
ss -ltnp 2>/dev/null | grep -E ':(8000|8010|8012|8080|8082)\b' || true
echo "=== PROCESSES (vllm/gateway/console) ==="
ps aux | grep -E 'vllm|local_gateway|web/server|uvicorn' | grep -v grep || true
echo "=== GEMMA PATH ==="
GEMMA=/workspace/gemma-4-31B-it/gemma-4-31B-it/gemma-4-31B-it
ls -la "$GEMMA" 2>/dev/null | head -30 || echo "missing gemma path"
du -sh /workspace/gemma-4-31B-it 2>/dev/null || true
ls /workspace/ai-platform-backups/source-snapshots 2>/dev/null | tail -10 || true
echo "=== PYTHON ENVS ==="
ls -d /tmp/*env* /tmp/vllm* /workspace/*env* 2>/dev/null || true
if [[ -x /tmp/vllm-clean-env/bin/python ]]; then
  /tmp/vllm-clean-env/bin/python - <<'PY'
import sys
print("python", sys.version)
try:
    import vllm
    print("vllm", vllm.__version__)
except Exception as e:
    print("vllm import failed", e)
try:
    import torch
    print("torch", torch.__version__, "cuda", torch.version.cuda)
    print("cuda_available", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("gpu0", torch.cuda.get_device_name(0), "vram_gb", round(torch.cuda.get_device_properties(0).total_memory/1024**3, 2))
except Exception as e:
    print("torch import failed", e)
PY
fi
echo "=== HEALTH ==="
for u in http://127.0.0.1:8000/v1/models http://127.0.0.1:8010/health http://127.0.0.1:8012/health http://127.0.0.1:8080/ http://127.0.0.1:8082/; do
  code=$(curl -s -o /tmp/_h.txt -w '%{http_code}' --max-time 5 "$u" || echo fail)
  echo "$u -> $code"
  head -c 200 /tmp/_h.txt 2>/dev/null; echo
done
echo "=== REPO ON POD ==="
ls /workspace/AI-PLAYBOOK.md 2>/dev/null || ls /tmp/AI-PLAYBOOK* 2>/dev/null || true
if [[ -d /workspace/AI-PLAYBOOK.md/.git ]]; then
  git -C /workspace/AI-PLAYBOOK.md rev-parse --abbrev-ref HEAD
  git -C /workspace/AI-PLAYBOOK.md rev-parse HEAD
  git -C /workspace/AI-PLAYBOOK.md status -sb
fi
echo "=== QWEN EXISTING? ==="
ls -d /workspace/qwen* /workspace/models/qwen* 2>/dev/null || echo "no qwen dir yet"
echo "DONE"
