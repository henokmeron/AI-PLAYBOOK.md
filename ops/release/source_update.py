"""Decide a source-only fast-forward.

This does not start, stop, or signal Qwen, the gateway, or the console.
"""
from __future__ import annotations


class SourceUpdateRefusal(RuntimeError):
    """The checkout was left unchanged."""


EXPECTED_ORIGIN = "https://github.com/henokmeron/AI-PLAYBOOK.md.git"


def plan_fast_forward(
    *,
    clean: bool,
    is_ancestor: bool,
    same_commit: bool,
    origin_url: str = EXPECTED_ORIGIN,
) -> str:
    if origin_url != EXPECTED_ORIGIN:
        raise SourceUpdateRefusal(
            "origin is not https://github.com/henokmeron/AI-PLAYBOOK.md.git. Nothing was changed."
        )
    if not clean:
        raise SourceUpdateRefusal("the checkout has tracked edits. Nothing was changed.")
    if same_commit:
        return "already-current"
    if not is_ancestor:
        raise SourceUpdateRefusal("the published branch is not a fast-forward. Nothing was changed.")
    return "fast-forward-source-only"


def acceptance(*, before: str, after: str, published: str) -> str:
    """A fast-forward is accepted only when HEAD is the published tip.

    This does not call a health URL and it does not reset the checkout.
    """
    if after != published:
        raise SourceUpdateRefusal(
            f"acceptance failed: HEAD {after} is not the published tip {published}. "
            f"A refused fast-forward leaves HEAD at {before}. Do not reset."
        )
    return f"acceptance: {before} -> {after}; health URLs were not called"
