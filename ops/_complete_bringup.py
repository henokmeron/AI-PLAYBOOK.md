#!/usr/bin/env python3
"""Full first-release bring-up on a driver-capable Pod (H100 / driver 580+)."""
from __future__ import annotations

import json
import os
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


def git(*args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args]


def ensure_repo() -> None:
    if not (REPO / ".git").is_dir():
        sh(["git", "clone", "--branch", BRANCH, "--single-branch", REMOTE, str(REPO)])
        return
    if REPO.stat().st_uid != os.getuid():
        sh(["chown", "-R", f"{os.getuid()}:{os.getgid()}", str(REPO)])
    sh(git("fetch", "origin", BRANCH))
    dirty = subprocess.run(
        git("status", "--porcelain", "--untracked-files=no"),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty:
        print(f"WARN: {REPO} has local tracked edits; not updating", flush=True)
        return
    sh(git("checkout", BRANCH))
    if subprocess.call(git("merge", "--ff-only", f"origin/{BRANCH}")) != 0:
        print(f"WARN: cannot fast-forward {REPO}; using current checkout", flush=True)


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
    """Install the canonical launcher (ops/release/START.sh); VERSION.txt is left alone."""
    sh(["bash", str(REPO / "ops" / "release" / "install-to-volume.sh")])


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
    sh(["bash", str(REPO / "ops" / "start-first-release.sh"), "--preflight"])
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
