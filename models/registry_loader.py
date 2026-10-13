"""Load and validate the platform model registry without exposing secrets."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised only when PyYAML missing
    raise RuntimeError(
        "PyYAML is required to load models/registry.yaml; install pyyaml in the "
        "target environment or vendor a minimal parser"
    ) from exc


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.yaml"


def registry_path_from_env() -> Path:
    override = os.environ.get("PLATFORM_MODEL_REGISTRY", "").strip()
    if override:
        return Path(override)
    return DEFAULT_REGISTRY_PATH


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or registry_path_from_env()
    if not target.is_file():
        raise FileNotFoundError(f"model registry not found: {target}")
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("model registry root must be a mapping")
    if not isinstance(data.get("candidates"), list) or not data["candidates"]:
        raise ValueError("model registry must declare a non-empty candidates list")
    for entry in data["candidates"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise ValueError("each candidate must have a non-empty string id")
    return data


def index_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in registry["candidates"]}


def get_model(registry: dict[str, Any], model_id: str) -> dict[str, Any]:
    models = index_by_id(registry)
    if model_id not in models:
        raise KeyError(f"unknown model id: {model_id}")
    return models[model_id]


def public_model_catalog(
    registry: dict[str, Any],
    *,
    runtime_health: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    """Browser/API-safe catalog: no filesystem paths, keys or host secrets."""
    production = registry.get("production")
    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    active = defaults.get("active_model_id") or production
    health = runtime_health or {}
    catalog: list[dict[str, Any]] = []
    for entry in registry["candidates"]:
        serving = entry.get("serving") if isinstance(entry.get("serving"), dict) else {}
        port = serving.get("listen_port")
        eligible = bool(entry.get("selection_eligible", True))
        loaded = health.get(entry["id"]) if entry["id"] in health else None
        catalog.append(
            {
                "id": entry["id"],
                "family": entry.get("family"),
                "status": entry.get("status"),
                "license": entry.get("license"),
                "modalities": entry.get("modalities") or [],
                "evaluation_status": entry.get("evaluation_status"),
                "selection_eligible": eligible,
                "is_production_default": entry["id"] == production,
                "is_active_default": entry["id"] == active,
                "listen_port": port,
                "runtime_loaded": loaded,
                "capabilities": entry.get("capabilities") or {},
                "task_routing": entry.get("task_routing") or {},
                "notes": entry.get("notes"),
            }
        )
    return catalog


def serving_listen_port(entry: dict[str, Any]) -> int | None:
    serving = entry.get("serving") if isinstance(entry.get("serving"), dict) else {}
    port = serving.get("listen_port")
    try:
        return int(port) if port is not None else None
    except (TypeError, ValueError):
        return None


def selection_decision(
    registry: dict[str, Any],
    requested: str | None,
    *,
    upstream_port: int | None,
) -> dict[str, Any]:
    """Deterministic selection metadata for logs/API (no prompts or secrets)."""
    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    silent = bool(defaults.get("silent_model_fallback", False))
    resolved = resolve_requested_model(registry, requested)
    models = index_by_id(registry)
    decision: dict[str, Any] = {
        "requested": requested,
        "resolved_id": resolved if resolved in models else None,
        "passthrough": resolved if resolved not in models else None,
        "reason": "default" if not requested else "explicit_request",
        "allowed": True,
        "error": None,
    }
    if decision["resolved_id"] is None and decision["passthrough"] is None:
        decision["allowed"] = False
        decision["error"] = "no_model_resolved"
        decision["reason"] = "unavailable"
        return decision
    if decision["resolved_id"] is not None:
        entry = models[decision["resolved_id"]]
        if entry.get("selection_eligible") is False:
            decision["allowed"] = False
            decision["error"] = "model_not_eligible"
            decision["reason"] = "not_eligible"
            return decision
        port = serving_listen_port(entry)
        decision["listen_port"] = port
        if upstream_port is not None and port is not None and port != upstream_port:
            if not silent:
                decision["allowed"] = False
                decision["error"] = (
                    f"model {decision['resolved_id']} requires runtime port {port}; "
                    f"this gateway upstream is on port {upstream_port}. "
                    "Stop/start the matching stack (ops/switch-gpu-model.sh) rather than "
                    "expecting a silent cross-runtime remap."
                )
                decision["reason"] = "runtime_mismatch"
                return decision
    return decision


def resolve_requested_model(
    registry: dict[str, Any],
    requested: str | None,
    *,
    allow_unlisted_passthrough: bool = True,
) -> str | None:
    """Resolve a client model field to a registry id or upstream passthrough string.

    Returns None when the caller should leave the upstream payload unchanged.
    """
    models = index_by_id(registry)
    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    default_id = defaults.get("active_model_id") or registry.get("production")
    if not requested or not str(requested).strip():
        return str(default_id) if isinstance(default_id, str) and default_id in models else None
    name = str(requested).strip()
    if name in models:
        return name
    # Allow OpenAI clients to pass the Hugging Face id or local path aliases.
    for entry in registry["candidates"]:
        aliases = {
            str(entry.get("huggingface_id") or ""),
            str(entry.get("runpod_path") or ""),
            str(entry.get("id") or ""),
        }
        if name in aliases:
            return entry["id"]
    if allow_unlisted_passthrough:
        return name
    raise KeyError(f"model not allowed by registry: {name}")


def upstream_model_token(registry: dict[str, Any], model_id: str) -> str:
    """Token to send to the currently configured OpenAI-compatible upstream."""
    entry = get_model(registry, model_id)
    path = entry.get("runpod_path")
    hf = entry.get("huggingface_id")
    if isinstance(path, str) and path.strip():
        return path.strip()
    if isinstance(hf, str) and hf.strip():
        return hf.strip()
    return model_id
