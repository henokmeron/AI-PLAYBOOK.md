#!/usr/bin/env python3
"""Full first-release bring-up on a driver-capable Pod (H100 / driver 580+)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path("/tmp/AI-PLAYBOOK")
BRANCH = "feature/qwen3.5-27b-integration"
REMOTE = "https://github.com/henokmeron/AI-PLAYBOOK.md.git"
ENV = Path("/tmp/vllm-qwen-env")
MODEL = Path(
    "/workspace/models/Qwen3.5-27B/fc05daec18b0a78c049392ed2e771dde82bdf654"
)
KEY = Path("/tmp/platform-gateway.key")
DIAG = Path("/workspace/platform-diagnostics/complete")
RELEASE = Path("/workspace/ai-platform-release")
ARCHIVE_DIR = Path("/workspace/runtime-setup/qwen-vllm")


def sh(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kwargs)


def healthy(url: str, timeout: float = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def http_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None, timeout: float = 180):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw[:2000]}
        return exc.code, parsed


def _lf(path: Path) -> None:
    if path.is_file():
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def overlay_volume_release_ops() -> None:
    """Prefer durable ops copies from /workspace/ai-platform-release/ops when present."""
    src = RELEASE / "ops"
    if not src.is_dir():
        return
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        dest = REPO / "ops" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        _lf(dest)
    print(f"OVERLAY_OPS_FROM={src}", flush=True)


def ensure_repo() -> None:
    if not (REPO / ".git").is_dir():
        sh(["git", "clone", "--branch", BRANCH, "--single-branch", REMOTE, str(REPO)])
    else:
        sh(["git", "-C", str(REPO), "fetch", "origin", BRANCH])
        sh(["git", "-C", str(REPO), "checkout", BRANCH])
        # Soft update: keep local ops overlays from the volume release folder.
        sh(["git", "-C", str(REPO), "reset", "--hard", f"origin/{BRANCH}"])
    overlay_volume_release_ops()
    for rel in (
        "ops/start-first-release.sh",
        "ops/restore-qwen-runtime.sh",
        "ops/archive-qwen-runtime.sh",
        "ops/_complete_bringup.py",
        "scripts/restore-vllm-environment.sh",
        "rag/setup_pypdf.sh",
        "rag/setup_openpyxl.sh",
    ):
        _lf(REPO / rel)


def build_ld_path() -> str:
    nvidia = ENV / "lib/python3.12/site-packages/nvidia"
    dirs: set[str] = set()
    if nvidia.is_dir():
        for so in nvidia.rglob("lib*.so*"):
            dirs.add(str(so.parent))
    return ":".join(sorted(dirs))


def ensure_qwen_env() -> dict:
    info: dict = {}
    if not (ENV / "bin/vllm").is_file():
        print("Restoring Qwen env from Global Volume archive…", flush=True)
        sh(["bash", str(REPO / "ops/restore-qwen-runtime.sh")])
    env = os.environ.copy()
    ld = build_ld_path()
    if ld:
        env["LD_LIBRARY_PATH"] = ld
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"
    env["VLLM_DO_NOT_TRACK"] = "1"
    chk = subprocess.run(
        [
            str(ENV / "bin/python"),
            "-c",
            "import torch,vllm; print(torch.__version__, torch.version.cuda, "
            "torch.cuda.is_available(), vllm.__version__, "
            "torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    info["probe"] = (chk.stdout + chk.stderr).strip()
    info["probe_ok"] = chk.returncode == 0 and "True" in chk.stdout
    if not info["probe_ok"]:
        raise RuntimeError(f"Qwen env GPU probe failed: {info['probe']}")
    info["ld_set"] = bool(ld)
    return info


def start_qwen(env: dict) -> None:
    if healthy("http://127.0.0.1:8002/v1/models"):
        print("Qwen already up", flush=True)
        return
    DIAG.mkdir(parents=True, exist_ok=True)
    log = (DIAG / "qwen-vllm.log").open("w", encoding="utf-8")
    cmd = [
        str(ENV / "bin/python"),
        str(ENV / "bin/vllm"),
        "serve",
        str(MODEL),
        "--host",
        "127.0.0.1",
        "--port",
        "8002",
        "--trust-remote-code",
        "--language-model-only",
        "--reasoning-parser",
        "qwen3",
        "--max-model-len",
        "8192",
        "--max-num-seqs",
        "256",
        "--gpu-memory-utilization",
        "0.92",
        "--default-chat-template-kwargs",
        '{"enable_thinking": false}',
    ]
    proc = subprocess.Popen(
        cmd, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
    )
    (DIAG / "qwen-vllm.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
    print("STARTED_QWEN", proc.pid, flush=True)
    for i in range(360):
        time.sleep(5)
        if healthy("http://127.0.0.1:8002/v1/models"):
            print("QWEN_READY", (i + 1) * 5, "s", flush=True)
            return
        if proc.poll() is not None:
            raise RuntimeError(
                (DIAG / "qwen-vllm.log").read_text(errors="replace")[-3000:]
            )
    raise RuntimeError("Qwen start timeout")


def ensure_key() -> str:
    if not KEY.is_file():
        key = subprocess.check_output(
            ["openssl", "rand", "-base64", "48"], text=True
        ).strip()
        KEY.write_text(key, encoding="utf-8")
        KEY.chmod(0o600)
    return KEY.read_text(encoding="utf-8").strip()


def setup_rag_deps(env: dict) -> None:
    for script in ("rag/setup_pypdf.sh", "rag/setup_openpyxl.sh"):
        path = REPO / script
        if path.is_file():
            subprocess.call(["bash", str(path)], env=env)


def start_gateway(key: str) -> None:
    if healthy("http://127.0.0.1:8010/health"):
        print("Gateway already up", flush=True)
        return
    # Prefer env python for PyYAML
    subprocess.call(
        [str(ENV / "bin/python"), "-m", "pip", "install", "--quiet", "pyyaml"]
    )
    gw_env = os.environ.copy()
    gw_env.update(
        {
            "PLATFORM_HOST": "127.0.0.1",
            "PLATFORM_PORT": "8010",
            "PLATFORM_API_KEY": key,
            "PLATFORM_API_KEY_FILE": str(KEY),
            "VLLM_UPSTREAM_URL": "http://127.0.0.1:8002/v1",
            "PLATFORM_MODEL_REGISTRY": str(REPO / "models/registry.yaml"),
            "PLATFORM_DEFAULT_MODEL_ID": "qwen3.5-27b",
            "PYTHONPATH": f"{REPO / 'api'}:{REPO / 'models'}:{REPO / 'rag'}",
            "RAG_DOCS_DIR": "/workspace/rag-demo-docs",
            "RAG_MANAGED_DOCS_DIR": "/workspace/rag-managed-docs",
        }
    )
    if "LD_LIBRARY_PATH" in os.environ:
        gw_env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    log = (DIAG / "gateway.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(ENV / "bin/python"), str(REPO / "api/local_gateway.py")],
        cwd=str(REPO / "api"),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=gw_env,
        start_new_session=True,
    )
    (DIAG / "gateway.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
    time.sleep(2)
    if not healthy("http://127.0.0.1:8010/health"):
        raise RuntimeError((DIAG / "gateway.log").read_text(errors="replace")[-2000:])
    print("GATEWAY_OK", flush=True)


def start_console() -> None:
    if healthy("http://127.0.0.1:8080/api/status"):
        print("Console already up", flush=True)
        return
    web_env = os.environ.copy()
    web_env.update(
        {
            "WEB_HOST": "127.0.0.1",
            "WEB_PORT": "8080",
            "PLATFORM_GATEWAY_URL": "http://127.0.0.1:8010",
            "PLATFORM_API_KEY_FILE": str(KEY),
            "PLATFORM_MODEL_ID": "qwen3.5-27b",
        }
    )
    log = (DIAG / "console.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["/usr/bin/python3", str(REPO / "web/server.py")],
        cwd=str(REPO / "web"),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=web_env,
        start_new_session=True,
    )
    (DIAG / "console.pid").write_text(str(proc.pid) + "\n", encoding="utf-8")
    time.sleep(2)
    if not healthy("http://127.0.0.1:8080/api/status"):
        raise RuntimeError((DIAG / "console.log").read_text(errors="replace")[-2000:])
    print("CONSOLE_OK", flush=True)


def write_release_launcher() -> None:
    """Durable on-volume launcher directory (not a zip; scripts + pointers only)."""
    RELEASE.mkdir(parents=True, exist_ok=True)
    ops_out = RELEASE / "ops"
    ops_out.mkdir(parents=True, exist_ok=True)
    for name in (
        "_complete_bringup.py",
        "start-first-release.sh",
        "restore-qwen-runtime.sh",
        "archive-qwen-runtime.sh",
        "start-qwen-isolated.sh",
        "switch-gpu-model.sh",
        "_pod_e2e_verify.py",
    ):
        src = REPO / "ops" / name
        # Prefer the currently executing bring-up script when syncing itself.
        if name == "_complete_bringup.py":
            here = Path(__file__).resolve()
            if here.is_file():
                src = here
        if src.is_file():
            dest = ops_out / name
            dest.write_bytes(src.read_bytes())
            _lf(dest)
    # Also keep gateway/console patches that matter for recovery without git.
    for rel in ("api/local_gateway.py", "models/registry.yaml", "web/server.py"):
        src = REPO / rel
        if src.is_file():
            dest = RELEASE / "tree" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            _lf(dest)
    (RELEASE / "VERSION.txt").write_text(
        "first-release-qwen-primary\n"
        f"branch={BRANCH}\n"
        "entry=START.sh\n"
        "venv_policy=archive_on_volume_extract_to_tmp\n",
        encoding="utf-8",
    )
    start = RELEASE / "START.sh"
    start.write_text(
        """#!/usr/bin/env bash
# One-command first-release start from the Global Volume.
# Does not unzip a venv onto FUSE. Restores/runs from /tmp using volume archives.
set -Eeuo pipefail
RELEASE_DIR="$(cd "$(dirname "$0")" && pwd)"
export REPO_ROOT="${REPO_ROOT:-/tmp/AI-PLAYBOOK}"
BRANCH=feature/qwen3.5-27b-integration
if [[ ! -d "$REPO_ROOT/.git" ]]; then
  git clone --branch "$BRANCH" --single-branch https://github.com/henokmeron/AI-PLAYBOOK.md.git "$REPO_ROOT"
else
  git -C "$REPO_ROOT" fetch origin "$BRANCH" || true
  git -C "$REPO_ROOT" checkout "$BRANCH" || true
  git -C "$REPO_ROOT" reset --hard "origin/$BRANCH" || true
fi
# Overlay durable ops + critical tree files from this volume folder (source of recovery).
if [[ -d "$RELEASE_DIR/ops" ]]; then
  mkdir -p "$REPO_ROOT/ops"
  cp -a "$RELEASE_DIR/ops/." "$REPO_ROOT/ops/"
fi
if [[ -d "$RELEASE_DIR/tree" ]]; then
  cp -a "$RELEASE_DIR/tree/." "$REPO_ROOT/"
fi
if [[ -f "$REPO_ROOT/ops/_complete_bringup.py" ]]; then
  exec /usr/bin/python3 "$REPO_ROOT/ops/_complete_bringup.py"
fi
exec bash "$REPO_ROOT/ops/start-first-release.sh" --start
""",
        encoding="utf-8",
    )
    try:
        start.chmod(0o755)
    except OSError:
        # Global Volume FUSE often rejects chmod; bash START.sh still works.
        pass
    readme = RELEASE / "README.md"
    readme.write_text(
        """# AI Platform Release (Global Volume)

This directory is the durable entrypoint on `/workspace`. It is **not** a zipped
Python environment (FUSE cannot run those reliably).

## What lives where

| Asset | Location |
| --- | --- |
| This launcher | `/workspace/ai-platform-release/START.sh` |
| Ops scripts (volume copy) | `/workspace/ai-platform-release/ops/` |
| Critical source overlays | `/workspace/ai-platform-release/tree/` |
| Model weights | `/workspace/models/…` and Gemma path |
| Runtime archives | `/workspace/runtime-setup/` (`tar.zst` → extract to `/tmp`) |
| Managed docs | `/workspace/rag-managed-docs` |
| Git source | cloned to `/tmp/AI-PLAYBOOK` then overlaid |

## Start (after SSH into a Pod with the Global Volume attached)

```bash
bash /workspace/ai-platform-release/START.sh
```

Then tunnel the console:

```bash
ssh -N -L 18080:127.0.0.1:8080 -p <tcp-port> -i <key> root@<pod-ip>
```

Open `http://127.0.0.1:18080`

## Requirements

- NVIDIA driver **≥580** (CUDA 13-capable) for current vLLM wheels
- Global Volume mounted at `/workspace`
- Do not extract venvs onto `/workspace`; always `/tmp`
- Qwen serve uses `--max-num-seqs 256` (Mamba cache limit)
""",
        encoding="utf-8",
    )
    print(f"RELEASE_DIR={RELEASE}", flush=True)


def e2e(key: str) -> dict:
    headers = {"Authorization": f"Bearer {key}"}
    out: dict = {"chat": {}, "models": {}, "rag": {}}
    st, chat = http_json(
        "POST",
        "http://127.0.0.1:8010/v1/chat/completions",
        {
            "model": "qwen3.5-27b",
            "messages": [{"role": "user", "content": "Reply with exactly: PLATFORM_OK"}],
            "max_tokens": 32,
            "temperature": 0,
        },
        headers=headers,
    )
    content = (
        chat.get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    out["chat"] = {
        "status": st,
        "content": content,
        "selection": chat.get("platform_selection"),
        "pass": "PLATFORM_OK" in (content or ""),
    }
    st2, models = http_json(
        "GET", "http://127.0.0.1:8010/v1/platform/models", headers=headers
    )
    out["models"] = {
        "status": st2,
        "default_model_id": models.get("default_model_id"),
        "ids": [m.get("id") for m in (models.get("models") or [])],
        "pass": st2 == 200 and bool(models.get("models")),
    }
    # console status
    stc, console = http_json("GET", "http://127.0.0.1:8080/api/status")
    out["console"] = {"status": stc, "connection": console.get("connection")}
    # RAG upload/ask/delete
    import base64

    coll = "complete-release-check"
    doc = b"The platform release keyword is OCEAN-PINE-77 for verification only.\n"
    st_u, up = http_json(
        "POST",
        "http://127.0.0.1:8010/v1/rag/documents",
        {
            "collection": coll,
            "filename": "release-note.txt",
            "content_base64": base64.b64encode(doc).decode(),
            "overwrite": True,
        },
        headers=headers,
    )
    st_a, ask = http_json(
        "POST",
        "http://127.0.0.1:8010/v1/rag/ask",
        {
            "collection": coll,
            "question": "What is the platform release keyword?",
            "top_k": 4,
        },
        headers=headers,
    )
    answer = ask.get("answer") or ""
    # delete
    req = urllib.request.Request(
        f"http://127.0.0.1:8010/v1/rag/documents?collection={coll}&filename=release-note.txt",
        headers=headers,
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        del_status = resp.status
        del_body = json.loads(resp.read().decode())
    # follow-up should not reuse deleted evidence strongly
    st_f, follow = http_json(
        "POST",
        "http://127.0.0.1:8010/v1/rag/ask",
        {
            "collection": coll,
            "question": "What is the platform release keyword?",
            "top_k": 4,
            "history": [
                {"role": "user", "content": "What is the platform release keyword?"},
                {"role": "assistant", "content": answer},
            ],
        },
        headers=headers,
    )
    follow_ans = follow.get("answer") or ""
    out["rag"] = {
        "upload_status": st_u,
        "ask_status": st_a,
        "answer": answer[:300],
        "ask_pass": "OCEAN-PINE-77" in answer,
        "delete_status": del_status,
        "deleted": del_body.get("removed_from_index"),
        "follow_status": st_f,
        "follow_answer": follow_ans[:300],
        "follow_pass": st_f == 200
        and (
            follow.get("status") == "abstained"
            or "OCEAN-PINE-77" not in follow_ans
        ),
    }
    return out


def main() -> int:
    DIAG.mkdir(parents=True, exist_ok=True)
    if not MODEL.is_dir():
        raise SystemExit(f"missing model {MODEL}")
    ensure_repo()
    write_release_launcher()
    info = ensure_qwen_env()
    env = os.environ.copy()
    ld = build_ld_path()
    if ld:
        env["LD_LIBRARY_PATH"] = ld
        os.environ["LD_LIBRARY_PATH"] = ld
    env["PATH"] = f"{ENV / 'bin'}:{env.get('PATH', '')}"
    env["TMPDIR"] = "/tmp"
    env["VLLM_RPC_BASE_PATH"] = "/tmp"
    env["VLLM_DO_NOT_TRACK"] = "1"
    setup_rag_deps(env)
    start_qwen(env)
    key = ensure_key()
    start_gateway(key)
    start_console()
    results = {"env": info, "e2e": e2e(key)}
    (DIAG / "complete-e2e.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2)[:4000], flush=True)
    ok = (
        results["e2e"]["chat"].get("pass")
        and results["e2e"].get("models", {}).get("pass", True)
        and results["e2e"]["rag"].get("ask_pass")
        and results["e2e"]["rag"].get("follow_pass")
        and results["e2e"]["console"].get("connection") in {"ready", "degraded"}
    )
    print("COMPLETE_PASS" if ok else "COMPLETE_PARTIAL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
