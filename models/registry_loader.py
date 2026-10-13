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


def public_model_catalog(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Browser/API-safe catalog: no filesystem paths, keys or host secrets."""
    production = registry.get("production")
    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    active = defaults.get("active_model_id") or production
    catalog: list[dict[str, Any]] = []
    for entry in registry["candidates"]:
        serving = entry.get("serving") if isinstance(entry.get("serving"), dict) else {}
        catalog.append(
            {
                "id": entry["id"],
                "family": entry.get("family"),
                "status": entry.get("status"),
                "license": entry.get("license"),
                "modalities": entry.get("modalities") or [],
                "evaluation_status": entry.get("evaluation_status"),
                "is_production_default": entry["id"] == production,
                "is_active_default": entry["id"] == active,
                "listen_port": serving.get("listen_port"),
                "capabilities": entry.get("capabilities") or {},
                "notes": entry.get("notes"),
            }
        )
    return catalog


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
