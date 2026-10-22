"""Decide a source-only fast-forward.

This does not start, stop, or signal Qwen, the gateway, or the console.
"""
from __future__ import annotations


class SourceUpdateRefusal(RuntimeError):
    """The checkout was left unchanged."""


def plan_fast_forward(*, clean: bool, is_ancestor: bool, same_commit: bool) -> str:
    if not clean:
        raise SourceUpdateRefusal("the checkout has tracked edits. Nothing was changed.")
    if same_commit:
        return "already-current"
    if not is_ancestor:
        raise SourceUpdateRefusal("the published branch is not a fast-forward. Nothing was changed.")
    return "fast-forward-source-only"
